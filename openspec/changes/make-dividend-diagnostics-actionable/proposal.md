# Proposal

## Why

The first real v2.5.0 dry run produced 114 unusable historical-dividend findings: 44 groups shared one compound reason and details omitted the evidence. Saved Flex and Ghostfolio evidence measured missing Ghostfolio profile ISIN in 44/44 groups, dates at midnight in Europe/Paris in 5/44, and no other failed identity check. After this change, all 44 groups must reach amount comparison in the real dry run. Two separate absent groups need proximity explanations.

## What Changes

- Split identity into named checks with expected/observed values. Missing profile ISIN is unavailable; a nonempty conflict blocks identity.
- Compare the IBKR business day with the Ghostfolio instant rendered in IANA `TZ`. Accept Flex `YYYYMMDD;HHmmss TimeZone` without changing general UTC conversion. Query 1671605 already emits this format; v2.5.0 returns `None`.
- Missing or invalid IANA `TZ` forces the entire run into `DRY_RUN` before any write, with one WARNING line and a final-notification mention.
- **BREAKING**: require timezone-qualified dividend/PIL/withholding rows. A missing or invalid Flex suffix fails the account before any Ghostfolio write, including cash; this failure never enables `DRY_RUN`.
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
