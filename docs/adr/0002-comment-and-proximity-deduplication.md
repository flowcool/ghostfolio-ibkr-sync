# Identify trades by comment and match nearby dividends conservatively

Date: 2026-10-12. Status: accepted.

The sync reads existing Ghostfolio activities once. Historical
`IBKR#<tradeID>` comments suppress trades globally across accounts.
New trades use `IBKR#v2#<source-account>:TRADE:<tradeID>` with the verified
report account. Trades without an ID are refused. New dividends use
`IBKR#v2#<source-account>:DIVIDEND:<actionID>`, one row per proven positive cash
action. Historical `dividend#<ISIN>#<date>`, raw-symbol and resolved-symbol
comments remain account-scoped.

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

For dividends, exact historical comments in the destination account win before
v2 coverage. Otherwise, complete positive-action coverage skips the group,
even when the stored rows moved to another destination account or became inactive.
Partial coverage fails the account and imports no dividend from that group.
Normal reruns do not fill missing actions. This refusal can recur for the whole
report window after partial server acceptance.

Before a group with no coverage can use proximity, the sync checks stored v2
dividend context for the same source account. A different known day or distinct
ISINs with no matching symbol rule out overlap. Different symbols alone cannot
prove distinct securities. A matching symbol or ISIN on the same day, or context that
cannot rule out overlap, blocks the group for manual review. The check retains
inactive rows and all contexts of duplicate identities. It ignores amounts and
destination ownership. Accepted rows also supply context to later queries in
the same run. This is an exact-context guard; it does not use a date window.
Safe trades, sales, cash updates and later accounts continue when a group fails.

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
because a different manual or legacy payment exists on day 1. Historical exact
comments can also hide a later distinct same-security/day event; they do not
prove completeness. Security/day groups remain the historical matching boundary;
new eligible groups are partitioned into actions before writing. The conflict
guard can refuse a legitimate additional same-day event. It cannot detect every
revision, including changes to both day and security. An existing exact identity
does not certify unchanged financial values. Review corrections manually. No
automatic backfill, correction or historical edit is authorized. Concurrent runs
with stale snapshots remain outside this protection.

Broker generations stay independent. IBKR writes v2. The inspected Bourse Direct
revision `3193086cd0223b0bfb18a388c53f1e0c65327dce` writes BD v1/v2;
its proposed common-grammar target is BD v3, not a delivered v3 writer.
DEGIRO revision `e8908adabd5453c9b57cb2dd687dc92a81ce15b2` writes
`DEGIRO#<source-account>:<kind>:<source-id>`. Its core remains pinned to
IBKR `5749146ff297133a6a85d9006bba60b65d9f7cde` under [ADR 0007](0007-pinned-degiro-core.md).
Sibling comments never become IBKR identities. An otherwise matching active
sibling row can still supply manual/proximity evidence in the same destination
account. Namespace separation does not disable these historical heuristics.
Shared-helper propagation requires a separate DEGIRO change; pins stay unchanged.
See [qualification and release order](../releasing.md#v2-writer-qualification-and-release-order)
for source, destination, maintenance and actual-image rollback gates.

Sources: `ghost_get_existing_orders` in the
[`ghostfolio` module](../../ghostfolio_ibkr_sync/ghostfolio.py), `_dividend_date_matches` in the
[`sync` module](../../ghostfolio_ibkr_sync/sync.py), `process_account` in the
[`app` module](../../ghostfolio_ibkr_sync/app.py), and
[conversion rules](../../README.md#how-activities-are-converted).
