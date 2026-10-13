# Proposal

## Why

OpenSpec lacks a reference for the running connector. Document existing behavior before changes.

## What Changes

Document Python/Docker, CRON, DRY_RUN, both authentications, sequential accounts, notifications, conversion, reconciliation, imports, cash and limits.

### Flex scope

Source: private real report `tmp/baseline-evidence/flex-20261013T164844Z.xml`, 2025-10-13–2026-10-12. Rebuild on source changes. Counts concern this report; absent types rely on README/tests.

| Record | Count | Scope/handling |
|---|---:|---|
| Trade / STK | 118 | In: conversion/filtering |
| Trade / CASH, OPT | 16, 1 | In: explicit exclusion |
| CashTransaction / Dividends | 48 | In: aggregation |
| CashTransaction / Payment In Lieu Of Dividends | 7 | In: aggregation; no rate, one-unit fallback |
| CashTransaction / Withholding Tax | 50 | In: dividend fee |
| CashTransaction / others, non-DETAIL | 0 | In: ignored; parsing tests |
| CashReportCurrency / BASE_SUMMARY | 1 | In: account balance |
| CashReportCurrency / others | 8 | In: ignored |
| AccountInformation | 1 | Out: unused |
| AssetSummary within Trades | 0 | In: ignored; parsing test |
| ChangeInDividendAccrual; CorporateAction | 0 | Out: unused; setup/limitations docs |
| Transfer; OpenPosition; ConversionRate | 0 | Out: unverified |
| Trade / other categories, unusual buySell | 0 | Open: financial correctness |

## Capabilities

### New Capabilities

- `connector-runtime`: existing behavior reference.

### Modified Capabilities

None.

## Impact

Planning only. No runtime/API/dependency/deployment/sibling changes. XML and checksum manifest stay outside Git (local exclude rule only; `.gitignore` does not cover `tmp/`).

## Non-goals

No fixes, cleanup/CI/publication specification, new tests, financial writes, apply, archive or push. Only authorized IBKR report acquisition contacted a real service.
