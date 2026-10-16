#!/usr/bin/env python3
"""Sync Interactive Brokers trades and dividends to a self-hosted Ghostfolio instance."""

import base64
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from math import ceil, isfinite

import requests

# Transitional until the image installs the package: the notification worker
# runs this file with -I, which leaves the script directory off sys.path.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)

from ghostfolio_ibkr_sync.config import (  # noqa: E402
    APPRISE_URLS_MAX,
    NOTIFY_PAYLOAD_MAX,
    dry_run_requested,
    load_config,
    load_notification_config,
    timezone_preview_reason,
)
from ghostfolio_ibkr_sync.diagnostics import (  # noqa: E402,F401
    _historical_currency_context,
    _historical_currency_reason,
    _historical_destination,
    _historical_destination_currency,
    _historical_identity_checks,
    _historical_proximity,
    _historical_representations,
    _historical_source_values,
    _historical_values,
    classify_dividend_deltas,
    dividend_declared_rate,
    historical_dividend_findings,
)
from ghostfolio_ibkr_sync.ghostfolio import (  # noqa: E402,F401
    GHOST_AUTH_TIMEOUT,
    GHOST_REDIRECT_ERROR,
    _existing_dividend_amounts,
    _HEADER_SAFE_TOKEN_RE,
    _UNRESOLVED_SYMBOL_RE,
    accepted_import_subset,
    activity_date_is_current,
    activity_is_active,
    ghost_exchange_access_token,
    ghost_find_account_id,
    ghost_get_accounts,
    ghost_get_existing_orders,
    ghost_headers,
    ghost_import_activities,
    ghost_response_is_redirect,
    ghost_update_cash_balance,
    mark_import_uncertain,
    parse_unresolved_symbol,
)
from ghostfolio_ibkr_sync.ibkr import (  # noqa: E402,F401
    DIVIDEND_ACCRUAL_REQUIRED,
    DIVIDEND_CASH_TYPES,
    DIVIDEND_FIELD_NAMES,
    DIVIDEND_PAYMENT_KEYS,
    FLEX_SUFFIX_PATTERN,
    IBKR_ALLOWED_STMT_PREFIXES,
    IBKR_MAX_XML_BYTES,
    IBKR_NETWORK_RETRY_DELAYS,
    IBKR_SEND_RETRY_CODES,
    IBKR_SEND_RETRY_DELAYS,
    IBKR_SEND_URL,
    IBKR_STMT_URL,
    SKIP_ASSET_CATEGORIES,
    WITHHOLDING_CASH_TYPE,
    _dividend_cash_sum,
    _dividend_decimal,
    _ibkr_get,
    _parse_float,
    _redact,
    dividend_field_prerequisites,
    dividend_input_compatible,
    fetch_flex_report,
    flex_provenance_failures,
    historical_dividend_report_window,
    log_lab_evidence,
    parse_base_currency,
    parse_cash_dividends,
    parse_cash_report,
    parse_ibkr_datetime,
    parse_trades,
)
from ghostfolio_ibkr_sync.sync import (  # noqa: E402,F401
    CURRENCY_MINOR_UNITS,
    DIVIDEND_MATCH_DAYS,
    MINOR_UNIT_MARKETS,
    _dividend_date_matches,
    _dividend_day,
    _historical_currency,
    _historical_minor_unit,
    _match_manual_entry,
    _proximity_amounts,
    _source_dividend_fee,
    convert_dividend_to_activity,
    convert_trade_to_activity,
    dividend_structured_quantity,
    filter_trades_by_holdings,
    load_mapping,
    log_dividend_proximity_skip,
    minor_unit_conversion,
    resolve_symbol,
)

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
# urllib3 logs full request lines (incl. the IBKR token query param) at DEBUG.
logging.getLogger("urllib3").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def legacy_token_expiry_days(config, now=None):
    """Read an unverified JWT expiry for reminders only, never authentication."""
    if config.get("ghost_access_token") is not None:
        return None
    raw_days = os.environ.get("GHOST_TOKEN_EXPIRY_WARNING_DAYS", "14").strip()
    if not re.fullmatch(r"[0-9]{1,3}", raw_days) or int(raw_days) > 365:
        log.warning("GHOST_TOKEN_EXPIRY_WARNING_DAYS is invalid; using 14 days")
        raw_days = "14"
    warning_days = int(raw_days)
    if warning_days == 0:
        return None
    try:
        token = config.get("ghost_token")
        if not isinstance(token, str) or len(token) > 16384:
            raise ValueError
        parts = token.split(".")
        if (len(parts) != 3 or not parts[0] or not parts[2]
                or not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", parts[1])):
            raise ValueError
        payload = json.loads(base64.b64decode(
            parts[1] + "=" * (-len(parts[1]) % 4), altchars=b"-_", validate=True))
        expiry = payload.get("exp") if isinstance(payload, dict) else None
        if type(expiry) not in (int, float) or not isfinite(expiry):
            raise ValueError
        seconds_left = expiry - (time.time() if now is None else now)
        if seconds_left > warning_days * 86400:
            return None
        return max(0, ceil(seconds_left / 86400))
    except (ValueError, OverflowError, RecursionError):
        log.debug("Legacy GHOST_TOKEN has no usable JWT expiry; reminder skipped")
        return None


def historical_dividend_comparison(dividends, account_id, mapping, positions, report_window=None,
                                   existing_dividend_comments=()):
    """Classified historical comparison; evidence collection lives in diagnostics (moves with 3.3)."""
    return classify_dividend_findings(historical_dividend_findings(
        dividends, account_id, mapping, positions, report_window, existing_dividend_comments))


def _readable_values(destination):
    """Gross/fee/currency of one destination row, or None when unavailable."""
    values = destination["values"]
    if "unavailable" in values:
        return None
    return values["gross"], values["fee"], values["currency"]


def _readable_set(label, kind, reason=None, related=()):
    return {"class": kind, "label": label, "reason": reason, "related": list(related)}


def _match_candidates(finding, twins):
    """Candidate Ghostfolio rows of one IBKR dividend, deduplicated by activity id.

    Sources, in order: compared rows, legacy-comment twins, historical-comment rows,
    proximity-window rows. Read-only: nothing here selects, repairs or writes.
    """
    rows = [(item, "compared", True) for item in finding.get("destination", [])]
    rows += [(twin["destination"][0], "twin", False) for twin in twins]
    for key, origin in (("historical_comment", "historical comment"), ("proximity", "proximity")):
        listed = finding.get(key)
        listed = listed["candidates"] if isinstance(listed, dict) else listed or []
        rows += [(item, origin, item.get("comment") == finding["source"]) for item in listed]
    # Only "fail" blocks; "unavailable" (legacy rows without ISIN) stays eligible.
    failed = {check["activity_id"] for check in finding.get("identity_checks", [])
              if check["status"] == "fail"}
    seen = set()
    candidates = []
    for item, origin, canonical in rows:
        if item["activity_id"] in seen:
            continue
        seen.add(item["activity_id"])
        candidates.append({"activity_id": item["activity_id"], "origin": origin, "canonical": canonical,
                           "identity_failed": item["activity_id"] in failed or item.get("active") is False,
                           "symbol": item["symbol"], "local_date": item["local_date"],
                           "utc_date": item["utc_date"], "values": item["values"]})
    return candidates


def _match_is_strong(finding, candidate):
    """Strong: same security, local day, gross and fee (quantity is shown, never scored)."""
    values = _readable_values(candidate)
    return (values is not None and "source_gross" in finding
            and candidate["symbol"] == finding["security"]["symbol"]
            and candidate["local_date"] == finding["source_date"]
            and values == (finding["source_gross"], finding["source_fee"], finding["source_currency"]))


def _propose_match(finding, twins):
    """Return the proposal for one IBKR dividend: strong, weak or "none".

    Strong: Keep goes to the equal row with a canonical comment, else the compared row,
    else the lowest activity id; other equal rows are Duplicate, unequal rows Differs.
    Weak (candidates exist, none strong: same security and local day, or inside the
    proximity window; a quantity or one-unit gap lands here): every row is Differs, no
    Keep, and the action asks for a manual comparison. None: no candidate at all.
    A row failing an identity check (inactive, or a "fail" check; "unavailable" does not
    count) is always Differs and never makes a proposal strong.
    """
    candidates = _match_candidates(finding, twins)
    if not candidates:
        return {"confidence": "none", "rows": [], "action_activity_id": None, "manual_comparison": False}
    strong = [row for row in candidates
              if not row["identity_failed"] and _match_is_strong(finding, row)]
    if not strong:
        for row in candidates:
            row["label"] = "Differs"
        return {"confidence": "weak", "rows": candidates,
                "action_activity_id": candidates[0]["activity_id"], "manual_comparison": True}
    keep = min(strong, key=lambda row: (not row["canonical"], row["origin"] != "compared",
                                        str(row["activity_id"])))
    for row in candidates:
        if row is keep:
            row["label"] = ("Keep" if row["values"]["quantity"] == finding["source_quantity"]
                            else "Keep, quantity differs")
        else:
            row["label"] = "Duplicate" if row in strong else "Differs"
    action = next((row for row in candidates if row["label"] == "Duplicate"),
                  next((row for row in candidates if row["label"] == "Differs"), None))
    return {"confidence": "strong", "rows": candidates,
            "action_activity_id": action["activity_id"] if action else None,
            "manual_comparison": False}


def _declared_rate_rounding(finding):
    """Complete proven pattern: one row, equal quantity and fee, destination gross equals
    quantity x declared rate, and the cash gross differs by exactly one minor unit."""
    rate = finding.get("declared_rate")
    representations = finding.get("representations", [])
    if rate is None or len(representations) != 1 or "gross" not in finding:
        return False
    row = representations[0]
    unit = _historical_minor_unit(finding["source_currency"])
    return (row["kind"] == "single" and not row["component_deltas"] and unit is not None
            and not any(row["quantity_deltas"]) and not row["fee_delta"]
            and abs(row["gross_delta"]) == unit
            and finding["gross"] == finding["source_quantity"] * rate)


def classify_dividend_findings(findings):
    """Attach finding["readable"] (class, label, reason, related ids) to every finding.

    Classes: coherent, outside_window, noise, information, to_check. Pair detection
    (probable duplicate, equal-total split, absent/outside-coverage pair) needs the
    whole list; it never changes a finding's category. Every finding that is not
    coherent, outside window, information or noise is "to_check" with its reason.
    """
    compared = [f for f in findings if f["source"] is not None and "representations" in f]
    twins = defaultdict(list)
    for finding in findings:
        if (finding["source"] is not None or finding["category"] != "uncertain"
                or finding["reason"] != "legacy destination comment cannot prove source identity"):
            continue
        row = finding["destination"][0]
        for group in compared:
            if row["symbol"] == group["security"]["symbol"] and row["local_date"] == group["source_date"]:
                twins[id(group)].append(finding)
                finding["readable"] = _readable_set(
                    "probable duplicate", "to_check",
                    "legacy-comment row with the same security and day as a compared dividend",
                    group["activity_ids"])
                break
    outside = {}
    for finding in findings:
        if (finding["source"] is None and finding["category"] == "uncertain"
                and "readable" not in finding):
            outside[finding["activity_ids"][0]] = finding
    for finding in findings:
        if "readable" in finding:
            continue
        category = finding["category"]
        if category in ("coherent_single", "coherent_components"):
            result = _readable_set("coherent", "coherent")
        elif category == "outside_window":
            result = _readable_set("outside window", "outside_window", finding["reason"])
        elif category == "differences" or category == "probable_repetition":
            delta = finding.get("delta_class")
            if category == "probable_repetition":
                result = _readable_set("repeated representation", "to_check", finding["reason"])
            elif delta == "noise":
                result = _readable_set("rounding noise", "noise")
            elif delta == "quantity":
                result = _readable_set("quantity difference", "to_check")
            elif delta == "minimal" and _declared_rate_rounding(finding):
                result = _readable_set("legacy declared-rate rounding", "information",
                                       "Legacy row uses the declared rate; IBKR paid a rounded cash amount.")
            elif delta == "minimal":
                result = _readable_set("minimal difference, cause unknown", "to_check")
            else:
                result = _readable_set("amount difference", "to_check")
        elif category == "absent":
            result = _readable_set("possibly missing in Ghostfolio", "to_check", finding["reason"])
            carriers = {item["activity_id"] for item in finding.get("historical_comment", [])}
            for activity_id in carriers:
                row = outside.get(activity_id)
                if row is None or "readable" in row or "source_gross" not in finding:
                    continue
                values = _readable_values(row["destination"][0])
                if (values is not None and row["destination"][0]["symbol"] == finding["security"]["symbol"]
                        and row["destination"][0]["local_date"] == finding["source_date"]
                        and values == (finding["source_gross"], finding["source_fee"],
                                       finding["source_currency"])):
                    reason = "skipped by historical comment; matching destination row outside proven coverage"
                    result = _readable_set("absent source paired with outside-coverage row",
                                           "information", reason, [activity_id])
                    row["readable"] = _readable_set("outside-coverage row paired with absent source",
                                                    "information", reason, [finding["source"]])
                    break
        elif category == "uncertain" and finding["source"] is not None:
            context = finding.get("currency_context")
            destination = finding.get("destination", [])
            values = [_readable_values(row) for row in destination]
            if context and finding["reason"] in (
                    "missing currency", "conflicting currencies", "unsupported currency"):
                kind = "information" if finding["reason"] == "unsupported currency" else "to_check"
                result = _readable_set(finding["reason"], kind, finding["reason"])
            elif (len(destination) > 1 and "source_gross" in finding and all(values)
                  and not any(check["status"] == "fail" for check in finding.get("identity_checks", []))
                  and finding["reason"] not in ("contested destination ownership",
                                                "duplicate destination activity identity")
                  and {v[2] for v in values} == {finding["source_currency"]}
                  and sum(v[0] for v in values) == finding["source_gross"]
                  and sum(v[1] for v in values) == finding["source_fee"]):
                result = _readable_set(f"total equal to IBKR, split over {len(destination)} rows",
                                       "information", finding["reason"])
            else:
                result = _readable_set("uncertain", "to_check", finding["reason"])
        else:
            result = _readable_set("uncertain", "to_check", finding["reason"])
        finding["readable"] = result
    for group in compared:
        if twins[id(group)]:
            group["readable"]["related"] = [tid for twin in twins[id(group)] for tid in twin["activity_ids"]]
    for finding in findings:
        if finding["source"] is not None:
            finding["match"] = _propose_match(finding, twins.get(id(finding), []))
            for twin in twins.get(id(finding), []):
                twin["match"] = finding["match"]
                twin["match_source"] = finding
    return findings


def _plain(value):
    """Plain decimal text: no Decimal(...), no exponent."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format(Decimal(str(value)), "f")
    return "unavailable" if value is None or value == "" else str(value)


def _plain_signed(value):
    text = _plain(value)
    return text if text.startswith("-") or text == "unavailable" else "+" + text


def _plain_money(value, currency):
    """Quantize one displayed monetary value to its explicit currency unit."""
    unit = _historical_minor_unit(currency)
    if unit is None or value is None:
        return "unavailable"
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    with localcontext() as context:
        context.prec = max(28, len(number.as_tuple().digits) + abs(number.adjusted()) + 4)
        return format(number.quantize(unit, rounding=ROUND_HALF_UP), "f")


def _plain_signed_money(value, currency):
    text = _plain_money(value, currency)
    return text if text.startswith("-") or text == "unavailable" else "+" + text


def _plain_values(values):
    if "unavailable" in values:
        return f"values unavailable ({values['unavailable']})"
    currency = values["currency"]
    return (f"quantity {_plain(values['quantity'])}, gross {_plain_money(values['gross'], currency)} "
            f"{currency}, fee {_plain_money(values['fee'], currency)} {currency}")


def _plain_deltas(row, currency):
    quantities = ", ".join(_plain_signed(delta) for delta in row["quantity_deltas"])
    return (f"quantity {quantities}, gross {_plain_signed_money(row['gross_delta'], currency)} "
            f"{currency}, fee {_plain_signed_money(row['fee_delta'], currency)} {currency}")


READABLE_ACTIONS = {
    "quantity difference": "Compare the quantity in Ghostfolio with the IBKR statement; fix the activity by hand if IBKR is right.",
    "minimal difference, cause unknown": "Check whether IBKR revised the amount after the import; the gap is one minor unit.",
    "amount difference": "Compare the amounts with the IBKR statement; fix the activity by hand if IBKR is right.",
    "repeated representation": "Compare each representation with the IBKR statement; delete by hand only the ones confirmed as duplicates.",
    "probable duplicate": "Check whether this row repeats the IBKR dividend; delete it by hand if it does.",
    "possibly missing in Ghostfolio": "Check whether the dividend is missing in Ghostfolio; add it by hand if it is.",
    "uncertain": "Read the reason and compare both sides by hand.",
}


def _readable_action(readable):
    if readable["class"] == "information":
        return "No action needed."
    if readable["class"] in ("coherent", "outside_window", "noise"):
        return "No action needed."
    return READABLE_ACTIONS.get(readable["label"], READABLE_ACTIONS["uncertain"])


MATCH_REASONS = {"strong": "same security, local day, gross and fee",
                 "weak": "candidate rows exist, none equal in gross and fee"}


def _match_action(match):
    """One action line naming the row to act on (wording follows READABLE_ACTIONS)."""
    if match["confidence"] == "weak":
        return (f"Compare activity {match['action_activity_id']} and the other rows with the IBKR "
                "statement by hand; no row is proposed to keep.")
    row = next((row for row in match["rows"] if row["activity_id"] == match["action_activity_id"]), None)
    if row is None:
        keep = next(row for row in match["rows"] if row["label"] in ("Keep", "Keep, quantity differs"))
        return f"No action needed: keep activity {keep['activity_id']}."
    if row["label"] == "Duplicate":
        return (f"Check whether activity {row['activity_id']} repeats the IBKR dividend; "
                "delete it by hand if it does.")
    return (f"Compare activity {row['activity_id']} with the IBKR statement; "
            "fix it by hand if IBKR is right.")


def _format_match(finding):
    """Lines of the Proposed match section, without the block's sole action line."""
    match = finding.get("match")
    if match is None:
        return []
    source = finding.get("match_source", finding)
    if match["confidence"] == "none":
        return ["  Proposed match: no confident match"]
    lines = [f"  Proposed match ({match['confidence']}: {MATCH_REASONS[match['confidence']]})"]
    if "source_gross" in source:
        currency = source["source_currency"]
        lines.append(f"    IBKR {_plain(source['source'])}: quantity {_plain(source['source_quantity'])}, "
                     f"gross {_plain_money(source['source_gross'], currency)} {currency}, "
                     f"fee {_plain_money(source['source_fee'], currency)} {currency}")
    else:
        lines.append(f"    IBKR {_plain(source['source'])}: values unavailable")
    for row in match["rows"]:
        lines.append(f"    {row['label']}: activity {_plain(row['activity_id'])} "
                     f"({_plain(row['symbol'])}), local day {_plain(row['local_date'])}, "
                     f"UTC date {_plain(row['utc_date'])}, "
                     + _plain_values(row["values"]))
    return lines


def _finding_action(finding):
    if finding["readable"]["label"] == "legacy declared-rate rounding":
        return "No action: IBKR rounding accepted."
    match = finding.get("match")
    # Twins share the proposal, but each block's action belongs to its compared row.
    destination = finding.get("destination", [])
    if destination:
        activity_id = _plain(destination[0]["activity_id"])
        if finding["readable"]["class"] != "to_check":
            return _readable_action(finding["readable"])
        if finding["readable"]["label"] == "quantity difference":
            return (f"Compare activity {activity_id} with the IBKR statement: compare the quantity "
                    "by hand; fix it by hand if IBKR is right.")
        if finding["readable"]["label"] == "probable duplicate":
            return (f"Check whether activity {activity_id} repeats the IBKR dividend; "
                    "delete it by hand if it does.")
        if match is not None and match["confidence"] == "weak":
            return (f"Compare activity {activity_id} and the other rows with the IBKR "
                    "statement by hand; no row is proposed to keep.")
        return (f"Compare activity {activity_id} with the IBKR statement; "
                "fix it by hand if IBKR is right.")
    if match is not None and match["confidence"] != "none":
        if match["action_activity_id"] is None and finding["readable"]["class"] == "to_check":
            keep = next(row for row in match["rows"] if row["label"] in ("Keep", "Keep, quantity differs"))
            return (f"Compare activity {keep['activity_id']} with the IBKR statement; "
                    "fix it by hand if IBKR is right.")
        return _match_action(match)
    return _readable_action(finding["readable"])


def format_historical_dividend_finding(finding, account_id):
    """Render one finding as plain English lines (no repair, no selection, nothing written)."""
    readable = finding["readable"]
    kind = {"to_check": "to check", "information": "information", "noise": "noise",
            "coherent": "coherent", "outside_window": "outside report window"}[readable["class"]]
    lines = [f"[DRY RUN] Dividend {kind}: {readable['label']} (account {account_id})"]
    if finding["source"] is not None:
        security = finding["security"]
        lines.append(f"  Security: {_plain(security['symbol'])} (ISIN {_plain(security['isin'])}), "
                     f"dividend date {_plain(finding['source_date'])}, reference {_plain(finding['source'])}")
        if "source_gross" in finding:
            currency = finding["source_currency"]
            lines.append(f"  IBKR: quantity {_plain(finding['source_quantity'])}, "
                         f"gross {_plain_money(finding['source_gross'], currency)} {currency}, "
                         f"fee {_plain_money(finding['source_fee'], currency)} {currency}")
        else:
            lines.append(f"  IBKR: {_plain(finding['source'])}")
    else:
        lines.append("  IBKR: no dividend of the report is tied to this Ghostfolio row")
    for item in finding.get("destination", []):
        lines.append(f"  Ghostfolio: activity {_plain(item['activity_id'])} "
                     f"({_plain(item['symbol'])}) on {_plain(item['utc_date'])}, "
                     + _plain_values(item["values"]))
    if "gross_delta" in finding:
        lines.append("  Difference (Ghostfolio minus IBKR): "
                     + _plain_deltas(finding, finding["source_currency"]))
    elif len(finding.get("representations", [])) > 1:
        for number, row in enumerate(finding["representations"], 1):
            lines.append(f"  Difference of representation {number} (Ghostfolio minus IBKR): "
                         + _plain_deltas(row, finding["source_currency"]))
    lines.append(f"  Reason: {readable['reason'] or readable['label']}")
    if readable["label"] == "probable duplicate":
        lines.append("  This row looks like a duplicate: legacy comment, same security and same day as the "
                     "IBKR dividend (activity "
                     + ", ".join(_plain(value) for value in readable["related"]) + ").")
    elif readable["related"] and readable["class"] == "to_check" and finding["source"] is not None:
        lines.append("  Probable duplicates: legacy-comment rows with the same security and day "
                     "(activity " + ", ".join(_plain(value) for value in readable["related"]) + ").")
    for check in finding.get("identity_checks", []):
        if check["status"] != "pass":
            observed = check["observed"]
            if isinstance(observed, dict):
                observed = (f"local date {_plain(observed.get('local'))} "
                            f"(UTC date {_plain(observed.get('utc'))})")
            lines.append(f"  Identity check {check['check']} {check['status']} for activity "
                         f"{_plain(check['activity_id'])}: expected {_plain(check['expected'])}, "
                         f"found {_plain(observed)}"
                         + (f" ({check['reason']})" if check.get("reason") else ""))
    context = finding.get("currency_context")
    if context:
        lines.append(f"  Currency: IBKR {_plain(context['source'])}, Ghostfolio "
                     f"{', '.join(_plain(value) for value in context['destination'])} "
                     f"(from {', '.join(_plain(value) for value in context['provenance'])})")
    for item in finding.get("historical_comment") or []:
        lines.append(f"  Skipped by historical comment: activity {_plain(item['activity_id'])} "
                     f"(comment {_plain(item['comment'])}, {_plain(item['utc_date'])}), "
                     + _plain_values(item["values"]))
    proximity = finding.get("proximity")
    if proximity:
        lines.append(f"  Skipped by proximity: same symbol within {_plain(proximity['window_days'])} "
                     f"days of {_plain(proximity['matched_date'])}; weak candidates do not certify identity")
        lines.append(f"    Gross: source {_plain(proximity['source_gross'])}, "
                     f"candidate {_plain(proximity['candidate_gross'])}")
        for item in proximity["candidates"]:
            lines.append(f"    Weak candidate: activity {_plain(item['activity_id'])} "
                         f"(comment {_plain(item['comment'])}, {_plain(item['utc_date'])}), "
                         + _plain_values(item["values"]))
    lines += _format_match(finding)
    lines.append(f"  Action: {_finding_action(finding)}")
    lines.append("  Nothing was written.")
    return "\n".join(lines)


def _plain_counts(counts):
    """Deterministic name:count summary, or none when empty."""
    return ",".join(f"{name}:{count}" for name, count in sorted(counts.items())) or "none"


def log_historical_dividend_comparison(findings, account_id):
    """Report private diagnostic evidence without changing outcomes or persistence.

    Information blocks come first, then the summary line, then each item to check.
    Coherent, outside-window and noise findings log at DEBUG only.
    """
    counts = defaultdict(int)
    classes = defaultdict(int)
    failed = defaultdict(int)
    unavailable = defaultdict(int)
    to_check = []
    for finding in findings:
        counts[finding["category"]] += 1
        classes[finding["readable"]["class"]] += 1
        for check in finding.get("identity_checks", []):
            if check["status"] == "fail":
                failed[check["check"]] += 1
            elif check["status"] == "unavailable":
                unavailable[check["check"]] += 1
        klass = finding["readable"]["class"]
        if klass == "to_check":
            to_check.append(finding)
        elif klass == "information":
            log.info("%s", format_historical_dividend_finding(finding, account_id))
        else:
            log.debug("%s", format_historical_dividend_finding(finding, account_id))
    log.info("[DRY RUN] Dividend report: %d to check, %d informational, %d noise",
             classes["to_check"], classes["information"], classes["noise"])
    for finding in to_check:
        log.info("%s", format_historical_dividend_finding(finding, account_id))
    log.info("[DRY RUN] Historical dividends account=%s coverage=%d source_groups=%d "
             "unmatched_destination=%d categories=%s failed_checks=%s unavailable_checks=%s",
             account_id, len(findings),
             sum(finding["source"] is not None for finding in findings),
             sum(finding["source"] is None for finding in findings), _plain_counts(counts),
             _plain_counts(failed), _plain_counts(unavailable))
    return {"to_check": classes["to_check"], "informational": classes["information"],
            "noise": classes["noise"]}


def process_account(config, ibkr_account_id, query_id, ghost_account_name, mapping,
                    existing_trade_ids, existing_dividend_comments, positions):
    """Process a single IBKR account: fetch, parse, and sync to Ghostfolio.

    The two existing_* sets are shared across accounts and updated in place with
    whatever this account imports, so a later account will not re-import them.

    Returns a tuple of (unmapped, ok) where ok is False if any step failed.
    """
    log.info("Processing IBKR account %s (Ghostfolio: %s)", ibkr_account_id, ghost_account_name)
    ok = True

    # Fetch the Flex Query report
    try:
        xml_text = fetch_flex_report(config["ibkr_token"], query_id)
    except Exception as exc:
        log.error("Failed to fetch Flex Query for account %s: %s", ibkr_account_id, exc)
        return {}, False

    # Find the Ghostfolio account
    try:
        ghost_account_id = ghost_find_account_id(config, ghost_account_name)
    except (requests.RequestException, RuntimeError) as exc:
        log.error("Failed to look up Ghostfolio account '%s': %s", ghost_account_name, exc)
        return {}, False
    if ghost_account_id is None:
        return {}, False

    if ghost_account_id in config.get("_uncertain_import_accounts", set()):
        log.error("Account %s has an uncertain earlier import outcome; refusing further writes", ghost_account_id)
        return {}, False

    # Flex provenance is a prerequisite: fail before any import, cash or platform write
    provenance = flex_provenance_failures(xml_text)
    if provenance:
        log.error("Flex Query %s: cash rows without a valid 'YYYYMMDD;HHmmss TimeZone' dateTime "
                  "(%s); account failed before any write. Add Date/Time with time zone to the "
                  "query, see README", query_id,
                  ", ".join(f"{kind}: {count}" for kind, count in sorted(provenance.items())))
        return {}, False

    # Required dividend fields are a prerequisite too, even with no new dividend
    gaps = dividend_field_prerequisites(xml_text)
    if gaps:
        log.error("Flex Query %s: required dividend fields missing from the report (%s); account "
                  "failed before any write. Tick these fields in the query, see README",
                  query_id, ", ".join(gaps))
        return {}, False

    # Parse trades and dividends
    trades = parse_trades(xml_text)
    dividends = parse_cash_dividends(xml_text)
    if dividends is None:
        log.error("Flex Query %s has no Cash Transactions section: dividends not synced. "
                  "Add Cash Transactions (Dividends, Payment In Lieu Of Dividends, "
                  "Withholding Tax) to the query, see README", query_id)
        ok = False
        dividends = []
    log.debug("Found %d trades and %d dividend payments in Flex Query report",
              len(trades), len(dividends))

    # CASH (FX conversions) and OPT are never imported; drop them before any gate
    trades = [t for t in trades if t.get("assetCategory", "") not in SKIP_ASSET_CATEGORIES]

    # Prepare actual import candidates before calculating their position impact.
    unmapped = {}
    prepared_trades = []
    skipped_dup = 0
    skipped_other = 0

    unique = {}
    conflicts = set()
    for index, trade in enumerate(trades):
        tid = trade.get("tradeID", "")
        if not tid:
            # Keep each unidentified row so rejection diagnostics remain complete.
            unique[("missing", index)] = trade
        elif tid in unique:
            skipped_dup += 1
            if trade != unique[tid]:
                conflicts.add(tid)
        else:
            unique[tid] = trade
    if conflicts:
        log.error("Conflicting repeated trade IDs excluded: %s", ", ".join(sorted(conflicts)))
        ok = False

    for trade in unique.values():
        trade_id = trade.get("tradeID", "")
        if not trade_id:
            log.warning("Skipping trade for %s (%s) — missing tradeID, cannot deduplicate safely",
                        trade.get("symbol") or trade.get("isin") or "unknown",
                        trade.get("dateTime", ""))
            skipped_other += 1
            ok = False
            continue
        if trade_id in conflicts:
            skipped_other += 1
            continue
        if trade_id in existing_trade_ids:
            skipped_dup += 1
            continue

        trade_unmapped = {}
        activity = convert_trade_to_activity(trade, ghost_account_id, mapping, trade_unmapped)
        if activity is None or not activity_date_is_current(activity) or not all(isfinite(activity[field]) for field in ("quantity", "unitPrice", "fee")):
            log.error("Trade %s cannot be converted safely; excluded before holdings checks", trade_id)
            skipped_other += 1
            ok = False
            continue
        # The gate must use the same signed quantity the converted BUY/SELL will
        # add to Ghostfolio, while retaining raw fields for manual-entry matching.
        prepared_trades.append({**trade,
                                "quantity": (-1 if activity["type"] == "SELL" else 1) * activity["quantity"],
                                "_activity": activity, "_unmapped": trade_unmapped})

    trades = filter_trades_by_holdings(prepared_trades, positions, ghost_account_id, mapping,
                                      existing_trade_ids)
    activities = []
    for trade in trades:
        activities.append(trade["_activity"])
        unmapped.update(trade["_unmapped"])

    log.info("New trade activities: %d, duplicates skipped: %d, other skipped: %d",
             len(activities), skipped_dup, skipped_other)

    # Establish identity and deduplicate before checking quantity or schema.
    report_counts = None
    if config.get("dry_run"):
        findings = historical_dividend_comparison(dividends, ghost_account_id, mapping, positions,
                                                 historical_dividend_report_window(xml_text),
                                                 existing_dividend_comments)
        report_counts = log_historical_dividend_comparison(findings, ghost_account_id)
    div_activities = []
    div_skipped_dup = 0
    candidates = []
    for div in dividends:
        if not div["payments"] or div["amount"] <= 0:
            # Preserve existing diagnostics for reversals and tax-only rows.
            convert_dividend_to_activity(div, ghost_account_id, mapping, unmapped)
            continue
        symbol = resolve_symbol(div["isin"], div["symbol"], mapping)
        identity = {
            "accountId": ghost_account_id, "symbol": symbol,
            "date": f"{div['date']}T00:00:00+00:00",
            "comment": f"dividend#{div['isin'] or div['symbol']}#{div['date']}",
        }
        old_comment = f"dividend#{symbol}#{div['date']}"
        if ((ghost_account_id, identity["comment"]) in existing_dividend_comments
                or (ghost_account_id, old_comment) in existing_dividend_comments):
            div_skipped_dup += 1
            continue
        matched = _dividend_date_matches(positions, identity) if symbol else None
        if matched:
            log_dividend_proximity_skip(symbol, div, matched)
            div_skipped_dup += 1
            continue
        candidates.append(div)

    # A schema mismatch blocks only account dividends, not trades or cash.
    if dividend_input_compatible(candidates):
        for div in candidates:
            activity = convert_dividend_to_activity(div, ghost_account_id, mapping, unmapped)
            if activity and not activity_date_is_current(activity):
                log.error("Future or invalid dividend date; deferred until a later run")
                ok = False
                continue
            if activity:
                div_activities.append(activity)

    if report_counts is None:
        log.info("New dividend activities: %d, duplicates skipped: %d",
                 len(div_activities), div_skipped_dup)
    else:
        log.info("New dividend activities: %d, duplicates skipped: %d; dividend report: "
                 "%d to check, %d informational, %d noise",
                 len(div_activities), div_skipped_dup, report_counts["to_check"],
                 report_counts["informational"], report_counts["noise"])

    activities.extend(div_activities)

    # Create buys/dividends first. A server-skipped BUY cannot back a later SELL,
    # even in this account's batch. Dry-run uses proposed buys for simulation.
    phases = [[a for a in activities if a["type"] != "SELL"],
              [a for a in activities if a["type"] == "SELL"]]
    for phase in phases:
        if not phase:
            continue
        if ghost_account_id in config.get("_uncertain_import_accounts", set()):
            ok = False
            break
        if phase[0]["type"] == "SELL":
            totals = defaultdict(float)
            for a in phase:
                totals[a["symbol"]] += a["quantity"]
            rejected = {symbol for symbol, qty in totals.items()
                        if positions["qty"].get((ghost_account_id, symbol), 0) - qty < -0.001}
            if rejected:
                log.warning("Sells excluded after accepted-buy check: %s", ", ".join(sorted(rejected)))
                phase = [a for a in phase if a["symbol"] not in rejected]
                ok = False
        if not phase:
            continue
        imported, import_ok = ghost_import_activities(config, phase)
        for activity in imported:
            comment = activity["comment"]
            if comment.startswith("IBKR#"):
                existing_trade_ids.add(comment.split("#", 1)[1])
                sign = -1.0 if activity["type"] == "SELL" else 1.0
                positions["qty"][(activity["accountId"], activity["symbol"])] += sign * activity["quantity"]
            elif comment.startswith("dividend#"):
                existing_dividend_comments.add((activity["accountId"], comment))
        if not import_ok:
            ok = False

    # Update cash balance (independent of import success)
    try:
        cash_balance = parse_cash_report(xml_text)
        if cash_balance is not None:
            if not ghost_update_cash_balance(config, ghost_account_id, cash_balance,
                                         parse_base_currency(xml_text)):
                ok = False
        else:
            log.warning("No BASE_SUMMARY cash balance found in report")
    except Exception as exc:
        log.error("Failed to update cash balance: %s", exc)
        ok = False

    return unmapped, ok


# ---------------------------------------------------------------------------
# Run outcome
# ---------------------------------------------------------------------------

# Allowed failure reasons per stage.  An outcome holds only these fixed codes,
# counts and 1-based account ordinals - never an error text, URL, identifier or
# amount - so it can be summarised outside the logs.
OUTCOME_REASONS = {
    "config": ("invalid_configuration",),
    "mapping": ("invalid_mapping",),
    "ghost_auth": ("login_failed",),
    "ghost_startup": ("activities_unavailable", "token_rejected"),
    "account": ("account_failed", "unexpected_error"),
    "unexpected": ("unhandled_error",),
}
MAX_OUTCOME_FAILURES = 20


def is_token_rejection(exc):
    """True when Ghostfolio answered 401/403, i.e. the bearer token is expired or invalid."""
    response = getattr(exc, "response", None)
    return (isinstance(exc, requests.HTTPError) and response is not None
            and response.status_code in (401, 403))


def new_run_outcome():
    """Return an empty run-local outcome."""
    return {"failures": [], "dropped": 0, "accounts_total": 0, "accounts_failed": 0}


def record_failure(outcome, stage, reason, ordinal=None):
    """Record one failure; unknown codes collapse to unexpected/unhandled_error."""
    if reason not in OUTCOME_REASONS.get(stage, ()):
        stage, reason = "unexpected", "unhandled_error"
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
        ordinal = None
    if len(outcome["failures"]) >= MAX_OUTCOME_FAILURES:
        outcome["dropped"] += 1
        return
    outcome["failures"].append({"stage": stage, "reason": reason, "ordinal": ordinal})


# ---------------------------------------------------------------------------
# Failure notifications (Apprise, isolated worker process)
# ---------------------------------------------------------------------------

NOTIFY_WORKER_FLAG = "--notify-worker"
# The worker inherits only what Apprise needs to reach a destination: never the
# IBKR or Ghostfolio credentials.
NOTIFY_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR",
                        "REQUESTS_CA_BUNDLE", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                        "http_proxy", "https_proxy", "no_proxy")
