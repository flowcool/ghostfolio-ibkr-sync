# Identify trades by comment and match nearby dividends conservatively

Date: 2026-10-12. Status: accepted (existing behavior).

The sync reads existing Ghostfolio activities once and skips trades whose
`IBKR#<tradeID>` comment is already present; the trade-ID set is shared across
accounts, not account-scoped. Trades without an ID are refused. Dividend
comments use `dividend#<ISIN>#<date>` (raw IBKR symbol when ISIN is absent), with
account-scoped matching and support for older resolved-symbol comments.

To avoid duplicating manual or legacy dividends, an active YAHOO dividend of
the same resolved symbol in the same destination account within inclusive
±3 calendar days also suppresses a candidate, regardless of amount. Rows whose
comment starts with `dividend#` do not enter this proximity index. Trust
principle: a row with a connector comment is ours and is trusted by exact
comment identity; a user edit of such a row is out of contract. A distinct
payment next to an imported one is therefore imported.
Inactive activities retain their identifiers but do not supply proximity evidence.
A proximity skip stays a skip, but it is visible. The source gross is compared
with the existing row's quantity × unitPrice after normalization to a common
major unit. Equal gross logs INFO; different or not comparable gross (for
example an unsupported denomination) logs one WARNING with both dates, gross
values, fees and the operator action: check IBKR and add the payment by hand if
it is distinct. Equal gross does not prove the same payment. Exit status and
notifications do not change.
This heuristic can omit distinct payments: a payment on day 3 can be skipped
because a different manual or legacy payment exists on day 1. Same-security/day cash rows are
aggregated, not tracked as distinct payment events. Review unusual schedules
and later corrections manually; this is not exact financial reconciliation or
protection against simultaneous runs using stale snapshots.

Sources: `ghost_get_existing_orders` in the
[`ghostfolio` module](../../ghostfolio_ibkr_sync/ghostfolio.py), `_dividend_date_matches` in the
[`sync` module](../../ghostfolio_ibkr_sync/sync.py), `process_account` in the
[`app` module](../../ghostfolio_ibkr_sync/app.py), and
[conversion rules](../../README.md#how-activities-are-converted).
