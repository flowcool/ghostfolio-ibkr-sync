# Proposal

## Why

Ghostfolio dedup ignores destination accounts; one can suppress another. Reading v2 first preserves rollback.

## What Changes

- Read legacy and IBKR v2 identities without v2 writes.
- **BREAKING:** Stop before writes for invalid reserved identities.
- **BREAKING:** Fail one account for partial coverage or short 2xx acceptance. Keep proven rows, avoid retries, and continue safely.
- Amend ADR 0002 and guidance; add no ADR.
- Keep the rc.4 GO. Require another for rc.5. Defer writes and migration to rc.6.

### Flex scope

| Record | Rows | Scope |
|---|---:|---|
| Trade / STK | 118 | Identity |
| Trade / CASH, OPT | 16, 1 | Unchanged |
| CashTransaction / dividend, PIL, withholding | 48, 7, 50 | Identity |
| CashTransaction / other DETAIL | 134 | Out |
| CashReportCurrency / BASE_SUMMARY, other | 1, 8 | Out |
| AccountInformation | 1 | Out |
| ChangeInDividendAccrual | 154 | Action evidence |
| AssetSummary, CorporateAction | 0 | Out |
| Transfer, OpenPosition, ConversionRate | 0 | Unobserved |

## Capabilities

### Modified Capabilities

- `connector-runtime`: identities and short acceptance.

## Impact

Parsing, tests, ADR 0002 and guidance change. Sibling work is separate.

## Non-goals

No v2 write/migration, mutation, conversion, sibling, release, deployment or live run.
