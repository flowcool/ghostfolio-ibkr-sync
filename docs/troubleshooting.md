# Troubleshooting

## "has no Cash Transactions section: dividends not synced"

The Flex Query does not include the Cash Transactions section. Add it as described in [Create a Flex Query](ibkr-setup.md#2-create-a-flex-query); trades still sync meanwhile, but the run exits 1.

## "cash rows without a valid 'YYYYMMDD;HHmmss TimeZone' dateTime"

The full line starts with `Flex Query <id>:` and ends with `account failed before any write`. A DETAIL dividend, payment-in-lieu or withholding row has no valid time-zone suffix, so the account fails before any import, cash or platform write. The run exits 1; other accounts still run and `DRY_RUN` is not enabled. In the Flex query, set the time format to **HHmmss TimeZone** (see [Create a Flex Query](ibkr-setup.md#2-create-a-flex-query)).

## "required dividend fields missing from the report"

The query lacks an attribute the connector requires, or the Change in Dividend Accruals section. The line names each missing XML attribute with the IBKR field to tick, for example `CashTransaction.conid (ConID (Contract ID))`, and ends with `account failed before any write`. Tick the named fields, save the query and re-run. A single empty or malformed value does not trigger this error: it rejects only that payment. See [Prepare for structured dividend quantities](ibkr-setup.md#prepare-for-structured-dividend-quantities).

## "TZ is missing" or "TZ is not a valid IANA timezone"

The run logs `<reason>: whole run forced to DRY_RUN, no Ghostfolio writes`. Nothing is written for any account, and the run sends one notification naming the reason when `APPRISE_URLS` is set. Set `TZ` to an IANA zone such as `Europe/Paris` and recreate the container. The image sets no default `TZ`.

## "Duplicate Ghostfolio target"

`Configuration error: Duplicate Ghostfolio target '<name>': each IBKR account needs its own target`. Two IBKR accounts point at one Ghostfolio account, either by a repeated name in `GHOST_ACCOUNT_NAMES` or, without names, by a repeated IBKR account ID. The run exits 1 before any network call. Give each IBKR account its own Ghostfolio account; the second balance would overwrite the first.

## "Cash balance not updated for account ..."

The cash balance is sent only when the IBKR base currency equals the Ghostfolio account currency. The account fails and no balance is sent in two cases: `IBKR base currency X differs from Ghostfolio account currency Y` (change the Ghostfolio account currency, or use the matching account), and `the report has no base currency` (select **CurrencyPrimary** under **Account Information** in the Flex query). `DRY_RUN` runs the same check.

## "Unknown buySell ... trade rejected"

The Flex report has a trade whose Buy/Sell value is not exactly `BUY` or `SELL`, for example a cancellation (`SELL (Ca.)`). The row is never imported, the log adds `Trade <id> cannot be converted safely; excluded before holdings checks`, and the account fails. Other trades import normally. Every run fails while the row stays in the 365-day report window. Check the trade in IBKR; there is no ENV override.

## "Not importing buy ... matches a manual Ghostfolio buy"

An IBKR buy was **not** imported because Ghostfolio already has a buy of the same quantity within 2 days that has no `IBKR#` comment, so it is most likely the same purchase entered by hand. Importing it would double the position. Put `IBKR#<tradeID>` (the ID shown in the warning) in the comment of that manual entry and the warning goes away. If it was a different purchase, add the missing buy by hand. See [What the tool skips automatically](configuration.md#what-the-tool-skips-automatically).

## "Mapping file ... not found"

The mapping file is missing at the configured path (or at the default `mapping.yaml` in the working directory, `/app` in the image). The run stops before contacting IBKR or Ghostfolio, because raw IBKR symbols can book trades on the wrong security (ticker collisions). Check the volume mount (`./mapping.yaml:/app/mapping.yaml`); if the host file did not exist when the container was created, Docker created a directory at `/app/mapping.yaml` instead: create the file on the host and recreate the container. Or set `MAPPING_FILE=""` to run without mappings on purpose. Invalid YAML, or a `symbol_mapping` that is not `ISIN: TICKER` pairs, also stops the run.

## "not valid for the specified data source YAHOO"

An imported symbol is not recognised by Yahoo Finance. Check the unmapped ISINs output at the end of the run and add the correct Yahoo Finance ticker to your mapping file. European ETFs almost always need an explicit mapping with an exchange suffix.

## Import fails but activities were expected

If Ghostfolio identifies an unresolved symbol, the tool drops that symbol and retries the remaining activities. Other import failures stop that account's import. It still updates cash and processes remaining accounts, but the run **exits 1** so your scheduler flags it. Fix the failing symbol in your mapping file and re-run; duplicate detection will skip already-imported activities.

## Run stops before importing anything

Before any import, the tool reads all existing Ghostfolio activities in one request, because deduplication depends on them. If that list cannot be trusted, the run stops with exit 1 and writes nothing (no import, no cash balance update):

- `Ghostfolio redacted activity values (quantity/comment are null)` — Ghostfolio hides quantities and comments when **Presenter View** (restricted view, the eye icon) is on for the Ghostfolio user the sync signs in as, or when the token lacks the `portfolio:read:values` scope. Without the `IBKR#` comments every trade would look new. Turn Presenter View off, or use a token with full read access, and re-run.
- `Ghostfolio activity at index N has a missing or invalid asset profile symbol` — a BUY, SELL or DIVIDEND is missing a usable `assetProfile` (or legacy `SymbolProfile`). Check the API response and server compatibility; the tool refuses to reconcile against an empty position context.
- `Ghostfolio returned N activities but reports count=M` — the list and its total disagree, usually because an activity was added or deleted in Ghostfolio during the read. Re-run; the next scheduled run recovers on its own.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Every account synced cleanly |
| 1 | Missing or inconsistent configuration (including a missing or invalid mapping file, or both/neither Ghostfolio credential), the Ghostfolio login failed (`GHOST_ACCESS_TOKEN`), the initial activities fetch failed or could not be trusted (redacted values, count mismatch), a Ghostfolio target is repeated, at least one account failed, or an unhandled error occurred |

A run is best-effort: an error on one account is logged and the remaining accounts are still processed, but any failure makes the whole run exit 1. Failures that count include an IBKR Flex Query fetch error, a Flex query without the time-zone suffix or the required dividend fields, a refused cash balance (currency mismatch or no base currency), an unknown trade side, a Ghostfolio account name that does not exist, an import returning 4xx/5xx, a failed cash balance update, and an unexpected error while processing the account (logged with its traceback; the other accounts are still processed).

With [notifications](configuration.md#notifications-apprise) configured, every completed exit-1 run sends one failure summary, including simulation. Required user actions join one summary per completed run until current evidence resolves them. Missing or invalid `TZ` also notifies in simulation. Clean success sends no heartbeat. Delivery never changes the exit code.

Unmapped ISINs are **not** a failure - they are reported at the end of the run as a prompt to update your mapping file, and the run still exits 0. Activities that Ghostfolio itself detects as duplicates are not a failure either. The tool logs `Ghostfolio created X of Y` and counts only submitted rows matched to the server-created activity list as imported. An unknown or unverifiable import outcome fails the account and blocks subsequent imports and processing of later queries targeting that account for the rest of the run.

## Portfolio values are wrong after sync

Run **Gather All Data** in Ghostfolio **Admin** - **Market Data**. This fetches historical prices for all symbols. Without this step, performance charts and current values will be missing or incorrect. You may need to also check that all required currency pairs are present in **Market Data**.

## Negative positions appearing in Ghostfolio

This happens when a sell trade is imported without its corresponding buy. The tool checks each security's net batch quantity against Ghostfolio holdings, and logs an `ERROR` when existing holdings plus new trades would be negative. This guard does not check chronological balances, and cannot repair a pre-existing negative position. Invalid or non-finite trade conversions, including raw commissions, are excluded before the holdings calculation and make the run exit 1. Repeated trade IDs are counted once; conflicting rows sharing an ID are excluded. Buys are submitted before sells, and the sell guard is recomputed from the accepted buys. Only rows matched to the server-created activity list update local holdings; an unknown import outcome blocks subsequent imports to that account in the run. Dry-run simulates proposed buys and cannot predict server duplicate handling. Review conversion errors and compare positions after importing. Typical causes: the buy was recorded on another Ghostfolio account (for example before a broker transfer), or a split was not applied to the old transactions. Fix the position in Ghostfolio; the next run then imports normally.

## IBKR symbol variants (for example CSNKYz vs CSNKY)

IBKR sometimes appends a suffix to symbol names for certain listings. The tool filters by both symbol name and ISIN, so variants of the same security are handled together.

## Token expiry

The IBKR Flex Web Service token expires based on the expiry you set when generating it. Set a calendar reminder before it expires. If the script starts failing with authentication errors, generate a new token in IBKR Account Management.

With `GHOST_ACCESS_TOKEN` the Ghostfolio side needs no renewal: each run logs in afresh. With the legacy `GHOST_TOKEN`, the session token expires: regenerate it using the curl command in the [Ghostfolio Setup](configuration.md#configuration-reference) section and update your container environment variable, or switch to `GHOST_ACCESS_TOKEN`. An expired or invalid token makes the run exit 1 with `ghost_startup: token_rejected`, which is notified when `APPRISE_URLS` is set.

In legacy mode, startup reads the JWT's `exp` claim locally. Within **14 days** of
expiry (including an already expired token), it logs a `WARNING` with the days
remaining and sends an Apprise reminder after the run completes, when configured.
Set `GHOST_TOKEN_EXPIRY_WARNING_DAYS` to an integer from `0` to `365` to change the
window; `0` disables the reminder, and invalid values warn and fall back to `14`.
The reminder alone never fails the sync. Every completed run, including simulation,
sends the configured reminder while renewal remains required. Interrupted runs
send no completion notification. Tokens without a usable numeric
`exp` (including malformed JWTs) skip the check with a fixed debug message. The
payload is not signature-verified and is used only for the reminder: Ghostfolio
still decides whether the token is valid. The token and its other claims are never
included in the reminder. `GHOST_ACCESS_TOKEN` mode skips this check entirely.

## "Ghostfolio login failed: ..."

Only with `GHOST_ACCESS_TOKEN`. The run stops with exit 1 before reading or writing anything. The message is deliberately short and never contains a token:

- `HTTP 403` — Ghostfolio refused the security token: check it (copy/paste, no quotes), or generate a new one.
- `HTTP 3xx` — `GHOST_HOST` redirects (for example `http://` to `https://`, or a missing path); set it to the final URL.
- `HTTP 429` — Ghostfolio throttled the login; it clears by itself, the next run retries.
- `network error` — Ghostfolio is unreachable from the container (network, host name, port).
- `response is not JSON` / `response has no usable authToken` — `GHOST_HOST` does not point at the Ghostfolio API (for example a reverse-proxy page).

## Options trades being skipped

This is intentional. Options (`OPT`) are skipped because Ghostfolio does not support them as an asset class.

## FX conversions being skipped

Also intentional. Trades with assetCategory `CASH` are FX conversion transactions, not investment positions.


[Back to the README](../README.md)
