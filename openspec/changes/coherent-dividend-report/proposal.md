# Proposal

## Why

The current dividend dry-run report contradicts its import summary and can describe one activity twice. It also exposes Python formatting and misclassifies known currency and one-yen cases, so counts alone cannot make the report safe to use.

## What Changes

- Link the dividend import summary to the report outcome.
- Treat a matching legacy `dividend#<symbol>#<date>` comment as the same report identity and emit one block.
- Emit one coherent action per block. Remove raw Python representations and round monetary output to the currency minor unit.
- Separate missing, conflicting and unsupported currency states. Support KRW as a zero-decimal currency.
- Recognize a legacy row whose gross equals quantity times the IBKR declared rate while paid cash differs by one minor unit. Report the known rounding cause as visible audit information, with no action because the IBKR rounding is accepted.
- Require the real dry-run log to pass `scripts/check_dividend_report.py` with zero violations, then require a human reading of every block.

## Flex Record Scope

Built from the saved 2026-10-15 Flex evidence and current sanitized fixtures.

| Flex record | Scope | Use |
|---|---|---|
| `CashTransaction` Dividend / Payment In Lieu, DETAIL | In | Payment identity and paid gross |
| `CashTransaction` Withholding Tax, DETAIL | In | Paid fee |
| `ChangeInDividendAccrual` | In | Quantity and declared `grossRate` evidence |
| `CashTransaction` SUMMARY or other cash types | Out | No report input |
| `Trade` | Out | No dividend-report change |
| `CashReportCurrency` / `AccountInformation` | Out | Cash balance and base currency unchanged |
| `AssetSummary` | Out | Ignored today |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: Make the dividend dry-run report coherent, readable and acceptance-tested.

## Impact

Affected runtime areas are historical dividend identity, classification, formatting and account summary logging in `ibkr_to_ghostfolio.py`. Offline diagnostic tests and the versioned report checker provide proof. No API, ENV, dependency, import-selection or financial-write behavior changes.

## Non-goals

- No account-scoped identity v2.
- No `dividend-proximity-amount-evidence` behavior.
- No automatic update or deletion of Ghostfolio activities.
