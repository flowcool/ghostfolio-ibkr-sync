## Context

`positions["dividend_dates"]` (built in `ghost_get_existing_orders`) feeds `_dividend_date_matches`, used by `process_account` and mirrored by `_historical_proximity`. Exact identity is checked earlier against `existing_dividend_comments`.

## Decisions

1. **Index only non-connector rows.** In `ghost_get_existing_orders`, skip the append when the comment starts with `dividend#` (same test already used for `dividend_comments`). Remove the run-local append after import in `process_account`. Rationale: exact comment identity already covers these rows.
2. **Store gross with the date.** Each index entry becomes `(date, gross, currency)` with gross = `Decimal(str(quantity)) * Decimal(str(unitPrice))`, `None` when a value or currency is missing. Live runs need it too, so it is not taken from `dividend_evidence` (dry-run only).
3. **Compare gross.** `_dividend_date_matches` returns the matching entry. The caller compares with the source gross (`div["amount"]`, same currency) after rounding to the minor unit, reusing `_historical_minor_unit`. Equal: INFO as today. Different, or not comparable: one WARNING. Both skip.
4. **Mirror.** `_historical_proximity` drops connector-comment rows from `candidates` and adds source and candidate gross.
5. **Failure semantics.** No new exception, no `ok=False`, no notification: findings never change exits.

## Risks

- A manual row with net or converted amounts warns although it is a true duplicate. Acceptable: it was skipped before too, now it is visible.
- Callers that unpack `dividend_dates` entries as bare dates: grep before the change, update in the same task.

## Rollback

Revert the commits; behavior returns to the pre-change skip. No data is written.
