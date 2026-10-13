# Proposal

## Why

Captures support 46 payment groups/49 actions. IBKR quantity resolves unrated PIL and contradicts rounded inference; accrual amounts/tax differ from payments.

## What Changes

- **BREAKING:** require enriched Flex; remove description inference and one-unit fallback.
- Associate IBKR quantities conservatively; retain cash payment evidence.
- Reject incompatible dividend input or individual unsupported payments locally.

Inventory rebuilt from saved baseline/diagnostic captures (B/D):

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

Runtime, offline tests, README/setup; unchanged dependencies/ENV.

## Non-goals

Historical reconciliation, maintenance, monetary revision, regrouping, shared-helper changes, service access. Private captures stay outside Git.
