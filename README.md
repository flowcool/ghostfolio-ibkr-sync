# ghostfolio-ibkr-sync

[![Build and checks](https://github.com/flowcool/ghostfolio-ibkr-sync/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/flowcool/ghostfolio-ibkr-sync/actions/workflows/docker-publish.yml)
[![CodeQL](https://github.com/flowcool/ghostfolio-ibkr-sync/actions/workflows/codeql.yml/badge.svg)](https://github.com/flowcool/ghostfolio-ibkr-sync/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/flowcool/ghostfolio-ibkr-sync)](https://github.com/flowcool/ghostfolio-ibkr-sync/releases)

**Your IBKR trades, dividends and cash balance in self-hosted [Ghostfolio](https://ghostfol.io), on a daily schedule.**

| Import | Reconcile | Run |
| --- | --- | --- |
| Trades, dividend payments and withholding tax | Trade IDs, manual-entry matching and a holdings gate | Docker on amd64 / arm64, or plain Python |
| ISIN → Yahoo Finance ticker mapping | Separate Ghostfolio accounts for IBKR sub-accounts | One-off runs, cron scheduling and a preview with `DRY_RUN=1` |
| | Automatic Ghostfolio login from the security token | Optional failure alerts (ntfy, Telegram, email...) through Apprise |

```mermaid
flowchart LR
    IBKR[IBKR Flex Query] --> XML[Trades, dividends and cash]
    XML --> Mapping[ISIN to Yahoo ticker]
    Ghostfolio[Existing Ghostfolio activities] --> Checks[Deduplication and holdings checks]
    Mapping --> Checks
    Checks --> Preview[Dry-run preview]
    Checks --> Import[Import activities and update cash]
```

[Get started](#get-started) · [Configuration](#configuration) · [Mapping](#mapping-file) · [Troubleshooting](#troubleshooting) · [Limitations](#limitations) · [Contribute](CONTRIBUTING.md)

## Get started

1. Configure [IBKR Flex Web Service and your query](#ibkr-setup), then [create your Ghostfolio account and token](#ghostfolio-setup). Use the same account currency as the IBKR base currency.
2. Copy [`mapping.yaml.example`](mapping.yaml.example) to `mapping.yaml` and review your securities' Yahoo tickers. The mapping file must exist unless you explicitly disable it.
3. Run the [Docker preview](#dry-run-first) with `DRY_RUN=1`. Review ticker mappings, skipped trades and the proposed cash balance before enabling writes.
4. Run [once](#single-account-one-off-run), then configure [scheduled runs](#docker-compose--portainer). After the first import, gather historical market data in Ghostfolio.

**Before importing:** back up Ghostfolio using your deployment's backup procedure. The sync adds activities and updates cash; there is no automatic undo. The first Flex Query covers at most 365 days, so older positions must already be represented in Ghostfolio. Splits and other corporate actions need manual reconciliation. See [Limitations](#limitations).

## Overview

This tool fetches your IBKR activity statements via Flex Queries, parses trades and dividends, maps ISINs to Yahoo Finance tickers, and pushes everything into Ghostfolio. It handles multiple sub-accounts, deduplicates activities, updates cash balances, syncs dividend payments (including withholding tax), and skips FX conversions and options trades. With `GHOST_ACCESS_TOKEN` it logs in to Ghostfolio by itself at every run, so there is no session token to renew, and with `APPRISE_URLS` it sends one alert when a run fails or the legacy session token is about to expire (see [Failure notifications](#failure-notifications-apprise)).

## Why this exists

This fork of [obol89/ghostfolio-ibkr-sync](https://github.com/obol89/ghostfolio-ibkr-sync) parses IBKR XML directly, uses only `requests` and `pyyaml` for the sync itself (Apprise is loaded only by a separate, optional notification worker), and keeps symbol mapping under your control. It is intended for investors operating their own Ghostfolio instance who want repeatable daily imports and visible reconciliation warnings.

## How it works

One run does this, in order:

1. Load the configuration and the symbol mapping. A missing or invalid mapping file stops the run before anything is contacted.
2. Read **all** existing Ghostfolio activities once. Deduplication depends on them, so if the list looks incomplete or redacted the run stops and writes nothing.
3. Then, for each IBKR account in turn (steps 3 to 6): fetch its Flex Query report (two steps: request, then poll until IBKR has generated the statement), find the Ghostfolio account by name (if `GHOST_ACCOUNT_NAMES` is unset, the IBKR account IDs are used as names, with a warning), and parse trades, dividend payments and the cash balance.
4. Decide what is new: skip FX and options; skip trades already in Ghostfolio (`IBKR#<tradeID>` comment) and trades without a trade ID (they cannot be deduplicated); skip dividends already in Ghostfolio (`dividend#...` comment, or any dividend of the same symbol in the same account within ±3 days); skip trades already entered by hand; and check the net quantity against existing holdings. This is a batch-level guard, not chronological position reconciliation.
5. Convert what is left to Ghostfolio activities and import them as a batch per account. If Ghostfolio reports an unresolved symbol, remove that symbol from the batch and retry the rest; the run still exits 1 so the omitted activities remain visible.
6. Set the account's cash balance. This happens even if the import failed; it is skipped, with a warning, only when the report has no base-currency cash row. After all accounts, the run exits `0` if every account was clean and `1` otherwise.

The tool never deletes or edits an existing Ghostfolio activity: it only adds new ones and updates each account's cash balance (and its platform, if `GHOST_PLATFORM_ID` is set and the account has none). Add `DRY_RUN=1` to see the whole decision without any write (see [Dry run first](#dry-run-first)).

Activities are read from `assetProfile` on current Ghostfolio APIs (the legacy
`SymbolProfile` response field was removed in 3.78.0). Legacy-only responses
remain supported for older versions. If both fields are present, `assetProfile`
takes precedence. BUY, SELL and DIVIDEND activities must have a profile with a
nonempty string `symbol`; otherwise the run stops before any import or cash
balance update. ISIN remains optional, as some assets do not have one.

## Docker image

```
ghcr.io/flowcool/ghostfolio-ibkr-sync:latest
```

Multi-arch image (linux/amd64 and linux/arm64). New images are published automatically on every push to main.

Tagged releases (see [Releases](https://github.com/flowcool/ghostfolio-ibkr-sync/releases)) are also published as `:X.Y.Z` and `:X.Y`. Select a full version for controlled upgrades; record the deployed image digest for a reproducible rollback, since container tags are mutable. `:latest` always follows main. CI also refreshes the main image weekly. See [build and release guarantees](.github/BUILD.md).

The running version is logged at container start and at the beginning of every sync:

```
ghostfolio-ibkr-sync version v2.2.0
2026-10-09 06:05:00 [INFO] Starting IBKR to Ghostfolio sync (version v2.2.0)
```

`:latest` reports `vX.Y.Z-N-g<sha>` (N commits after the last release, exact commit `<sha>`).

### Upgrading to 2.2

See the [2.2 upgrade and rollback guide](docs/upgrading-to-2.2.md).

## Prerequisites

- A running self-hosted Ghostfolio instance, version **2.248.0 or newer**
- An Interactive Brokers account with Flex Web Service enabled
- Docker (for containerised runs) or Python 3.12+ with the pinned packages from `requirements.txt` (CI and the container use Python 3.12)

The tool reads existing activities via `GET /api/v1/activities`, which landed in Ghostfolio 2.248.0. The `/api/v1/order` endpoints it replaced were deprecated in that same release and removed in 3.5.0, so on Ghostfolio 3.x this is the only endpoint that works.

## IBKR Setup

Follow the [Flex Web Service and query setup guide](docs/ibkr-setup.md):
enable the service, create one 365-day query per sub-account with the required
trade and cash fields, and obtain its Query ID.

## Ghostfolio Setup

### 1. Choose how the sync authenticates

Set **exactly one** of these two variables (both set, or neither, stops the run with exit 1):

- **`GHOST_ACCESS_TOKEN` (recommended)** — the Ghostfolio *security token* you sign in with
  (shown when the user was created; Ghostfolio can generate a new one). At the start of every
  run, after the configuration and mapping file are validated and before anything is read from
  Ghostfolio or IBKR, the sync exchanges it once for a fresh session token via
  `POST /api/v1/auth/anonymous`. There is nothing to renew by hand. A dry run logs in too
  (logging in writes no financial data). The security token is long-lived: treat it like a
  password, and rotate it in Ghostfolio if it leaks.
- **`GHOST_TOKEN` (legacy)** — a session bearer you obtain yourself; it is used as is and
  **expires**, so you have to regenerate it periodically:

  ```bash
  curl -X POST http://localhost:3333/api/v1/auth/anonymous \
    -H 'Content-Type: application/json' \
    -d '{"accessToken": "YOUR_GHOSTFOLIO_SECURITY_TOKEN"}'
  ```

  The response contains an `authToken` field. Use it as `GHOST_TOKEN`.

With `GHOST_ACCESS_TOKEN`, `GHOST_HOST` must be a plain `http://` or `https://` URL (an
optional path is allowed): user credentials, a query string, a fragment, whitespace or control
characters are refused before any request. The login request does not follow redirects, so point
`GHOST_HOST` at the final Ghostfolio URL. A run never logs in again midway: if the session token
is refused later in the run, that run fails with exit 1 and the next run logs in afresh.

**Plain `http://` is for a trusted network only.** The login request carries the long-lived
security token in its body, so over `http://` anyone who can observe the path can capture it
(the session token of every later request, in either mode, is exposed the same way). Use
`http://` only when the sync reaches Ghostfolio over a private link, such as the internal Docker
network of a shared compose stack (`http://ghostfolio:3333`). When the traffic crosses any other
network, point `GHOST_HOST` at an `https://` URL.

**Switching modes / rollback:** remove one variable and set the other, then recreate the
container. Images released before `GHOST_ACCESS_TOKEN` existed only understand `GHOST_TOKEN`:
when rolling back to one, set `GHOST_TOKEN` again first.

### 2. Create an IBKR Platform

1. Go to Ghostfolio **Admin** - **Platform**
2. Click **Add Platform**
3. Enter a name like `Interactive Brokers` and a URL like `https://www.interactivebrokers.com`
4. Save it

To find the Platform ID, query the API with a session token (the `authToken` returned by the curl command above):

```bash
curl http://localhost:3333/api/v1/platform \
  -H 'Authorization: Bearer YOUR_AUTH_TOKEN'
```

Look for the `id` field of the IBKR platform entry. Use this as `GHOST_PLATFORM_ID`.

### 3. Create accounts

Create one Ghostfolio account per IBKR sub-account:

1. Go to **Accounts** and click **Add Account**
2. Set the name to match what you will use in `GHOST_ACCOUNT_NAMES` (for example `IBKR Individual` or `IBKR Joint`)
3. Select the IBKR platform you created
4. Set the currency to match the sub-account base currency
5. Repeat for each sub-account

### 4. Add currencies

If your IBKR trades involve currencies that are not yet in Ghostfolio:

1. Go to **Admin** - **Market Data**
2. Search for and add any missing currency pairs (for example `USDEUR`, `USDGBP`, `USDCHF`)
3. Ghostfolio needs these to convert values to your base currency

### 5. After your first import

After the first sync, go to **Admin** - **Market Data** and click **Gather All Data**. This fetches historical prices from Yahoo Finance for all newly imported symbols. Without this step, portfolio values and performance charts will be incorrect. Run it again after adding symbols from a new import.

## Configuration

All configuration is done via environment variables:

| Variable | Required | Description | Example |
|---|---|---|---|
| `IBKR_TOKEN` | Yes | IBKR Flex Web Service token | `1234567890abcdef` |
| `IBKR_ACCOUNT_IDS` | Yes | Comma-separated IBKR account IDs | `U1234567` |
| `IBKR_QUERY_IDS` | Yes | Comma-separated Flex Query IDs (one per account) | `123456` |
| `GHOST_ACCESS_TOKEN` | One of these two | Ghostfolio security token, exchanged for a session token at the start of each run (recommended; see [Ghostfolio Setup](#1-choose-how-the-sync-authenticates)) | `a1b2c3...` |
| `GHOST_TOKEN` | One of these two | Ghostfolio session bearer token, used as is (legacy; expires) | `eyJhbGciOi...` |
| `GHOST_TOKEN_EXPIRY_WARNING_DAYS` | No | Legacy token reminder window, integer 0-365 days (default `14`; `0` disables). Invalid values warn and use `14`. Ignored with `GHOST_ACCESS_TOKEN` | `14` |
| `GHOST_HOST` | Yes | Ghostfolio base URL | `http://ghostfolio:3333` |
| `GHOST_CURRENCY` | No | Legacy setting, currently unused; it does not override or convert currencies | `EUR` |
| `GHOST_PLATFORM_ID` | No | Platform ID for IBKR in Ghostfolio | `abc123-def456` |
| `GHOST_ACCOUNT_NAMES` | No | Comma-separated Ghostfolio account names (must match account count) | `IBKR Individual` |
| `MAPPING_FILE` | No | Path to symbol mapping YAML (default: `mapping.yaml`). The run stops (exit 1) if the file is missing or invalid; set it to an empty value (`MAPPING_FILE=""`) to run without mappings on purpose | `/app/mapping.yaml` |
| `CRON` | No | Five numeric cron fields for recurring runs (Docker only); validated before startup | `0 6 * * *` |
| `TZ` | No | Timezone for cron scheduling | `Europe/Warsaw` |
| `LOG_LEVEL` | No | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`) | `DEBUG` |
| `APPRISE_URLS` | No | JSON list of [Apprise](https://github.com/caronc/apprise/wiki) URLs for failures and legacy token expiry reminders (blank or `[]` = off); see [Failure notifications](#failure-notifications-apprise) | `["ntfys://ntfy.sh/my-topic"]` |
| `APPRISE_TIMEOUT` | No | Seconds allowed for one notification, integer 1-30 (default `10`) | `10` |
| `DRY_RUN` | No | If truthy (`1`/`true`/`yes`/`on`), runs the full pipeline (fetch, convert, dedup) and logs the activities and cash balance it *would* write, without financial writes to Ghostfolio; token exchange still occurs with `GHOST_ACCESS_TOKEN` | `1` |

## Mapping File

The mapping file maps ISINs to Yahoo Finance ticker symbols. This is necessary because IBKR identifies securities by ISIN while Ghostfolio uses Yahoo Finance tickers for price data.

### Format

Use a `symbol_mapping` key at the top level (a missing or empty key is treated as an empty mapping with a warning):

```yaml
symbol_mapping:
  IE00B52MJD48: EIMI.L        # iShares MSCI EM IMI - London
  DE0002635307: EXSA.DE       # iShares STOXX Europe 600 - Frankfurt
  IE00B4L5Y983: IWDA.AS       # iShares Core MSCI World - Amsterdam
  CH0110869143: CHSPI.SW      # iShares Core SPI - Swiss Exchange
```

### Which symbols need mapping

US-listed securities (VOO, QQQ, NVDA, AAPL, etc.) are recognised by Yahoo Finance using the IBKR symbol directly, so they do not need an explicit mapping.

European ETFs and stocks require mapping because Yahoo Finance uses exchange suffixes that differ from IBKR symbols:

| Exchange | Suffix | Example |
|---|---|---|
| London Stock Exchange | `.L` | `EIMI.L` |
| Frankfurt / Xetra | `.DE` | `EXSA.DE` |
| Amsterdam | `.AS` | `IWDA.AS` |
| SIX Swiss Exchange | `.SW` | `CHSPI.SW` |

### Finding Yahoo Finance tickers

1. Go to [finance.yahoo.com](https://finance.yahoo.com)
2. Search for the security by name or ISIN
3. Use the ticker shown on the Yahoo Finance page, including the exchange suffix

### Unmapped ISINs

When the script encounters an ISIN not in the mapping file, it falls back to the IBKR symbol and **attempts to import the activity**. If Ghostfolio cannot resolve that ticker, the tool drops its activities, imports the remaining activities if any remain, and exits 1. At the end of the run it logs one self-contained warning per ISIN:

```
[WARNING] Unmapped ISIN JP3637000005 (TRINITY INDUSTRIAL CORP) uses IBKR symbol '6382.T' as ticker (fallback) — verify in Ghostfolio or add to mapping symbol_mapping: 'JP3637000005: <yahoo ticker>'
```

If the fallback ticker is wrong for Yahoo Finance, add the ISIN to your mapping file with the correct ticker. Trades are reported only on the run that imports them; dividends on the fallback are reported on every run.

## What the tool skips automatically

- **FX conversion trades** - trades with assetCategory `CASH` are currency conversions, not investment positions
- **Options trades** - trades with assetCategory `OPT` are skipped (Ghostfolio does not support options)
- **Sells that would make a position negative** - the Flex Query only covers 365 days, so a sell of a position bought earlier arrives without its buy. For each security (per Ghostfolio account, by the ticker it will be imported under), the tool adds the quantity Ghostfolio already holds to the net quantity of IBKR trades not yet imported. If the result is zero or more, the candidates pass the first check. Buys and dividends are submitted first; sells are checked again using only newly created buys confirmed by the server response. If it would go negative, that security is refused by the initial check. If the second check fails, successful buys from the first phase remain and the sells are skipped.
- **Sells you already entered by hand** - an IBKR sell is treated as already recorded when Ghostfolio has a manual sell (no `IBKR#` comment) of the same quantity within ±2 days, under any symbol sharing the ISIN. Several IBKR fills of one day are also matched against a single manual entry by their sum. When a manual sell is nearby but the quantity does not match, the sell is not imported and a warning asks you to check by hand.
- **Buys you already entered by hand** - the same rule applies to buys (manual buy without `IBKR#` comment, same quantity, ±2 days, any symbol sharing the ISIN, fills matched by their sum). Unlike sells, a skipped buy is **always** reported as a `WARNING` naming the trade ID and the manual entry, because skipping it silently would hide a missing purchase. To silence the warning, put `IBKR#<tradeID>` in that manual entry's comment: the trade is then recognised by ID. If the match is a coincidence (a different purchase with the same quantity within 2 days), or a nearby manual buy has another quantity, the IBKR buy stays skipped (and warned about on every run) until you add it by hand or fix the manual entry. This is deliberate: a visible gap is safer than a silent duplicate.
- **Positions held under another symbol** - if Ghostfolio holds the security under a different symbol with the same ISIN (for example a manual entry on another listing), the sell is not imported and a warning gives the mapping line that fixes it.
- **Dividend reversals and orphan tax corrections** - dividend and withholding rows of the same security and day are summed; a net zero (reversed payment) is skipped, and a withholding tax row without a dividend that day is not imported and logged as a `WARNING` to check by hand.
- **Duplicate activities** - the tool checks existing Ghostfolio activities before importing and skips anything already present.

### Log levels

A clean, fully reconciled run normally emits only `INFO` lines. `WARNING` means *check this*, `ERROR` means *data is not in sync and needs action*:

| Level | Meaning |
|---|---|
| `DEBUG` | FX/options skipped, each sell not imported because already reconciled |
| `INFO` | Sells imported for long-held positions; one summary line of sells not imported (already entered manually, or no Ghostfolio position) |
| `WARNING` | Unmapped ISIN on symbol fallback; position held under another symbol; manual sell or buy nearby with another quantity; buy skipped because it matches a manual buy; withholding tax without a dividend the same day; network retry |
| `ERROR` | Ghostfolio holds some quantity but the IBKR sells exceed it — fix the position in Ghostfolio; IBKR/Ghostfolio request failures; run aborted before any write (see [Run stops before importing anything](docs/troubleshooting.md#run-stops-before-importing-anything)) |

## How activities are converted

| Source (IBKR) | Ghostfolio activity |
|---|---|
| Trade | `BUY` when IBKR says `BUY`, otherwise `SELL`. Quantity and price are absolute values. The comment is `IBKR#<tradeID>`, the data source is always `YAHOO`. |
| Commission | `fee` = the commission cost. A positive `ibCommission` (a rebate) is recorded as a fee of 0 and logged as a `WARNING`, because Ghostfolio fees cannot be negative. |
| Dividend | One `DIVIDEND` per security and day: dividends and payments in lieu are summed (a reversal nets out), withholding tax becomes the `fee`. A net refund of tax is recorded as a fee of 0 with a `WARNING`. The comment is `dividend#<ISIN>#<date>` (or the IBKR symbol when there is no ISIN) and the date is the date of the cash transaction at 00:00 UTC. A dividend is treated as already present if Ghostfolio has that comment, **or any dividend of the same symbol in the same account within ±3 days** (so a real dividend that falls that close to a manual one is not imported). |
| Dividend quantity and price | Read from the description (`... USD 0.25 PER SHARE ...`): quantity = amount ÷ rate, rounded to whole shares when within 1 %, price derived so that quantity × price equals the payment. Without such a rate the whole amount is booked as one unit. |
| Date and time | IBKR timestamps are treated as UTC. A manual entry made in local time can differ by a day, which is why the manual-entry matching accepts ±2 days. |
| Currency | The trade or dividend currency, except on markets where Yahoo quotes the minor unit (below). |

**Minor-unit markets.** Yahoo Finance quotes some exchanges in the minor unit (pence, cents) while IBKR reports the major unit. For these the price **and** the fee (or withholding tax) are multiplied by 100 and the currency is changed so that amounts stay correct:

| Yahoo suffix | IBKR currency | Sent to Ghostfolio as | Status |
|---|---|---|---|
| `.L` (London) | GBP | GBp | verified on real trades |
| `.JO` (Johannesburg) | ZAR | ZAc | inferred, not verified |
| `.TA` (Tel Aviv) | ILS | ILA | inferred, not verified |

If you trade on `.JO` or `.TA` and amounts look 100 times off, check this table first.

## Running

### Single account (one-off run)

```bash
docker run --rm --network your-ghostfolio-network \
  -e IBKR_TOKEN=your_token \
  -e IBKR_ACCOUNT_IDS=U1234567 \
  -e IBKR_QUERY_IDS=123456 \
  -e GHOST_ACCESS_TOKEN=your_ghost_security_token \
  -e GHOST_HOST=http://ghostfolio:3333 \
  -e GHOST_ACCOUNT_NAMES="IBKR Main" \
  -v "$(pwd)/mapping.yaml:/app/mapping.yaml:ro" \
  ghcr.io/flowcool/ghostfolio-ibkr-sync:latest
```

### Without Docker

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp mapping.yaml.example mapping.yaml  # edit the copied mappings for your securities
export IBKR_TOKEN=your_token
export IBKR_ACCOUNT_IDS=U1234567
export IBKR_QUERY_IDS=123456
export GHOST_ACCESS_TOKEN=your_ghost_security_token
export GHOST_HOST=http://localhost:3333
export GHOST_ACCOUNT_NAMES="IBKR Main"
.venv/bin/python ibkr_to_ghostfolio.py
```

### Dry run first

Add `DRY_RUN=1` to try a configuration safely. The full pipeline runs (fetch, convert, deduplicate, gate) and the activities and cash balance that *would* be written are logged, but no activities are imported and no cash balance is updated. With `GHOST_ACCESS_TOKEN`, the authentication POST still exchanges the security token for a session token. IBKR report generation is requested and existing Ghostfolio data is read. This preview does not validate symbols through the Ghostfolio import endpoint, so a successful preview does not guarantee a successful import. Logs include financial activity details; keep them private.

```bash
docker run --rm --network your-ghostfolio-network -e DRY_RUN=1 -e LOG_LEVEL=DEBUG \
  -e IBKR_TOKEN=your_token -e IBKR_ACCOUNT_IDS=U1234567 -e IBKR_QUERY_IDS=123456 \
  -e GHOST_ACCESS_TOKEN=your_ghost_security_token -e GHOST_HOST=http://ghostfolio:3333 \
  -e GHOST_ACCOUNT_NAMES="IBKR Main" \
  -v "$(pwd)/mapping.yaml:/app/mapping.yaml:ro" \
  ghcr.io/flowcool/ghostfolio-ibkr-sync:latest
```

Look for lines starting with `[DRY RUN]`; when there is nothing to import the log simply says `No new activities to import`. Replace `your-ghostfolio-network` with the Docker network shared with Ghostfolio. Run it again after upgrading to a new version: comparing the log with the previous version's shows exactly what the new version changes.

## Failure notifications (Apprise)

Optional. When `APPRISE_URLS` is set, a run that **completes with exit 1** sends one
notification through [Apprise](https://github.com/caronc/apprise/wiki), which supports
ntfy, Gotify, Telegram, Discord, Slack, email and many more. A completed successful run
also sends a reminder when its legacy `GHOST_TOKEN` is about to expire (see
[Token expiry](docs/troubleshooting.md#token-expiry)); the reminder keeps exit 0. Give it a JSON list (up to 10
URLs, each up to 2048 characters; put one URL per entry, as an entry holding several
space- or comma-separated URLs counts each one toward the limit of 10):

```yaml
      APPRISE_URLS: '["ntfys://ntfy.sh/my-private-topic", "tgram://BOT_TOKEN/CHAT_ID"]'
      APPRISE_TIMEOUT: "10"
```

**What is sent:** a fixed title, the UTC time, how many accounts failed out of how many, and
one line per failure with a fixed stage and reason code (for example
`account: account_failed (account #2)`, where `#2` is the position in `IBKR_ACCOUNT_IDS`).
Never error messages, account IDs or names, symbols, amounts, URLs or tokens: read the
container log for details. Up to 20 failure lines, then `and N more`.
`ghost_startup: token_rejected` means Ghostfolio refused the token (HTTP 401/403): with the
legacy `GHOST_TOKEN` this is how an expired session token shows up (see
[Token expiry](docs/troubleshooting.md#token-expiry)).

Expiry reminders use the fixed code `ghost_auth: token_expiring` and a rounded-up count
of days remaining (`0` means expired). If the run also fails, the reminder is included
in the same failure notification. At most one notification is sent per completed run;
there is no daily state, so multiple runs in one day can repeat the reminder.

**When nothing is sent:** successful runs without an expiry reminder, runs that only
logged other warnings (for example unmapped ISINs), dry runs (`DRY_RUN` is honoured even when the rest of the configuration is
invalid), runs stopped by a signal, and when `APPRISE_URLS` is blank or `[]`. If
`APPRISE_URLS` or `APPRISE_TIMEOUT` is invalid, the run logs
`APPRISE_URLS or APPRISE_TIMEOUT is invalid: failure notifications disabled` and syncs as usual.

**Delivery:** Apprise runs in a separate short-lived worker process with only network
settings in its environment (`PATH`, locale, CA bundle and proxy variables; never the IBKR or
Ghostfolio credentials), the URLs passed on its standard input, and its output discarded, so a
misbehaving plugin cannot print your destination credentials into the log. One deadline,
`APPRISE_TIMEOUT`, covers the whole worker (Python start, Apprise import, sending, exit); a
worker still running at the deadline is killed. This adds at most `APPRISE_TIMEOUT` seconds,
plus Apprise's import time inside it, to a notifying run. There is **no retry**: after a timeout
the notification may or may not have arrived (`Failure notification timed out (it may still
arrive; not retried)`). Delivery problems (`timeout`, `failed`, `invalid_destination`,
`unavailable` when Apprise cannot be imported, `payload_too_large`, `spawn_failed`, which
includes a script piped on standard input as in `python - < ibkr_to_ghostfolio.py`) are logged as warnings
and never change the run's exit code. Apprise and its pinned dependencies ship in the image
and are only imported by the worker.

**Rollback:** remove `APPRISE_URLS` (or set it to `[]`) and recreate the container; the sync
behaves exactly as without the feature. Older images ignore the variable.

## Docker Compose / Portainer

For scheduled runs with multiple sub-accounts, run a separate container per account with staggered cron times. The `CRON` environment variable uses [supercronic](https://github.com/aptible/supercronic) internally.

Use exactly five fields separated by a single space or tab, containing only
digits and `*`, `/`, `,`, `-` (for example `0 6 * * *` or `*/15 * * * *`).
Named days/months, macros such as `@daily`, seconds fields and embedded commands
are rejected. The entrypoint checks the grammar, then runs `supercronic -test`
before starting the scheduler. Invalid schedules exit 1 with a fixed diagnostic;
the supplied value and validator output are not logged. An unset or empty `CRON`
still runs the sync once immediately.

```yaml
services:
  ibkr-sync-individual:
    image: ghcr.io/flowcool/ghostfolio-ibkr-sync:latest
    restart: unless-stopped
    read_only: true
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=16m,mode=1777
    environment:
      TZ: Europe/Warsaw
      IBKR_TOKEN: ${IBKR_TOKEN:?Set IBKR_TOKEN}
      IBKR_ACCOUNT_IDS: U1234567
      IBKR_QUERY_IDS: 123456
      GHOST_ACCESS_TOKEN: ${GHOST_ACCESS_TOKEN:?Set GHOST_ACCESS_TOKEN}
      GHOST_HOST: http://ghostfolio:3333
      GHOST_ACCOUNT_NAMES: "IBKR Individual"
      MAPPING_FILE: /app/mapping.yaml
      CRON: "0 6 * * *"
      # Optional: one alert per failed run (see Failure notifications)
      # APPRISE_URLS: '["ntfys://ntfy.sh/my-private-topic"]'
    volumes:
      - ./mapping.yaml:/app/mapping.yaml:ro
    networks:
      - ghostfolio

  ibkr-sync-joint:
    image: ghcr.io/flowcool/ghostfolio-ibkr-sync:latest
    container_name: ghostfolio-ibkr-sync-joint
    restart: unless-stopped
    read_only: true
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=16m,mode=1777
    environment:
      TZ: Europe/Warsaw
      IBKR_TOKEN: ${IBKR_TOKEN:?Set IBKR_TOKEN}
      IBKR_ACCOUNT_IDS: U7654321
      IBKR_QUERY_IDS: 654321
      GHOST_ACCESS_TOKEN: ${GHOST_ACCESS_TOKEN:?Set GHOST_ACCESS_TOKEN}
      GHOST_HOST: http://ghostfolio:3333
      GHOST_ACCOUNT_NAMES: "IBKR Joint"
      MAPPING_FILE: /app/mapping.yaml
      CRON: "5 6 * * *"
    volumes:
      - ./mapping.yaml:/app/mapping.yaml:ro
    networks:
      - ghostfolio

networks:
  ghostfolio:
    external: true
```

Use `http://ghostfolio:3333` (internal Docker network hostname) rather than an external IP or localhost. Stagger the cron times by a few minutes so the two containers do not run simultaneously.

Supply `IBKR_TOKEN` and `GHOST_ACCESS_TOKEN` through the environment used by
Compose, a private `.env` file beside the Compose file, or Portainer stack
environment variables. Do not put real credentials into the YAML. For a local
`.env`, restrict permissions to its owner (`chmod 600 .env`) and keep it out of
version control and shared backups/artifacts. Required-value interpolation
refuses startup configuration when either credential is missing or empty.
`docker compose config` can print resolved secrets: prefer `config --quiet`
for validation and never share resolved output. Environment values are not a
secret vault; administrators with Docker access can inspect them.
Both services share these variables when their credentials are the same. If
they differ, use separate required variables per service, for example
`IBKR_TOKEN: ${IBKR_TOKEN_JOINT:?Set IBKR_TOKEN_JOINT}` and
`GHOST_ACCESS_TOKEN: ${GHOST_ACCESS_TOKEN_JOINT:?Set GHOST_ACCESS_TOKEN_JOINT}`
for the joint account, and supply those values through the same private sources.

This example uses the recommended access-token mode. For legacy session-token
mode, replace the `GHOST_ACCESS_TOKEN` line in **both** services with
`GHOST_TOKEN: ${GHOST_TOKEN:?Set GHOST_TOKEN}` and do not set both modes.

The read-only root keeps application code immutable. The private runtime
crontab is generated under `/tmp`; its 16 MiB tmpfs is writable, non-executable
and ephemeral. The sync itself does not write persistent files. Optional
notification plugins may have their own storage requirements; verify your
configured notifier before adopting a read-only root filesystem.
Use a **published** image containing the `/tmp` crontab change: older images
writing `/app/crontab` cannot run this hardened example. Merging the runtime
change is not enough: wait for its image publication workflow to succeed, then
pull and recreate the container. `:latest` remains the example's choice and
follows `main`; operators may instead select an available full version or a
recorded digest for controlled upgrades. No deployment is changed automatically.

This is a standalone sync stack for an existing Ghostfolio instance. Replace the credentials, account names and network name before deploying. In Portainer, use an absolute host path for `mapping.yaml`. Create that file first and make it readable by the non-root container user (for a non-secret mapping file, `chmod o+r mapping.yaml` is one option). The mount is read-only. A scheduled container waits for its first cron tick; remove `CRON` for an immediate one-off run. A separate stack does not wait for Ghostfolio readiness.

## Troubleshooting

See the [troubleshooting guide](docs/troubleshooting.md) for exit codes,
import failures, missing positions, token expiry and login diagnostics.
For interrupted operator maintenance, use the [cleanup recovery guide](docs/cleanup.md).

## Limitations

- **Flex XML size** - each SendRequest or GetStatement response is limited to
  10 MiB (10,485,760 response-body bytes) before XML parsing. Larger responses
  fail with `IBKR Flex response exceeds XML size limit`; no financial writes
  are made for that query. The limit includes the exact boundary and measures
  the body after HTTP decompression, not a Content-Length header. This is a
  parsing guard, not a streaming download or total-memory limit: `requests`
  still buffers the response before the check. Keep the 365-day recovery
  window; review unnecessary Flex fields/sections rather than shortening it
  just to fit the limit.
- **No options support** - Ghostfolio does not support options as an asset class; options trades are skipped entirely
- **365-day window** - IBKR Flex Query maximum period is 365 days. On the first run, trades older than that are not imported: enter older buys by hand (or keep them from a previous tool). Afterwards the daily sync accumulates history in Ghostfolio, and later sells of those positions are imported as long as Ghostfolio holds the buy.
- **Yahoo Finance data quality** - price data can have gaps, delays, or missing metadata (sector, country) for non-US ETFs and smaller listings
- **Stock splits and other corporate actions are not handled** - Ghostfolio keeps your transactions as they were, while Yahoo returns split-adjusted prices, so a split makes the valuation wrong until the old transactions are corrected by hand (multiply the quantity and divide the unit price by the ratio, and fix the stored market data). The Corporate Actions section of Flex reports is not parsed; it does not create split or merger activities.
- **Cash balance is a single base-currency figure** - the balance written to each Ghostfolio account is IBKR's total ending cash in the account's base currency, with no conversion. Give the Ghostfolio account the same currency as the IBKR base currency (see [Create accounts](#3-create-accounts)).
- **Daily data only** - Activity Statements update once daily after market close; intraday syncing is not possible
- **Token management** - the IBKR Flex token expires and requires manual renewal: set a recurring calendar reminder (up to 1 year). On the Ghostfolio side, `GHOST_ACCESS_TOKEN` logs in on every run; only the legacy `GHOST_TOKEN` needs manual renewal.
- **Account-scoped queries** - use a separate Flex Query per sub-account. Several account/query pairs can run sequentially in one container; separate containers are recommended for operational isolation.
- **Additive imports** - later IBKR corrections to already-imported trades or same-date dividends are not reconciled. Dividend proximity matching can suppress distinct payments within ±3 days; check unusual payment schedules and tax corrections manually.
- **Commission currency** - commissions are booked in the activity currency; a different IBKR commission currency is not converted.
- **Cleanup is not transactional** - cleanup requires complete financial evidence, equal fees, a unique one-to-one pair and unchanged fresh copies of both rows. Draft or excluded candidates are refused. PUT can succeed while DELETE fails; stop and inspect both rows and the safety log before any recovery. A new apply writes a private YAML journal with exact preimages and known/unknown outcomes. Explicit journal recovery can finish an unchanged pair; it does not recreate deleted activities or repair changed records.
- **Active position context** - drafts and excluded activities/accounts retain their import identifiers for deduplication, but cannot contribute holdings, manual matches or dividend proximity evidence. Holdings and manual reconciliation use active YAHOO profiles; other sources cannot back YAHOO sells. Excluded target accounts are refused. Future timestamps are deferred with exit 1 until a later run; this conservative instant check avoids server-local draft assignment even when import responses omit tags. Accepted imports use the actual server profile symbol; a canonicalized symbol can require an explicit mapping before sells under the original ticker are allowed.
- **Batch guard limitations** - the gate checks net quantity, not chronological balances. Buy and sell phases are separate requests, so successful buys can remain if sells fail. A dry-run previews candidates without verifying server acceptance.
- **No overlap protection** - avoid concurrent sync runs targeting the same Ghostfolio account; deduplication is based on a snapshot read at startup.

## Inspecting an interrupted cleanup

The [cleanup and recovery guide](docs/cleanup.md) explains separately authorized
maintenance, private journals, read-only inspection and guarded resume.
Cleanup is not part of the additive sync; review its safety requirements first.

## Development

The sync is a single file, `ibkr_to_ghostfolio.py`, with `requests` and `pyyaml` as its only runtime dependencies; `apprise` (with a pinned dependency closure in `requirements.txt`) is imported only by the notification worker (`--notify-worker`). Tests are offline (no network, no Ghostfolio, no IBKR): they exercise the pure decision logic with mocked HTTP.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # pytest stays out of the Docker image
.venv/bin/python -m pytest -q
```

CI runs tests, an audit of the complete Python CI environment and Docker builds/scans for amd64 and arm64 on every pull request to `main`, including documentation-only changes. Required checks must pass before merging; PR builds never publish images. CodeQL analyzes Python separately. See [.github/BUILD.md](.github/BUILD.md) for publication rules, weekly maintenance and rollback. A change to the sync logic should come with a test; use synthetic fixtures and mocked HTTP for regression checks. See [Contributing](CONTRIBUTING.md) for review and reporting guidance.

Every runtime dependency is pinned. A daily workflow ([`dependency-release-watch.yml`](.github/workflows/dependency-release-watch.yml)) opens one `dependency-release` issue per new stable release of a pin (`requirements.txt` from PyPI, supercronic from GitHub): read the release notes, bump the pin in a PR if needed, then close the issue. Dependabot waits 14 days before proposing a pip update, except for security fixes.

## Credits and license

Forked from [obol89/ghostfolio-ibkr-sync](https://github.com/obol89/ghostfolio-ibkr-sync), with thanks to its contributors. See [LICENSE](LICENSE) for the inherited **MIT NON-AI License**, including its additional restrictions.
