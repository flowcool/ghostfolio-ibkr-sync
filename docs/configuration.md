# Configuration and operations

This guide contains the complete environment reference, mapping rules, runtime behavior, and Docker Compose example. Start with the [README quick start](../README.md#quick-start), then return here for the detailed settings.



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


## Configuration reference

All configuration is done via environment variables:

| Variable | Required | Explanation | Example | Default when unset |
| --- | --- | --- | --- | --- |
| `IBKR_TOKEN` | Yes | IBKR Flex Web Service token. | `replace-with-your-ibkr-flex-token` | None; startup fails |
| `IBKR_ACCOUNT_IDS` | Yes | Comma-separated IBKR account IDs. | `U1234567,U7654321` | None; startup fails |
| `IBKR_QUERY_IDS` | Yes | Comma-separated Flex Query IDs, one per account. | `123456,654321` | None; startup fails |
| `GHOST_ACCESS_TOKEN` | One of these two | Recommended Ghostfolio security token, exchanged for a session token at each run. | `replace-with-your-ghostfolio-security-token` | None; one token mode is required |
| `GHOST_TOKEN` | One of these two | Legacy Ghostfolio session bearer token. | `replace-with-your-session-token` | None; one token mode is required |
| `GHOST_TOKEN_EXPIRY_WARNING_DAYS` | No | Legacy token reminder window. `0` disables the reminder. | `14` | `14` |
| `GHOST_HOST` | Yes | Ghostfolio base URL. | `http://ghostfolio:3333` | None; startup fails |
| `GHOST_PLATFORM_ID` | No | Ghostfolio platform ID used when an account has no platform. | `replace-with-platform-id` | Empty; platform update skipped |
| `GHOST_ACCOUNT_NAMES` | No | Comma-separated Ghostfolio account names, in IBKR account order. | `IBKR Individual,IBKR Joint` | IBKR account IDs |
| `MAPPING_FILE` | No | ISIN-to-Yahoo ticker mapping YAML path. | `/app/mapping.yaml` | `mapping.yaml` |
| `CORPORATE_ACTION_STATE_FILE` | For BUY/SELL | Private persistent state, initialized in simulation. | `/state/corporate-actions.yaml` | Missing: trade hold and exit 1 |
| `CORPORATE_ACTION_EVIDENCE_FILE` | No | Private official effective-date document bindings. | `/state/effective-dates.yaml` | Dates remain unproven |
| `ACTIVITY_REVIEW_FILE` | No | Persistent activity review YAML path. | `/review/activities.yaml` | Empty; review disabled |
| `CRON` | No | Five-field Docker schedule. | `0 6 * * *` | Empty; one immediate run |
| `TZ` | For writes | Valid IANA timezone for dividend dates and scheduling. | `Europe/Paris` | Empty; writes force simulation |
| `LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, or `ERROR`. | `INFO` | `INFO` |
| `APPRISE_URLS` | No | JSON list of Apprise notification URLs. | `[]` | Empty; notifications disabled |
| `APPRISE_TIMEOUT` | No | Notification timeout in seconds, from 1 to 30. | `10` | `10` |
| `DRY_RUN` | No | Simulation mode. Only `false`, `0`, `no`, or `off` request writes. | `true` | Simulation |


## Mapping and reconciliation

The mapping file maps ISINs to Yahoo Finance ticker symbols. It does not learn new mappings or rewrite itself. IBKR identifies securities by ISIN while Ghostfolio uses Yahoo Finance tickers for price data, so European listings often need a reviewed entry.

Reconciliation is a separate runtime step. The connector uses source identities, existing activities, same-ISIN manual-entry matching, proximity rules, and a holdings gate before it selects imports. An unresolved ticker produces a warning or a failed activity subset; it does not silently create a mapping. Optional `ACTIVITY_REVIEW_FILE` can generate exact or probable one-to-one correction proposals, but a correction requires an explicit approval and qualified readback.

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

Lab acceptance needs `LOG_LEVEL=DEBUG` for native `LAB_EVIDENCE` window, preview and cash records.

A clean, fully reconciled run normally emits only `INFO` lines. `WARNING` means *check this*, `ERROR` means *data is not in sync and needs action*:

| Level | Meaning |
|---|---|
| `DEBUG` | FX/options skipped, each sell not imported because already reconciled |
| `INFO` | Sells imported for long-held positions; one summary line of sells not imported (already entered manually, or no Ghostfolio position) |
| `WARNING` | Unmapped ISIN on symbol fallback; position held under another symbol; manual sell or buy nearby with another quantity; buy skipped because it matches a manual buy; withholding tax without a dividend the same day; network retry |
| `ERROR` | Ghostfolio holds some quantity but the IBKR sells exceed it — fix the position in Ghostfolio; IBKR/Ghostfolio request failures; account failed before any write because a Flex prerequisite is missing (time-zone suffix, dividend fields); cash balance refused (currency mismatch or no base currency); trade rejected (unknown `buySell`); run aborted before any write (see [Run stops before importing anything](troubleshooting.md#run-stops-before-importing-anything)) |

## How activities are converted

| Source (IBKR) | Ghostfolio activity |
|---|---|
| Trade | `BUY` when IBKR says `BUY`, `SELL` when IBKR says `SELL`. Any other value (for example a cancellation) rejects the row: an error is logged, the account run is not ok and the other trades import normally. The row is never imported, so every run fails while it stays inside the 365-day report window. Quantity and price are absolute values. The comment is `IBKR#v2#<source-account>:TRADE:<tradeID>`, the data source is always `YAHOO`. |
| Commission | `fee` = the commission cost. A positive `ibCommission` (a rebate) is recorded as a fee of 0 and logged as a `WARNING`, because Ghostfolio fees cannot be negative. |
| Dividend | One `DIVIDEND` per source account and positive cash action (`actionID`). Dividend and payment-in-lieu portions of the same action share one quantity. Distinct ordinary/bonus actions produce separate activities and can have different quantities. The comment is `IBKR#v2#<source-account>:DIVIDEND:<actionID>`. The date is the cash payment day at 00:00 UTC. Historical security/day comments still win before action selection. Complete v2 coverage skips the group; partial coverage fails the account without filling missing actions. Otherwise, a manual or legacy dividend of the same symbol and destination account within ±3 days can suppress the group. Existing activities remain untouched. |
| Dividend quantity and price | Each net-positive cash action matches accruals by nonempty `accountId`, `conid`, `currency`, `actionID` and `exDate`. It needs exactly one `Re` with `payDate` on the cash day and `date` or `reportDate` on that day. All associated quantities must agree as positive finite decimals. Dividend/PIL portions of one action share one common quantity; distinct actions retain their own quantities; quantities are never summed or rounded. Price = cash gross ÷ quantity, regardless of accrual gross, tax or rate. Zero-net actions provide no quantity; negative-net actions, mixed currencies and conflicting evidence reject the group. Quantity and price must remain positive finite numbers, and fees nonnegative finite, after conversion and minor-unit scaling; overflow or positive underflow rejects the group. |
| Dividend withholding | Each tax/refund row must match one payment action by nonempty source account, action ID, contract, currency and payment day. Tax ex-date may be absent or empty; a nonempty ex-date must match. No amount ratio or description assigns tax. Cash totals are conserved before each action’s signed tax is summed and a net refund is clamped to fee 0 with a warning. Opposite signed taxes on different actions can produce a different fee total from the former group clamp. Missing, conflicting or negative-net action evidence rejects the whole group and fails the account. Trades, safe sales, cash and later accounts continue. Withholding-only groups stay not payable. A zero-net action creates no activity; any remaining signed tax is logged with its action and amount for manual review. |
| Date and time | IBKR timestamps are treated as UTC. A manual entry made in local time can differ by a day, which is why the manual-entry matching accepts ±2 days. |
| Currency | The trade or dividend currency, except on markets where Yahoo quotes the minor unit (below). |

New trade identities use the verified IBKR source account, not the Ghostfolio account name or UUID. Every selected trade (excluding CASH/OPT) must have `accountId` equal to the report's Account Information account and the configured source account. Select **ClientAccountID** and **TradeID** in Trades (Execution). A missing or mismatched account, unsafe identity segment or oversized comment fails that account before any activity, cash or platform write, even if the trade is already stored.

The shared v2 formats are `IBKR#v2#<source-account>:TRADE:<tradeID>` and `IBKR#v2#<source-account>:DIVIDEND:<actionID>`. Account and event segments accept only ASCII letters, digits, `.`, `_` and `-`. The full comment must contain at most 2000 ASCII characters. The writer does not trim, escape, hash, truncate or use a legacy fallback. Historical reader acceptance stays unchanged. New eligible trades and dividend actions use these v2 formats. [Source and isolated-image qualification](releasing.md#v2-writer-qualification-and-release-order) remain required before enabling writes. Synthetic tests do not prove vendor ID stability or deployed image behavior. After any v2 row exists, rollback must retain the rc.5 reader or a newer qualified dual reader.

New dividend payment rows must have a source `accountId` that matches the verified report account. Missing or unsafe account/action segments, or oversized comments, fail the account before any financial write. Every action in a security/day group must pass validation before any dividend from that group is sent. Import batches can accept a subset; partial coverage requires separately approved recovery. Enrich the complete Cash Transactions and Change in Dividend Accruals sections as described in [IBKR setup](ibkr-setup.md#prepare-for-structured-dividend-quantities). Missing quantity evidence keeps its existing local rejection outcome.

**Minor-unit markets.** Yahoo Finance quotes some exchanges in the minor unit (pence, cents) while IBKR reports the major unit. For these the price **and** the fee (or withholding tax) are multiplied by 100 and the currency is changed so that amounts stay correct:

| Yahoo suffix | IBKR currency | Sent to Ghostfolio as | Status |
|---|---|---|---|
| `.L` (London) | GBP | GBp | verified on real trades |
| `.JO` (Johannesburg) | ZAR | ZAc | inferred, not verified |
| `.TA` (Tel Aviv) | ILS | ILA | inferred, not verified |

If you trade on `.JO` or `.TA` and amounts look 100 times off, check this table first.

## Running

### Single account (one-off run)

Compose is the [first-install path](getting-started.md). For an autonomous Docker
run, create a separate private `.env.run`. The Compose `.env` uses suffixed names
and cannot be passed directly to `docker run`. Docker ENV files do not expand
variables or remove quotes: use unquoted values, including account names.

```dotenv
TZ=Europe/Paris
IBKR_TOKEN=replace-with-your-ibkr-flex-token
IBKR_ACCOUNT_IDS=U1234567
IBKR_QUERY_IDS=123456
GHOST_ACCESS_TOKEN=replace-with-your-ghostfolio-security-token
GHOST_HOST=http://ghostfolio:3333
GHOST_ACCOUNT_NAMES=IBKR Individual
MAPPING_FILE=/app/mapping.yaml
CORPORATE_ACTION_STATE_FILE=/state/corporate-actions.yaml
```

Keep CRON out of this file. Edit the mapping before setting its final ownership.
Prepare `.env.run` with mode `0600`. The runtime user `10001:10001` must own and
read the mapping file (mode `0600`) and own the state directory (mode `0700`):

```bash
chmod 600 .env.run mapping.yaml
mkdir -p state/individual
chmod 700 state/individual
sudo chown 10001:10001 mapping.yaml state/individual
```

Replace `your-ghostfolio-network` with the existing network shared with Ghostfolio.
Set GHOST_HOST to a service name or alias that exists on that network. Use the
same per-account state directory as Compose. Stop its scheduled service before
this run, or run before starting the schedule. Do not overlap writers or create
a second state inventory to bypass a lock. Existing multi-account installations
must also pause the other writer if it uses this account.

```bash
docker run --rm --network your-ghostfolio-network \
  --user 10001:10001 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m,mode=1777 \
  --env-file .env.run -e DRY_RUN=true \
  -v "$(pwd)/mapping.yaml:/app/mapping.yaml:ro" \
  -v "$(pwd)/state/individual:/state" \
  ghcr.io/flowcool/ghostfolio-ibkr-sync:latest
```

The first simulation initializes missing state after valid report acquisition.
It can maintain local evidence files; it sends no financial write. Review the
bounded inventory, mapping and holds. Back up Ghostfolio before deliberately
changing the command to `-e DRY_RUN=false`. Resume the schedule only after the
one-off container exits and the result is understood.

### Local development

Docker is the only supported way to run the sync. The image installs the
`ghostfolio_ibkr_sync` package and starts it with `python -m ghostfolio_ibkr_sync`.
Since v3.0.0 there is no `ibkr_to_ghostfolio.py` file or launcher: running the
repository from a source checkout is not supported. To test local changes, build the
image yourself. Run it with the command above, but replace
`ghcr.io/flowcool/ghostfolio-ibkr-sync:latest` with `ibkr-sync:local`:

```bash
docker build -t ibkr-sync:local .
```

### Dry run first

Starting with v3.0.0-rc.2, absent, empty or whitespace-only `DRY_RUN` selects
simulation. Every such invocation logs WARNING
`DRY_RUN not set: simulation, nothing written`, even if configuration fails.
Explicit `1`, `true`, `yes` or `on` also selects simulation. Values are trimmed
and case-insensitive. Only `0`, `false`, `no` or `off` requests live writes; all
other values exit 1 before any HTTP call. After rejection, only configured
Apprise Failure delivery may occur. No IBKR/Ghostfolio HTTP call or financial
write occurs. Other safety guards still apply.

Set `DRY_RUN=1` explicitly for the preview. The full pipeline runs (fetch, convert, deduplicate, gate) and the activities and cash balance that *would* be written are logged, but no activities are imported and no cash balance is updated. With `GHOST_ACCESS_TOKEN`, the authentication POST still exchanges the security token for a session token. IBKR report generation is requested and existing Ghostfolio data is read. This preview does not validate symbols through the Ghostfolio import endpoint, so a successful preview does not guarantee a successful import. Logs include financial activity details; keep them private.

Set a valid IANA `TZ`, such as `Europe/Paris`, even for one-off Docker runs.
Missing or invalid `TZ` forces every account into `DRY_RUN` before processing,
with one WARNING explaining the reason. No activities, cash or platform are
written. The final notification includes the reason when Apprise is configured,
even in default, blank or truthy simulation. Required token renewal also notifies
in simulation. A deliberate clean simulation alone sends no notification. Failed simulations send one
configured Failure notification. After review, set `DRY_RUN=false` and retain
valid `TZ` to permit writes.

Every DETAIL dividend, payment-in-lieu and withholding cash row must have
`dateTime` in `YYYYMMDD;HHmmss TimeZone` form, for example
`20260115;120000 EST` or `20260715;120000 EDT`. A missing or invalid suffix
fails the affected account before any import, cash or platform write. It does
not enable `DRY_RUN`; other accounts retain their configured mode. Other cash
types are outside this check. Follow the [staged activation and rollback
procedure](ibkr-setup.md#activate-timezone-aware-dividend-diagnostics).

Every dry run also compares historical dividends in the target account before
deduplication. The INFO summary reports coverage and categories; details for
differences or uncertainty include source comments and activity IDs. A coherent
single activity has the canonical source comment, consistent security and local
date in `TZ`, and exactly equal quantity, gross and fee. The IBKR `YYYYMMDD`
is the source business day; the destination instant is rendered in `TZ` for
comparison. Flex suffixes provide provenance; import UTC conversion is unchanged.
Gross comes from broker cash; accruals establish quantity. Component quantities
are never summed. Several
activities with the same group comment do not prove a component partition,
even when their amounts sum correctly; that comparison stays uncertain.
An independently identified component set must cover every source component
exactly once. Each component keeps its own quantity and monetary comparison.
The reader does not invent component identities for historical activities.
Two or more identity-proven complete representations indicate probable repetition,
even if their quantities or amounts differ. Incomplete partitions and contested
ownership remain uncertain. Matching amounts never establish completeness, and
the diagnostic never searches arbitrary subsets of activities.

The diagnostic retains original JSON decimals from the existing activities GET.
It never reconstructs exact evidence from floats. Activity currency determines
the denomination; only an explicit null permits profile currency fallback, with
its provenance retained. Supported denominations are USD, EUR, GBP, CHF, JPY,
CAD, AUD, NZD, HKD, SGD, SEK, NOK, DKK, PLN, CZK, HUF, ILS, ZAR and the existing
GBp, ZAc and ILA minor units. Missing or unsupported context stays uncertain;
the log then shows the observed source and destination currency and provenance
on a `currency context:` line, whatever the supported list says.
Gross and fee differences use destination minus source, without a tolerance.
Every nonzero exact delta remains visible, including differences smaller than
float precision. Source fee is the positive part of the negative net cash
withholding; signed withholding and refund rows and their total remain separate
evidence. Coherence requires exact quantity, gross and fee agreement; a complete
representation with a discrepancy is not coherent.
The diagnostic adds no reads, writes or files. Findings do not change
import selection, cash updates or exit codes. Required user checks join the
consolidated notification. Live runs do not
run this comparison. Use the one-off command below without `CRON`.

`absent` means no canonical destination comment was found. It does not establish
that a payment is missing: legacy comments, symbol-only comments, proximity and
timezone explanations cannot certify identity. Inactive or unsupported records,
conflicting security/date context and missing/conflicting accruals stay uncertain.
Missing destination profile ISIN is unavailable evidence and permits amount
comparison; a nonempty conflicting ISIN blocks identity. Details name the
active, activity-ID, data-source, symbol, local-date and ISIN checks with
expected and observed values. INFO counts failed checks. WARNING shows actionable
anomaly blocks with securities, source and destination UTC/local dates, activity IDs,
quantity, gross, fee and currency. An `absent` group suppressed by deduplication
shows the skip path that import selection takes: `skipped by historical comment`
when the account has an old `dividend#<symbol>#<date>` comment (active or not),
else `skipped by proximity` (rows with a `dividend#` comment never count as proximity candidates, and the block also shows source and candidate gross). Each shows candidate values and active status; the
group remains absent and neither label certifies identity. Outside-window records also show their security,
date and values.
The summary counts source payment groups and unmatched destination dividends
separately. Every unmatched target-account dividend remains visible. A UTC date
outside explicit, consistent Flex statement `fromDate`/`toDate` bounds is reported
as `outside_window`; without valid bounds, history stays uncertain. The connector
does not infer a window from the first or last payment. Short reports cannot
verify older history. No category authorizes a repair.

Use the private `.env.run`, state mount and no-overlap procedure from
[the autonomous run](#single-account-one-off-run). Keep `CRON` out of the file. The command reads
only the report generated by its configured Flex query; Docker does not extend
the broker's report window. WARNING includes actionable anomaly and uncertainty details, IDs
and source references; DEBUG also includes coherent comparisons. Keep Docker
logs private and capture them before removing a container if you need evidence.
The dividend diagnostic creates no separate report file; log retention depends on
Docker logging. Simulation can initialize corporate state, retain safety evidence
and rotate eligible local reports. These local writes are not financial writes. Financial state remains unchanged, but authentication and
IBKR report generation still contact the configured services. Technical read
failures still fail the run; actionable diagnostic findings join one notification.

```bash
docker run --rm --network your-ghostfolio-network \
  --user 10001:10001 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m,mode=1777 \
  --env-file .env.run -e DRY_RUN=true -e LOG_LEVEL=DEBUG \
  -v "$(pwd)/mapping.yaml:/app/mapping.yaml:ro" \
  -v "$(pwd)/state/individual:/state" \
  ghcr.io/flowcool/ghostfolio-ibkr-sync:latest
```

The dividend comparison ends with one line, `[DRY RUN] Dividend report: N to check, N informational, N noise`, followed by the detail of each item to check. Findings are written in plain English: the reason, the IBKR and Ghostfolio values side by side, one action line and the statement that nothing was written. Coherent and outside-window findings appear at `DEBUG` only. Differences of less than half a minor unit are noise; a difference of exactly one minor unit with equal quantity is named "minimal difference, cause unknown"; a legacy-comment row on the same security and day is named "probable duplicate". Each item to check that has a candidate carries a "Proposed match": the IBKR dividend and the candidate Ghostfolio rows, each labelled Keep, Duplicate or Differs, with a "strong" or "weak" confidence and the row to act on; with no candidate it reads "no confident match". A proposal never writes, repairs or changes the counts or exit code. Formatting does not add a second notification.

Look for lines starting with `[DRY RUN]`; when there is nothing to import the log simply says `No new activities to import`. Replace `your-ghostfolio-network` with the Docker network shared with Ghostfolio. Run it again after upgrading to a new version: comparing the log with the previous version's shows exactly what the new version changes.

## Flex retry policy

IBKR sometimes answers the Flex SendRequest step with a transient error. The
connector retries it by `ErrorCode`, never by message text.

- **Retried:** `1001`, `1004`, `1005`, `1006`, `1007`, `1008`, `1009`, `1018`,
  `1019`, `1021`.
- **Fail at once:** `1003`, `1010` to `1017` (including expired or invalid token
  `1012`/`1015`), `1020`, and any missing or unknown code.
- **Schedule:** at most five SendRequest attempts, with waits of 60, 120, 300 and
  600 seconds between them: 18 minutes of scheduled waiting. Network timeouts and
  connection retries come on top of that.
- **Exhaustion:** the run fails with the last IBKR message (token redacted), the
  statement is never requested, and nothing is written for the affected account.
  Other accounts in a multi-account run are still processed.
- **GetStatement window:** after SendRequest succeeds, the connector polls up to 60
  times, waiting 5 seconds after each pending response: 300 seconds of scheduled
  waiting (previously 10 attempts). Pending means status `Warn` or `ErrorCode`
  `1019`; any other error fails at once.
- **Polling exhaustion:** if all 60 responses stay pending, the run fails with a
  timeout and nothing is written for the affected account. Other accounts in a
  multi-account run are still processed.

No ENV change is needed. This is connector policy based on IBKR's
[Version 3 error table](https://www.ibkrguides.com/clientportal/performanceandstatements/flex3error.htm),
not a guarantee that IBKR recovers.

## Notifications (Apprise)

Optional. When `APPRISE_URLS` is set, each completed run with a failure, required
user action or eligible corporate-action notice sends at most one consolidated
notification through [Apprise](https://github.com/caronc/apprise/wiki), which supports
ntfy, Gotify, Telegram, Discord, Slack, email and many more. A completed successful run
in any simulation or live mode also sends a reminder when its legacy `GHOST_TOKEN` is about to expire (see
[Token expiry](troubleshooting.md#token-expiry)); the reminder keeps exit 0. Give it a JSON list (up to 10
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
[Token expiry](troubleshooting.md#token-expiry)).

Expiry reminders use the fixed code `ghost_auth: token_expiring` and a rounded-up count
of days remaining (`0` means expired). If the run also fails, the reminder is included
in the same failure notification. At most one notification is sent per completed run;
there is no daily state, so multiple runs in one day can repeat the reminder.

Missing or invalid IANA `TZ` in any mode also sends a final
notification naming the forced-preview reason, even on success. It shares the single summary with any
failures or expiry reminder. Notification delivery does not change exit status.

**Simulation since rc.2:** failed runs send one configured Failure notification,
including default, blank or truthy `DRY_RUN` and invalid-value rejection. Failure
with an expiry reminder or forced preview uses the same summary, never a second
dispatch. Delivery does not change exit status.

**When nothing is sent:** clean successful runs without a required action or an
eligible corporate-action notice; deliberate simulation alone; interrupted runs;
and disabled or invalid Apprise settings. Mapping, review, diagnostic checks and
other explicit required actions repeat once per completed run until resolved.
See [User action required](#user-action-required) and [Notification result](#notification-result).

**Delivery:** Apprise runs in a separate short-lived worker process with only network
settings in its environment (`PATH`, locale, CA bundle and proxy variables; never the IBKR or
Ghostfolio credentials), the URLs passed on its standard input, and its output discarded, so a
misbehaving plugin cannot print your destination credentials into the log. One deadline,
`APPRISE_TIMEOUT`, covers the whole worker (Python start, Apprise import, sending, exit); a
worker still running at the deadline is killed. This adds at most `APPRISE_TIMEOUT` seconds,
plus Apprise's import time inside it, to a notifying run. There is **no retry**: after a timeout
the notification may or may not have arrived (`Failure notification timed out (it may still
arrive; not retried)`). Delivery problems (`timeout`, `failed`, `invalid_destination`,
`unavailable` when Apprise cannot be imported, `payload_too_large`, `spawn_failed` when the worker
process (`python -I -m ghostfolio_ibkr_sync --notify-worker`) cannot start) are logged as warnings
and never change the run's exit code. Apprise and its pinned dependencies ship in the image
and are only imported by the worker.

**Rollback:** remove `APPRISE_URLS` (or set it to `[]`) and recreate the container; the sync
behaves exactly as without the feature. Older images ignore the variable.

## Docker Compose / Portainer

The repository root contains the canonical hardened [`compose.yaml`](../compose.yaml) and a safe [`.env.example`](../.env.example). Copy the environment file, edit the account-specific values, and validate the resolved model with `docker compose config --quiet` before starting a service.

For a first preview, run one account without its schedule:

```bash
docker compose run --rm -e CRON= ibkr-sync-individual
```

Keep `DRY_RUN=true` until the preview is understood. Set `DRY_RUN=false` only after a backup and a deliberate review. For recurring runs, set `CRON_INDIVIDUAL` and `CRON_JOINT` in `.env`, then run `docker compose up -d`. Use `10001:10001`, mode `0600`, and a read-only mapping mount as shown in the canonical file. Stagger schedules when several sub-accounts share one Ghostfolio instance.

The image runs as the stable non-root UID/GID `10001:10001`. The mapping file must be readable by that user:

```bash
chmod 0600 mapping.yaml
sudo chown 10001:10001 mapping.yaml
```

The `CRON` value uses exactly five numeric fields. Named days/months, macros, seconds fields, and embedded commands are rejected before the scheduler starts. An empty `CRON` runs one sync immediately.

### Run once by hand in a scheduled container

To trigger one run without waiting for the cron tick, execute the cron command in the running
container. It uses the container's environment, so `DRY_RUN` behaves as configured (with `DRY_RUN`
true, nothing is written):

```bash
docker exec <container> python -m ghostfolio_ibkr_sync
```

This is the only supported way to run the sync by hand. The old
`python /app/ibkr_to_ghostfolio.py` command no longer works: v3.0.0 removed that file
without a compatibility launcher, so update any script or note that calls it.


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
- **Corporate actions** - detection holds unsafe BUY/SELL. Treatment remains manual. See [persistent evidence, date proof and recovery](../README.md#corporate-action-safety).
- **Cash balance is a single base-currency figure** - the balance written to each Ghostfolio account is IBKR's total ending cash in the account's base currency, with no conversion. The Ghostfolio account must have the same currency as the IBKR base currency (see [Create accounts](#3-create-accounts)); the sync refuses to write the balance otherwise.
- **Daily data only** - Activity Statements update once daily after market close; intraday syncing is not possible
- **Token management** - the IBKR Flex token expires and requires manual renewal: set a recurring calendar reminder (up to 1 year). On the Ghostfolio side, `GHOST_ACCESS_TOKEN` logs in on every run; only the legacy `GHOST_TOKEN` needs manual renewal.
- **Account-scoped queries** - use a separate Flex Query per sub-account. Several account/query pairs can run sequentially in one container; separate containers are recommended for operational isolation.
- **Additive imports** - with activity review disabled, later IBKR corrections to stored trades or same-date dividends are not reconciled. Optional review exposes supported one-to-one corrections for explicit approval. Dividend proximity matching (manual or legacy rows only, never rows with a `dividend#` comment) can suppress a distinct payment within ±3 days; the skip is logged (`INFO` when the gross agrees, one `WARNING` otherwise) and the payment must then be added by hand. A row with a `dividend#` comment is trusted by exact identity; editing such a row is outside the contract. Check unusual payment schedules and tax corrections manually.
- **Commission currency** - commissions are booked in the activity currency; a different IBKR commission currency is not converted.
- **Cleanup is not transactional** - cleanup requires complete financial evidence, equal fees, a unique one-to-one pair and unchanged fresh copies of both rows. Draft or excluded candidates are refused. PUT can succeed while DELETE fails; stop and inspect both rows and the safety log before any recovery. A new apply writes a private YAML journal with exact preimages and known/unknown outcomes. Explicit journal recovery can finish an unchanged pair; it does not recreate deleted activities or repair changed records.
- **Active position context** - drafts and excluded activities/accounts retain their import identifiers for deduplication, but cannot contribute holdings, manual matches or dividend proximity evidence. Holdings and manual reconciliation use active YAHOO profiles; other sources cannot back YAHOO sells. Excluded target accounts are refused. Future timestamps are deferred with exit 1 until a later run; this conservative instant check avoids server-local draft assignment even when import responses omit tags. Accepted imports use the actual server profile symbol; a canonicalized symbol can require an explicit mapping before sells under the original ticker are allowed.
- **Batch guard limitations** - the gate checks net quantity, not chronological balances. Buy and sell phases are separate requests, so successful buys can remain if sells fail. A dry-run previews candidates without verifying server acceptance.
- **No overlap protection** - avoid concurrent sync runs targeting the same Ghostfolio account; deduplication is based on a snapshot read at startup.


### User action required

Required actions send one consolidated reminder on every completed run, including
simulation. Repeated observations of one event and reason count once. Reminders
continue while current evidence requires action. Clean success sends no heartbeat.
Review approval does not suppress a reminder when missing proof still blocks work.


### Notification result

Each completed run reports `not required`, `disabled`, `invalid configuration`,
`sent`, `failed`, or `timeout, delivery unconfirmed`. Configure APPRISE_URLS and
APPRISE_TIMEOUT when a required notification is disabled or invalid. `sent`
means the transport reported success; it does not prove device receipt. A timeout
can still deliver later. The connector makes one attempt and does not retry.
Delivery failure does not change the financial result or process exit code.


Mapping and trade reminders use `mapping_unverified`, `mapping_conflict`,
`trade_manual`, `trade_position` or `trade_invalid`. Private logs identify the
source scope. Verify the intended security in Ghostfolio or correct MAPPING_FILE.
For manual matches, compare source and destination before any reference repair.
Current valid source fields and verified destination ownership prove resolution.
Mapping checks still run for already imported trades in the acquired window.
Normal CASH/OPT exclusions, absent positions and recovered network retries do not
create required-action reminders by themselves.


Dividend actions use `dividend_rejected` for missing/conflicting cash, quantity,
payment association or withholding evidence. `dividend_reversal` identifies an
orphan reversal. `dividend_signed_tax` identifies signed zero-net tax, orphan tax
or a withholding refund. `dividend_check` identifies a discrepant proximity skip.
Inspect preserved Flex and Ghostfolio evidence. Never invent payment or quantity,
and never resend an uncertain transaction. Complete consistent current evidence,
verified destination agreement or documented manual resolution proves resolution.
Ordinary zero-net payments without signed tax remain exclusions. Future dates
remain deferred work. A representation limit alone does not request correction.


Simulation reports dividend items to check at WARNING. Concrete comparisons
that require intervention join the same `dividend_check` reminder. Inspect the
named activity and both sides of the comparison. Current agreement or documented
manual resolution proves resolution. Information, accepted rounding and noise
alone send no reminder. Named representation or coverage limits remain visible
as evidence limitations without requesting an impossible correction. No diagnostic
changes financial selection, grants cleanup authority or writes a correction.


Corporate-action holds and concrete historical discrepancies repeat in the same
summary as other actions. Private conclusions name scope and the configured state
path. Restore the stated evidence; acknowledgment and state reset do not release
holds. Nonblocking findings without a user action keep first/change/resumption
notifications. Automatic evidence maintenance remains a retry and is reported as
such; it does not request approval. Token renewal and invalid or missing TZ also
notify in simulation. Correct the named setting; simulation does not resolve it.


### Cycle result

Completed cycles report `success`, `success with user action required`, or
`failure`. Failure takes priority. Exit codes keep their existing meaning.
Accepted imports or simulated proposals, duplicate skips, unique review-held
events, other holds and deferred automatic work appear separately. Decision
counts can overlap. Unknown evidence reads `unavailable`, never an invented zero.
Cash is reported per account as `simulated`, `request reported successful`,
`not updated` or `uncertain/failed`. Request success is not independent balance
readback. Cash success does not mean held activities were imported.

For example, `success with user action required` can report zero accepted imports,
review-held events and `cash=request reported successful`. The notification result
appears beside the cycle result. Automatic deferral alone remains `success`.


### Application log levels and streams

DEBUG and INFO use stdout. WARNING and above use stderr. Each application record
has one timestamp and one level. The scheduler passes application output directly
and keeps its lifecycle messages separate. A transport stream is not a severity.
For a clean scheduled run, application INFO stays INFO without scheduler wrapping.
`LOG_LEVEL` still filters application records. LAB_EVIDENCE JSON remains at DEBUG.
Startup and each sync cycle show `ghostfolio-ibkr-sync version X.Y.Z — commit <12-character SHA>`.
The build sets `APP_VERSION` and `APP_REVISION` automatically from the validated
release tag and source commit. No operator setting or startup network lookup is
needed. The version is the target software version. An RC reports the same target
version before stable publication; its registry tag still contains `-rc.N`.
Stable promotion preserves the qualified digest. Older images retain their original
RC build text. Local builds without release metadata report `dev` and `unknown`.
