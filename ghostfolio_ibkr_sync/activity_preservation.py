"""Pure exact activity comparison; raw capture hashes remain tamper evidence."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

# getActivities on the pinned API exposes these server-owned values. Paired
# retained reads also show account.updatedAt and profile enrichment changing
# while stored activities remain unchanged. Unknown paths are never discarded.
IGNORED = {
    (): {"updatedAt", "value", "valueInBaseCurrency", "feeInBaseCurrency",
         "feeInAssetProfileCurrency", "unitPriceInAssetProfileCurrency"},
    ("account",): {"updatedAt"},
    ("assetProfile",): {"updatedAt", "activitiesCount", "dateOfFirstActivity", "watchedByCount"},
    ("SymbolProfile",): {"updatedAt", "activitiesCount", "dateOfFirstActivity", "watchedByCount"},
}


def preserved_values(row: dict[str, Any]) -> dict[str, Any]:
    """Strict by default, including unknown fields and nested relationships."""
    def normalize(value: Any, path: tuple[str, ...]) -> Any:
        if isinstance(value, dict):
            return {key: normalize(item, (*path, key)) for key, item in value.items()
                    if key not in IGNORED.get(path, set())}
        if isinstance(value, list):
            return [normalize(item, (*path, "[]")) for item in value]
        if path in (("quantity",), ("unitPrice",), ("fee",)):
            number = Decimal(str(value))
            if not number.is_finite():
                raise ValueError("Non-finite preserved activity number")
            return number
        if path in (("date",), ("createdAt",)) and isinstance(value, str):
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("Missing preserved timestamp timezone")
            return timestamp.astimezone(UTC)
        return value

    result = normalize(row, ())
    if not isinstance(result, dict):
        raise ValueError("Invalid preserved activity")
    return result


def preserved_equal(before: dict[str, Any], after: dict[str, Any]) -> bool:
    def equal(left: Any, right: Any) -> bool:
        if isinstance(left, dict) and isinstance(right, dict):
            return left.keys() == right.keys() and all(equal(left[key], right[key]) for key in left)
        if isinstance(left, list) and isinstance(right, list):
            return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right, strict=True))
        # Raw live JSON retains Decimal types. Canonical journal evidence keeps
        # their exact text; compare that pair without normalizing arbitrary text.
        if isinstance(left, Decimal) and isinstance(right, str):
            return left.is_finite() and left == Decimal(right)
        if isinstance(right, Decimal) and isinstance(left, str):
            return right.is_finite() and right == Decimal(left)
        if isinstance(left, bool) or isinstance(right, bool):
            return type(left) is type(right) and left == right
        return bool(left == right)

    try:
        return equal(preserved_values(before), preserved_values(after))
    except (ValueError, ArithmeticError, TypeError):
        return False
