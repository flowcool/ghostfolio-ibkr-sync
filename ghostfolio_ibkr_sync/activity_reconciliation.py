"""Bounded reconciliation authority. Matching never changes transport precision."""

import re
from collections.abc import Mapping
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from math import isfinite, ulp
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PROFILES = ("off", "conservative", "balanced", "permissive")
PRECISION = {"JPY": 0, "GBP": 2, "USD": 2, "EUR": 2, "CAD": 2}
LIMITS = {"conservative": (0, Decimal(0)),
          "balanced": (1, Decimal("0.001")),
          "permissive": (100, Decimal("0.01"))}


def date_eligible(name: str, source: str, target: str, kind: str,
                  timezone: str) -> tuple[bool, dict[str, str]]:
    try:
        if any(re.search(r"\.[0-9]{7,}", value) for value in (source, target)):
            return False, {"reason": "Unsupported timestamp precision"}
        zone = ZoneInfo(timezone)
        instants = [datetime.fromisoformat(value.replace("Z", "+00:00")) for value in (source, target)]
        if any(value.tzinfo is None for value in instants):
            return False, {"reason": "Missing source or destination timezone"}
        dates = [value.astimezone(zone).date() for value in instants]
        distance = abs((dates[1] - dates[0]).days)
        limit = (3 if kind == "DIVIDEND" else 2) if name == "permissive" else 0
        return name in LIMITS and distance <= limit, {
            "timezone": timezone, "source instant": source, "destination instant": target,
            "source local date": str(dates[0]), "destination local date": str(dates[1]),
            "calendar distance": str(distance), "elapsed seconds": str((instants[1] - instants[0]).total_seconds())}
    except (ValueError, ZoneInfoNotFoundError):
        return False, {"reason": "Missing or invalid timezone or timestamp"}


def denomination(currency: str) -> tuple[str, Decimal]:
    """Only the documented fixed GBP/GBp conversion can grant authority."""
    return ("GBP", Decimal("0.01")) if currency == "GBp" else (currency, Decimal(1))


def gross_within_limits(name: str, source: Decimal, destination: Decimal,
                        currency: str) -> bool:
    major, _ = denomination(currency)
    if (name not in LIMITS or major not in PRECISION or not source.is_finite()
            or not destination.is_finite() or source <= 0 or destination <= 0):
        return False
    units, relative = LIMITS[name]
    with localcontext() as context:
        context.prec = max(50, len(source.as_tuple().digits) + len(destination.as_tuple().digits) + 20)
        difference = abs(destination - source)
        # Multiplication avoids division rounding at the inclusive relative edge.
        return (difference <= Decimal(units).scaleb(-PRECISION[major])
                and difference <= source * relative)


def financial_eligible(name: str, source: Mapping[str, str], destination: Mapping[str, str],
                       *, dividend_quantity_proven: bool = False) -> bool:
    """Fees cannot select a pair. Source conversion already validates them."""
    try:
        major, factor = denomination(source["currency"])
        other_major, other_factor = denomination(destination["currency"])
        if major != other_major or source["type"] != destination["type"]:
            return False
        quantity, other_quantity = Decimal(source["quantity"]), Decimal(destination["quantity"])
        if (not quantity.is_finite() or not other_quantity.is_finite()
                or quantity <= 0 or other_quantity <= 0):
            return False
        if quantity != other_quantity and (source["type"] != "DIVIDEND" or not dividend_quantity_proven):
            return False
        with localcontext() as context:
            context.prec = 100
            gross = quantity * Decimal(source["unitPrice"]) * factor
            other = other_quantity * Decimal(destination["unitPrice"]) * other_factor
        return gross_within_limits(name, gross, other, major)
    except (KeyError, InvalidOperation, ValueError):
        return False


def decimal_text(number: Decimal) -> str:
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def numeric_evidence(event: Mapping[str, Any], destination: Mapping[str, Any]) -> dict[str, Any]:
    """Reproduce only the converter's known multiply/divide/JSON path.

    Endpoints must equal either the source mathematical total or the reproduced
    converter total. A nearby arbitrary number never establishes this cause.
    """
    values, evidence = event["values"], event["source evidence"]
    major, factor = denomination(values["currency"])
    other_major, other_factor = denomination(destination["currency"])
    if major not in PRECISION or major != other_major:
        raise RuntimeError("Unsupported automatic denomination")
    with localcontext() as context:
        context.prec = 100
        quantity = Decimal(values["quantity"])
        if values["type"] in ("BUY", "SELL"):
            raw_quantity = abs(Decimal(evidence["quantity"]))
            raw_price = abs(Decimal(evidence["tradePrice"]))
            raw_currency = evidence["currency"]
            _, raw_factor = denomination(raw_currency)
            source_gross = raw_quantity * raw_price * raw_factor
            scale = raw_factor / factor
            reproduced = float(raw_price) * float(scale)
        else:
            raw_quantity = Decimal(evidence["accruals"][0]["quantity"])
            raw_gross = sum((Decimal(row["amount"]) for row in evidence["payments"]), Decimal(0))
            _, raw_factor = denomination(evidence["payments"][0]["currency"])
            source_gross = raw_gross * raw_factor
            with localcontext() as conversion:
                conversion.prec = 50
                reproduced = float(raw_gross / raw_quantity) * float(raw_factor / factor)
        wire_price = Decimal(str(reproduced))
        projected_gross = quantity * Decimal(values["unitPrice"]) * factor
        destination_gross = Decimal(str(destination["quantity"])) * Decimal(str(destination["unitPrice"])) * other_factor
        if not all(x.is_finite() for x in (source_gross, projected_gross, destination_gross)):
            raise RuntimeError("Non-finite gross evidence")
        bound = Decimal.from_float(ulp(reproduced)) * abs(quantity) * factor * 4 if isfinite(reproduced) else Decimal(0)
        residue = (quantity == raw_quantity and Decimal(values["unitPrice"]) == wire_price
                   and source_gross != projected_gross
                   and destination_gross in (source_gross, projected_gross)
                   and abs(projected_gross - source_gross) <= bound)
        precision = Decimal(1).scaleb(-PRECISION[major])
        return {"currency": major, "precision": PRECISION[major],
                "source gross": decimal_text(source_gross),
                "payload gross": decimal_text(projected_gross),
                "destination gross": decimal_text(destination_gross),
                "gross difference": decimal_text(destination_gross - source_gross),
                "source display": format(source_gross.quantize(precision, rounding=ROUND_HALF_EVEN), "f"),
                "destination display": format(destination_gross.quantize(precision, rounding=ROUND_HALF_EVEN), "f"),
                "reproduced price": decimal_text(wire_price), "residue bound": decimal_text(bound),
                "calculation residue": residue,
                "cause": "reproduced conversion multiply/divide/JSON" if residue else "no proven residue"}
