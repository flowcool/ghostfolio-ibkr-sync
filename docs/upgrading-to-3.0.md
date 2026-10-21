# Upgrading to 3.0

3.0 is a major release. An existing 2.x setup keeps running only after four things are in
place: a valid `TZ`, a time-zone suffix and extra dividend fields in the Flex query, and
distinct Ghostfolio targets whose currency equals the IBKR base currency. Without them the
sync stops writing or fails accounts after you pull `:latest`. Starting with rc.2,
writes also require an explicit false `DRY_RUN`. Do the steps below first.

Before you start:

- Back up Ghostfolio and record the installed image digest, as described in
  [Releasing](releasing.md#runtime-rollback) and the [Docker image guide](../README.md#docker-image).
  Keep your ENV and mounts.
- A release candidate, `v3.0.0-rc.N`, can be published for testing before `:latest` moves. It
  never moves `:latest`, `:X.Y.Z` or `:X.Y`. To test it on a scheduled Compose install, follow
  [Try a release candidate](#try-a-release-candidate).
- Run once with `DRY_RUN=1 LOG_LEVEL=DEBUG` after each change below, using the
  [README preview command](../README.md#dry-run-first) (no `CRON`), or
  [one manual run in your scheduled container](../README.md#run-once-by-hand-in-a-scheduled-container).
- Pause scheduled imports if the container runs live. On rc.2 or later, live
  mode requires explicit false `DRY_RUN`. Older images can also write when it
  is unset. With `DRY_RUN=true`, nothing is written, so keep the schedule running.

## Simulation default (breaking since v3.0.0-rc.2)

Absent, empty or whitespace-only `DRY_RUN` now selects simulation. Each
invocation logs WARNING `DRY_RUN not set: simulation, nothing written`, even
if configuration fails. After trimming spaces and ignoring case, `1/true/yes/on`
simulates. Only `0/false/no/off` requests live writes. Other values exit 1 before
any HTTP call. After rejection, only configured Apprise Failure delivery may
follow; no IBKR/Ghostfolio HTTP calls or financial writes occur.

Simulation still logs in, reads data and runs the preview. It writes no activity,
cash or platform data. Failed simulations send one configured Failure
notification, including default/blank/truthy modes and invalid `DRY_RUN`.
Successful simulations send nothing, including expiry-only reminders and
previews. Failure with an expiry reminder or forced preview uses one summary.
Without configured Apprise, nothing is sent. Delivery does not change exit status.

Keep `DRY_RUN=true` while reviewing the preview. Then set `DRY_RUN=false` and
recreate the container to permit writes. Keep valid `TZ`; all other safety guards
still apply. Removing `DRY_RUN` no longer permits writes. For rollback, restore
the recorded image digest with retained ENV and mounts as described below.
Older images can interpret absent `DRY_RUN` as live mode. Set `DRY_RUN=true`
explicitly before a rollback preview.

## Is my Flex query already compliant?

Run once with `DRY_RUN` true and read the log. The query is ready for 3.0 when the run shows
neither the time-zone `ERROR` of step 2 (`cash rows without a valid 'YYYYMMDD;HHmmss TimeZone'
dateTime`) nor the dividend-field `ERROR` of step 3 (`required dividend fields missing from the
report`). Use a 3.0 image for this check: older images do not run the check. A report with no
dividend rows raises neither error, so it cannot show that the dividend fields are present.

## 1. Set `TZ` (required to write)

**What changes.** A missing or invalid IANA `TZ` forces the whole run into `DRY_RUN`: no
activity, cash balance or platform write for any account.

**Action.** Set `TZ` to an IANA zone such as `Europe/Warsaw` (not `EST` or `CET`) and recreate
the container. The image sets no default.

**Symptom if not done.** Nothing is imported, and the log shows
`TZ is missing: whole run forced to DRY_RUN, no Ghostfolio writes` (or
`TZ is not a valid IANA timezone: ...`). With `APPRISE_URLS` set, one notification names the reason,
even when every account succeeds, if `DRY_RUN` is explicitly false. Successful
default/blank/truthy simulations stay silent; failed simulations send Failure.

## 2. Add the time zone to the Flex query times (breaking)

**What changes.** Every DETAIL dividend, payment-in-lieu and withholding cash row must carry
`dateTime` as `YYYYMMDD;HHmmss TimeZone`, for example `20260115;120000 EST`. Other cash types
are not checked.

**Action.** In IBKR Client Portal, go to **Performance & Reports** > **Flex Queries**, edit your
**Activity Flex Query** and:

1. Open **General Configuration**.
2. Set the date format to **YYYYMMDD** and the time format to **HHmmss TimeZone**, and keep the
   date/time separator as a semicolon (`;`).
3. Click **Continue**, then **Save**.

**Order matters.** Images up to 2.5.0 cannot read the time-zone suffix. If you change the query
while one of them still runs, its next run logs `Skipping cash transaction ...: invalid amount or
date` for dividends and `Could not parse dateTime ... for trade ...` for trades, and those rows are
not imported. Upgrade to 3.0 right after you change the query. If you already changed the query
and still run 2.5.0 or older, upgrade now, or restore the query time format to **HHmmss** and the
previous image together.

**Symptom if not done.** The account fails before any import, cash or platform write, `DRY_RUN`
is not enabled, other accounts still run and the run exits 1:

```
Flex Query <id>: cash rows without a valid 'YYYYMMDD;HHmmss TimeZone' dateTime (Dividends: 3); account failed before any write. Add Date/Time with time zone to the query, see README
```

## 3. Add the dividend fields to the Flex query (breaking)

**What changes.** If the report has dividend, payment-in-lieu or withholding cash rows, a
Cash Transactions attribute that is missing from every row, or a missing Change in Dividend
Accruals section, fails the account up front. Before 3.0 this blocked only the dividends.

**Action.** In the same query:

1. Open **Cash Transactions**. Keep **Dividends**, **Payment In Lieu Of Dividends**,
   **Withholding Tax** and **Detail**. Select **all available fields**; make sure **ClientAccountID**,
   **CurrencyPrimary**, **ConID (Contract ID)**, **ActionID** and **Ex Date** are ticked. Click **Save**.
2. Add **Change in Dividend Accruals** and select **all available fields**, including
   **ClientAccountID**, **CurrencyPrimary**, **ConID**, **ActionID**, **Quantity**, **Code**, **Date**,
   **Ex Date**, **Pay Date** and **Report Date**. Click **Save**.
3. Keep the other sections, **XML** and **Last 365 Calendar Days**. Click **Continue** and **Save**.

The full list is in [IBKR setup](ibkr-setup.md#prepare-for-structured-dividend-quantities).

**Symptom if not done.** The account fails before any write, `DRY_RUN` is not enabled and the run
exits 1. The line names each missing attribute with the IBKR field to tick:

```
Flex Query <id>: required dividend fields missing from the report (CashTransaction.conid (ConID (Contract ID))); account failed before any write. Tick these fields in the query, see README
```

A report with no dividend rows is not affected. One row with an empty value is not this error:
it rejects only that payment.

## 4. Use one Ghostfolio account per IBKR account, in the IBKR base currency

**What changes.**

- Two IBKR accounts that resolve to the same Ghostfolio target are refused at start-up. The target is
  the name in `GHOST_ACCOUNT_NAMES`, or the IBKR account ID when no names are set.
- The cash balance is written only if the Ghostfolio account currency equals the IBKR base currency
  (the Account Information `CurrencyPrimary` of the report). Before 3.0 a mismatch sent the IBKR
  figure to an account in another currency.

**Action.** Give each IBKR account its own Ghostfolio account. Make the Ghostfolio account currency
equal to the IBKR base currency. Keep **CurrencyPrimary** ticked under **Account Information** in the
query.

**Symptom if not done.**

```
Configuration error: Duplicate Ghostfolio target '<name>': each IBKR account needs its own target
Cash balance not updated for account <id>: IBKR base currency <X> differs from Ghostfolio account currency <Y>
Cash balance not updated for account <id>: the report has no base currency (Account Information CurrencyPrimary missing from the Flex Query)
```

The first stops the run with exit 1 before any network call. The others send no balance and fail the
account; trades and dividends of that account are still processed.

## 5. Remove `GHOST_CURRENCY` (optional)

The setting was never used and is gone from the documentation. A value still set is ignored. Delete it
from your ENV at your convenience.

## 6. Unknown trade side

**What changes.** A trade whose Buy/Sell value is not exactly `BUY` or `SELL` (for example a
cancellation, `SELL (Ca.)`) is rejected, never imported, and fails the account. Other trades import
normally.

**Action.** None in the connector. If a cancellation sits in your report, check the trade in IBKR.

**Symptom.** The run exits 1 on every run while the row stays inside the 365-day window:

```
Unknown buySell 'SELL (Ca.)' for trade <id>; trade rejected
Trade <id> cannot be converted safely; excluded before holdings checks
```

## 7. Other changes to know

- **Versioned dividend history.** New dividends use
  `IBKR#v2#<source-account>:DIVIDEND:<actionID>`, one activity per positive
  cash action. Dividend and PIL portions of that action share one quantity.
  Historical resolved-symbol, raw-symbol and ISIN `dividend#<key>#<date>`
  comments still win in their destination account. This can hide a later
  distinct event on the same security/day. A historical match does not prove
  that every event was imported. No automatic backfill or repair occurs.
- **Partial acceptance needs explicit recovery.** Ghostfolio can accept only
  part of an import batch. The sync retains proven accepted identities and
  fails the account. Normal reruns refuse partial action coverage. The error
  can recur while that group stays inside the configured report window.
  Look for `partial versioned action coverage` and
  `explicit reviewed recovery required`. Keep accepted rows. Do not change
  their comments or add a historical comment to bypass the refusal. Recovery
  needs complete source and destination evidence, settled requests, stopped
  competing writers, a reviewed manifest and a separately approved operation.
  This change does not make a recovery command available yet.
- **Action conflict needs manual review.** With no exact coverage, the sync
  checks existing v2 dividends for the same source account, security and day.
  An unexpected action or unknown overlapping context blocks that group.
  Look for `versioned action-context conflict or unknown overlap`.
  A legitimate additional same-day event can also be refused. Trades, safe
  sales, independent cash and later accounts continue. V2 dividends never
  supply proximity or historical dividend-report evidence. A changed amount
  under an existing identity is not corrected. Revisions that also change
  day or security can evade this guard; review source corrections manually.
- **Rollback floor after v2 history.** Once any v2 activity exists, retain
  rc.5 or a newer qualified dual reader. Stop writers and set `DRY_RUN=true`
  before rollback. Pre-rc.5 code must never run against that history.
  A reader rollback keeps existing rows and can still refuse partial coverage.
  Resume writes only after mixed-history review and separate authorization.
  Existing cleanup tools must not run against v2 history until separately
  qualified. Writer release and image-backed qualification remain separate.
- **Longer Flex waits.** A transient IBKR SendRequest error is retried (up to five attempts, 18 minutes of
  scheduled waits) and GetStatement polls up to 60 times (300 seconds). A failing run can take longer.
  No ENV change is needed. See [Flex retry policy](../README.md#flex-retry-policy).
- **Dry-run dividend report wording.** Findings are plain English with a summary line
  `[DRY RUN] Dividend report: N to check, N informational, N noise` and a "Proposed match" section. If a
  script parses these logs, update it. Exit codes and notifications do not change. The report only
  appears under `DRY_RUN`.
- **Stable channel.** `:latest` follows the current stable release only. See the
  [Docker image guide](../README.md#docker-image).

## Try a release candidate

Use this on an existing scheduled Compose install to test `v3.0.0-rc.N` before the stable release.
With `DRY_RUN` true, the candidate writes nothing.

1. Record the installed image digest using the [Docker image guide](../README.md#docker-image).
   Save that exact reference with the ENV and mounts for rollback.
2. Set the image to the candidate tag and `DRY_RUN` to `true`, then redeploy:

   ```yaml
   image: ghcr.io/flowcool/ghostfolio-ibkr-sync:3.0.0-rc.N
   environment:
     DRY_RUN: "true"
   ```

   ```bash
   docker compose up -d
   ```

3. Run once by hand, with the same environment as the cron
   ([README](../README.md#run-once-by-hand-in-a-scheduled-container)):

   ```bash
   docker exec <container> python -m ghostfolio_ibkr_sync
   ```

   The old `python /app/ibkr_to_ghostfolio.py` command no longer works: the candidate
   removed that file without a compatibility launcher. Update any script that calls it.

4. Read the log with the [Verify](#verify) list. The first start-up line names the candidate:
   `ghostfolio-ibkr-sync version v3.0.0-rc.N`.
5. For rollback, respect the rc.5 reader floor after any v2 activity exists
   (see [Other changes](#7-other-changes-to-know)). Select the saved qualified image
   digest with the retained ENV and mounts, then run
   `docker compose up -d`. Set `DRY_RUN=true` explicitly for a rollback preview;
   older images can write when the variable is absent. If you changed the Flex query for 3.0, see the order warning in step 2.
6. The latest candidates run the refactored typed package. The 10-day production soak
   restarts on this refactored candidate, and the stable release follows only after it.
7. After the stable release, return to `:latest` (or pin `:3.0.0`). A pinned `-rc.N` tag gets no
   automatic update, so change it yourself.

## Verify

Run once with `DRY_RUN=1 LOG_LEVEL=DEBUG` (or `DRY_RUN` true in a scheduled container, see above).
Expect:

- the version in the start-up log, `ghostfolio-ibkr-sync version v3.0.0` (or `v3.0.0-rc.N` for a candidate);
- none of the `ERROR` and `WARNING` lines of steps 1 to 4 and 6;
- a dividend report you can read.

After review, set `DRY_RUN=false` to permit writes and resume the schedule if you paused it.
Keep `DRY_RUN=true` if you only test a candidate.

## Roll back

After any v2 activity exists, stop writers and use rc.5 or a newer qualified dual
reader with `DRY_RUN=true`. Never restore pre-rc.5 code against v2 history.
Otherwise, pin the previous image digest you recorded and recreate the container with the same ENV
and mounts. This restores the runtime only: activities, cash balances and platform updates already
written stay. The extra Flex fields can remain. Images up to 2.5.0 do not parse the time-zone suffix, so
also set the Flex query time format back to **HHmmss** (no TimeZone) before running them.

[Back to the README](../README.md)
