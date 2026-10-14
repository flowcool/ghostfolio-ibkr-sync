# Design

## Context

Current reads discard dividend IDs/values. Captures cover one account/window.

## Goals / Non-Goals

Preserve import decisions; add no state.

## Decisions

- Retain dividend records in `ghost_get_existing_orders` context; reuse its validated GET/profile precedence. Preserve return shape/indexes; flag downstream projection.
- Reuse `parse_cash_dividends`, `dividend_structured_quantity`, `resolve_symbol`, `minor_unit_conversion` and `activity_is_active`. Add pure comparison in `process_account` before dry-run deduplication. Compare component vectors, common quantities and competing sets; preserve decimal differences. Proximity is not identity.
- Reuse logging/`finalize_run`. BourseDirect's read-only comparison separates evidence/repair; do not copy its net/quantity-one convention.

## Risks / Trade-offs

Rounded stored prices → display exact deltas, never infer acceptable error. Unknown timezone/ownership or unsupported history → uncertain/outside-window. Repeated subsets → evaluate canonical versus alternative representations, avoid arbitrary subset search. Private logs → README disclosure.

## Migration Plan

Restore the previous image digest for runtime rollback; revert this planning commit for document rollback.
