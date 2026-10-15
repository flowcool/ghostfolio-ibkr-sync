## Why

Native logs omit the Flex period, complete preview payloads and exact cash target. The lab needs these values without a mounted adapter.

## What Changes

- Add three DEBUG evidence kinds: `window`, `preview` and `cash`.
- Use `LAB_EVIDENCE ` followed by compact JSON with only `kind` and `value`.
- Preserve the removed adapter's value shapes. Keep existing INFO output byte-identical.

## Scope

The existing inventory came from the saved Flex report used for the original proposal. Only evidence changes.

| Flex record considered | In scope | Out of scope |
| --- | --- | --- |
| FlexQueryResponse / FlexStatements / FlexStatement | Explicit statement period | XML persistence |
| AccountInformation | Existing cash currency | Other metadata |
| Trades / Trade, STK | Existing preview payload | Conversion changes |
| Trade, CASH / OPT | None | New imports |
| CashTransactions / CashTransaction, DETAIL Dividends / Payment In Lieu Of Dividends / Withholding Tax | Existing preview payload | Selection changes |
| CashTransaction, Other Fees / Deposits/Withdrawals / Broker Interest Paid | None | New imports |
| CashReport / CashReportCurrency | Existing cash target | Currency conversion |
| ChangeInDividendAccruals / ChangeInDividendAccrual | None | New evidence |
| CorporateActions / ConversionRates / ConversionRate / AssetSummary / non-DETAIL cash | None | New processing |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: expose three native DEBUG evidence kinds.

## Impact

Change `ibkr_to_ghostfolio.py`, offline tests and one README line. No new dependency, ENV setting or HTTP call. Flag downstream propagation of shared Ghostfolio helpers in the code PR. The lab owns provider checks and stored-state acceptance.

## Non-goals

No envelope, run ID, run start/end, import stages, provider checks or import summary. No change to financial behavior, guards or notifications. No archive or release in this task.
