"""Bounded reconciliation authority. Matching never changes transport precision."""

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation, localcontext

PROFILES = ("off", "conservative", "balanced", "permissive")
PRECISION = {"JPY": 0, "GBP": 2, "USD": 2, "EUR": 2, "CAD": 2}
LIMITS = {"conservative": (0, Decimal(0)),
          "balanced": (1, Decimal("0.001")),
          "permissive": (100, Decimal("0.01"))}


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
