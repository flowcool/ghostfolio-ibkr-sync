## Context

`positions["dividend_dates"]` (from `ghost_get_existing_orders`) feeds `_dividend_date_matches`, used by `process_account` and mirrored by `_historical_proximity`. Exact identity is checked earlier.

## Decisions

1. **Index only non-connector rows.** In `ghost_get_existing_orders`, skip the append when the comment starts with `dividend#` (same test already used for `dividend_comments`). Remove the run-local append after import in `process_account`. Trust principle (Florent): a row with a connector comment is ours and trusted by exact identity; a user edit of such a row is out of contract. The old `dividend#<symbol>#<date>` comment stays covered by the exact `old_comment` check.
2. **Store gross with the date.** Each index entry becomes `(date, gross, currency, fee)` with gross = `Decimal(str(quantity)) * Decimal(str(unitPrice))` and fee = `Decimal(str(fee))`; gross and fee are `None` when a value is missing or invalid.
3. **Compare gross.** `_dividend_date_matches` returns the matching entry. The caller compares the exact source gross (`div["gross"]`, Decimal, never float `div["amount"]`) with the entry gross. Both sides go through `_historical_currency` to a common major unit (GBp handling as in `convert_dividend_to_activity`), rounded to `_historical_minor_unit`. A denomination that `_historical_currency` does not support (for example KRW) is "not comparable". Equal: INFO "amounts agree" with both fee values. Different, or not comparable: one WARNING naming the operator action. Both skip.
4. **Mirror.** `_historical_proximity` drops connector-comment rows from `candidates` and adds source and candidate gross. Every consumer of the matcher return changes, including the readable report (~2349).
5. **Failure semantics.** No new exception, `ok=False` or notification.

## Risks

- A manual row with net or converted amounts warns although it is a true duplicate. Acceptable: it was skipped before; now it is visible.
- A distinct payment next to a manual row (ordinary 25, PIL 100 next day) stays skipped. The WARNING is the recovery path: the operator adds it by hand.
- Callers that unpack `dividend_dates` entries as bare dates: grep, update in task 2.1.

## Rollback

Code revert restores the pre-change skip. It does not remove activities already imported by the new code. Such rows are removed by hand under a separate decision, with a verified backup.
