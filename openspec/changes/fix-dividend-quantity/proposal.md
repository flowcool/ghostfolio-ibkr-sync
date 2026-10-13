# Proposal

## Why

Investigation found ten conversion mismatches across 46 groups: 45 inferred candidates, one unrated payment. Inference does not independently prove entitlement.

## What Changes

- Retain usable rates across dividend/PIL portions and distinguish ordinary/bonus distributions.
- Validate complete numeric/currency tokens; preserve conservative one-unit fallback with a reasoned WARNING.
- Separate read-only reconciliation and historical maintenance into later changes.

Unchanged saved-report inventory:

| Flex record | Count | Scope |
|---|---:|---|
| CashTransaction: Dividends | 48 | In: quantity evidence |
| CashTransaction: Payment In Lieu Of Dividends | 7 | In: portions |
| CashTransaction: Withholding Tax | 50 | In: preserve fee |
| Trade | 135 | Out |
| CashReportCurrency | 9 | Out |
| AccountInformation | 1 | Out |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: forward dividend conversion and upgrade guidance.

## Impact

Runtime, synthetic tests and README. Stricter interpretation requires compatibility notices under docs/releasing.md.

## Non-goals

Destination reconciliation, persistent exceptions, notification/exit changes, historical writes, repeated-payment cleanup, monetary/withholding revision, mixed-currency regrouping, external rates and holdings inference. Monetary discrepancies retain their existing work owner. Private evidence stays outside Git.
