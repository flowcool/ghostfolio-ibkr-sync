# ghostfolio-ibkr-sync

Sync Interactive Brokers trades and dividends to a self-hosted [Ghostfolio](https://ghostfol.io) instance.

This tool fetches your IBKR activity statements via Flex Queries, parses trades and dividends, maps ISINs to Yahoo Finance tickers, and pushes everything into Ghostfolio. It handles multiple sub-accounts, deduplicates activities, updates cash balances, syncs dividend payments (including withholding tax), and skips FX conversions and options trades.

## Why this exists

This project replaces [agusalex/ghostfolio-sync](https://github.com/AgustaRC/ghostfolio-sync), which has several issues:

- Broken multi-account support
- No proper ISIN-to-Yahoo-ticker mapping
- Does not handle options trades gracefully (crashes instead of skipping)
- Relies on the outdated `ibflex` Python library, which breaks on newer IBKR Flex Query fields
- No cash balance syncing

This script parses the IBKR XML directly, avoids fragile third-party libraries, and gives you full control over symbol mapping.

## Docker image

```
ghcr.io/obol89/ghostfolio-ibkr-sync:latest
```

Multi-arch image (linux/amd64 and linux/arm64). New images are published automatically on every push to main.

## Prerequisites

- A running self-hosted Ghostfolio instance
- An Interactive Brokers account with Flex Web Service enabled
- Docker (for containerised runs) or Python 3.10+ with `requests` and `pyyaml`

## IBKR Setup

### 1. Enable Flex Web Service

1. Log in to IBKR Client Portal or Account Management
2. Go to **Settings** - **Reporting** - **Flex Queries**
3. At the bottom of the page, find **Flex Web Service** and click **Configure**
4. Generate a new token (or note your existing one)
5. Set the expiration to **1 year** so you do not have to rotate it frequently
6. Save the token - you will need it as `IBKR_TOKEN`

### 2. Create a Flex Query

**Important:** If you have multiple sub-accounts, create one Flex Query per sub-account. See the multi-account section below before creating your queries.

1. On the same Flex Queries page, click **Create** under **Activity Flex Query**
2. Give it a name like `Ghostfolio Sync - Individual`
3. Set the period to **Last 365 Calendar Days**

   > **⚠️ Critical — do not use a shorter period (e.g. Last Month, Last Quarter)**
   >
   > The sync script relies on the 365-day window to match opening and closing trades.
   > A shorter period causes two classes of silent failures:
   >
   > - **Missing sells**: a sell trade within the period whose matching buy is outside the
   >   window will be skipped without error (the script sees only a closing trade with no
   >   corresponding open and drops it to avoid creating phantom short positions).
   > - **Silent re-imports on period change**: if you later switch to 365 days, all trades
   >   from the gap period will look new to the dedup system — creating duplicates for any
   >   trades you had previously entered manually or synced under a different period.
   >
   > **Recovery if you already used a shorter period:**
   > The script ships with `cleanup_duplicates.py`. Run it in dry-run mode first
   > (`python cleanup_duplicates.py`), then with `--apply` once you have verified the
   > output. It patches existing manual entries with their IBKR trade ID so future syncs
   > recognise them, and removes the duplicate IBKR-synced copies.

4. Select the following sections and fields:

**Account Information:**
- ClientAccountID
- CurrencyPrimary

**Cash Report:**
- CurrencyPrimary
- EndingCash

**Trades (Execution):**

Do not use "Select All" for the Trades section. IBKR adds new fields over time that can break XML parsing. Select only these fields individually:

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

**Change in Dividend Accruals (Detail):**
- ClientAccountID
- CurrencyPrimary
- Symbol
- ISIN
- FIGI
- Date
- Quantity
- Fee
- GrossRate
- Code

5. Under **General Configuration**, set **Include Currency Rates** to **No**

   This is required. With currency rates enabled, IBKR sends non-standard currency codes (for example `RUS` instead of `RUB`) that break parsing.

6. Save the query and note the Query ID (click the info icon next to the query to find it)

### 3. Multi-account setup

If you have multiple IBKR sub-accounts (for example individual and joint):

- Create **one Flex Query per sub-account**, with only that sub-account selected in the account filter
- Run **one container per sub-account** - do not combine multiple accounts into one Flex Query
- **Exclude paper trading or management accounts** that have no positions - these will cause errors

The tool processes each IBKR account independently and syncs it to a matching Ghostfolio account.

### 4. Find the Query ID

On the Flex Queries page, click the **info icon** (circle with "i") next to your query. The Query ID is displayed in the popup. You need this as `IBKR_QUERY_IDS`.

### 5. Data availability

Activity Statement data updates once daily after market close. Running the sync during market hours will only include trades from the previous day or earlier.

## Ghostfolio Setup

### 1. Get an auth token

```bash
curl -X POST http://localhost:3333/api/v1/auth/anonymous \
  -H 'Content-Type: application/json' \
  -d '{"accessToken": "YOUR_GHOSTFOLIO_ACCESS_TOKEN"}'
```

The response contains an `authToken` field. Use this as `GHOST_TOKEN`. This token expires and will need to be regenerated periodically.

### 2. Create an IBKR Platform

1. Go to Ghostfolio **Admin** - **Platform**
2. Click **Add Platform**
3. Enter a name like `Interactive Brokers` and a URL like `https://www.interactivebrokers.com`
4. Save it

To find the Platform ID, query the API:

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
| `GHOST_TOKEN` | Yes | Ghostfolio auth bearer token | `eyJhbGciOi...` |
| `GHOST_HOST` | Yes | Ghostfolio base URL | `http://ghostfolio:3333` |
| `GHOST_CURRENCY` | No | Default currency (default: `USD`) | `EUR` |
| `GHOST_PLATFORM_ID` | No | Platform ID for IBKR in Ghostfolio | `abc123-def456` |
| `GHOST_ACCOUNT_NAMES` | No | Comma-separated Ghostfolio account names (must match account count) | `IBKR Individual` |
| `MAPPING_FILE` | No | Path to symbol mapping YAML (default: `mapping.yaml`) | `/app/mapping.yaml` |
| `CRON` | No | Cron schedule for recurring runs (Docker only) | `0 6 * * *` |
| `TZ` | No | Timezone for cron scheduling | `Europe/Warsaw` |
| `LOG_LEVEL` | No | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`) | `DEBUG` |

## Mapping File

The mapping file maps ISINs to Yahoo Finance ticker symbols. This is necessary because IBKR identifies securities by ISIN while Ghostfolio uses Yahoo Finance tickers for price data.

### Format

The file must have a `symbol_mapping` key at the top level:

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

When the script encounters an ISIN not in the mapping file, it falls back to the IBKR symbol. At the end of each run, it prints all unmapped ISINs in a format you can copy-paste directly into your mapping file:

```
Unmapped ISINs found. Add to your mapping file under symbol_mapping:

  DE0002635307: ???  # IBKR symbol: EXSA, description: ISHARES STOXX EU 600
  IE00B52MJD48: ???  # IBKR symbol: EIMI, description: ISHARES MSCI EM IMI
```

Replace `???` with the correct Yahoo Finance ticker.

## What the tool skips automatically

- **FX conversion trades** - trades with assetCategory `CASH` are currency conversions, not investment positions
- **Options trades** - trades with assetCategory `OPT` are skipped (Ghostfolio does not support options)
- **Orphaned closing trades** - if a symbol has only sell/close trades in the 365-day window with no corresponding buys, all trades for that symbol are skipped. This means the original buy predates the query period and importing the sell would create a phantom short position.
- **Net negative positions** - if the net quantity across all trades for a symbol is negative (more sold than bought in the window), all trades for that symbol are skipped for the same reason. This catches cases where IBKR uses different symbol variants for the same ISIN.
- **Dividends for filtered symbols** - if trades for a symbol are skipped for either of the above reasons, dividend entries for that symbol are also skipped, matched by both symbol name and ISIN to handle IBKR symbol variants.
- **Duplicate activities** - the tool checks existing Ghostfolio activities before importing and skips anything already present.

## Running

### Single account (one-off run)

```bash
docker run --rm \
  -e IBKR_TOKEN=your_token \
  -e IBKR_ACCOUNT_IDS=U1234567 \
  -e IBKR_QUERY_IDS=123456 \
  -e GHOST_TOKEN=your_ghost_token \
  -e GHOST_HOST=http://ghostfolio:3333 \
  -e GHOST_ACCOUNT_NAMES="IBKR Main" \
  -v ./mapping.yaml:/app/mapping.yaml \
  ghcr.io/obol89/ghostfolio-ibkr-sync:latest
```

### Without Docker

```bash
pip install -r requirements.txt
export IBKR_TOKEN=your_token
export IBKR_ACCOUNT_IDS=U1234567
export IBKR_QUERY_IDS=123456
export GHOST_TOKEN=your_ghost_token
export GHOST_HOST=http://localhost:3333
export GHOST_ACCOUNT_NAMES="IBKR Main"
python ibkr_to_ghostfolio.py
```

## Docker Compose / Portainer

For scheduled runs with multiple sub-accounts, run a separate container per account with staggered cron times. The `CRON` environment variable uses [supercronic](https://github.com/aptible/supercronic) internally.

```yaml
services:
  ibkr-sync-individual:
    image: ghcr.io/obol89/ghostfolio-ibkr-sync:latest
    container_name: ghostfolio-ibkr-sync-individual
    restart: unless-stopped
    depends_on:
      - ghostfolio
    environment:
      TZ: Europe/Warsaw
      IBKR_TOKEN: your_token
      IBKR_ACCOUNT_IDS: U1234567
      IBKR_QUERY_IDS: 123456
      GHOST_TOKEN: your_ghost_token
      GHOST_HOST: http://ghostfolio:3333
      GHOST_ACCOUNT_NAMES: "IBKR Individual"
      MAPPING_FILE: /app/mapping.yaml
      CRON: "0 6 * * *"
    volumes:
      - ./mapping.yaml:/app/mapping.yaml
    networks:
      - ghostfolio

  ibkr-sync-joint:
    image: ghcr.io/obol89/ghostfolio-ibkr-sync:latest
    container_name: ghostfolio-ibkr-sync-joint
    restart: unless-stopped
    depends_on:
      - ghostfolio
    environment:
      TZ: Europe/Warsaw
      IBKR_TOKEN: your_token
      IBKR_ACCOUNT_IDS: U7654321
      IBKR_QUERY_IDS: 654321
      GHOST_TOKEN: your_ghost_token
      GHOST_HOST: http://ghostfolio:3333
      GHOST_ACCOUNT_NAMES: "IBKR Joint"
      MAPPING_FILE: /app/mapping.yaml
      CRON: "5 6 * * *"
    volumes:
      - ./mapping.yaml:/app/mapping.yaml
    networks:
      - ghostfolio

networks:
  ghostfolio:
    external: true
```

Use `http://ghostfolio:3333` (internal Docker network hostname) rather than an external IP or localhost. Stagger the cron times by a few minutes so the two containers do not run simultaneously.

In Portainer, paste this as a stack definition and deploy it directly. Make sure the `ghostfolio` network name matches the network your Ghostfolio instance is on.

## Troubleshooting

### "positionActionID" or unknown field errors on import

You used "Select All" for the Trades section in your Flex Query. IBKR adds new fields periodically and some of them confuse the parser. Delete the query and recreate it, selecting only the individual fields listed in the setup section.

### "Unknown currency RUS" or similar invalid currency codes

You have **Include Currency Rates** enabled in your Flex Query's General Configuration. Set it to **No** and re-run.

### "AccountInformation NoneType" or account has no data

The IBKR account ID you specified has no activity (often a paper trading or master management account). Exclude it from `IBKR_ACCOUNT_IDS` and `IBKR_QUERY_IDS`.

### "not valid for the specified data source YAHOO"

An imported symbol is not recognised by Yahoo Finance. Check the unmapped ISINs output at the end of the run and add the correct Yahoo Finance ticker to your mapping file. European ETFs almost always need an explicit mapping with an exchange suffix.

### Import fails but activities were expected

The tool logs the error and continues to update the cash balance rather than crashing. Fix the failing symbol in your mapping file and re-run - duplicate detection will skip already-imported activities.

### Portfolio values are wrong after sync

Run **Gather All Data** in Ghostfolio **Admin** - **Market Data**. This fetches historical prices for all symbols. Without this step, performance charts and current values will be missing or incorrect. You may need to also check that all required currency pairs are present in **Market Data**.

### Negative positions appearing in Ghostfolio

This happens when a sell trade is imported without its corresponding buy. The tool filters these automatically using orphaned closing trade detection and net negative position detection. If you still see negative positions, they were likely imported before this filtering was in place - delete them manually in Ghostfolio.

### IBKR symbol variants (for example CSNKYz vs CSNKY)

IBKR sometimes appends a suffix to symbol names for certain listings. The tool filters by both symbol name and ISIN, so variants of the same security are handled together.

### Token expiry

The IBKR Flex Web Service token expires based on the expiry you set when generating it. Set a calendar reminder before it expires. If the script starts failing with authentication errors, generate a new token in IBKR Account Management.

The Ghostfolio auth token also expires. Regenerate it using the curl command in the Ghostfolio Setup section and update your container environment variable.

### Options trades being skipped

This is intentional. Options (`OPT`) are skipped because Ghostfolio does not support them as an asset class.

### FX conversions being skipped

Also intentional. Trades with assetCategory `CASH` are FX conversion transactions, not investment positions.

## Limitations

- **No options support** - Ghostfolio does not support options as an asset class; options trades are skipped entirely
- **365-day window** - IBKR Flex Query maximum period is 365 days. Positions opened before that window will not be imported. Fully closed positions older than 365 days are also not imported - this is expected behaviour, not a bug.
- **Yahoo Finance data quality** - price data can have gaps, delays, or missing metadata (sector, country) for non-US ETFs and smaller listings
- **Daily data only** - Activity Statements update once daily after market close; intraday syncing is not possible
- **Token management** - both the IBKR Flex token and the Ghostfolio auth token expire and require manual renewal. Set a recurring calendar reminder for the IBKR token (up to 1 year).
- **One container per account** - running multiple sub-accounts requires multiple containers with separate Flex Queries
