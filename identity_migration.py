"""Offline exact identity migration preview, outside the runtime image.

This stage classifies exact eligibility. It cannot authorize conversion.
No runtime configuration, credential loader or network client is used.
"""

import argparse
import logging
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date
from decimal import Decimal
from fractions import Fraction
from math import isfinite
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from ghostfolio_ibkr_sync.app import (
    record_accepted_activities,
    select_account_activities,
)
from ghostfolio_ibkr_sync.ghostfolio import (
    activity_is_active,
    format_versioned_activity_identity,
    index_existing_activities,
    parse_versioned_activity_identity,
)
from ghostfolio_ibkr_sync.ibkr import (
    DIVIDEND_CASH_TYPES,
    WITHHOLDING_CASH_TYPE,
    _dividend_cash_sum,
    dividend_field_prerequisites,
    flex_provenance_failures,
    historical_dividend_report_window,
    parse_cash_dividends,
    parse_ibkr_datetime,
    parse_source_account_ids,
    parse_trades,
)
from ghostfolio_ibkr_sync.sync import (
    _historical_currency,
    convert_dividend_actions,
    convert_trade_to_activity,
    dividend_action_quantities,
    dividend_positive_actions,
    minor_unit_conversion,
    partition_dividend_actions,
    rejected_sell_symbols,
    resolve_symbol,
    split_import_phases,
)
from identity_maintenance import (
    canonical_json,
    digest,
    exact_json,
    instant,
    publish_private,
    require,
    safe_path,
)


def keyed_yaml(data: bytes) -> dict[str, Any]:
    """Accept JSON-compatible keyed YAML without duplicate keys or aliases."""
    root = yaml.compose(data, Loader=yaml.SafeLoader)
    seen: set[int] = set()

    def check(node: Any) -> None:
        require(id(node) not in seen, "YAML aliases are not allowed")
        seen.add(id(node))
        if isinstance(node, yaml.MappingNode):
            keys: set[str] = set()
            for key, value in node.value:
                require(isinstance(key, yaml.ScalarNode) and key.tag == 'tag:yaml.org,2002:str'
                        and key.value and key.value not in keys, "Invalid or duplicate YAML key")
                keys.add(key.value)
                check(value)
        elif isinstance(node, yaml.SequenceNode):
            for child in node.value:
                check(child)
        else:
            require(isinstance(node, yaml.ScalarNode) and node.tag in {
                'tag:yaml.org,2002:str', 'tag:yaml.org,2002:int',
                'tag:yaml.org,2002:bool', 'tag:yaml.org,2002:null'}, "Unsupported YAML value")

    check(root)
    result = yaml.safe_load(data)
    require(isinstance(result, dict), "Inputs must be keyed YAML")
    return result


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_snapshot(snapshot: Any, metadata: Any) -> None:
    require(isinstance(metadata, dict), "Missing snapshot metadata")
    require(metadata.get("complete") is True and metadata.get("unredacted") is True,
            "Incomplete or redacted snapshot")
    for key in ("capture_ref", "destination_version", "destination_image"):
        require(text(metadata.get(key)), "Missing snapshot provenance")
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", metadata["destination_image"]),
            "Invalid destination image digest")
    instant(metadata.get("captured_at"))
    require(isinstance(snapshot, dict) and isinstance(snapshot.get("activities"), list),
            "Invalid snapshot")
    rows = snapshot["activities"]
    require(type(metadata.get("count")) is int and metadata["count"] == len(rows)
            and isinstance(snapshot.get("count"), Decimal) and snapshot["count"] == len(rows),
            "Incomplete snapshot count")
    ids: set[str] = set()
    for row in rows:
        require(isinstance(row, dict) and text(row.get("id")) and row["id"] not in ids,
                "Missing or duplicate activity ID")
        ids.add(row["id"])
        require("comment" in row and (row["comment"] is None or isinstance(row["comment"], str)),
                "Missing or redacted comment")
        for key in ("quantity", "unitPrice", "fee"):
            require(isinstance(row.get(key), Decimal) and row[key].is_finite(),
                    "Missing or redacted financial number")
        require(text(row.get("type")) and type(row.get("isDraft")) is bool
                and isinstance(row.get("tags"), list), "Incomplete activity context")
        # Null assignment/currency can be legitimate. Preserve it for exclusion
        # by the exact eligibility stage; never invent account or asset evidence.
        for key in ("accountId", "currency"):
            require(key in row and (row[key] is None or text(row[key])), "Missing activity context")
        instant(row.get("date"))
        require(any(key in row for key in ("assetProfile", "SymbolProfile")),
                "Missing security context")
        for key in ("assetProfile", "SymbolProfile"):
            if key in row:
                require(row[key] is None or isinstance(row[key], dict), "Invalid security context")


