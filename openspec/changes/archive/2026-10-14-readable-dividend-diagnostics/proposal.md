## Why

The real DRY_RUN on the production query (114 historical dividend findings) passes its counts but the operator cannot act on it. Of 11 "differences", 1 is sub-cent rounding, 6 are one-yen gaps and 4 are real quantity errors. Ten more rows look like old duplicates but read as "uncertain". The log shows Python text such as `Decimal('0')` and `7.2E-17`, jargon reasons, no action line, and a final summary printed as a dictionary. Release is blocked until the log reads in plain words.

## What changes

- Rounding below half a minor unit of the source currency is classified "noise": still counted, no longer a difference.
- A gap of exactly one minor unit (6 JPY rows) gets its own bucket: "minimal difference, cause unknown".
- Old-comment rows that share security and day with a compared group read "probable duplicate". Their category stays uncertain.
- Two or more destination rows whose totals equal the source read "total equal to IBKR, split over N rows". No split is claimed as proven.
- Every finding to check or inform carries a plain reason, both sides' values, an action line, and "Nothing was written".
- The final summary reads "N to check, N informational, N noise" and lists the items to check. Coherent and outside-window findings stay at DEBUG.
- No Python representation appears in any finding line.

## Record types considered

Source: saved real Flex report (query 1492040) and the DRY_RUN log of 2026-10-14.

| Flex record | Decision |
|---|---|
| CashTransaction Dividends, Payment In Lieu, Withholding Tax | In scope (compared, unchanged) |
| ChangeInDividendAccrual | In scope (quantity evidence, unchanged) |
| Other cash types, Trades, Cash Report | Out of scope |

## Non-goals

- No detection of amounts revised by IBKR after first import. The operator decided this out (it needs stored first-import amounts and a live-run hook, for a case not observed in 97 groups). A revision shows as "amount differs".
- No change to matching, identity rules, exit codes, notifications, live runs or data. No repair.
- No KRW support.

## Order

Implementation waits for task 1.1 of `fail-account-on-missing-dividend-fields` to merge (same file).
