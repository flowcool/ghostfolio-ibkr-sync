# Identify trades by comment and match nearby dividends conservatively

Date: 2026-10-12. Status: accepted (existing behavior).

The sync reads existing Ghostfolio activities once and skips trades whose
`IBKR#<tradeID>` comment is already present; the trade-ID set is shared across
accounts, not account-scoped. Trades without an ID are refused. Dividend
comments use `dividend#<ISIN>#<date>` (raw IBKR symbol when ISIN is absent), with
account-scoped matching and support for older resolved-symbol comments.

To avoid duplicating manual or legacy dividends, an active YAHOO dividend of
the same resolved symbol in the same destination account within inclusive
±3 calendar days also suppresses a candidate, regardless of amount or comment.
Inactive activities retain their identifiers but do not supply proximity evidence.
This heuristic can omit distinct payments: a payment on day 3 can be skipped
because a different payment exists on day 1. Same-security/day cash rows are
aggregated, not tracked as distinct payment events. Review unusual schedules
and later corrections manually; this is not exact financial reconciliation or
protection against simultaneous runs using stale snapshots.

Sources: `ghost_get_existing_orders`, `_dividend_date_matches` and
`process_account` in the [runtime](../../ibkr_to_ghostfolio.py), and
[conversion rules](../../README.md#how-activities-are-converted).
