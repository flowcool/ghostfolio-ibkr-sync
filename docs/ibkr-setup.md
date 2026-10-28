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
   >   (see [What the tool skips automatically](configuration.md#what-the-tool-skips-automatically)).
   > - **New historical candidates when widening the period**: trade-ID dedup still
   >   recognises previously synced activities, but older manual entries or activities
   >   from another importer may need reconciliation before importing the wider report.
   >
   > **Recovery after a shorter window:** compare existing history before widening
   > the query. See [historical maintenance](maintenance.md). Pair cleanup tools
   > are not qualified for v2 history; never run them there without separate
   > qualification and operation approval. A simulation does not authorize deletion.

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

New trade comments are `IBKR#v2#<source-account>:TRADE:<tradeID>`. New dividend comments are `IBKR#v2#<source-account>:DIVIDEND:<actionID>`, one per proven action. Each segment permits only `[A-Za-z0-9._-]+`, without transformation or fallback. Historical comments remain readable. See the [conversion rules](configuration.md#how-activities-are-converted) for limits and rollback requirements.

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
- Dividend Type (when available; `dividendType`)

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
- Symbol and ISIN
- Gross Rate, Gross Amount, Tax, Fee and Net Amount (available evidence)

Dividends are read from these actual cash payments, not from dividend accruals: IBKR marks accrual corrections, cancellations and payouts all with the same code, so importing every accrual reversal produces phantom and duplicate dividends. Cash Transactions also give the withholding tax actually paid. **Change in Dividend Accruals** supplies quantity evidence only; include it with the fields above.

> **Upgrading from an older version:** add the Cash Transactions section before running the new image. Without it the run logs an `ERROR`, imports trades but no dividends, and exits 1. Dividends already in Ghostfolio are recognised by their `dividend#` comment, or, for manual or legacy rows without that comment, by a dividend of the same symbol in the same account within 3 days (logged as `INFO` when the gross agrees, otherwise as one `WARNING` telling you to check IBKR and add the payment by hand if it is distinct), so they are not imported twice. Phantom dividends imported by older versions are not removed: check your IBKR dividends in Ghostfolio by hand.

### Corporate Actions (required)

Select **Corporate Actions**, even when the report contains no events. An empty
section records no observed event in that report window. A missing section holds
all BUY/SELL for that source account; independent cash keeps its existing guards.

Include ClientAccountID (`accountId`), Type, ActionID, TransactionID,
LevelOfDetail, ConID, ISIN, Symbol, Quantity, CurrencyPrimary, Date/Time **with
time zone**, Report Date, Description and Action Description. Include available
Amount, Proceeds and realized/value fields. Missing cash is different from zero.
Do not add Open Positions solely for this feature. These fields do not prove
complete lifetime coverage or authorize corporate-action treatment.

### Query output settings

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

## Existing installation links

### Prepare for structured dividend quantities

Existing installation? Use the [upgrade procedure](upgrading-to-3.0.md#prepare-for-structured-dividend-quantities).

### Simulation default since v3.0.0-rc.2

Existing installation? Use the [upgrade procedure](upgrading-to-3.0.md#simulation-default-since-v300-rc2).

### Activate timezone-aware dividend diagnostics

Existing installation? Use the [upgrade procedure](upgrading-to-3.0.md#activate-timezone-aware-dividend-diagnostics).

[Back to the README](../README.md)
