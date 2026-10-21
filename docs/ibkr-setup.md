# IBKR Setup

## 1. Enable Flex Web Service

1. Log in to IBKR Client Portal or Account Management
2. Go to **Settings** - **Reporting** - **Flex Queries**
3. At the bottom of the page, find **Flex Web Service** and click **Configure**
4. Generate a new token (or note your existing one)
5. Set the expiration to **1 year** so you do not have to rotate it frequently
6. Save the token - you will need it as `IBKR_TOKEN`

## 2. Create a Flex Query

**Important:** If you have multiple sub-accounts, create one Flex Query per sub-account. See the multi-account section below before creating your queries.

1. On the same Flex Queries page, click **Create** under **Activity Flex Query**
2. Give it a name like `Ghostfolio Sync - Individual`
3. Set the period to **Last 365 Calendar Days**

   > **⚠️ Critical — do not use a shorter period (e.g. Last Month, Last Quarter)**
   >
   > 365 days is the widest period IBKR allows. A wide window lets the sync recover
   > trades missed during a gap in daily runs (container down, expired token), as long
   > as they are still inside the period. A shorter period causes two classes of silent
   > failures:
   >
   > - **Missing trades**: trades older than the period are never seen, and a sell whose
   >   buy is outside the window is imported only if Ghostfolio already holds that buy
   >   (see [What the tool skips automatically](../README.md#what-the-tool-skips-automatically)).
   > - **New historical candidates when widening the period**: trade-ID dedup still
   >   recognises previously synced activities, but older manual entries or activities
   >   from another importer may need reconciliation before importing the wider report.
   >
   > **Recovery if you already used a shorter period:** review existing activities
   > against the statement before widening the query. The repository contains
   > `cleanup_duplicates.py` and `cleanup_dividends.py`. They require matching
   > account, currency and asset-profile identity, unique one-to-one matches,
   > and fresh records before mutation. These checks cannot prove that two
   > similar payments represent the same event, and the tools do not provide
   > transactional protection against concurrent edits. Review every proposed
   > pair against the statement and take a verified backup before `--apply`;
   > dry-run output alone is not proof that deletion is safe. These tools are
   > not included in the Docker image.
   > Dividend cleanup lists candidates up to 35 days apart in dry-run, but
   > `--apply` keeps both records unchanged when their dates differ by more than
   > 7 days and exits 1. Verify distant ex-date/payment-date pairs manually;
   > there is no bypass flag. A shorter date gap still does not prove event identity.

4. Select the following sections and fields:

**Account Information:**
- ClientAccountID
- CurrencyPrimary

**Cash Report:**
- CurrencyPrimary
- EndingCash

**Trades (Execution):**

Select these fields for a predictable report. **ClientAccountID** (`accountId`) and **TradeID** (`tradeID`) are mandatory for every selected trade. Its account must equal the configured account and Account Information evidence. A missing or mismatched account, unsafe identity or comment over 2000 ASCII characters fails the account before financial writes. CASH/OPT rows stay excluded. The parser ignores additional attributes:

- ClientAccountID
- CurrencyPrimary
- AssetClass
- SubCategory
- Symbol
- Description
- ISIN
- FIGI
- TradeID
- Multiplier
- DateTime
- TradeDate
- IBCommission
- IBCommissionCurrency
- Open/CloseIndicator
- Buy/Sell
- Exchange
- Quantity
- TradeMoney
- TradePrice

New trade comments are `IBKR#v2#<source-account>:TRADE:<tradeID>`. The shared dividend format is `IBKR#v2#<source-account>:DIVIDEND:<actionID>`; action writing follows separately. Each segment permits only `[A-Za-z0-9._-]+`, without transformation or fallback. Historical comments remain readable. See the [conversion rules](../README.md#how-activities-are-converted) for limits and rollback requirements.

**Cash Transactions:**

In the section options, tick only these types: **Dividends**, **Payment In Lieu Of Dividends**, **Withholding Tax**, and the **Detail** level of detail. Then select these fields:

- ClientAccountID
- CurrencyPrimary
- AssetClass
- Symbol
- Description
- ISIN
- FIGI
- Date/Time
- Amount
- Type
- LevelOfDetail (if listed)
- ConID (Contract ID)
- ActionID
- Ex Date
- Report Date

ConID, ActionID and Ex Date are mandatory: a report without them fails the account (see [Prepare for structured dividend quantities](#prepare-for-structured-dividend-quantities)).

**Change in Dividend Accruals:**

Mandatory as soon as the report has dividend, payment-in-lieu or withholding cash rows. Select **all available fields**, including:

- ClientAccountID
- CurrencyPrimary
- ConID (Contract ID)
- ActionID
- Quantity
- Code
- Date
- Ex Date
- Pay Date
- Report Date

Dividends are read from these actual cash payments, not from dividend accruals: IBKR marks accrual corrections, cancellations and payouts all with the same code, so importing every accrual reversal produces phantom and duplicate dividends. Cash Transactions also give the withholding tax actually paid. **Change in Dividend Accruals** supplies quantity evidence only; include it with the fields above.

> **Upgrading from an older version:** add the Cash Transactions section before running the new image. Without it the run logs an `ERROR`, imports trades but no dividends, and exits 1. Dividends already in Ghostfolio are recognised by their `dividend#` comment, or, for manual or legacy rows without that comment, by a dividend of the same symbol in the same account within 3 days (logged as `INFO` when the gross agrees, otherwise as one `WARNING` telling you to check IBKR and add the payment by hand if it is distinct), so they are not imported twice. Phantom dividends imported by older versions are not removed: check your IBKR dividends in Ghostfolio by hand.

5. Under **General Configuration**, set **Include Currency Rates** to **No**

   Currency-rate rows are not used by this tool. It does not convert the cash balance or commissions between currencies.

   Set the date format to **YYYYMMDD** and the time format to **HHmmss TimeZone**,
   and keep the date/time separator as a semicolon (`;`).
   DETAIL dividend, payment-in-lieu and withholding Cash Transactions must emit
   `dateTime` as `YYYYMMDD;HHmmss TimeZone`, such as `20260115;120000 EST`
   or `20260715;120000 EDT`. A missing or invalid timezone suffix fails that
   account before any import, cash or platform write. It does not enable
   `DRY_RUN`; other accounts retain their configured mode. Other cash types
   are outside this validation.

6. Save the query and note the Query ID (click the info icon next to the query to find it)

### Prepare for structured dividend quantities

Enrich the query before upgrading. Dividend quantities now require structured
accrual evidence. Description inference and the one-unit fallback are removed.

In **Performance & Reports > Flex Queries**, edit the existing **Activity Flex
Query** used by the connector:

1. Open **Cash Transactions**. Keep **Dividends**, **Payment In Lieu Of Dividends**,
   **Withholding Tax**, and **Detail**. Select **all available fields**, including
   action ID, contract ID, dividend type, ex-date and report date. These appear in
   XML as `actionID`, `conid`, `dividendType`, `exDate` and `reportDate`. Click **Save**.
2. Add **Change in Dividend Accruals** and select **all available fields**. Include
   account, currency, symbol, ISIN, contract/action IDs, **Quantity**, **Gross Rate**,
   **Gross Amount**, **Tax**, **Fee**, **Net Amount**, **Code**, **Date**, **Ex Date**,
   **Pay Date** and **Report Date**. Click **Save**.
3. Preserve **Account Information**, **Trades (Execution)** and **Cash Report**.
   Keep the same single account, **XML**, and **Last 365 Calendar Days**. Preserve
   **YYYYMMDD** dates and **HHmmss TimeZone** times. Keep other existing settings.
   Click **Continue** and save.

Structured accruals can support quantity and component identity. They do not
replace Cash Transactions as the source of paid gross amounts and withholding.
Accrual amounts and tax can differ from cash, and `Re` also marks corrections and
cancellations. Do not import accrual rows directly as dividend payments.

Required payment keys: a report where a payment attribute appears on no relevant cash row fails the account before any write, including trades and cash. The run logs one `ERROR` that names each missing attribute with the IBKR field to tick. It does not enable `DRY_RUN`. This matches the time-zone check.

- `accountId`: ClientAccountID
- `conid`: ConID (Contract ID)
- `currency`: CurrencyPrimary
- `actionID`: ActionID
- `exDate`: Ex Date

When the report has a relevant payment, dividend or withholding cash row, the `ChangeInDividendAccruals` section is also required. If it is absent, the account fails the same way. If it has rows, each of these attributes must appear on at least one of them: `accountId`, `conid`, `currency`, `actionID`, `exDate`, `quantity` (Quantity), `code` (Code), `date` (Date), `payDate` (Pay Date) and `reportDate` (Report Date). A present but empty section stays valid. Withholding rows keep their cash fields; they do not need accrual association keys.

A single empty or malformed value does not fail the account. It rejects only the affected payment: present but empty values, missing evidence in a short report window, and conflicting quantities. Rejected payments are not marked imported and can retry after the query or report window is corrected. Empty sections without payments are valid. Unrelated rows do not block valid payments. Existing dividends are deduplicated before evidence checks and remain untouched and unverified.

Before upgrading, back up Ghostfolio with your deployment's backup procedure and
record the previous image digest as described in [Releasing](releasing.md).
Keep the existing ENV, credentials and mounted configuration files. Upgrade the
image only after saving the enriched query. For runtime rollback, restore the
previous image digest with the same ENV and mounts and recreate the connector.
The extra Flex fields can remain because the previous runtime ignores them;
check its timestamp format requirements as described below.
Runtime rollback does not restore financial data or undo written activities.
Historical repairs require separate operator review; this upgrade does not
certify previously imported dividend quantities.

### Simulation default since v3.0.0-rc.2

Absent or blank `DRY_RUN` selects simulation. Each invocation logs WARNING
`DRY_RUN not set: simulation, nothing written`, even if configuration fails.
After trimming spaces and ignoring case, `1/true/yes/on` simulates; only
`0/false/no/off` requests writes. Any other value exits 1 before HTTP. Only
configured Apprise Failure delivery may follow rejection, with no IBKR/Ghostfolio
HTTP calls or financial writes. Simulation keeps login, reads and preview,
without activity, cash or platform writes.

Failed simulations send one configured Failure notification. Successful
simulations, including expiry-only reminders and previews, send nothing.
Failure combined with an expiry reminder or forced preview sends one summary.
Without configured Apprise, nothing is sent. Delivery does not change exit status.
Set `DRY_RUN=true` for the first run. After review, set `DRY_RUN=false` and keep
valid `TZ` to permit writes. Other safety guards still apply.
For rollback, restore the saved image digest with the retained ENV and mounts;
this does not undo financial writes.

### Activate timezone-aware dividend diagnostics

1. Back up Ghostfolio and record the current connector image digest. Keep ENV,
   credentials and mounts available for rollback. Pause scheduled imports while
   preparing the upgrade, unless `DRY_RUN` is already true (nothing is written then).
2. Save the enriched Flex Query with **YYYYMMDD** dates and **HHmmss TimeZone**
   times. Check the resulting DETAIL dividend, payment-in-lieu and withholding
   cash rows for timezone-qualified `dateTime` values. Keep the accrual fields
   described above.
3. Set `TZ` to the IANA timezone used to interpret Ghostfolio historical dates,
   for example `Europe/Warsaw`. This is required for writes even without cron.
   Flex abbreviations such as `EST` and `EDT` are provenance, not the IANA `TZ`.
   Missing or invalid `TZ` forces the whole run into `DRY_RUN` before accounts
   run. One WARNING names the reason. The final notification also names it
   when Apprise is configured and `DRY_RUN` is explicitly false, even if every
   account succeeds. Successful default/blank/truthy simulations send nothing,
   including expiry-only reminders and previews. Failed simulations send Failure.
4. Upgrade the image and run once with `DRY_RUN=1 LOG_LEVEL=DEBUG` and no `CRON`,
   using the [README preview command](../README.md#dry-run-first). Read the
   container logs. Verify no forced-preview WARNING or account suffix failure.
   Review proposed imports, cash, anomaly blocks and failed-check counts before
   enabling writes. The source business day is compared with the destination
   instant's local date in `TZ`; general UTC conversion for imports is unchanged.
   Missing profile ISIN permits amount comparison, but a conflicting ISIN blocks
   identity. `skipped by historical comment` and `skipped by proximity` name the skip path
   import selection takes; neither proves that a payment is present or correct.
   A `currency context:` line shows the observed source and destination currency.
5. Keep logs private: INFO and DEBUG can include securities, dates, activity IDs,
   quantities and financial amounts. Capture needed evidence before removing
   the one-off container. Do not publish raw logs or attach them to public issues.
   The diagnostic creates no persistent report and does not repair activities.
6. After reviewing the preview, set `DRY_RUN=false`, keep valid `TZ`
   and the qualified Flex format, then resume the schedule. A missing or invalid
   suffix still fails only its account and prevents its financial writes; the
   whole run exits 1 through normal failure handling.

For runtime rollback, restore the recorded image digest and recreate the
connector with the retained ENV and mounts. Extra Flex fields can remain, but
an older runtime may not accept timezone-qualified timestamps: check its format
requirements and replay a preview before resuming writes. Restoring an image
does not undo imported activities, cash or platform changes. Restore financial
data only through your separately reviewed backup procedure.

## 3. Multi-account setup

If you have multiple IBKR sub-accounts (for example individual and joint):

- Create **one Flex Query per sub-account**, with only that sub-account selected in the account filter
- Prefer **one container per sub-account** for independent scheduling and logs. One container can also process multiple accounts using equally sized, ordered `IBKR_ACCOUNT_IDS`, `IBKR_QUERY_IDS` and `GHOST_ACCOUNT_NAMES` lists. Each query must still select only its corresponding account.
- **Exclude paper trading or management accounts** that have no positions - these will cause errors

The tool processes each IBKR account independently and syncs it to a matching Ghostfolio account.

## 4. Find the Query ID

On the Flex Queries page, click the **info icon** (circle with "i") next to your query. The Query ID is displayed in the popup. You need this as `IBKR_QUERY_IDS`.

## 5. Data availability

Activity Statement data updates once daily after market close. Running the sync during market hours will only include trades from the previous day or earlier.


[Back to the README](../README.md)
