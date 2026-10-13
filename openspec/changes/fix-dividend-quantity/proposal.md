# Proposal

## Why

46 groups/49 actions support structured quantity and cash authority.

## What Changes

- **BREAKING:** require enriched Flex; remove description inference and one-unit fallback.
- Identity → deduplication → quantity checks; cash authority.
- Check candidate payments/relevant accruals; unrelated rows cannot block others.
- Reject overflow/positive underflow after conversion/scaling, including GBP→GBp.

Saved baseline/diagnostic inventory (B/D):

| Flex record | B/D | Scope |
|---|---:|---|
| CashTransaction: Dividends | 48/48 | In: payments |
| CashTransaction: Payment In Lieu Of Dividends | 7/7 | In: portions |
| CashTransaction: Withholding Tax | 50/50 | In: fees |
| ChangeInDividendAccrual: Po/Re | 0/78+76 | In: quantity evidence |
| CashTransaction: Other Fees | 0/97 | Out |
| CashTransaction: Deposits/Withdrawals | 0/1 | Out |
| CashTransaction: Broker Interest Paid | 0/36 | Out |
| Trade | 135/0 | Out |
| CashReportCurrency | 9/0 | Out |
| AccountInformation | 1/0 | Out |
| AssetSummary | 0/0 | Out |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: structured dividend quantities and migration.

## Impact

Runtime/tests/README/setup; dependencies/ENV unchanged.

## Non-goals

Historical reconciliation/maintenance, monetary revisions, regrouping, shared-helper changes, service access. Captures stay private.