# Worker exit code -> delivery status reported by send_notification.  Kept clear
# of the interpreter's own codes (1 uncaught error, 2 cannot open the script).
NOTIFY_EXIT_STATUS = {0: "sent", 10: "invalid_payload", 11: "unavailable", 12: "failed",
                      13: "invalid_destination"}


def notify_worker():
    """Worker process entry: deliver one notification read from stdin.

    Never runs the sync.  Apprise is imported here only, so the sync never
    loads it.  Exit codes: see NOTIFY_EXIT_STATUS.
    """
    logging.disable(logging.CRITICAL)
    raw = sys.stdin.buffer.read(NOTIFY_PAYLOAD_MAX + 1)
    try:
        payload = json.loads(raw) if len(raw) <= NOTIFY_PAYLOAD_MAX else None
    except ValueError:
        payload = None
    if (not isinstance(payload, dict)
            or not isinstance(payload.get("urls"), list) or not payload["urls"]
            or not all(isinstance(u, str) for u in payload["urls"])
            or not isinstance(payload.get("title"), str)
            or not isinstance(payload.get("body"), str)):
        return 10
    try:
        import apprise
    except ImportError:
        return 11
    notifier = apprise.Apprise()
    # One entry may hold several space- or comma-separated URLs: bound the
    # destinations Apprise actually expanded, not the list entries
    if (not all(notifier.add(url) for url in payload["urls"])
            or len(notifier) > APPRISE_URLS_MAX):
        return 13
    try:
        sent = notifier.notify(title=payload["title"], body=payload["body"])
    except Exception:
        return 12
    return 0 if sent else 12


