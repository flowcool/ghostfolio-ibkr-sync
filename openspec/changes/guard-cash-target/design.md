## Decisions

- **Product rule.** One IBKR account maps to one Ghostfolio account, by design (operator, 2026-10-14). The guard enforces it. Aggregation is rejected: a failed source would write a wrong sum.
- **Duplicate check.** In `load_config`, next to the existing length checks, compare the trimmed `account_names` (the key `ghost_find_account_id` matches). Raise `RuntimeError` naming the target; `run_sync` already logs it and returns 1.
- **Base currency source.** `parse_cash_report` reads only the `BASE_SUMMARY` row, and that row has no currency code (`currency="BASE_SUMMARY"`). The code is `AccountInformation` `currency` (`CurrencyPrimary`), selected in `docs/ibkr-setup.md`, present in the saved real report. A new small `parse_base_currency`, same style as `parse_cash_report`, returns it or None.
- **Account currency source.** `ghost_update_cash_balance` already GETs the account and sends `account_data["currency"]` in its PUT (`tests/test_ghostfolio.py`, payload test). That field is the source of truth; no extra request.
- **Guard placement.** `process_account` passes the base currency to `ghost_update_cash_balance`, which compares after its GET and returns False on a difference. The existing caller already marks the account failed. Absent base currency: warning and skip, like the missing `BASE_SUMMARY` warning (ADR 0004).
- **Dry run.** The GET is read-only, so `DRY_RUN` performs it and reports a mismatch. Otherwise the preview hides a live failure. One no-API dry-run test changes.
- **`GHOST_CURRENCY`.** Remove it from `load_config` and the README. Evidence: spec, README and code all call it unused; its default is `USD`, so using it would break EUR users. Removal changes nothing for them, since unknown ENV variables are ignored.
- **Downstream.** `ghost_update_cash_balance` is projected into ghostfolio-degiro-sync (ADR 0007); the PR flags it.
- **Rollback.** Revert the merge commit.

## Open questions

- Whether Flex always emits the `AccountInformation` currency: seen in one saved report only.
