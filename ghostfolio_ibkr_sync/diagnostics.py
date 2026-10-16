"""Financial decisions: historical dividend evidence and comparison.

Compares retained Ghostfolio dividend history with the IBKR source groups for the DRY_RUN
diagnostic. Read-only: no HTTP, no writes, nothing here certifies identity from amounts.
Finding classification, proposed matches, formatting and logging stay in the legacy file
until the next extraction task.
"""

import os
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, DecimalException, localcontext
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
                if item["activity"].get("accountId") == account_id]
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
            comments = {reference, f"dividend#{symbol}#{dividend['date']}"}
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
