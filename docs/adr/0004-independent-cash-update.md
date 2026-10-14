# Update cash independently of activity import success

Date: 2026-10-12. Status: accepted (existing behavior).

After the current account's import phases, `process_account` attempts to write
the Flex `BASE_SUMMARY` ending cash even when an import returns failure,
including an uncertain result. Cash is a broker snapshot, not a value derived
from accepted activities; the account can therefore show current cash alongside
missing or partially imported history. There is no transaction or automatic
rollback across activity imports and the cash update, and import failure still
makes the run fail.

This is not a promise to update cash after every error: early fetch/account
lookup failures or exceptions before reaching the cash stage bypass it. A report
without a `BASE_SUMMARY` cash row skips the update with a warning. An uncertain
import fences subsequent queries to the same destination account during that
run, but does not bypass the current invocation's cash stage. Dry runs perform
no financial write. The account currency is preserved without conversion, so it
must match IBKR's base currency: since 3.0 the update checks the Flex
`AccountInformation` currency against the Ghostfolio account currency. A
difference, or a report without that currency, sends no balance and fails the
account (after the import phases, so trades and dividends are unaffected).

Sources: `process_account`, `mark_import_uncertain`, `parse_cash_report` and
`ghost_update_cash_balance` in the [runtime](../../ibkr_to_ghostfolio.py), and
[How it works](../../README.md#how-it-works).
