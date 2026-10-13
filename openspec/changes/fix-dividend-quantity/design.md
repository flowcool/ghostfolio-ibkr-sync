# Design

## Context

Three coherent destination component sets and eight overlapping representations preclude treating quantity correction as historical recovery.

## Goals / Non-Goals

Preserve source payment evidence; no destination proof, new journals or service access.

## Decisions

Extend `parse_cash_dividends` to retain signed portions/labels. Reuse totals; replace last-description selection with complete currency/rate validation. Unique cancellation precedes inference; reject ambiguous associations.

`convert_dividend_to_activity` reuses rounding, `minor_unit_conversion` and WARNING logging. Ordinary/bonus quantities must agree after rounding; summed rates lose distribution meaning. Shared helpers remain unchanged.

Acceptance gross/fee arithmetic uses absolute/relative tolerances 1e-12 for floating-point noise, never destination discrepancies. Quantity agreement uses existing rounding.

## Risks / Trade-offs

Missing entitlement → label inference, retain fallback. Reversals, mixed currencies and incompatible components were not observed → conservative synthetic coverage. Existing repeated income → separate reconciliation and maintenance decisions; monetary discrepancies retain their existing owner.

## Migration Plan

README identifies stricter interpretation and affected inputs under docs/releasing.md. No mount/configuration migration. Before an authorized upgrade, back up destination data and pin an image version: latest follows main. Restore the recorded prior image digest for runtime rollback; written activities require separate reviewed recovery.