def source_events(reports: dict[str, tuple[str, str]], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Collapse repeated identical events, retaining every captured source reference.

    Conflicting repetitions remain one decision with all variants. No amount or
    proximity search establishes ownership. Runtime converters validate support;
    exact source decimals establish the financial comparison separately.
    """
    events: dict[str, dict[str, Any]] = {}
    mapping = config["symbol_mapping"]

    def add(account: str, kind: str, event_id: str, reference: str,
            evidence: Any, old: list[str], day: str | None, expected: dict[str, Any] | None,
            reason: str | None, group: str | None = None, coverage: list[str] | None = None) -> None:
        try:
            new = format_versioned_activity_identity(account, kind, event_id)
        except RuntimeError:
            new = None
            reason = "unsupported"
        key = new or f"invalid:{reference}"
        item = events.setdefault(key, {
            "event": key, "source_account": account, "kind": kind, "source_refs": [],
            "old_comments": sorted(set(old)), "new_comment": new, "day": day,
            "expected": expected, "reason": reason, "group": group,
            "coverage": coverage or [], "variants": [],
        })
        item["source_refs"].append(reference)
        item["old_comments"] = sorted(set(item["old_comments"]) | set(old))
        item["coverage"] = sorted(set(item["coverage"]) | set(coverage or []))
        if evidence not in item["variants"]:
            item["variants"].append(evidence)
        if len(item["variants"]) > 1 or item["expected"] != expected or item["reason"] != reason:
            item["reason"] = "conflicting"
        if kind == "TRADE" and sum(ref.rsplit(":", 2)[0] == reference.rsplit(":", 2)[0]
                                   for ref in item["source_refs"]) > 1:
            item["reason"] = "ambiguous"

    for name, (account, xml) in sorted(reports.items()):
        destination = config["accounts"][account]
        for index, trade in enumerate(parse_trades(xml)):
            reference = f"{name}:trade:{index}"
            expected = None
            reason = None
            day = (parse_ibkr_datetime(trade.get("dateTime")) or "")[:10] or None
            payload = convert_trade_to_activity(trade, destination, mapping, {})
            try:
                require(payload and trade.get("accountId") == account, "Unproven trade")
                require(all(isfinite(payload[field]) and (payload[field] >= 0 if field == "fee"
                                                         else payload[field] > 0)
                            for field in ("quantity", "unitPrice", "fee")), "Unsafe numeric projection")
                quantity, price, commission = [Decimal(trade[field]) for field in (
                    "quantity", "tradePrice", "ibCommission")]
                require(all(v.is_finite() for v in (quantity, price, commission)), "Invalid numbers")
                require(not commission or float(commission) != 0, "Commission underflow")
                quantity, price = quantity.copy_abs(), price.copy_abs()
                require(quantity > 0 and price > 0, "Nonpositive trade")
                currency, factor = minor_unit_conversion(payload["symbol"], trade["currency"])
                require(_historical_currency(currency), "Unsupported denomination")
                expected = {"accountId": destination, "symbol": payload["symbol"],
                            "isin": trade.get("isin"), "currency": currency, "type": trade["buySell"],
                            "quantity": quantity, "unitPrice": str(Fraction(price) * factor),
                            "gross": str(Fraction(quantity) * Fraction(price) * factor),
                            "fee": str(max(Fraction(0), -Fraction(commission)) * factor)}
            except (RuntimeError, KeyError, ValueError, ArithmeticError):
                reason = "unsupported"
            add(account, "TRADE", trade.get("tradeID", ""), reference, trade,
                [f"IBKR#{trade.get('tradeID', '')}"], day, expected, reason)

        groups = parse_cash_dividends(xml) or []
        # The runtime reader skips malformed cash dates/amounts. Migration must
        # keep that excluded evidence and must not certify the surviving subset.
        retained = Counter(canonical_json(row) for group in groups for row in group["cash_rows"])
        omitted = []
        for element in ET.fromstring(xml).iter("CashTransaction"):
            row = dict(element.attrib)
            if (row.get("type") not in (*DIVIDEND_CASH_TYPES, WITHHOLDING_CASH_TYPE)
                    or row.get("levelOfDetail", "DETAIL").upper() != "DETAIL"):
                continue
            signature = canonical_json(row)
            if retained[signature]:
                retained[signature] -= 1
            else:
                omitted.append(row)
        for index, row in enumerate(omitted):
            add(account, "DIVIDEND", row.get("actionID", ""), f"{name}:omitted-cash:{index}",
                {"omitted_cash": row}, [], None, None, "unsupported")
        for index, group in enumerate(groups):
            reference = f"{name}:dividend:{index}"
            symbol = resolve_symbol(group["isin"], group["symbol"], mapping)
            old = [f"dividend#{key}#{group['date']}"
                   for key in (symbol, group["symbol"], group["isin"]) if key]
            actions = dividend_positive_actions(group)
            parts = partition_dividend_actions(group, groups)
            quantities = dividend_action_quantities(group, quiet=True)
            try:
                proposed, ok = convert_dividend_actions(group, destination, mapping, {}, groups)
            except RuntimeError:
                proposed, ok = [], False
            try:
                coverage = sorted(format_versioned_activity_identity(a, "DIVIDEND", b)
                                  for a, b in actions or [])
            except RuntimeError:
                coverage = []
            group_key = f"{account}:{group['isin'] or group['symbol']}:{group['date']}"
            # Every cash action, including zero/negative or unproven actions, is visible.
            ids = sorted({row.get("actionID", "") for row in group["cash_rows"]}) or [""]
            relevant = [row for row in group["accruals"] if row.get("actionID", "") in ids]
            evidence = {"cash_rows": sorted(group["cash_rows"], key=canonical_json),
                        "accruals": sorted(relevant, key=canonical_json)}
            for action in ids:
                expected = None
                reason = None
                try:
                    require(parts is not None and quantities and ok and actions, "Invalid group")
                    require(all(row.get("accountId") == account for row in group["cash_rows"]),
                            "Unproven source ownership")
                    require(len(proposed) == len(actions), "Incomplete conversion")
                    part = next(p for p in parts if p["payments"][0].get("actionID") == action)
                    quantity = quantities[(account, action)]
                    currency, factor = minor_unit_conversion(symbol, group["currency"])
                    require(_historical_currency(currency), "Unsupported denomination")
                    gross = _dividend_cash_sum(part["payments"])
                    tax = _dividend_cash_sum([r for r in part["cash_rows"]
                                              if r.get("type") == WITHHOLDING_CASH_TYPE])
                    group_tax = _dividend_cash_sum([r for r in group["cash_rows"]
                                                    if r.get("type") == WITHHOLDING_CASH_TYPE])
                    require(gross is not None and tax is not None and group_tax is not None,
                            "Missing exact cash")
                    expected = {"accountId": destination, "symbol": symbol, "isin": group["isin"],
                                "currency": currency, "type": "DIVIDEND", "quantity": quantity,
                                "unitPrice": str(Fraction(gross) * factor / Fraction(quantity)),
                                "gross": str(Fraction(gross) * factor),
                                "signed_tax": str(Fraction(tax) * factor),
                                "group_signed_tax": str(Fraction(group_tax) * factor),
                                "fee": str(max(Fraction(0), -Fraction(tax)) * factor),
                                "historical_fee": str(max(Fraction(0), -Fraction(group_tax)) * factor)}
                    if len(actions) != 1:
                        reason = "aggregate"
                except (RuntimeError, KeyError, StopIteration, ValueError, ArithmeticError):
                    reason = "unsupported"
                if any(row.get("actionID") == action or not (row.get("isin") or row.get("symbol"))
                       or (row.get("isin") or row.get("symbol")) == (group["isin"] or group["symbol"])
                       for row in omitted):
                    reason = "conflicting"
                    evidence = {**evidence, "omitted_cash": omitted}
                # A proven zero-net action contributes tax to the historical
                # clamp, but claims no historical payment row of its own.
                aliases = [] if actions and (account, action) not in actions else old
                add(account, "DIVIDEND", action, reference, evidence, aliases, group["date"],
                    expected, reason, group_key, coverage)
    for event in events.values():
        event["source_refs"].sort()
        event["variants"].sort(key=canonical_json)
    return sorted(events.values(), key=lambda event: event["event"])


def exact_differences(row: dict[str, Any], event: dict[str, Any], timezone: str) -> list[dict[str, Any]]:
    """Compare original numbers by rational arithmetic, with no rounding tolerance."""
    expected = event["expected"]
    if any(not isfinite(float(row[field])) or (row[field] and float(row[field]) == 0)
           for field in ("quantity", "unitPrice", "fee")):
        return [{"field": "numeric_support", "expected": "finite representable numbers",
                 "observed": {field: row[field] for field in ("quantity", "unitPrice", "fee")}}]
    profile = row.get("assetProfile") if "assetProfile" in row else row.get("SymbolProfile")
    profile = profile or {}
    observed = {"accountId": row.get("accountId"), "symbol": profile.get("symbol"),
                "currency": row.get("currency"), "type": row.get("type"),
                "quantity": row["quantity"], "unitPrice": str(Fraction(row["unitPrice"])),
                "gross": str(Fraction(row["quantity"]) * Fraction(row["unitPrice"])),
                "fee": str(Fraction(row["fee"]))}
    comparisons = {key: (value, observed[key]) for key, value in expected.items() if key in observed}
    comparisons.update({"dataSource": ("YAHOO", profile.get("dataSource")),
                        "day": (event["day"], instant(row["date"]).astimezone(
                            ZoneInfo(timezone)).date().isoformat())})
    if expected.get("isin") and profile.get("isin"):
        comparisons["isin"] = expected["isin"], profile["isin"]
    if "historical_fee" in expected:
        comparisons["historical_fee"] = expected["historical_fee"], observed["fee"]
    if profile.get("currency"):
        comparisons["profile_currency"] = expected["currency"], profile["currency"]
    if row.get("dataSource") is not None:
        comparisons["row_dataSource"] = "YAHOO", row["dataSource"]
    if row.get("symbol") is not None:
        comparisons["row_symbol"] = expected["symbol"], row["symbol"]
    if row.get("account") is not None:
        account = row["account"]
        comparisons["account_context"] = expected["accountId"], (
            account.get("id") if isinstance(account, dict) else None)
    if row.get("assetProfile") is not None and row.get("SymbolProfile") is not None:
        comparisons["profile_context"] = row["assetProfile"], row["SymbolProfile"]
    return [{"field": key, "expected": want, "observed": got}
            for key, (want, got) in sorted(comparisons.items()) if want != got]


def classify_history(reports: dict[str, tuple[str, str]], rows: list[dict[str, Any]],
                     config: dict[str, Any]) -> dict[str, Any]:
    """One decision per source event and per saved row; never dispatch a request."""
    events = source_events(reports, config)
    by_comment: dict[str, list[dict[str, Any]]] = {}
    claims: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_comment.setdefault(row["comment"], []).append(row)
    for event in events:
        candidates = [row for comment in event["old_comments"] for row in by_comment.get(comment, [])
                      if event["kind"] == "TRADE" or row["accountId"] ==
                      config["accounts"][event["source_account"]]]
        event["activity_ids"] = sorted(row["id"] for row in candidates)
        for row in candidates:
            claims.setdefault(row["id"], []).append(event)
    replacements = []
    for event in events:
        ids = event["activity_ids"]
        occupied = by_comment.get(event["new_comment"], []) if event["new_comment"] else []
        covered = [comment for comment in event["coverage"] if comment in by_comment]
        reason = event["reason"]
        if event["day"] and not config["window"][0] <= event["day"] <= config["window"][1]:
            reason = "outside-window"
        elif covered and len(covered) < len(event["coverage"]):
            reason = "partial-coverage"
        elif occupied:
            reason = "conflicting" if ids else "already-v2"
        elif len(ids) > 1 or any(len(claims[row_id]) > 1 for row_id in ids):
            # Several actions of the same group mean aggregation, not duplicate ownership.
            linked = {other["event"]: other for row_id in ids for other in claims[row_id]}
            reason = ("aggregate" if reason != "conflicting" and len(ids) == 1 and event["group"] and
                      all(other["group"] == event["group"] for other in linked.values())
                      else "ambiguous")
        elif not ids and reason is None:
            reason = "absent-new-candidate"
        event["differences"] = []
        if ids and len(ids) == 1:
            row = next(row for row in rows if row["id"] == ids[0])
            try:
                active = activity_is_active(row)
                require(parse_versioned_activity_identity(row["comment"], row["type"]) is None,
                        "Historical row is not a legacy identity")
            except RuntimeError:
                active = False
            if event["expected"]:
                event["differences"] = exact_differences(row, event, config["timezone"])
            if reason is None:
                if not active:
                    reason = "unsupported"
                elif event["differences"]:
                    reason = "conflicting"
                else:
                    after = {**row, "comment": event["new_comment"]}
                    replacements.append({"id": row["id"], "old_comment": row["comment"],
                                         "new_comment": event["new_comment"], "event": event["event"],
                                         "before_fingerprint": digest(canonical_json(row)),
                                         "after_fingerprint": digest(canonical_json(after))})
        event["status"] = reason or "eligible-replacement"
        event["reason"] = reason
        event["evidence_status"] = "exact" if reason is None else "excluded"
        event["association_cardinality"] = {"historical_rows": len(ids),
            "source_events": max((len(claims[row_id]) for row_id in ids), default=1)}
        event["occupied_ids"] = sorted(row["id"] for row in occupied)
    decisions = []
    for row in sorted(rows, key=lambda row: row["id"]):
        linked = claims.get(row["id"], [])
        status = linked[0]["status"] if linked else "unsupported"
        reason = status
        if not linked:
            comment = row["comment"] or ""
            reason = "absent-source" if comment.startswith(("IBKR#", "dividend#")) else "manual"
            try:
                if parse_versioned_activity_identity(comment, row["type"]):
                    status = reason = "already-v2"
            except RuntimeError:
                reason = "invalid-identity"
        if not linked and not config["window"][0] <= instant(row["date"]).astimezone(
                ZoneInfo(config["timezone"])).date().isoformat() <= config["window"][1]:
            status = "outside-window"
        decisions.append({"id": row["id"], "fields": row, "status": status,
                          "reason": reason,
                          "evidence_status": "exact" if status == "eligible-replacement" else "excluded",
                          "association_cardinality": {"source_events": len(linked),
                                                      "historical_rows": 1},
                          "source_events": sorted(e["event"] for e in linked),
                          "fingerprint": digest(canonical_json(row))})
    return {"events": events, "rows": decisions,
            "counts": {"source_events": dict(sorted(Counter(e["status"] for e in events).items())),
                       "historical_rows": dict(sorted(Counter(r["status"] for r in decisions).items()))},
            "replacements": sorted(replacements, key=lambda r: r["id"])}


def coverage_gaps(reports: dict[str, tuple[str, str]], config: dict[str, Any]) -> list[str]:
    """Require continuous saved statement bounds for every declared account."""
    gaps = []
    start, end = [date.fromisoformat(day).toordinal() for day in config["window"]]
    for account in sorted(config["accounts"]):
        windows = [historical_dividend_report_window(xml) for source, xml in reports.values()
                   if source == account]
        require(all(bounds is not None for bounds in windows), "Missing statement bounds")
        covered_until = start - 1
        for low, high in sorted(bounds for bounds in windows if bounds is not None):
            first, last = date.fromisoformat(low).toordinal(), date.fromisoformat(high).toordinal()
            if first > covered_until + 1:
                break
            covered_until = max(covered_until, last)
        if covered_until < end:
            gaps.append(account)
    return gaps


def replay_selection(reports: dict[str, tuple[str, str]], rows: list[dict[str, Any]],
                     config: dict[str, Any]) -> dict[str, Any]:
    """Replay runtime selection and accepted-proposal holdings without I/O.

    Use the snapshot clock instead of wall time. The declared report order is
    the intended runtime query order. Each phase is fully accepted in isolated
    simulation state, as in the normal dry run.
    """
    trade_ids, dividends, positions = index_existing_activities({"count": len(rows), "activities": rows})
    captured = instant(config["snapshot"]["captured_at"])

    def current(activity: Any) -> bool:
        try:
            return instant(activity["date"]) <= captured
        except (RuntimeError, ValueError, KeyError, TypeError):
            return False

    def holdings() -> list[dict[str, Any]]:
        return [{"account": account, "symbol": symbol, "quantity": quantity}
                for (account, symbol), quantity in sorted(positions["qty"].items())]

    result: dict[str, Any] = {"initial_holdings": holdings(), "queries": []}
    for name in config["replay_order"]:
        account, xml = reports[name]
        destination = config["accounts"][account]
        trace: dict[str, Any] = {}
        item: dict[str, Any] = {"report": name, "source_account": account,
                                "destination_account": destination, "holdings_before": holdings()}
        prerequisites = dividend_field_prerequisites(xml)
        provenance = flex_provenance_failures(xml)
        if prerequisites or provenance:
            item.update({"prerequisite_failures": prerequisites, "provenance_failures": provenance,
                         "ok": False, "selected": [], "holdings": trace})
        else:
            activities, contexts, unmapped, ok = select_account_activities(
                xml, account, destination, config["symbol_mapping"], trade_ids, dividends,
                positions, date_is_current=current, holdings_trace=trace)
            phases = []
            for phase in split_import_phases(activities):
                rejected = rejected_sell_symbols(phase, positions, destination) if (
                    phase and phase[0]["type"] == "SELL") else set()
                accepted = [a for a in phase if a["symbol"] not in rejected]
                phases.append({"proposed": phase, "rejected_sell_symbols": sorted(rejected),
                               "selected": accepted})
                record_accepted_activities(accepted, positions, trade_ids, dividends, contexts)
            item.update({"ok": ok and not any(p["rejected_sell_symbols"] for p in phases),
                         "selected": [a for phase in phases for a in phase["selected"]],
                         "phases": phases, "holdings": trace, "unmapped": unmapped})
        item["holdings_after"] = holdings()
        result["queries"].append(item)
    result["final_holdings"] = holdings()
    return result


def prove_selection(reports: dict[str, tuple[str, str]], rows: list[dict[str, Any]],
                    config: dict[str, Any], replacements: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare complete payload and holdings decisions, never only counts."""
    gaps = coverage_gaps(reports, config)
    proof: dict[str, Any] = {"schema": "ibkr-selection-proof-v1", "equal": False,
                             "missing_windows": gaps, "replay_order": config["replay_order"],
                             "clock": config["snapshot"]["captured_at"]}
    if gaps:
        proof["reason"] = "incomplete-window"
        return proof
    changes = {replacement["id"]: replacement["new_comment"] for replacement in replacements}
    after = [{**row, "comment": changes.get(row["id"], row["comment"])} for row in rows]
    try:
        before_selection = replay_selection(reports, rows, config)
        after_selection = replay_selection(reports, after, config)
        proof.update({"before": before_selection, "after": after_selection,
                      "before_sha256": digest(canonical_json(before_selection)),
                      "after_sha256": digest(canonical_json(after_selection)),
                      "equal": canonical_json(before_selection) == canonical_json(after_selection)})
        proof["reason"] = None if proof["equal"] else "selection-changed"
    except (RuntimeError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        proof.update({"reason": "selection-unavailable", "error_type": type(error).__name__})
    return proof


def bind_selection(manifest: dict[str, Any], reports: dict[str, tuple[str, str]],
                   rows: list[dict[str, Any]], config: dict[str, Any]) -> None:
    planned = manifest["replacements"]
    proof = prove_selection(reports, rows, config, planned)
    proof["planned_replacements"] = planned
    manifest["selection_proof"] = proof
    if not proof["equal"]:
        blocked = {r["id"] for r in planned}
        for decision in [*manifest["events"], *manifest["rows"]]:
            if decision["status"] == "eligible-replacement":
                decision.update(status=proof["reason"], reason=proof["reason"], evidence_status="excluded")
        manifest["replacements"] = []
        manifest["pending"] = [proof["reason"]]
        require(all(r["status"] != "eligible-replacement" for r in manifest["rows"]
                    if r["id"] in blocked), "Incomplete blocked decisions")
    else:
        manifest["pending"] = []
    manifest["counts"] = {
        "source_events": dict(sorted(Counter(e["status"] for e in manifest["events"]).items())),
        "historical_rows": dict(sorted(Counter(r["status"] for r in manifest["rows"]).items()))}
    # Bind the actual implementation bytes as well as the declared checkout
    # revision. No Git process or credential-bearing environment is needed.
    root = Path(__file__).resolve().parent
    paths = ["identity_migration.py", "identity_maintenance.py",
             *[f"ghostfolio_ibkr_sync/{name}.py" for name in
               ("app", "sync", "ghostfolio", "ibkr", "models")]]
    manifest["implementation"] = {path: digest((root / path).read_bytes()) for path in paths}
    approved = {replacement["id"]: replacement["new_comment"]
                for replacement in manifest["replacements"]}
    manifest["ordered_row_fingerprints"] = [
        {"id": row["id"], "before": digest(canonical_json(row)),
         "after": digest(canonical_json({**row, "comment": approved.get(row["id"], row["comment"])}))}
        for row in rows]


def preview(inputs: Path, output: Path) -> str:
    config_path = safe_path(inputs)
    config_bytes = config_path.read_bytes()
    config = keyed_yaml(config_bytes)
    require(config.get("schema") == "ibkr-migration-inputs-v1", "Unsupported inputs schema")
    require(re.fullmatch(r"[0-9a-f]{40}", str(config.get("tool_commit", ""))),
            "Missing exact tool commit")
    require(text(config.get("timezone")), "Missing IANA timezone")
    ZoneInfo(config["timezone"])
    window = config.get("window")
    require(isinstance(window, list) and len(window) == 2 and all(text(v) for v in window),
            "Missing report window")
    require(date.fromisoformat(window[0]) <= date.fromisoformat(window[1]), "Invalid report window")
    accounts = config.get("accounts")
    require(config.get("inventory_complete") is True and isinstance(accounts, dict) and accounts,
            "Missing complete configured source inventory")
    for account, destination in accounts.items():
        format_versioned_activity_identity(account, "TRADE", "validation")
        require(text(destination), "Missing destination account mapping")
    mapping = config.get("symbol_mapping")
    require(isinstance(mapping, dict) and all(text(k) and text(v) for k, v in mapping.items()),
            "Invalid symbol mapping")
    records = config.get("reports")
    require(isinstance(records, dict) and records, "Missing keyed reports")
    bindings = {"inputs": digest(config_bytes)}
    captured: dict[Path, bytes] = {config_path: config_bytes}

    def read(ref: Any) -> bytes:
        require(isinstance(ref, dict) and text(ref.get("path")), "Missing saved input path")
        path = safe_path(config_path.parent / ref["path"])
        data = path.read_bytes()
        require(re.fullmatch(r"[0-9a-f]{64}", str(ref.get("sha256", "")))
                and digest(data) == ref["sha256"], "Saved input hash changed")
        require(path not in captured, "Duplicate input path")
        captured[path] = data
        return data

    reports: dict[str, Any] = {}
    saved_reports: dict[str, tuple[str, str]] = {}
    covered: set[str] = set()
    for name, ref in sorted(records.items()):
        require(isinstance(ref, dict) and ref.get("source_account") in accounts,
                "Report account missing from inventory")
        account = ref["source_account"]
        xml = read(ref).decode("utf-8-sig")
        require(parse_source_account_ids(xml) == {account}, "Report source account mismatch")
        bounds = historical_dividend_report_window(xml)
        require(bounds is not None, "Missing report window evidence")
        # Bounds are evidence of scope, not proof of full event completeness.
        reports[name] = {"source_account": account, "window": bounds, "sha256": ref["sha256"]}
        saved_reports[name] = account, xml
        covered.add(account)
    require(covered == accounts.keys(), "Inventory accounts lack saved reports")
    order = config.get("replay_order")
    require(isinstance(order, list) and all(isinstance(name, str) for name in order)
            and len(order) == len(records) and set(order) == set(records),
            "Replay order must contain each saved report exactly once")
    snapshot_ref = config.get("snapshot")
    snapshot = exact_json(read(snapshot_ref))
    validate_snapshot(snapshot, snapshot_ref)
    bindings.update({"snapshot": snapshot_ref["sha256"],
                     "mapping": digest(canonical_json(mapping)),
                     "inventory": digest(canonical_json(accounts))})
    manifest = {
        "schema": "ibkr-migration-preview-v1", "stage": "complete-import-selection-proof",
        "actionable": False, "replacements": [],
        "pending": ["complete-import-selection-proof"],
        "bindings": bindings, "tool_commit": config["tool_commit"],
        "timezone": config["timezone"], "window": window, "accounts": accounts,
        "symbol_mapping": mapping, "reports": reports,
        "snapshot": {k: v for k, v in snapshot_ref.items() if k != "path"},
        "limitations": ["Declared inventory and report bounds do not prove event completeness.",
                        "This evidence preview cannot authorize apply or rollback."],
    }
    manifest.update(classify_history(saved_reports, snapshot["activities"], config))
    bind_selection(manifest, saved_reports, snapshot["activities"], config)
    manifest["limitations"].append(
        "Proof is invalid after configuration, inventory, window, tool, image or snapshot changes; "
        "undeclared future accounts are outside this proof.")
    manifest["limitations"].append(
        "Historical deduplication does not certify event completeness or exact migration eligibility.")
    for path, data in captured.items():
        require(safe_path(path).read_bytes() == data, "Input changed during preview")
    data = canonical_json(manifest)
    manifest_hash = digest(data)
    publish_private(output, {"manifest.json": data,
                            "manifest.sha256": (manifest_hash + "\n").encode()}, list(captured))
    return manifest_hash


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("preview", help="Validate saved migration evidence offline")
    command.add_argument("--inputs", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Shared converters can log private source evidence. Keep the CLI output bounded.
    previous_logging_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        print(preview(args.inputs, args.output))
    except (RuntimeError, ValueError, OSError, KeyError, TypeError, SyntaxError, yaml.YAMLError) as error:
        parser.exit(1, f"Preview refused ({type(error).__name__}); check saved input evidence.\n")
    finally:
        logging.disable(previous_logging_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