def _notify_worker_argv():
    # -I: ignore PYTHON* variables, user site-packages and the current directory
    return [sys.executable, "-I", os.path.abspath(__file__), NOTIFY_WORKER_FLAG]


def _stop_worker(proc):
    """Kill the worker (and anything it started) if still running, then reap it."""
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
    proc.wait()


def send_notification(settings, title, body):
    """Deliver one notification through an isolated Apprise worker.

    Apprise plugins can block past any library timeout and can print their
    destination URL.  So the URLs travel on stdin, the worker gets an
    allowlisted environment and no output channel, and one deadline covers its
    whole life (import, setup, send, exit); on expiry it is killed and reaped.
    No retry: a timed-out send may still have been delivered.  Returns a fixed
    status string; SystemExit/KeyboardInterrupt propagate after the kill.
    """
    payload = json.dumps({"urls": settings["urls"], "title": title, "body": body}).encode()
    if len(payload) > NOTIFY_PAYLOAD_MAX:
        return "payload_too_large"
    # The worker re-runs this file: impossible when the script came from stdin
    if not os.path.isfile(os.path.abspath(__file__)):
        return "spawn_failed"
    env = {k: os.environ[k] for k in NOTIFY_ENV_ALLOWLIST if k in os.environ}
    try:
        proc = subprocess.Popen(_notify_worker_argv(), stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env=env, close_fds=True, start_new_session=True)
    except (OSError, ValueError):
        return "spawn_failed"
    try:
        proc.communicate(payload, timeout=settings["timeout"])
    except subprocess.TimeoutExpired:
        return "timeout"
    except Exception:
        return "failed"
    finally:
        _stop_worker(proc)
    return NOTIFY_EXIT_STATUS.get(proc.returncode, "failed")


