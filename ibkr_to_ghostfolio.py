#!/usr/bin/env python3
"""Sync Interactive Brokers trades and dividends to a self-hosted Ghostfolio instance."""

import logging
import os
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone

import requests
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

IBKR_SEND_URL = (
    "https://ndcdyn.interactivebrokers.com/AccountManagement"
    "/FlexWebService/SendRequest"
)
IBKR_STMT_URL = (
    "https://ndcdyn.interactivebrokers.com/AccountManagement"
    "/FlexWebService/GetStatement"
)

SKIP_ASSET_CATEGORIES = {"CASH", "OPT"}

# Both are legitimate IBKR Flex Web Service statement endpoints.
# ndcdyn = US/Americas, gdcdyn = EU/global (confirmed in IBKR Flex Web Service docs).
# Trailing slash is critical to prevent subdomain-spoof bypass.
IBKR_ALLOWED_STMT_PREFIXES = (
    "https://ndcdyn.interactivebrokers.com/",
    "https://gdcdyn.interactivebrokers.com/",
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config():
    """Load and validate configuration from environment variables."""
    required = ["IBKR_TOKEN", "IBKR_ACCOUNT_IDS", "IBKR_QUERY_IDS",
                "GHOST_TOKEN", "GHOST_HOST"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)

    account_ids = os.environ["IBKR_ACCOUNT_IDS"].split(",")
    query_ids = os.environ["IBKR_QUERY_IDS"].split(",")
    account_names = os.environ.get("GHOST_ACCOUNT_NAMES", "").split(",")

    if len(account_ids) != len(query_ids):
        log.error("IBKR_ACCOUNT_IDS and IBKR_QUERY_IDS must have the same number of entries")
        sys.exit(1)
    if account_names != [""] and len(account_names) != len(account_ids):
        log.error("GHOST_ACCOUNT_NAMES must match the number of IBKR_ACCOUNT_IDS")
        sys.exit(1)

    return {
        "ibkr_token": os.environ["IBKR_TOKEN"],
        "account_ids": [a.strip() for a in account_ids],
        "query_ids": [q.strip() for q in query_ids],
        "account_names": [n.strip() for n in account_names] if account_names != [""] else [],
        "ghost_token": os.environ["GHOST_TOKEN"],
        "ghost_host": os.environ["GHOST_HOST"].rstrip("/"),
        "ghost_currency": os.environ.get("GHOST_CURRENCY", "USD"),
        "ghost_platform_id": os.environ.get("GHOST_PLATFORM_ID", ""),
        "mapping_file": os.environ.get("MAPPING_FILE", "mapping.yaml"),
    }


# ---------------------------------------------------------------------------
# Symbol mapping
# ---------------------------------------------------------------------------

def load_mapping(path):
    """Load ISIN-to-Yahoo-ticker mapping from a YAML file."""
    if not os.path.isfile(path):
        log.warning("Mapping file %s not found, proceeding without mappings", path)
        return {}
    with open(path, "r") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("symbol_mapping", {})


def resolve_symbol(isin, ibkr_symbol, mapping):
    """Resolve an ISIN to a Yahoo Finance ticker.

    Returns the mapped ticker, or falls back to the IBKR symbol if no mapping
    exists.  Returns None only when both are empty.
    """
    if isin and isin in mapping:
        return mapping[isin]
    if ibkr_symbol:
        return ibkr_symbol
    return None


# ---------------------------------------------------------------------------
# IBKR Flex Query fetching
# ---------------------------------------------------------------------------

def fetch_flex_report(token, query_id, max_retries=10, retry_delay=5):
    """Fetch a Flex Query report from IBKR (two-step process)."""
    log.info("Requesting Flex Query %s from IBKR...", query_id)

    # Step 1 - send request
    resp = requests.get(IBKR_SEND_URL, params={"t": token, "q": query_id, "v": "3"},
                        timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)

    status = root.findtext("Status")
    if status != "Success":
        error_msg = root.findtext("ErrorMessage", "unknown error")
        raise RuntimeError(f"IBKR SendRequest failed: {error_msg}")

    ref_code = root.findtext("ReferenceCode")
    base_url = root.findtext("Url")
    if not base_url or not base_url.startswith(IBKR_ALLOWED_STMT_PREFIXES):
        raise RuntimeError(f"Unexpected IBKR statement URL: {base_url!r}")
    log.info("Got reference code %s, fetching statement...", ref_code)

    # Step 2 - poll for statement
    for attempt in range(1, max_retries + 1):
        resp = requests.get(base_url, params={"q": ref_code, "t": token, "v": "3"},
                            timeout=60)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        status = root.findtext("Status")
        error_code = root.findtext("ErrorCode")

        # ErrorCode 1019 means statement generation is still in progress
        if status == "Warn" or error_code == "1019":
            log.info("Statement not ready yet (attempt %d/%d), waiting %ds...",
                     attempt, max_retries, retry_delay)
            time.sleep(retry_delay)
            continue

        # Report is ready when Status is absent or FlexStatements are present
        if status is None or root.find("FlexStatements") is not None:
            log.info("Flex Query statement received")
            return resp.text

        error_msg = root.findtext("ErrorMessage", "unknown error")
        raise RuntimeError(f"IBKR GetStatement failed: {error_msg}")

    raise RuntimeError("Timed out waiting for IBKR Flex Query statement")


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

def parse_trades(xml_text):
    """Parse Trade elements from the Flex Query XML.

    Structure: FlexQueryResponse > FlexStatements > FlexStatement > Trades > Trade
    Skips AssetSummary and other non-Trade children of Trades elements.
    """
    root = ET.fromstring(xml_text)
    trades = []
    for trades_el in root.iter("Trades"):
        for child in trades_el:
            if child.tag == "Trade":
                trades.append(dict(child.attrib))
    return trades


def parse_cash_report(xml_text):
    """Return the ending cash balance in base currency from a Flex Query XML.

    Structure: FlexQueryResponse > FlexStatements > FlexStatement > CashReport > CashReportCurrency
    Uses the entry where currency="BASE_SUMMARY", which holds the total in base currency.
    Returns a float, or None if the entry is absent or unparseable.
    """
    root = ET.fromstring(xml_text)
    for entry in root.iter("CashReportCurrency"):
        if entry.attrib.get("currency") == "BASE_SUMMARY":
            ending_cash = entry.attrib.get("endingCash", "")
            if ending_cash:
                try:
                    return float(ending_cash)
                except ValueError:
                    pass
    return None


def parse_dividends(xml_text):
    """Parse ChangeInDividendAccrual elements from the Flex Query XML.

    Structure: FlexQueryResponse > FlexStatements > FlexStatement > ChangeInDividendAccruals > ChangeInDividendAccrual
    Only returns entries where the code attribute contains "Re" (realized).
    Entries with code "Pr" (pending/reversal) are skipped.
    """
    root = ET.fromstring(xml_text)
    dividends = []
    for el in root.iter("ChangeInDividendAccrual"):
        code = el.attrib.get("code", "")
        if "Re" in code:
            dividends.append(dict(el.attrib))
    return dividends


# ---------------------------------------------------------------------------
# Ghostfolio API helpers
# ---------------------------------------------------------------------------

def ghost_headers(token):
    """Return common headers for Ghostfolio API calls."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def ghost_get_accounts(config):
    """Fetch all accounts from Ghostfolio."""
    url = f"{config['ghost_host']}/api/v1/account"
    resp = requests.get(url, headers=ghost_headers(config["ghost_token"]), timeout=30)
    resp.raise_for_status()
    return resp.json()


def ghost_find_account_id(config, account_name):
    """Find a Ghostfolio account ID by name."""
    data = ghost_get_accounts(config)
    accounts = data.get("accounts", data) if isinstance(data, dict) else data
    for acc in accounts:
        if acc.get("name") == account_name:
            return acc["id"]
    log.error("Ghostfolio account '%s' not found. Available: %s",
              account_name, [a["name"] for a in accounts])
    sys.exit(1)


def ghost_get_existing_orders(config):
    """Fetch all existing orders from Ghostfolio.

    Returns a tuple of (trade_ids, dividend_comments):
    - trade_ids: set of tradeIDs extracted from "IBKR#..." comments
    - dividend_comments: set of full comment strings like "dividend#SPY#2024-01-15"
    """
    url = f"{config['ghost_host']}/api/v1/order"
    resp = requests.get(url, headers=ghost_headers(config["ghost_token"]), timeout=60)
    resp.raise_for_status()
    data = resp.json()
    trade_ids = set()
    dividend_comments = set()
    activities = data.get("activities", data) if isinstance(data, dict) else data
    for order in activities:
        comment = order.get("comment", "")
        if comment:
            if comment.startswith("IBKR#"):
                trade_ids.add(comment.split("#", 1)[1])
            elif comment.startswith("dividend#"):
                dividend_comments.add(comment)
    return trade_ids, dividend_comments


def ghost_import_activities(config, activities):
    """Import activities into Ghostfolio."""
    if not activities:
        log.info("No new activities to import")
        return
    url = f"{config['ghost_host']}/api/v1/import"
    payload = {"activities": activities}
    resp = requests.post(url, headers=ghost_headers(config["ghost_token"]),
                         json=payload, timeout=60)
    if resp.status_code >= 400:
        log.error("Import failed (%d): %s", resp.status_code, resp.text)
        log.error("Check your mapping file - a symbol may not be recognised by Ghostfolio")
        return
    log.info("Successfully imported %d activities", len(activities))


def ghost_update_cash_balance(config, account_id, balance):
    """Update the cash balance on a Ghostfolio account."""
    url = f"{config['ghost_host']}/api/v1/account/{account_id}"
    resp = requests.get(url, headers=ghost_headers(config["ghost_token"]), timeout=30)
    resp.raise_for_status()
    account_data = resp.json()

    payload = {
        "balance": balance,
        "currency": account_data["currency"],
        "id": account_id,
        "isExcluded": account_data.get("isExcluded", False),
        "name": account_data["name"],
        "platformId": account_data.get("platformId") or config.get("ghost_platform_id") or None,
    }
    resp = requests.put(url, headers=ghost_headers(config["ghost_token"]),
                        json=payload, timeout=30)
    if resp.status_code >= 400:
        log.error("Failed to update cash balance (%d): %s", resp.status_code, resp.text)
    else:
        log.info("Updated cash balance for account %s to %.2f", account_id, balance)


# ---------------------------------------------------------------------------
# Trade conversion
# ---------------------------------------------------------------------------

def convert_trade_to_activity(trade, ghost_account_id, mapping, unmapped):
    """Convert an IBKR trade dict to a Ghostfolio activity dict.

    Returns None if the trade should be skipped.
    Adds unmapped ISINs to the unmapped dict.
    """
    asset_category = trade.get("assetCategory", "")
    if asset_category in SKIP_ASSET_CATEGORIES:
        log.debug("Skipping %s trade: %s", asset_category, trade.get("symbol", ""))
        return None

    isin = trade.get("isin", "")
    ibkr_symbol = trade.get("symbol", "")
    description = trade.get("description", "")
    trade_id = trade.get("tradeID", "")
    currency = trade.get("currency", "")
    buy_sell = trade.get("buySell", "")
    quantity = trade.get("quantity", "0")
    trade_price = trade.get("tradePrice", "0")
    commission = trade.get("ibCommission", "0")
    date_time = trade.get("dateTime", "")

    symbol = resolve_symbol(isin, ibkr_symbol, mapping)
    if isin and isin in mapping:
        log.debug("Trade %s: ISIN %s resolved via mapping -> %s", trade_id, isin, symbol)
    elif symbol:
        log.debug("Trade %s: ISIN %s resolved via symbol fallback -> %s", trade_id, isin or "(none)", symbol)
        if isin:
            unmapped[isin] = {"symbol": ibkr_symbol, "description": description}
    else:
        log.warning("No symbol resolved for trade %s (ISIN: %s), skipping", trade_id, isin)
        return None

    # Parse quantity and fee
    try:
        qty = abs(float(quantity))
    except ValueError:
        log.warning("Invalid quantity '%s' for trade %s", quantity, trade_id)
        return None

    try:
        fee = abs(float(commission))
    except ValueError:
        fee = 0.0

    try:
        unit_price = abs(float(trade_price))
    except ValueError:
        log.warning("Invalid price '%s' for trade %s", trade_price, trade_id)
        return None

    # Determine activity type
    activity_type = "BUY" if buy_sell == "BUY" else "SELL"

    # Parse date - IBKR format is typically "YYYYMMDD;HHMMSS" or "YYYY-MM-DD, HH:MM:SS"
    iso_date = parse_ibkr_datetime(date_time)
    if not iso_date:
        log.warning("Could not parse dateTime '%s' for trade %s", date_time, trade_id)
        return None

    return {
        "accountId": ghost_account_id,
        "comment": f"IBKR#{trade_id}",
        "currency": currency,
        "dataSource": "YAHOO",
        "date": iso_date,
        "fee": fee,
        "quantity": qty,
        "symbol": symbol,
        "type": activity_type,
        "unitPrice": unit_price,
    }


def convert_dividend_to_activity(dividend, ghost_account_id, mapping, unmapped):
    """Convert an IBKR dividend accrual dict to a Ghostfolio DIVIDEND activity.

    Returns None if the dividend cannot be processed.
    Adds unmapped ISINs to the unmapped dict.
    """
    isin = dividend.get("isin", "")
    ibkr_symbol = dividend.get("symbol", "")
    currency = dividend.get("currency", "")
    date_str = dividend.get("date", "")
    quantity = dividend.get("quantity", "0")
    gross_rate = dividend.get("grossRate", "0")
    fee = dividend.get("fee", "0")

    symbol = resolve_symbol(isin, ibkr_symbol, mapping)
    if isin and isin in mapping:
        log.debug("Dividend %s: ISIN %s resolved via mapping -> %s", ibkr_symbol, isin, symbol)
    elif symbol:
        log.debug("Dividend %s: ISIN %s resolved via symbol fallback -> %s", ibkr_symbol, isin or "(none)", symbol)
        if isin:
            unmapped[isin] = {"symbol": ibkr_symbol, "description": ""}
    else:
        log.warning("No symbol resolved for dividend (ISIN: %s), skipping", isin)
        return None

    try:
        qty = abs(float(quantity))
    except ValueError:
        log.warning("Invalid quantity '%s' for dividend %s", quantity, ibkr_symbol)
        return None

    try:
        unit_price = abs(float(gross_rate))
    except ValueError:
        log.warning("Invalid grossRate '%s' for dividend %s", gross_rate, ibkr_symbol)
        return None

    try:
        wht = abs(float(fee))
    except ValueError:
        wht = 0.0

    iso_date = parse_ibkr_datetime(date_str)
    if not iso_date:
        log.warning("Could not parse date '%s' for dividend %s", date_str, ibkr_symbol)
        return None

    # Use date portion only for the comment key (YYYY-MM-DD)
    date_key = iso_date[:10]
    comment = f"dividend#{symbol}#{date_key}"

    return {
        "accountId": ghost_account_id,
        "comment": comment,
        "currency": currency,
        "dataSource": "YAHOO",
        "date": iso_date,
        "fee": wht,
        "quantity": qty,
        "symbol": symbol,
        "type": "DIVIDEND",
        "unitPrice": unit_price,
    }


def parse_ibkr_datetime(dt_str):
    """Parse IBKR datetime string to ISO 8601 format."""
    if not dt_str:
        return None

    # Try common IBKR formats
    for fmt in ("%Y%m%d;%H%M%S", "%Y-%m-%d, %H:%M:%S", "%Y-%m-%d;%H:%M:%S",
                "%Y%m%d", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(dt_str.strip(), fmt)
            return parsed.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    return None


# ---------------------------------------------------------------------------
# Trade filtering
# ---------------------------------------------------------------------------

def filter_orphaned_closing_trades(trades):
    """Remove trades for symbols that have closing trades but no opening trades.

    IBKR Flex Query covers at most 365 days. A position bought before that
    window but sold within it produces only closing ("C") trades in the export.
    Importing those sells without the corresponding buys would create phantom
    short positions in Ghostfolio.

    Rules:
    - Symbol has only "C" trades  → skip all (orphaned closes, buy predates window)
    - Symbol has both "O" and "C" → keep all (round-trip captured in full)
    - Symbol has only "O" trades  → keep all (currently open position)

    Trades without an openCloseIndicator are kept unconditionally.

    Returns (filtered_trades, orphaned_symbols, orphaned_isins, dropped_count).
    """
    # Group trade indices by symbol, tracking which indicators appear
    symbol_info = defaultdict(lambda: {"has_open": False, "has_close": False, "isin": ""})
    for trade in trades:
        indicator = trade.get("openCloseIndicator", "")
        symbol = trade.get("symbol", "")
        if not symbol or not indicator:
            continue
        if indicator == "O":
            symbol_info[symbol]["has_open"] = True
        elif indicator == "C":
            symbol_info[symbol]["has_close"] = True
        if not symbol_info[symbol]["isin"]:
            symbol_info[symbol]["isin"] = trade.get("isin", "")

    orphaned_symbols = {
        sym for sym, info in symbol_info.items()
        if info["has_close"] and not info["has_open"]
    }
    orphaned_isins = {
        symbol_info[sym]["isin"]
        for sym in orphaned_symbols
        if symbol_info[sym]["isin"]
    }

    for sym in sorted(orphaned_symbols):
        isin = symbol_info[sym]["isin"]
        log.warning(
            "Skipping %s (%s) - has closing trades but no opening trades in the "
            "365-day window. These are fully closed positions where the buy "
            "predates the query period.",
            sym, isin or "no ISIN",
        )

    filtered = [
        t for t in trades
        if t.get("symbol", "") not in orphaned_symbols
        and t.get("isin", "") not in orphaned_isins
    ]
    dropped = len(trades) - len(filtered)
    return filtered, orphaned_symbols, orphaned_isins, dropped


def filter_net_negative_positions(trades):
    """Remove trades for symbols whose net quantity across the window is negative.

    A net negative position means more shares were sold than bought within the
    365-day query period, which implies the original buy predates the window.
    Importing such trades would create a phantom short position in Ghostfolio.

    Grouping is by ISIN so that symbol variants (e.g. "CSNKY" / "CSNKYz")
    for the same security are treated as one position.  Falls back to symbol
    when ISIN is absent.

    IBKR encodes quantity as positive for buys and negative for sells, so
    net = sum(quantity) across all trades for the group.

    Returns (filtered_trades, negative_symbols, negative_isins, dropped_count).
    """
    # key → canonical symbol / isin for logging, net qty, all symbol variants
    group_info = defaultdict(lambda: {"symbol": "", "isin": "", "net_qty": 0.0, "symbols": set()})
    for trade in trades:
        symbol = trade.get("symbol", "")
        isin = trade.get("isin", "")
        key = isin if isin else symbol
        if not key:
            continue
        try:
            qty = float(trade.get("quantity", "0"))
        except ValueError:
            qty = 0.0
        group_info[key]["net_qty"] += qty
        group_info[key]["symbols"].add(symbol)
        if not group_info[key]["isin"]:
            group_info[key]["isin"] = isin
        if not group_info[key]["symbol"]:
            group_info[key]["symbol"] = symbol

    negative_keys = {key for key, info in group_info.items() if info["net_qty"] < -0.001}

    negative_symbols = set()
    negative_isins = set()
    for key in sorted(negative_keys):
        info = group_info[key]
        negative_symbols.update(info["symbols"])
        if info["isin"]:
            negative_isins.add(info["isin"])
        log.warning(
            "Skipping %s (%s) - net position is negative (%.4g shares). "
            "The original buy predates the 365-day query window.",
            info["symbol"], info["isin"] or "no ISIN", info["net_qty"],
        )

    filtered = [
        t for t in trades
        if t.get("symbol", "") not in negative_symbols
        and t.get("isin", "") not in negative_isins
    ]
    dropped = len(trades) - len(filtered)
    return filtered, negative_symbols, negative_isins, dropped


# ---------------------------------------------------------------------------
# Main sync logic
# ---------------------------------------------------------------------------

def process_account(config, ibkr_account_id, query_id, ghost_account_name, mapping):
    """Process a single IBKR account: fetch, parse, and sync to Ghostfolio."""
    log.info("Processing IBKR account %s (Ghostfolio: %s)", ibkr_account_id, ghost_account_name)

    # Fetch the Flex Query report
    try:
        xml_text = fetch_flex_report(config["ibkr_token"], query_id)
    except Exception as exc:
        log.error("Failed to fetch Flex Query for account %s: %s", ibkr_account_id, exc)
        return {}

    # Find the Ghostfolio account
    ghost_account_id = ghost_find_account_id(config, ghost_account_name)

    # Parse trades and dividends
    trades = parse_trades(xml_text)
    dividends = parse_dividends(xml_text)
    log.info("Found %d trades and %d dividend entries in Flex Query report",
             len(trades), len(dividends))

    # Drop orphaned closing trades (buy predates the 365-day query window)
    trades, orphaned_symbols, orphaned_isins, dropped_orphans = filter_orphaned_closing_trades(trades)
    if dropped_orphans:
        log.info("Dropped %d orphaned closing trade(s) with no matching open in window",
                 dropped_orphans)

    # Drop trades where net quantity across the window is negative
    trades, negative_symbols, negative_isins, dropped_negative = filter_net_negative_positions(trades)
    if dropped_negative:
        log.info("Dropped %d trade(s) with net negative position in window", dropped_negative)

    # Combined skip sets for dividend filtering
    skip_symbols = orphaned_symbols | negative_symbols
    skip_isins = orphaned_isins | negative_isins

    # Get existing orders to avoid duplicates
    existing_trade_ids, existing_dividend_comments = ghost_get_existing_orders(config)
    log.info("Found %d existing trade activities and %d existing dividend activities in Ghostfolio",
             len(existing_trade_ids), len(existing_dividend_comments))

    # Convert and filter trades
    unmapped = {}
    activities = []
    skipped_dup = 0
    skipped_other = 0

    for trade in trades:
        trade_id = trade.get("tradeID", "")
        if trade_id in existing_trade_ids:
            skipped_dup += 1
            continue

        activity = convert_trade_to_activity(trade, ghost_account_id, mapping, unmapped)
        if activity:
            activities.append(activity)
        else:
            asset_cat = trade.get("assetCategory", "")
            if asset_cat not in SKIP_ASSET_CATEGORIES:
                skipped_other += 1

    log.info("New trade activities: %d, duplicates skipped: %d, other skipped: %d",
             len(activities), skipped_dup, skipped_other)

    # Convert and filter dividends
    div_activities = []
    div_skipped_dup = 0

    for div in dividends:
        div_symbol = div.get("symbol", "")
        div_isin = div.get("isin", "")
        if div_symbol in skip_symbols or (div_isin and div_isin in skip_isins):
            log.debug("Skipping dividend for %s - position was fully closed (orphaned)", div_symbol)
            continue

        activity = convert_dividend_to_activity(div, ghost_account_id, mapping, unmapped)
        if activity:
            if activity["comment"] in existing_dividend_comments:
                div_skipped_dup += 1
            else:
                div_activities.append(activity)

    log.info("New dividend activities: %d, duplicates skipped: %d",
             len(div_activities), div_skipped_dup)

    activities.extend(div_activities)

    # Import all activities
    if activities:
        ghost_import_activities(config, activities)

    # Update cash balance
    try:
        cash_balance = parse_cash_report(xml_text)
        if cash_balance is not None:
            ghost_update_cash_balance(config, ghost_account_id, cash_balance)
        else:
            log.info("No BASE_SUMMARY cash balance found in report")
    except Exception as exc:
        log.error("Failed to update cash balance: %s", exc)

    return unmapped


def main():
    """Main entry point."""
    log.info("Starting IBKR to Ghostfolio sync")

    config = load_config()
    mapping = load_mapping(config["mapping_file"])
    log.info("Loaded %d symbol mappings", len(mapping))

    account_ids = config["account_ids"]
    query_ids = config["query_ids"]
    account_names = config["account_names"]

    # If no account names provided, use account IDs as names
    if not account_names:
        account_names = account_ids
        log.warning("No GHOST_ACCOUNT_NAMES provided, using IBKR account IDs as Ghostfolio account names")

    all_unmapped = {}

    for ibkr_id, qid, gf_name in zip(account_ids, query_ids, account_names):
        unmapped = process_account(config, ibkr_id, qid, gf_name, mapping)
        all_unmapped.update(unmapped)

    # Print unmapped ISINs summary
    if all_unmapped:
        print("\n" + "=" * 60)
        print("Unmapped ISINs found. Add to your mapping file under symbol_mapping:")
        print()
        for isin, info in sorted(all_unmapped.items()):
            symbol = info.get("symbol", "")
            desc = info.get("description", "")
            print(f"  {isin}: ???  # IBKR symbol: {symbol}, description: {desc}")
        print("=" * 60 + "\n")
    else:
        log.info("All ISINs resolved via mapping or symbol fallback")

    log.info("Sync complete")


if __name__ == "__main__":
    main()
