"""Financial decisions: historical dividend evidence and comparison.

Compares retained Ghostfolio dividend history with the IBKR source groups for the DRY_RUN
diagnostic. Read-only: no HTTP, no writes, nothing here certifies identity from amounts.
Also holds finding classification, proposed matches, plain-text formatting and logging of the report.
"""

import logging
import os
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, DecimalException, localcontext
from typing import Any, cast
from zoneinfo import ZoneInfo

from ghostfolio_ibkr_sync.config import timezone_preview_reason
from ghostfolio_ibkr_sync.ibkr import (
    DIVIDEND_PAYMENT_KEYS,
    WITHHOLDING_CASH_TYPE,
    DividendGroup,
    _dividend_cash_sum,
    _dividend_decimal,
    dividend_input_compatible,
)
from ghostfolio_ibkr_sync.sync import (
    DIVIDEND_MATCH_DAYS,
    Positions,
    SymbolMapping,
    _dividend_date_matches,
    _dividend_day,
    _historical_currency,
    _historical_minor_unit,
    _proximity_amounts,
    dividend_structured_quantity,
    resolve_symbol,
)

log = logging.getLogger(__name__)

# One retained destination activity: {"activity", "active", "index", "exact_json", ...}
Evidence = dict[str, Any]
# One diagnostic finding as built here and classified by the legacy file
Finding = dict[str, Any]

def dividend_declared_rate(dividend: DividendGroup) -> Decimal | None:
    """Return the finite grossRate of the unique matched payment Re, or None.

    Retained only for a source group with exactly one net-positive action; other
    shapes carry no declared-rate evidence. Evidence only: cash stays authoritative.
    """
    actions = defaultdict(list)
    keys = DIVIDEND_PAYMENT_KEYS
    for row in dividend.get("payments", []):
        actions[tuple(row.get(field, "") for field in keys)].append(row)
    positive = [key for key, rows in actions.items() if (_dividend_cash_sum(rows) or 0) > 0]
    if len(positive) != 1:
        return None
    key = positive[0]
    reversals = [row for row in dividend.get("accruals", [])
                 if all(not row.get(field) or row[field] == value for field, value in zip(keys, key, strict=True))
                 and row.get("code") == "Re"
                 and _dividend_day(row.get("payDate")) == dividend["date"]
                 and dividend["date"] in (_dividend_day(row.get("date")), _dividend_day(row.get("reportDate")))]
    if len(reversals) != 1:
        return None
    rate = _dividend_decimal(reversals[0].get("grossRate"))
    return rate if rate is not None and rate > 0 else None



def classify_dividend_deltas(currency: str, quantity_deltas: Sequence[Decimal],
                             gross_deltas: Sequence[Decimal], fee_deltas: Sequence[Decimal]) -> str:
    """Classify destination-minus-source deltas (major units) of one comparison.

    Returns "none", "noise", "minimal", "other" or "quantity", strongest first:
    any quantity delta is "quantity" (never noise); a gross/fee delta of half a
    minor unit or more other than exactly one minor unit is "other"; exactly one
    minor unit is "minimal"; below half a minor unit is "noise".
    """
    if any(quantity_deltas):
        return "quantity"
    unit = cast(Decimal, _historical_minor_unit(currency))
    classes = set()
    for delta in list(gross_deltas) + list(fee_deltas):
        size = abs(delta)
        if not size:
            continue
        classes.add("noise" if size < unit / 2 else "minimal" if size == unit else "other")
    for name in ("other", "minimal", "noise"):
        if name in classes:
            return name
    return "none"



def _historical_destination_currency(evidence: Evidence) -> tuple[Any, str]:
    """Observed destination currency value and where it was read from."""
    row = evidence["activity"]
    profile = row["assetProfile"] if "assetProfile" in row else row.get("SymbolProfile", {})
    currency = row.get("currency")
    provenance = "activity"
    if "currency" in row and currency is None:
        currency = profile.get("currency")
        provenance = "assetProfile" if "assetProfile" in row else "SymbolProfile"
    return currency, provenance


