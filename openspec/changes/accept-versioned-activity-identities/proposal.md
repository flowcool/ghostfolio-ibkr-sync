# Proposal

## Why

Ghostfolio duplicate detection ignores the destination account, so one account can silently suppress another. A reader-first release keeps rollback safe before versioned writes.

## What Changes

- Define the shared `<BROKER>#v<N>#<source-account>:<KIND>:<source-id>` grammar in an ADR.
- Read legacy and IBKR v2 trade/dividend comments without writing v2.
- **BREAKING:** Stop before financial writes on malformed, unknown-version, or partially covered v2 dividend identity.
- **BREAKING:** Treat a 2xx import response that creates fewer activities than submitted as a warning and failed run. Keep proven creations, do not retry, and continue cash and other accounts.
- Target reader-only `v3.0.0-rc.4` under the existing release GO.

### Flex scope

Counts come from the saved real baseline and enriched reports.

| Record | Rows | Scope |
|---|---:|---|
| Trade / STK | 118 | In: legacy and future identity |
| Trade / CASH, OPT | 16, 1 | Out: conversion unchanged |
| CashTransaction / dividend, PIL, withholding | 48, 7, 50 | In: dividend identity |
| CashTransaction / other DETAIL | 134 | Out |
| CashReportCurrency / BASE_SUMMARY, other | 1, 8 | Out |
| AccountInformation | 1 | Out |
| ChangeInDividendAccrual | 154 | In: action evidence only |
| AssetSummary, CorporateAction | 0 | Out |
| Transfer, OpenPosition, ConversionRate | 0 | Out: unobserved |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: accept versioned identities safely and fail visibly on short import acceptance.

## Impact

Comment indexing, import-result handling, tests and a shared ADR change. Sibling adoption remains separate.

## Non-goals

No v2 writes, comment migration, activity mutation, financial conversion change, sibling edit, release, deployment, or live-service run.
