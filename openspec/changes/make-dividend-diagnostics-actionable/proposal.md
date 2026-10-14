# Proposal

## Why

The first real v2.5.0 dry run produced 114 unusable historical-dividend findings: 44 groups shared one compound reason and details omitted the evidence. Saved Flex and Ghostfolio data exposed missing profile ISINs, Paris-local dates, and two proximity skips.

## What Changes

- Split identity into named checks with expected/observed values. Missing profile ISIN is unavailable; a nonempty conflict blocks identity.
- Compare the IBKR business day with the Ghostfolio instant rendered in IANA `TZ`. Accept Flex `HHmmss TimeZone` without changing general UTC conversion.
- **BREAKING**: require `TZ` and timezone-qualified dividend/PIL/withholding rows. Invalid input fails the account before any Ghostfolio write, including cash; it never enables `DRY_RUN`.
- Add readable anomaly blocks, failed-check counts, proximity explanations, and migration guidance.

## Flex Records

Saved source: query 1671605, SHA-256 `a8864f5d40ceccffac677d76cab97c2ffda37e06d0a6493f000ef4f50b0fd134`.

| Record type | Rows | Scope |
|---|---:|---|
| CashTransaction: Dividends | 48 | Identity, date, values |
| CashTransaction: Payment In Lieu Of Dividends | 7 | Identity, date, values |
| CashTransaction: Withholding Tax | 50 | Date, fee evidence |
| ChangeInDividendAccrual | 154 | Existing quantity evidence |
| CashTransaction: Broker Interest Paid | 36 | Out |
| CashTransaction: Other Fees | 97 | Out |
| CashTransaction: Deposits/Withdrawals | 1 | Out |
| Trade | Not selected | Parser compatibility only |

## Capabilities

### Modified Capabilities

- `connector-runtime`: timezone prerequisites, historical identity evidence, readable diagnostics, and failure isolation.

## Impact

Parsing, diagnostics, account orchestration, tests, README, and IBKR setup guidance change. Shared-helper propagation must be assessed.

## Non-goals

No activity repair, persistence, proximity-deduplication fix, general import-date conversion, production replay, or financial write.