def _historical_currency_context(dividend: DividendGroup, candidates: Sequence[Evidence]) -> dict[str, Any]:
    """Observed source and destination currency values for a currency-blocked finding."""
    observed = [_historical_destination_currency(item) for item in candidates]
    return {"source": dividend.get("currency"),
            "destination": [currency for currency, _ in observed],
            "provenance": [provenance for _, provenance in observed]}


def _historical_currency_reason(dividend: DividendGroup, candidates: Sequence[Evidence]) -> str | None:
    """Return the precise currency problem, or None when all codes agree."""
    observed = [dividend.get("currency")]
    observed += [_historical_destination_currency(item)[0] for item in candidates]
    if any(not isinstance(currency, str) or not currency for currency in observed):
        return "missing currency"
    normalized: list[Any] = [_historical_currency(currency) for currency in observed]
    if any(currency is None for currency in normalized):
        return "unsupported currency"
    if len({currency[0] for currency in normalized}) != 1:
        return "conflicting currencies"
    return None


def _historical_values(evidence: Evidence) -> tuple[Any, str | None]:
    """Read quantity/gross/fee only from original JSON, with currency provenance."""
    currency, provenance = _historical_destination_currency(evidence)
    row = evidence["activity"]
    if not isinstance(currency, str) or not currency:
        return None, "missing currency"
    unit = _historical_currency(currency)
    if unit is None:
        return None, "unsupported currency"
    if not evidence["exact_json"]:
        return None, "original JSON numeric evidence unavailable"
    numbers = [row.get(field) for field in ("quantity", "unitPrice", "fee")]
    if any(not isinstance(value, Decimal) or not value.is_finite() for value in numbers):
        return None, "missing or invalid exact numeric evidence"
    quantity, price, fee = numbers
    if quantity <= 0 or price <= 0 or fee < 0:
        return None, "unsupported quantity, price or fee"
    with localcontext() as context:
        context.prec = max(28, sum(len(value.as_tuple().digits) for value in numbers) + 4)
        try:
            gross = quantity * price * unit[1]
            fee = fee * unit[1]
        except DecimalException:
            return None, "unsupported decimal range"
    return {"quantity": quantity, "gross": gross, "fee": fee, "currency": unit[0],
            "denomination": currency, "currency_provenance": provenance}, None


def _historical_representations(candidates: list[Evidence],
                                components: Mapping[tuple[str, ...], Any]) -> tuple[list[list[Evidence]], str | None]:
    """Partition only independently identified evidence, never by amount.

    Optional component/representation identities belong to retained diagnostic
    evidence, not the API activity or its comment. The reader does not invent
    these identities for ordinary historical rows.
    """
    if len(candidates) == 1 and "representation" not in candidates[0]:
        return [candidates], None
    partitions = defaultdict(list)
    for item in candidates:
        representation = item.get("representation")
        if not isinstance(representation, str) or not representation:
            return [], "component partition identity not proven"
        partitions[representation].append(item)
    complete = []
    for rows in partitions.values():
        identities = [row.get("component") for row in rows]
        if len(rows) == 1 and identities == [None]:
            complete.append(rows)
        elif (all(isinstance(key, tuple) and key in components for key in identities)
              and len(identities) == len(set(identities)) == len(components)):
            complete.append(rows)
        else:
            return [], "incomplete or conflicting component coverage"
    return complete, None