NOTIFY_TITLE = "ghostfolio-ibkr-sync: run failed"
TOKEN_EXPIRY_NOTIFY_TITLE = "ghostfolio-ibkr-sync: token expiring"
FORCED_PREVIEW_NOTIFY_TITLE = "ghostfolio-ibkr-sync: forced preview"


def build_forced_preview_summary(reason):
    """Fixed advisory line: the run wrote nothing because of the TZ prerequisite."""
    return f"- forced DRY_RUN: {reason}; no Ghostfolio writes. Set a valid IANA TZ."


def build_token_expiry_summary(days):
    """Fixed advisory code and remaining-day count; no JWT claims are disclosed."""
    return (f"- ghost_auth: token_expiring (days remaining: {days})\n"
            "Regenerate GHOST_TOKEN or switch to GHOST_ACCESS_TOKEN.")


def build_failure_summary(outcome, now=None):
    """Plain-text summary: fixed codes, UTC time, counts and account ordinals only."""
    now = now or datetime.now(timezone.utc)
    lines = [f"Run failed at {now.strftime('%Y-%m-%d %H:%M')} UTC.",
             f"Accounts failed: {int(outcome['accounts_failed'])} of {int(outcome['accounts_total'])}."]
    for failure in outcome["failures"]:
        stage, reason = failure["stage"], failure["reason"]
        if reason not in OUTCOME_REASONS.get(stage, ()):
            stage, reason = "unexpected", "unhandled_error"
        ordinal = failure["ordinal"]
        where = f" (account #{ordinal})" if type(ordinal) is int and ordinal > 0 else ""
        lines.append(f"- {stage}: {reason}{where}")
    if outcome["dropped"]:
        lines.append(f"- and {int(outcome['dropped'])} more")
    if outcome.get("token_expiry_days") is not None:
        lines.append(build_token_expiry_summary(outcome["token_expiry_days"]))
    if outcome.get("forced_preview"):
        lines.append(build_forced_preview_summary(outcome["forced_preview"]))
    lines.append("Details are in the container log.")
    return "\n".join(lines)


