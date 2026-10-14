# Design

## Context

Current reads discard dividend IDs/values and decode JSON numbers as floats. Captures cover one account/window, including null activity currencies and GBP activity / GBp profile pairs.

## Goals / Non-Goals

Preserve import decisions; add no state.

## Decisions

- Retain dividend records in `ghost_get_existing_orders` context from the same validated GET. Preserve exact JSON numeric tokens through decimal decoding before any float conversion; keep the existing float-based import/position path, return tuple, indexes, validation and read count unchanged. Reuse assetProfile precedence over legacy SymbolProfile; flag downstream projection.
- Use a nonempty activity currency for price and fee; only null activity currency permits a supported profile fallback, with provenance. Unsupported/missing currency context stays uncertain. Normalize values into common major/minor units without replacing the activity denomination or rescaling from a conflicting profile currency.
- Reuse `parse_cash_dividends`, `dividend_structured_quantity`, `resolve_symbol`, `minor_unit_conversion` and `activity_is_active`. Add pure comparison in `process_account` before dry-run deduplication. Compare component vectors and common quantities without summing quantities. Build only identity-proven whole-payment or component representations; require each component once and full source coverage. Completeness concerns identity/coverage; coherence additionally requires exact quantity, gross and fee agreement. Multiple complete representations mean probable repetition even with discrepancies. Do not search arbitrary subsets. Resolve destination ownership across all source groups before certification; disputed ownership leaves every affected comparison uncertain. Proximity is not identity.
- Compute destination gross from exact stored quantity × unitPrice and sum gross/fee only over complete representations. Compare with exact broker cash gross and fee=max(0,-cash withholding), after common-unit normalization. Delta is destination minus source; retain every nonzero delta, raw signed tax/refund rows and totals separately. No tolerance, rounded display suppression or change to import accounting.
- Reuse logging/`finalize_run`. BourseDirect's read-only comparison separates evidence/repair; do not copy its net/quantity-one convention.

## Risks / Trade-offs

Rounded stored prices → display exact deltas, never infer acceptable error. Unknown timezone/ownership or unsupported history → uncertain/outside-window. Unproven component partitions → uncertain, never infer completeness from matching amounts. Private logs → README disclosure.

## Migration Plan

Restore the previous image digest for runtime rollback; revert this planning commit for document rollback.
