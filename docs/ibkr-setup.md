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

Select these fields for a predictable report. The parser ignores additional attributes, but missing required values can cause trades to be skipped:

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

Dividends are read from these actual cash payments, not from dividend accruals: IBKR marks accrual corrections, cancellations and payouts all with the same code, so accruals produce phantom and duplicate dividends. Cash Transactions also give the withholding tax actually paid. The **Change in Dividend Accruals** section is no longer used and can be removed from the query.

> **Upgrading from an older version:** add the Cash Transactions section before running the new image. Without it the run logs an `ERROR`, imports trades but no dividends, and exits 1. Dividends already in Ghostfolio are recognised by their `dividend#` comment, or by any dividend of the same symbol in the same account within 3 days, so they are not imported twice. Phantom dividends imported by older versions are not removed: check your IBKR dividends in Ghostfolio by hand.

5. Under **General Configuration**, set **Include Currency Rates** to **No**

   Currency-rate rows are not used by this tool. It does not convert the cash balance or commissions between currencies.

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


[Back to the README](../README.md)