def finalize_run(outcome, code):
    """Send at most one notification for failures or a legacy-token reminder.

    Ordinary warnings and successful simulations remain silent. Failures
    notify in every mode, including invalid configuration. Delivery never changes
    the exit code. A reminder on a failed run joins its failure notification.
    """
    days = outcome.get("token_expiry_days")
    preview = outcome.get("forced_preview")
    if code == 0 and (dry_run_requested() or (days is None and not preview)):
        return
    label = "Failure" if code else ("Forced preview" if preview else "Token expiry")
    try:
        settings = load_notification_config()
        if settings is None:
            return
        if code:
            title, body = NOTIFY_TITLE, build_failure_summary(outcome)
        elif preview:
            title, body = FORCED_PREVIEW_NOTIFY_TITLE, build_forced_preview_summary(preview)
            if days is not None:
                body += "\n" + build_token_expiry_summary(days)
        else:
            title, body = TOKEN_EXPIRY_NOTIFY_TITLE, build_token_expiry_summary(days)
        status = send_notification(settings, title, body)
    except Exception:
        log.warning("%s notification could not be sent: internal error", label)
        return
    if status == "sent":
        log.info("%s notification sent", label)
    elif status == "timeout":
        log.warning("%s notification timed out (it may still arrive; not retried)", label)
    else:
        log.warning("%s notification not delivered: %s", label, status)


