# Upgrading to 3.0

3.0 is a major release. An existing 2.x setup keeps running only after four things are in
place: a valid `TZ`, a time-zone suffix and extra dividend fields in the Flex query, and
distinct Ghostfolio targets whose currency equals the IBKR base currency. Without them the
sync stops writing or fails accounts after you pull `:latest`. Do the steps below first.

Before you start:

- Back up Ghostfolio and record the installed image digest, as described in
  [Releasing](releasing.md#runtime-rollback) and the [Docker image guide](../README.md#docker-image).
  Keep your ENV and mounts.
- A release candidate, `v3.0.0-rc.N`, can be published for testing before `:latest` moves. It
  never moves `:latest`, `:X.Y.Z` or `:X.Y`. Run it as a one-off container with `DRY_RUN=1`
  and a pinned `:3.0.0-rc.N` tag, then switch to the stable tag once it is published. See
  [the release candidate steps](releasing.md#release-candidate-optional).
- Run once with `DRY_RUN=1 LOG_LEVEL=DEBUG` and no `CRON` after each change below, using the
  [README preview command](../README.md#dry-run-first).

## 1. Set `TZ` (required to write)

**What changes.** A missing or invalid IANA `TZ` forces the whole run into `DRY_RUN`: no
activity, cash balance or platform write for any account.

**Action.** Set `TZ` to an IANA zone such as `Europe/Warsaw` (not `EST` or `CET`) and recreate
the container. The image sets no default.

**Symptom if not done.** Nothing is imported, and the log shows
`TZ is missing: whole run forced to DRY_RUN, no Ghostfolio writes` (or
`TZ is not a valid IANA timezone: ...`). With `APPRISE_URLS` set, one notification names the reason,
even when every account succeeds.

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

- **Longer Flex waits.** A transient IBKR SendRequest error is retried (up to five attempts, 18 minutes of
  scheduled waits) and GetStatement polls up to 60 times (300 seconds). A failing run can take longer.
  No ENV change is needed. See [Flex retry policy](../README.md#flex-retry-policy).
- **Dry-run dividend report wording.** Findings are plain English with a summary line
  `[DRY RUN] Dividend report: N to check, N informational, N noise` and a "Proposed match" section. If a
  script parses these logs, update it. Exit codes and notifications do not change. The report only
  appears under `DRY_RUN`.
- **Stable channel.** `:latest` follows the current stable release only. See the
  [Docker image guide](../README.md#docker-image).

## Verify

Run once with `DRY_RUN=1 LOG_LEVEL=DEBUG`. Expect none of the lines above, the version in the start-up
log, and a dividend report you can read. Then remove `DRY_RUN`, and resume the schedule.

## Roll back

Pin the previous image tag (or the digest you recorded) and recreate the container with the same ENV
and mounts. This restores the runtime only: activities, cash balances and platform updates already
written stay. The extra Flex fields can remain. Images up to 2.5.0 do not parse the time-zone suffix, so
also set the Flex query time format back to **HHmmss** (no TimeZone) before running them.

[Back to the README](../README.md)
