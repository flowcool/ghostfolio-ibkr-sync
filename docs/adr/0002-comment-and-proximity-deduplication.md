# Identify trades by comment and match nearby dividends conservatively

Date: 2026-10-12. Status: accepted.

The sync reads existing Ghostfolio activities once. Historical
`IBKR#<tradeID>` comments suppress trades globally across accounts.
New trades use `IBKR#v2#<source-account>:TRADE:<tradeID>` with the verified
report account. Trades without an ID are refused. Dividend
comments use `dividend#<ISIN>#<date>` (raw IBKR symbol when ISIN is absent), with
account-scoped matching and support for older resolved-symbol comments.

The reader also accepts strict versioned identities in the global
`IBKR#v2#<source-account>:<kind>:<source-id>` namespace. Source-account and
source-id segments use ASCII letters, digits, `.`, `_`, or `-`. `TRADE` applies
only to BUY and SELL activities. `DIVIDEND` applies only to DIVIDEND activities.
Exact lowercase `IBKR#v` reserves the namespace. An unsupported version,
malformed segment, unknown kind, or activity-type mismatch stops the run before
any financial write with the fixed `invalid_identity` outcome. Other
`IBKR#<rest>` comments keep their legacy meaning. The reader indexes v2 comments
globally by source account and exact comment, independent of the destination
Ghostfolio account. A v2 trade identity suppresses only the matching source
account and trade ID; the same trade ID from another source account remains a
candidate. Legacy trade comments retain their global behavior. The reader does
not change historical comments automatically.

During a run, only proven accepted rows update import state. Accepted v2
BUY/SELL rows update their identity index and destination holdings. Accepted v2
DIVIDEND rows update only the v2 index. They never add holdings or legacy-global
trade IDs. Omitted buys cannot authorize later sales. Accepted subsets remain
recorded even when the account fails.

Manual trade matches stay in a separate ephemeral `(source-account, tradeID)`
set. Repeated queries for that source account skip the matched trade. Another
source account with the same tradeID remains eligible. Manual matches never
add legacy-global trade IDs or v2 accepted identities. Advice for a manual BUY
shows its exact proposed v2 comment. Dry runs copy the loaded snapshot and
share simulated state across queries; they do not change the loaded real state.

To avoid duplicating manual or legacy dividends, an active YAHOO dividend of
the same resolved symbol in the same destination account within inclusive
±3 calendar days also suppresses a candidate, regardless of amount. Rows whose
comment starts with `dividend#` do not enter this proximity index. Trust
principle: a row with a connector comment is ours and is trusted by exact
comment identity; a user edit of such a row is out of contract. A distinct
payment next to an imported one is therefore imported.
Inactive activities retain their identifiers but do not supply proximity evidence.
Versioned dividend identities are connector-owned. They do not supply proximity
or historical-diagnostic evidence.
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
