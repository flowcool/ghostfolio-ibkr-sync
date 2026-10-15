## Why

Native container logs omit evidence needed to check an import. A mounted observer supplied it. Version 3.0.0-rc.3 must expose the evidence through the normal entry point, including scheduled runs.

## What Changes

- Add versioned, single-line JSON evidence at DEBUG only (production INFO log unchanged) for each run, Flex period, activity, account import result and cash target.
- Include all ten activity payload fields. Distinguish preview, submission and confirmed acceptance.
- Preserve cash precision and currency. Record real-run outcomes without claiming that an HTTP success proves stored state.
- Expose provider lookup inputs per candidate. The acceptance consumer retains the provider GET and validates identity, currency and positive finite market price.
- Keep the existing readable dividend report and zero-candidate counters.

## Scope

Inventory source: saved `Ghostfolio_Sync_-_Individual.xml`; only element counts, cash types and trade categories were inspected. Rebuild this table if that source changes.

| Flex record | In scope | Out of scope |
| --- | --- | --- |
| FlexQueryResponse / FlexStatements / FlexStatement | Explicit statement bounds | XML persistence |
| AccountInformation | Existing base currency | Other account metadata |
| Trades / Trade, STK | Converted candidate evidence | Conversion changes |
| Trade, CASH / OPT | Existing exclusions | New imports |
| CashTransactions / CashTransaction, DETAIL Dividends / Payment In Lieu Of Dividends / Withholding Tax | Converted dividend evidence | Selection changes |
| CashTransaction, Other Fees / Deposits/Withdrawals / Broker Interest Paid | None | New imports |
| CashReport / CashReportCurrency | BASE_SUMMARY target | Currency conversion; other cash rows |
| ChangeInDividendAccruals / ChangeInDividendAccrual | Existing quantity association | New accrual logging |
| CorporateActions (empty in source) / ConversionRates / ConversionRate | None | New processing |
| AssetSummary; non-DETAIL cash (existing exclusion tests) | None | New processing |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: add native evidence and document its consumer boundary.

## Impact

Implementation will touch `ibkr_to_ghostfolio.py`, offline tests and README. No dependency or ENV setting is added. Import/cash helper changes require downstream propagation review. The lab consumer must adopt the new grammar separately before wrapper removal is accepted.

## Non-goals

This PR proposes behavior only. It does not implement code, release an image, run a lab or access production. No new provider request, automatic repair, changed financial selection, exit code or notification is proposed.
