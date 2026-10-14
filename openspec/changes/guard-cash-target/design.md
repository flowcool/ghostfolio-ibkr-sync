## Decisions

- **Product rule.** One IBKR account maps to one Ghostfolio account, by design (operator, 2026-10-14). The guard enforces it. Aggregation is rejected: a failed source would write a wrong sum.
- **Duplicate check.** In `load_config`, next to the existing length checks, compare the effective targets: names, or IBKR ids when `GHOST_ACCOUNT_NAMES` is empty (`run_sync` default). Exact match, like `ghost_find_account_id`. Raise `RuntimeError` naming the target; `run_sync` already logs it and returns 1.
- **Base currency source.** `parse_cash_report` reads only the `BASE_SUMMARY` row, and that row has no currency code (`currency="BASE_SUMMARY"`). The code is `AccountInformation` `currency` (`CurrencyPrimary`), selected in `docs/ibkr-setup.md`, present in the saved real report. A new small `parse_base_currency`, same style as `parse_cash_report`, returns it or None.
- **Account currency source.** `ghost_update_cash_balance` already GETs the account and sends `account_data["currency"]` in its PUT (`tests/test_ghostfolio.py`, payload test). That field is the source of truth; no extra request.
- **Guard placement.** `process_account` passes the base currency to `ghost_update_cash_balance`, which compares after its GET and returns False on a difference; the caller already marks the account failed. Absent base currency: error naming the missing field, no PUT, account failed; a warning would let cash go stale unnoticed. `docs/ibkr-setup.md` requires the field.
- **Dry run.** `DRY_RUN` performs the read-only GET and reports a mismatch, so the preview matches a live run. One no-API dry-run test changes.
- **`GHOST_CURRENCY`.** Remove it from `load_config` and the README. Spec, README and code call it unused; its `USD` default would break EUR users if used. Unknown ENV variables are ignored, so removal changes nothing.
- **Downstream.** `ghost_update_cash_balance` is projected into ghostfolio-degiro-sync (ADR 0007); the PR flags it.
- **Rollback.** Revert the merge commit.