def _historical_identity_checks(item: Evidence, dividend: DividendGroup,
                                symbol: str | None) -> list[dict[str, Any]]:
    """Evaluate the six identity checks with expected/observed values.

    The source YYYYMMDD stays the IBKR business day; it is compared with the
    destination instant's calendar day in the local IANA TZ. An absent profile
    ISIN is unavailable evidence and does not block; a nonempty conflict fails.
    """
    row = item["activity"]
    profile = row["assetProfile"] if "assetProfile" in row else row.get("SymbolProfile", {})
    observed_date: dict[str, str | None] = {"utc": None, "local": None}
    tz_reason = timezone_preview_reason()
    try:
        instant = datetime.fromisoformat(row.get("date", "").replace("Z", "+00:00"))
        if instant.tzinfo is not None:
            observed_date["utc"] = instant.astimezone(UTC).date().isoformat()
            if tz_reason is None:
                observed_date["local"] = instant.astimezone(
                    ZoneInfo(os.environ.get("TZ", "").strip())).date().isoformat()
    except Exception:
        pass
    profile_isin = profile.get("isin")
    if not dividend["isin"] or not profile_isin:
        isin_status = "unavailable"
    else:
        isin_status = "pass" if profile_isin == dividend["isin"] else "fail"
    rows = [
        ("active", bool(item["active"]), True, item["active"]),
        ("id", bool(row.get("id")), "nonempty", row.get("id")),
        ("data_source", profile.get("dataSource") == "YAHOO", "YAHOO", profile.get("dataSource")),
        ("symbol", profile.get("symbol") == symbol, symbol, profile.get("symbol")),
        ("date", observed_date["local"] == dividend["date"], dividend["date"], observed_date),
    ]
    checks = [{"activity_id": row.get("id"), "check": name, "status": "pass" if ok else "fail",
               "expected": expected, "observed": observed} for name, ok, expected, observed in rows]
    if tz_reason is not None:
        # No local calendar can be computed: the date is unavailable evidence, not a mismatch
        checks[-1].update({"status": "unavailable", "reason": f"{tz_reason}; forced preview"})
    checks.append({"activity_id": row.get("id"), "check": "isin", "status": isin_status,
                   "expected": dividend["isin"] or None, "observed": profile_isin or None})
    return checks