def run_sync(outcome):
    """Run one sync.  Returns the exit code; every exit 1 is recorded in outcome."""
    try:
        config = load_config()
    except RuntimeError as exc:
        log.error("Configuration error: %s", exc)
        record_failure(outcome, "config", "invalid_configuration")
        return 1
    reason = timezone_preview_reason()
    if reason:
        config["dry_run"] = True
        outcome["forced_preview"] = reason
        log.warning("%s: whole run forced to DRY_RUN, no Ghostfolio writes", reason)
    if config["dry_run"]:
        log.info("DRY RUN enabled (DRY_RUN) — no writes will be sent to Ghostfolio")
    try:
        mapping = load_mapping(config["mapping_file"])
    except RuntimeError as exc:
        log.error("%s", exc)
        record_failure(outcome, "mapping", "invalid_mapping")
        return 1
    log.info("Loaded %d symbol mappings", len(mapping))

    days = legacy_token_expiry_days(config)
    if days is not None:
        outcome["token_expiry_days"] = days
        if days:
            log.warning("Legacy GHOST_TOKEN expires in %d day(s); regenerate it or "
                        "switch to GHOST_ACCESS_TOKEN", days)
        else:
            log.warning("Legacy GHOST_TOKEN has expired; regenerate it or "
                        "switch to GHOST_ACCESS_TOKEN")

    # Access mode: one fresh bearer per run, after local validation and before
    # any Ghostfolio or IBKR call (dry-run included: a login writes nothing).
    # Never re-authenticated mid-run.
    if config.get("ghost_access_token") is not None:
        try:
            config["ghost_token"] = ghost_exchange_access_token(
                config["ghost_host"], config.pop("ghost_access_token"))
        except RuntimeError as exc:
            log.error("%s", exc)
            record_failure(outcome, "ghost_auth", "login_failed")
            return 1
        log.info("Authenticated to Ghostfolio with GHOST_ACCESS_TOKEN")

    account_ids = config["account_ids"]
    query_ids = config["query_ids"]
    account_names = config["account_names"]

    # If no account names provided, use account IDs as names
    if not account_names:
        account_names = account_ids
        log.warning("No GHOST_ACCOUNT_NAMES provided, using IBKR account IDs as Ghostfolio account names")

    # Fetch existing activities once for the whole run; process_account keeps the
    # sets current as it imports
    try:
        existing_trade_ids, existing_dividend_comments, positions = ghost_get_existing_orders(config)
    except (requests.RequestException, RuntimeError) as exc:
        log.error("Failed to fetch existing Ghostfolio activities: %s", exc)
        if is_token_rejection(exc):
            log.error("Ghostfolio rejected the token: an expired GHOST_TOKEN must be "
                      "regenerated, or switch to GHOST_ACCESS_TOKEN")
            record_failure(outcome, "ghost_startup", "token_rejected")
        else:
            record_failure(outcome, "ghost_startup", "activities_unavailable")
        return 1
    log.info("Found %d existing trade activities and %d existing dividend activities in Ghostfolio",
             len(existing_trade_ids), len(existing_dividend_comments))

    all_unmapped = {}
    failed_accounts = []
    outcome["accounts_total"] = len(account_ids)

    for ordinal, (ibkr_id, qid, gf_name) in enumerate(zip(account_ids, query_ids, account_names), 1):
        # process_account handles the failures it expects; an unforeseen error in one
        # account must cost that account, not the accounts still to be processed
        reason = "account_failed"
        try:
            unmapped, ok = process_account(config, ibkr_id, qid, gf_name, mapping,
                                           existing_trade_ids, existing_dividend_comments, positions)
        except Exception:
            log.exception("Unexpected error while processing IBKR account %s", ibkr_id)
            unmapped, ok, reason = {}, False, "unexpected_error"
        all_unmapped.update(unmapped)
        if not ok:
            failed_accounts.append(ibkr_id)
            outcome["accounts_failed"] += 1
            record_failure(outcome, "account", reason, ordinal)

    # Log unmapped ISINs: one self-contained line per ISIN so each survives line-based log viewers.
    # Trades are reported only on their import run (deduped before conversion);
    # dividends are converted before dedup, so they repeat on every run.
    for isin, info in sorted(all_unmapped.items()):
        symbol = info.get("symbol") or ""
        desc = info.get("description") or ""
        log.warning("Unmapped ISIN %s (%s) uses IBKR symbol %r as ticker (fallback) — "
                    "verify in Ghostfolio or add to mapping symbol_mapping: '%s: <yahoo ticker>'",
                    isin, desc or "no description", symbol, isin)
    if not all_unmapped:
        log.info("No unmapped ISINs in this run")

    if failed_accounts:
        log.error("Sync completed with errors for %d of %d account(s): %s",
                  len(failed_accounts), len(account_ids), ", ".join(failed_accounts))
        return 1

    log.info("Sync complete")
    return 0


def main():
    """Main entry point.  Returns a process exit code (0 = clean, 1 = failure).

    SystemExit and KeyboardInterrupt propagate untouched: an interrupted run is
    not a completed run and sends no notification.
    """
    log.info("Starting IBKR to Ghostfolio sync (version %s)", os.environ.get("APP_VERSION", "dev"))
    if not os.environ.get("DRY_RUN", "").strip():
        log.warning("DRY_RUN not set: simulation, nothing written")
    outcome = new_run_outcome()
    try:
        code = run_sync(outcome)
    except Exception:
        log.exception("Sync failed with an unhandled error")
        record_failure(outcome, "unexpected", "unhandled_error")
        code = 1
    finalize_run(outcome, code)
    return code


if __name__ == "__main__":
    if sys.argv[1:] == [NOTIFY_WORKER_FLAG]:
        sys.exit(notify_worker())
    sys.exit(main())