def _historical_destination(item: Evidence, checks: Sequence[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Describe one destination activity for private reports: security, dates, values."""
    row = item["activity"]
    profile = row["assetProfile"] if "assetProfile" in row else row.get("SymbolProfile", {})
    dates: dict[str, str | None] = {"utc": None, "local": None}
    for check in checks or []:
        if check["check"] == "date" and check["activity_id"] == row.get("id"):
            dates = check["observed"]
    if dates["utc"] is None:
        try:
            instant = datetime.fromisoformat(row.get("date", "").replace("Z", "+00:00"))
            if instant.tzinfo is not None:
                local = None
                if timezone_preview_reason() is None:
                    local = instant.astimezone(ZoneInfo(os.environ.get("TZ", "").strip())).date().isoformat()
                dates = {"utc": instant.astimezone(UTC).date().isoformat(), "local": local}
        except (ValueError, TypeError, AttributeError):
            pass
    values, reason = _historical_values(item)
    return {"activity_id": row.get("id"), "symbol": profile.get("symbol"), "isin": profile.get("isin") or None,
            "utc_date": dates["utc"], "local_date": dates["local"],
            "values": values if values is not None else {"unavailable": reason}}


def _historical_source_values(dividend: DividendGroup) -> dict[str, Any]:
    """Source-only quantity/gross/fee, available whatever the identity checks say."""
    unit = _historical_currency(dividend.get("currency"))
    gross = _dividend_cash_sum(dividend["payments"])
    tax = _dividend_cash_sum([row for row in dividend.get("cash_rows", [])
                              if row.get("type") == WITHHOLDING_CASH_TYPE])
    if unit is None or gross is None or tax is None:
        return {}
    quantity = (dividend_structured_quantity(dividend, quiet=True)
                if dividend_input_compatible([dividend], quiet=True) else None)
    try:
        return {"source_quantity": quantity, "source_gross": gross * unit[1],
                "source_fee": max(Decimal(0), tax.copy_negate()) * unit[1], "source_currency": unit[0]}
    except DecimalException:
        return {}


def _historical_proximity(positions: Positions, account_id: str, evidence: Sequence[Evidence],
                          symbol: str | None, dividend: DividendGroup) -> dict[str, Any] | None:
    """Weak candidates that make the import path skip an absent group by proximity.

    Mirrors the import-time proximity check; never certifies identity.
    """
    if not symbol:
        return None
    source_day = datetime.strptime(dividend["date"], "%Y-%m-%d")
    matched = _dividend_date_matches(positions, {"accountId": account_id, "symbol": symbol,
                                                 "date": f"{dividend['date']}T00:00:00+00:00"})
    if not matched:
        return None
    candidates = []
    for item in evidence:
        row = item["activity"]
        profile = row["assetProfile"] if "assetProfile" in row else row.get("SymbolProfile", {})
        if not (item["active"] and profile.get("dataSource") == "YAHOO" and profile.get("symbol") == symbol
                and row.get("accountId") == account_id):
            continue
        if (row.get("comment") or "").startswith("dividend#"):
            continue  # connector rows are not in the proximity index
        try:
            near = abs((datetime.strptime((row.get("date") or "")[:10], "%Y-%m-%d") - source_day).days)
        except ValueError:
            continue
        if near <= DIVIDEND_MATCH_DAYS:
            candidates.append({**_historical_destination(item), "comment": row.get("comment") or None})
    source_text, candidate_text, _ = _proximity_amounts(dividend, matched)
    return {"matched_date": matched[0], "window_days": DIVIDEND_MATCH_DAYS, "candidates": candidates,
            "source_gross": source_text, "candidate_gross": candidate_text}


def historical_dividend_findings(dividends: Sequence[DividendGroup], account_id: str, mapping: SymbolMapping,
                                 positions: Positions, report_window: tuple[str, str] | None = None,
                                 existing_dividend_comments: Collection[tuple[str, str]] = ()) -> list[Finding]:
    """Compare retained history conservatively, independently of import selection.

    A canonical comment proves group identity only with matching security/date.
    It cannot partition several activities into ordinary/bonus or PIL components.
    Never use matching amounts to manufacture that missing component identity.
    existing_dividend_comments is the unmutated set import selection reads.
    """
    findings = []
    evidence = [item for item in positions.get("dividend_evidence", [])
                if item["activity"].get("accountId") == account_id
                and not (item["activity"].get("comment") or "").startswith("IBKR#v")]
    # Resolve all claims first. Neither input order nor repeated IDs may allow
    # one destination activity to certify several source groups.
    owners = defaultdict(set)
    groups = []
    for group_index, dividend in enumerate(dividends):
        if not dividend.get("payments"):
            continue
        reference = f"dividend#{dividend['isin'] or dividend['symbol']}#{dividend['date']}"
        symbol = resolve_symbol(dividend["isin"], dividend["symbol"], mapping)
        claim_comments = {reference}
        claim_comments.add(f"dividend#{dividend['symbol']}#{dividend['date']}")
        if symbol:
            claim_comments.add(f"dividend#{symbol}#{dividend['date']}")
        candidates = [item for item in evidence
                      if item["activity"].get("comment") in claim_comments]
        groups.append((dividend, reference, symbol, candidates))
        for item in candidates:
            owners[item["activity"].get("id")].add(group_index)
    claimed: set[int] = set()
    for dividend, reference, symbol, candidates in groups:
        finding = {"source": reference, "activity_ids": [item["activity"].get("id") for item in candidates],
                   "category": "uncertain", "reason": "destination identity not proven",
                   "security": {"symbol": symbol, "isin": dividend["isin"] or None},
                   "source_date": dividend["date"], **_historical_source_values(dividend)}
        findings.append(finding)
        if not candidates:
            finding["category"] = "absent"
            finding["reason"] = "no canonical destination identity; weak matches cannot certify absence"
            # Same predicate and order as import selection: comment first, then proximity.
            comments = {reference, f"dividend#{symbol}#{dividend['date']}",
                        f"dividend#{dividend['symbol']}#{dividend['date']}"}
            if any((account_id, comment) in existing_dividend_comments for comment in comments):
                finding["historical_comment"] = [
                    {**_historical_destination(item), "comment": item["activity"].get("comment"),
                     "active": item["active"]}
                    for item in evidence if item["activity"].get("comment") in comments]
                finding["reason"] += "; skipped by historical comment (non-certifying)"
                continue
            proximity = _historical_proximity(positions, account_id, evidence, symbol, dividend)
            if proximity:
                finding["proximity"] = proximity
                finding["reason"] += "; skipped by proximity (non-certifying)"
            continue
        claimed.update(item["index"] for item in candidates)
        checks = [check for item in candidates for check in _historical_identity_checks(item, dividend, symbol)]
        finding["identity_checks"] = checks
        finding["destination"] = [_historical_destination(item, checks) for item in candidates]
        if any(len(owners[item["activity"].get("id")]) != 1 for item in candidates):
            finding["reason"] = "contested destination ownership"
            continue
        if len({item["activity"].get("id") for item in candidates}) != len(candidates):
            finding["reason"] = "duplicate destination activity identity"
            continue
        valid = not any(check["status"] == "fail" for check in checks)
        if not valid:
            finding["reason"] = "inactive, unsupported or conflicting security/date identity"
            continue
        if not dividend_input_compatible([dividend], quiet=True):
            finding["reason"] = "incompatible source quantity schema"
            continue
        quantity = dividend_structured_quantity(dividend, quiet=True)
        if quantity is None:
            finding["reason"] = "missing or conflicting source quantity evidence"
            continue
        keys = DIVIDEND_PAYMENT_KEYS
        components = defaultdict(list)
        for row in dividend["payments"]:
            components[tuple(row.get(key, "") for key in keys)].append(row)
        representations, reason = _historical_representations(candidates, components)
        if reason:
            finding["reason"] = reason
            continue
        currency_reason = _historical_currency_reason(dividend, candidates)
        if currency_reason:
            finding["reason"] = currency_reason
            finding["currency_context"] = _historical_currency_context(dividend, candidates)
            continue
        decoded: dict[int, Any] = {}
        for item in candidates:
            values, reason = _historical_values(item)
            if reason:
                break
            decoded[item["index"]] = values
        if reason:
            finding["reason"] = reason
            if reason in ("missing currency", "unsupported currency"):
                finding["currency_context"] = _historical_currency_context(dividend, candidates)
            continue
        unit: Any = _historical_currency(dividend.get("currency"))
        gross = _dividend_cash_sum(dividend["payments"])
        tax_rows = [row for row in dividend.get("cash_rows", [])
                    if row.get("type") == WITHHOLDING_CASH_TYPE]
        tax = _dividend_cash_sum(tax_rows)
        if gross is None or tax is None or gross <= 0:
            finding["reason"] = "missing or invalid source money evidence"
            continue
        with localcontext() as context:
            numbers = [gross, tax, quantity] + [value[field] for value in decoded.values()
                                               for field in ("gross", "fee", "quantity")]
            context.prec = max(28, max(value.adjusted() for value in numbers)
                               - min(value.as_tuple().exponent for value in numbers) + 4)
            try:
                source_gross = gross * unit[1]
                source_fee = max(Decimal(0), tax.copy_negate()) * unit[1]
                signed_tax_total = tax * unit[1]
                comparisons: list[dict[str, Any]] = []
                for rows in representations:
                    values = [decoded[item["index"]] for item in rows]
                    differences: dict[str, Any] = {"quantity_deltas": [value["quantity"] - quantity for value in values],
                                   "gross_delta": sum(value["gross"] for value in values) - source_gross,
                                   "fee_delta": sum(value["fee"] for value in values) - source_fee}
                    component_deltas: list[dict[str, Any]] = []
                    for item, value in zip(rows, values, strict=True):
                        key = item.get("component")
                        if key is not None:
                            component_gross = cast(Decimal, _dividend_cash_sum(components[key])) * unit[1]
                            component_tax = cast(Decimal, _dividend_cash_sum([row for row in tax_rows
                                if tuple(row.get(field, "") for field in keys) == key]))
                            component_deltas.append({"component": key,
                                "gross_delta": value["gross"] - component_gross,
                                "fee_delta": value["fee"] - max(Decimal(0), -component_tax) * unit[1]})
                    coherent = (not any(differences["quantity_deltas"])
                                and not differences["gross_delta"] and not differences["fee_delta"]
                                and not any(delta["gross_delta"] or delta["fee_delta"]
                                            for delta in component_deltas))
                    comparisons.append({"activity_ids": [item["activity"].get("id") for item in rows],
                                        "kind": "single" if len(rows) == 1 and rows[0].get("component") is None else "components",
                                        "coherent": coherent, **differences,
                                        "delta_class": classify_dividend_deltas(
                                            unit[0], differences["quantity_deltas"],
                                            [differences["gross_delta"]]
                                            + [delta["gross_delta"] for delta in component_deltas],
                                            [differences["fee_delta"]]
                                            + [delta["fee_delta"] for delta in component_deltas]),
                                        "component_deltas": component_deltas,
                                        "values": values})
            except DecimalException:
                finding["reason"] = "unsupported decimal range"
                continue
        finding["representations"] = comparisons
        finding["signed_tax_rows"] = [dict(row) for row in tax_rows]
        finding["signed_tax_total"] = signed_tax_total
        if len(comparisons) == 1:
            finding.update({key: value for key, value in comparisons[0].items()
                            if key in ("gross_delta", "fee_delta", "quantity_deltas", "delta_class")})
            if len(comparisons[0]["values"]) == 1:
                finding.update(comparisons[0]["values"][0])
                finding["quantity_delta"] = comparisons[0]["quantity_deltas"][0]
        rate = dividend_declared_rate(dividend)
        if rate is not None:
            try:
                finding["declared_rate"] = rate * unit[1]
            except DecimalException:
                pass
        finding["source_quantity"] = quantity
        finding["source_gross"] = source_gross
        finding["source_fee"] = source_fee
        finding["category"] = ("probable_repetition" if len(comparisons) > 1 else
                               "coherent_" + comparisons[0]["kind"] if comparisons[0]["coherent"] else "differences")
        finding["reason"] = "exact identity-proven representation comparison"
    for item in evidence:
        if item["index"] not in claimed:
            row = item["activity"]
            category = "uncertain"
            reason = "destination outside proven source coverage"
            try:
                date = datetime.fromisoformat(row.get("date", "").replace("Z", "+00:00"))
                utc_day = (date.date().isoformat() if date.tzinfo is not None
                           and cast(timedelta, date.utcoffset()).total_seconds() == 0 else None)
            except (ValueError, TypeError, AttributeError):
                utc_day = None
            if utc_day and report_window and not report_window[0] <= utc_day <= report_window[1]:
                category = "outside_window"
                reason = "destination UTC date outside explicit report window; source evidence unavailable"
            elif not item["active"]:
                reason = "inactive destination outside proven source coverage"
            elif not utc_day:
                reason = "timezone or invalid destination date cannot prove source identity"
            elif not (row.get("comment") or "").startswith("dividend#"):
                reason = "legacy destination comment cannot prove source identity"
            findings.append({"source": None, "activity_ids": [item["activity"].get("id")],
                             "category": category, "reason": reason,
                             "destination": [_historical_destination(item)]})
    return findings


def historical_dividend_comparison(dividends: Sequence[DividendGroup], account_id: str, mapping: SymbolMapping,
                                   positions: Positions, report_window: tuple[str, str] | None = None,
                                   existing_dividend_comments: Collection[tuple[str, str]] = ()) -> list[Finding]:
    return classify_dividend_findings(historical_dividend_findings(
        dividends, account_id, mapping, positions, report_window, existing_dividend_comments))


def _readable_values(destination: Evidence) -> tuple[Any, Any, Any] | None:
    """Gross/fee/currency of one destination row, or None when unavailable."""
    values = destination["values"]
    if "unavailable" in values:
        return None
    return values["gross"], values["fee"], values["currency"]


def _readable_set(label: str, kind: str, reason: str | None = None,
                  related: Collection[Any] = ()) -> dict[str, Any]:
    return {"class": kind, "label": label, "reason": reason, "related": list(related)}


def _match_candidates(finding: Finding, twins: Sequence[Finding]) -> list[dict[str, Any]]:
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


def _match_is_strong(finding: Finding, candidate: dict[str, Any]) -> bool:
    """Strong: same security, local day, gross and fee (quantity is shown, never scored)."""
    values = _readable_values(candidate)
    return (values is not None and "source_gross" in finding
            and candidate["symbol"] == finding["security"]["symbol"]
            and candidate["local_date"] == finding["source_date"]
            and values == (finding["source_gross"], finding["source_fee"], finding["source_currency"]))


def _propose_match(finding: Finding, twins: Sequence[Finding]) -> dict[str, Any]:
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


def _declared_rate_rounding(finding: Finding) -> bool:
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


def classify_dividend_findings(findings: list[Finding]) -> list[Finding]:
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
                values: Any = _readable_values(row["destination"][0])
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


def _plain(value: Any) -> str:
    """Plain decimal text: no Decimal(...), no exponent."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format(Decimal(str(value)), "f")
    return "unavailable" if value is None or value == "" else str(value)


def _plain_signed(value: Any) -> str:
    text = _plain(value)
    return text if text.startswith("-") or text == "unavailable" else "+" + text


def _plain_money(value: Any, currency: str) -> str:
    """Quantize one displayed monetary value to its explicit currency unit."""
    unit = _historical_minor_unit(currency)
    if unit is None or value is None:
        return "unavailable"
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    with localcontext() as context:
        context.prec = max(28, len(number.as_tuple().digits) + abs(number.adjusted()) + 4)
        return format(number.quantize(unit, rounding=ROUND_HALF_UP), "f")


def _plain_signed_money(value: Any, currency: str) -> str:
    text = _plain_money(value, currency)
    return text if text.startswith("-") or text == "unavailable" else "+" + text


def _plain_values(values: Mapping[str, Any]) -> str:
    if "unavailable" in values:
        return f"values unavailable ({values['unavailable']})"
    currency = values["currency"]
    return (f"quantity {_plain(values['quantity'])}, gross {_plain_money(values['gross'], currency)} "
            f"{currency}, fee {_plain_money(values['fee'], currency)} {currency}")


def _plain_deltas(row: Mapping[str, Any], currency: str) -> str:
    quantities = ", ".join(_plain_signed(delta) for delta in row["quantity_deltas"])
    return (f"quantity {quantities}, gross {_plain_signed_money(row['gross_delta'], currency)} "
            f"{currency}, fee {_plain_signed_money(row['fee_delta'], currency)} {currency}")


READABLE_ACTIONS: dict[str, str] = {
    "quantity difference": "Compare the quantity in Ghostfolio with the IBKR statement; fix the activity by hand if IBKR is right.",
    "minimal difference, cause unknown": "Check whether IBKR revised the amount after the import; the gap is one minor unit.",
    "amount difference": "Compare the amounts with the IBKR statement; fix the activity by hand if IBKR is right.",
    "repeated representation": "Compare each representation with the IBKR statement; delete by hand only the ones confirmed as duplicates.",
    "probable duplicate": "Check whether this row repeats the IBKR dividend; delete it by hand if it does.",
    "possibly missing in Ghostfolio": "Check whether the dividend is missing in Ghostfolio; add it by hand if it is.",
    "uncertain": "Read the reason and compare both sides by hand.",
}


def _readable_action(readable: Mapping[str, Any]) -> str:
    if readable["class"] == "information":
        return "No action needed."
    if readable["class"] in ("coherent", "outside_window", "noise"):
        return "No action needed."
    return READABLE_ACTIONS.get(readable["label"], READABLE_ACTIONS["uncertain"])


MATCH_REASONS: dict[str, str] = {"strong": "same security, local day, gross and fee",
                 "weak": "candidate rows exist, none equal in gross and fee"}


def _match_action(match: Mapping[str, Any]) -> str:
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


def _format_match(finding: Finding) -> list[str]:
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


def _finding_action(finding: Finding) -> str:
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


def format_historical_dividend_finding(finding: Finding, account_id: str) -> str:
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


def _plain_counts(counts: Mapping[str, int]) -> str:
    """Deterministic name:count summary, or none when empty."""
    return ",".join(f"{name}:{count}" for name, count in sorted(counts.items())) or "none"


def log_historical_dividend_comparison(findings: Sequence[Finding], account_id: str) -> dict[str, int]:
    """Report private diagnostic evidence without changing outcomes or persistence.

    Information blocks come first, then the summary line, then each item to check.
    Coherent, outside-window and noise findings log at DEBUG only.
    """
    counts: defaultdict[str, int] = defaultdict(int)
    classes: defaultdict[str, int] = defaultdict(int)
    failed: defaultdict[str, int] = defaultdict(int)
    unavailable: defaultdict[str, int] = defaultdict(int)
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
