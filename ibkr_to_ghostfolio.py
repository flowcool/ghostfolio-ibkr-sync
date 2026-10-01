#!/usr/bin/env python3
"""Sync Interactive Brokers trades and dividends to a self-hosted Ghostfolio instance."""

import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import quote, quote_plus

import requests
import yaml

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
# urllib3 logs full request lines (incl. the IBKR token query param) at DEBUG.
logging.getLogger("urllib3").setLevel(logging.WARNING)

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
# ndcdyn = current unified endpoint (Flex Web Service V3).
# gdcdyn = legacy endpoint (V2) still seen in some account responses.
# Trailing slash is critical to prevent subdomain-spoof bypass.
IBKR_ALLOWED_STMT_PREFIXES = (
    "https://ndcdyn.interactivebrokers.com/",
    "https://gdcdyn.interactivebrokers.com/",
)

# Cash Transactions types that carry a dividend payment or its withholding tax
DIVIDEND_CASH_TYPES = ("Dividends", "Payment In Lieu Of Dividends")
WITHHOLDING_CASH_TYPE = "Withholding Tax"

# An existing Ghostfolio dividend of the same account and symbol within this
# many days counts as the same payment (manual entries, older comment formats)
DIVIDEND_MATCH_DAYS = 3


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config():
    """Load and validate configuration from environment variables."""
    required = ["IBKR_TOKEN", "IBKR_ACCOUNT_IDS", "IBKR_QUERY_IDS",
                "GHOST_TOKEN", "GHOST_HOST"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    account_ids = os.environ["IBKR_ACCOUNT_IDS"].split(",")
    query_ids = os.environ["IBKR_QUERY_IDS"].split(",")
    account_names = os.environ.get("GHOST_ACCOUNT_NAMES", "").split(",")

    if len(account_ids) != len(query_ids):
        raise RuntimeError("IBKR_ACCOUNT_IDS and IBKR_QUERY_IDS must have the same number of entries")
    if account_names != [""] and len(account_names) != len(account_ids):
        raise RuntimeError("GHOST_ACCOUNT_NAMES must match the number of IBKR_ACCOUNT_IDS")

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
        "dry_run": os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes", "on"),
    }


# ---------------------------------------------------------------------------
# Symbol mapping
# ---------------------------------------------------------------------------

def load_mapping(path):
    """Load ISIN-to-Yahoo-ticker mapping from a YAML file.

    An empty path (MAPPING_FILE="") is the explicit opt-out.  A missing or
    invalid file raises: syncing with raw IBKR symbols can book trades on the
    wrong security (ticker collisions).
    """
    if not path:
        log.warning("MAPPING_FILE is empty: proceeding without symbol mappings")
        return {}
    if not os.path.isfile(path):
        raise RuntimeError(
            f"Mapping file {path} not found (set MAPPING_FILE=\"\" to run without mappings)")
    try:
        with open(path, "r") as fh:
            data = yaml.safe_load(fh)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise RuntimeError(f"Cannot read mapping file {path}: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise RuntimeError(f"Mapping file {path}: top level must be a mapping with a symbol_mapping key")
    mapping = data.get("symbol_mapping") or {}
    if not isinstance(mapping, dict):
        raise RuntimeError(f"Mapping file {path}: symbol_mapping must be ISIN: TICKER pairs")
    bad = [k for k, v in mapping.items() if not (isinstance(k, str) and isinstance(v, str) and v)]
    if bad:
        raise RuntimeError(f"Mapping file {path}: entries {bad[:5]} are not ISIN: \"TICKER\" strings "
                           "(quote numeric tickers)")
    if not mapping:
        log.warning("Mapping file %s has no symbol_mapping entries", path)
    return mapping


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

IBKR_NETWORK_RETRY_DELAYS = (10, 30)


def _ibkr_get(url, params, timeout):
    """GET an IBKR Flex endpoint with retry on transient network errors.

    The token travels in the query string, so requests exception messages
    embed it via the URL. Redact it before re-raising, and drop the exception
    chain so no traceback can leak it either.
    """
    token = params.get("t", "")
    delays = IBKR_NETWORK_RETRY_DELAYS
    for attempt in range(len(delays) + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt < len(delays):
                log.warning("IBKR network error (attempt %d/%d), retrying in %ds: %s",
                            attempt + 1, len(delays) + 1, delays[attempt],
                            _redact(str(exc), token))
                time.sleep(delays[attempt])
                continue
            msg = _redact(str(exc), token)
        except requests.RequestException as exc:
            msg = _redact(str(exc), token)
        raise RuntimeError(f"IBKR request failed: {msg}") from None


def _redact(text, secret):
    if not secret:
        return text
    for form in {secret, quote_plus(secret), quote(secret, safe="")}:
        text = text.replace(form, "***")
    return text


def fetch_flex_report(token, query_id, max_retries=10, retry_delay=5):
    """Fetch a Flex Query report from IBKR (two-step process)."""
    log.debug("Requesting Flex Query %s from IBKR...", query_id)

    # Step 1 - send request
    resp = _ibkr_get(IBKR_SEND_URL, {"t": token, "q": query_id, "v": "3"}, timeout=30)
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
        resp = _ibkr_get(base_url, {"q": ref_code, "t": token, "v": "3"}, timeout=60)

        root = ET.fromstring(resp.text)
        status = root.findtext("Status")
        error_code = root.findtext("ErrorCode")

        # ErrorCode 1019 means statement generation is still in progress
        if status == "Warn" or error_code == "1019":
            log.debug("Statement not ready yet (attempt %d/%d), waiting %ds...",
                      attempt, max_retries, retry_delay)
            time.sleep(retry_delay)
            continue

        # Report is ready when Status is absent or FlexStatements are present
        if status is None or root.find("FlexStatements") is not None:
            log.debug("Flex Query statement received")
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


def _parse_float(value):
    """Return float(value), or None if value cannot be parsed."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


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


def parse_cash_dividends(xml_text):
    """Parse dividend payments from the Cash Transactions section.

    Structure: FlexQueryResponse > FlexStatements > FlexStatement > CashTransactions > CashTransaction
    Dividend accruals are not used: IBKR marks corrections, cancellations and
    payouts alike with code "Re", so an accrual cannot tell a payment apart.

    Rows are summed per (ISIN or symbol, date): dividends and payments in lieu
    into "amount", withholding tax (negative, refunds positive) into "tax".
    Returns None if the report has no Cash Transactions section, else a list
    of dicts with isin, symbol, currency, date, amount, tax, description.
    """
    root = ET.fromstring(xml_text)
    if next(root.iter("CashTransactions"), None) is None:
        return None
    groups = {}
    for el in root.iter("CashTransaction"):
        row = el.attrib
        tx_type = row.get("type", "")
        if tx_type not in DIVIDEND_CASH_TYPES and tx_type != WITHHOLDING_CASH_TYPE:
            continue
        # SUMMARY rows repeat the DETAIL rows when both levels are selected
        if row.get("levelOfDetail", "DETAIL").upper() != "DETAIL":
            continue
        amount = _parse_float(row.get("amount"))
        date_iso = parse_ibkr_datetime(row.get("dateTime", ""))
        if amount is None or not date_iso:
            log.warning("Skipping cash transaction %s for %s: invalid amount or date",
                        tx_type, row.get("symbol", ""))
            continue
        key = (row.get("isin") or row.get("symbol", ""), date_iso[:10])
        group = groups.setdefault(key, {
            "isin": row.get("isin", ""), "symbol": row.get("symbol", ""),
            "currency": row.get("currency", ""), "date": date_iso[:10],
            "amount": 0.0, "tax": 0.0, "description": ""})
        if row.get("currency", "") != group["currency"]:
            log.warning("Dividend %s %s: rows in %s and %s summed as %s — check by hand",
                        group["symbol"], group["date"], group["currency"],
                        row.get("currency", ""), group["currency"])
        if tx_type == WITHHOLDING_CASH_TYPE:
            group["tax"] += amount
        else:
            group["amount"] += amount
            # the last payment row carries the current rate after a correction
            if amount > 0:
                group["description"] = row.get("description", "")
    return list(groups.values())


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
    """Find a Ghostfolio account ID by name.

    Returns None if no account matches, so the caller can skip this account and
    still process the remaining ones.
    """
    data = ghost_get_accounts(config)
    accounts = data.get("accounts", data) if isinstance(data, dict) else data
    for acc in accounts:
        if acc.get("name") == account_name:
            return acc["id"]
    log.error("Ghostfolio account '%s' not found. Available: %s",
              account_name, [a["name"] for a in accounts])
    return None


def ghost_get_existing_orders(config):
    """Fetch all existing activities from Ghostfolio.

    Uses one GET /api/v1/activities (no paging).  The /api/v1/order
    endpoints were deprecated in Ghostfolio 2.248.0 and removed in 3.5.0.

    Returns a tuple of (trade_ids, dividend_comments, positions):
    - trade_ids: set of tradeIDs extracted from "IBKR#..." comments
    - dividend_comments: set of full comment strings like "dividend#SPY#2024-01-15"
    - positions: {"qty": net BUY-SELL qty by (accountId, symbol),
                  "isin_symbols": symbols seen by (accountId, isin),
                  "manual_sells": [[date, qty], ...] by (accountId, symbol) for
                                  SELLs without an IBKR# comment,
                  "manual_buys": same for BUYs without an IBKR# comment,
                  "dividend_dates": [date, ...] by (accountId, symbol) for
                                    every DIVIDEND}
    """
    url = f"{config['ghost_host']}/api/v1/activities"
    headers = ghost_headers(config["ghost_token"])
    trade_ids = set()
    dividend_comments = set()
    positions = {"qty": defaultdict(float), "isin_symbols": defaultdict(set),
                 "manual_sells": defaultdict(list), "manual_buys": defaultdict(list),
                 "dividend_dates": defaultdict(list)}

    # One request without skip/take: Ghostfolio has no take cap (default
    # MAX_SAFE_INTEGER), so one call returns one consistent list, with no
    # offset drift if activities are added or deleted between pages.
    # count comes from a separate query, so a mismatch fails closed.
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    activities = data.get("activities", [])
    total = data.get("count")
    if total != len(activities):
        raise RuntimeError(
            f"Ghostfolio returned {len(activities)} activities but reports count={total}; "
            "refusing to sync on an incomplete list (duplicates risk)")
    # quantity is a required field; Ghostfolio returns it as null only when it
    # redacts the response (user restricted view, or a token without the
    # portfolioReadValues scope), which also nulls the IBKR# comments
    if any(a.get("quantity") is None for a in activities):
        raise RuntimeError(
            "Ghostfolio redacted activity values (quantity/comment are null): "
            "disable restricted view for the GHOST_TOKEN user, or use a token "
            "with the portfolio:read:values scope; refusing to sync without "
            "existing IBKR# IDs (duplicates risk)")

    for order in activities:
        # comment is nullable in Ghostfolio, so JSON null arrives as None
        comment = order.get("comment") or ""
        if comment.startswith("IBKR#"):
            tid = comment.split("#", 1)[1]
            if tid:
                trade_ids.add(tid)
        elif comment.startswith("dividend#"):
            dividend_comments.add(comment)

        if order.get("type") == "DIVIDEND":
            symbol = (order.get("SymbolProfile") or {}).get("symbol")
            if symbol:
                positions["dividend_dates"][(order.get("accountId") or "", symbol)].append(
                    (order.get("date") or "")[:10])

        if order.get("type") in ("BUY", "SELL"):
            qty = _parse_float(order.get("quantity")) or 0.0
            if order["type"] == "SELL":
                qty = -qty
            account_id = order.get("accountId") or ""
            profile = order.get("SymbolProfile") or {}
            symbol = profile.get("symbol")
            if symbol:
                positions["qty"][(account_id, symbol)] += qty
                if profile.get("isin"):
                    positions["isin_symbols"][(account_id, profile["isin"])].add(symbol)
                if not comment.startswith("IBKR#"):
                    key = "manual_sells" if order["type"] == "SELL" else "manual_buys"
                    positions[key][(account_id, symbol)].append(
                        [(order.get("date") or "")[:10], abs(qty)])

    log.info("Scanned %d existing Ghostfolio activities", len(activities))
    return trade_ids, dividend_comments, positions


def ghost_import_activities(config, activities):
    """Import activities into Ghostfolio.  Returns True on success.

    Ghostfolio reports its own duplicate detection per activity in a 200
    response and silently skips those, so a short accepted count is not a
    failure.
    """
    if not activities:
        log.info("No new activities to import")
        return True
    if config.get("dry_run"):
        log.info("[DRY RUN] would import %d activities (no POST sent):", len(activities))
        for a in activities:
            log.info("[DRY RUN]   %-8s %-14s qty=%s price=%s %s fee=%s  %s",
                     a.get("type"), a.get("symbol"), a.get("quantity"),
                     a.get("unitPrice"), a.get("currency"), a.get("fee"),
                     a.get("comment"))
        return True
    url = f"{config['ghost_host']}/api/v1/import"
    payload = {"activities": activities}
    try:
        resp = requests.post(url, headers=ghost_headers(config["ghost_token"]),
                             json=payload, timeout=60)
    except requests.RequestException as exc:
        log.error("Import request failed: %s", exc)
        return False
    if resp.status_code >= 400:
        log.error("Import failed (%d): %s", resp.status_code, resp.text)
        log.error("Check your mapping file - a symbol may not be recognised by Ghostfolio")
        return False

    accepted = None
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and isinstance(body.get("activities"), list):
        accepted = len(body["activities"])
    if accepted is not None and accepted < len(activities):
        log.info("Ghostfolio accepted %d of %d activities (the rest were detected as duplicates)",
                 accepted, len(activities))
    else:
        log.info("Successfully imported %d activities", len(activities))
    return True


def ghost_update_cash_balance(config, account_id, balance):
    """Update the cash balance on a Ghostfolio account.  Returns True on success.

    The GET response carries far more than the update DTO accepts (aggregations,
    relations, timestamps).  Ghostfolio 3.x validates bodies with
    forbidNonWhitelisted, so echoing it back is a hard 400.  The payload is
    therefore built explicitly from the five fields UpdateAccountDto requires:
    balance, currency, id, name and platformId (nullable).

    comment, tags and isExcluded are optional in the DTO and deliberately left
    out - Prisma does not touch a column that is absent from the update, so
    omitting them preserves the stored values.  For isExcluded that also keeps
    the payload portable: it was a deprecated DTO field up to Ghostfolio 3.38.0
    and removed in 3.39.0, so sending it fails outright on newer instances.
    """
    if config.get("dry_run"):
        log.info("[DRY RUN] would set cash balance for account %s to %.2f (no PUT sent)",
                 account_id, balance)
        return True
    url = f"{config['ghost_host']}/api/v1/account/{account_id}"
    resp = requests.get(url, headers=ghost_headers(config["ghost_token"]), timeout=30)
    resp.raise_for_status()
    account_data = resp.json()

    payload = {
        "balance": balance,
        "currency": account_data["currency"],
        "id": account_id,
        "name": account_data["name"],
        "platformId": account_data.get("platformId") or config.get("ghost_platform_id") or None,
    }
    resp = requests.put(url, headers=ghost_headers(config["ghost_token"]),
                        json=payload, timeout=30)
    if resp.status_code >= 400:
        log.error("Failed to update cash balance (%d): %s", resp.status_code, resp.text)
        return False
    log.info("Updated cash balance for account %s to %.2f", account_id, balance)
    return True


# ---------------------------------------------------------------------------
# Trade conversion
# ---------------------------------------------------------------------------

# Exchanges where IBKR reports the major currency unit but the YAHOO data
# source quotes the minor (sub-cent) unit. Keyed by Yahoo symbol suffix:
#   suffix -> (ibkr_currency, yahoo_minor_currency, factor)
# Without scaling, amounts land 100x too small against the minor-unit
# SymbolProfile.
#
#   .L  (London)   GBP -> GBp  : PRODUCTION-VERIFIED against real trades (PR #18).
#   .JO (JSE)      ZAR -> ZAc  : INFERRED, not yet verified against real IBKR
#   .TA (TASE)     ILS -> ILA  : data. Yahoo quotes these in cents/agorot, but
#                                whether IBKR reports the MAJOR unit (as it does
#                                for LSE) is unconfirmed. If IBKR already reports
#                                cents/agorot for a market, remove its row here
#                                to avoid a reversed 100x error. Confirm against
#                                a real .JO/.TA trade before trusting the amounts.
MINOR_UNIT_MARKETS = {
    ".L": ("GBP", "GBp", 100),
    ".JO": ("ZAR", "ZAc", 100),
    ".TA": ("ILS", "ILA", 100),
}


def minor_unit_conversion(symbol, currency):
    """Return (currency, factor) to convert an IBKR major-unit price to the
    minor unit quoted by YAHOO for markets that quote in sub-cents.

    A Ghostfolio activity carries a single currency shared by unitPrice AND
    fee, so the caller must scale EVERY monetary field (price and
    fee/withholding tax) by the returned factor.
    """
    for suffix, (ibkr_currency, minor_currency, factor) in MINOR_UNIT_MARKETS.items():
        if symbol.endswith(suffix) and currency == ibkr_currency:
            return minor_currency, factor
    return currency, 1


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
    qty = _parse_float(quantity)
    if qty is None:
        log.warning("Invalid quantity '%s' for trade %s", quantity, trade_id)
        return None
    qty = abs(qty)

    try:
        raw_commission = float(commission)
        if raw_commission > 0:
            log.warning("Trade %s: positive ibCommission %.4g (rebate) — clamped to 0, not recorded",
                        trade_id, raw_commission)
        # Negative ibCommission = cost (normal). Positive = rebate; clamp to 0
        # since Ghostfolio fee cannot be negative. IBKR sign convention: outflows
        # are negative, inflows (rebates) are positive.
        fee = max(0.0, -raw_commission)
    except ValueError:
        log.warning("Invalid ibCommission '%s' for trade %s, defaulting fee to 0", commission, trade_id)
        fee = 0.0

    unit_price = _parse_float(trade_price)
    if unit_price is None:
        log.warning("Invalid price '%s' for trade %s", trade_price, trade_id)
        return None
    unit_price = abs(unit_price)

    # Minor-unit markets (.L GBp, .JO ZAc, .TA ILA): IBKR reports the major
    # unit, YAHOO quotes the sub-cent unit. Scale price AND fee (single shared
    # activity currency) so the fee is not silently read as sub-cents.
    minor_currency, minor_factor = minor_unit_conversion(symbol, currency)
    if minor_factor != 1:
        log.debug("Trade %s: %s %s->%s, price+fee x%d", trade_id, symbol, currency, minor_currency, minor_factor)
    currency = minor_currency
    unit_price *= minor_factor
    fee *= minor_factor

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
    """Convert a parse_cash_dividends() entry to a Ghostfolio DIVIDEND activity.

    Returns None if the dividend cannot be processed.
    Adds unmapped ISINs to the unmapped dict.
    """
    isin = dividend["isin"]
    ibkr_symbol = dividend["symbol"]
    currency = dividend["currency"]
    amount = dividend["amount"]

    if amount <= 0:
        if amount < 0:
            # a reversal dated apart from its payment: the original stays in Ghostfolio
            log.warning("Dividend %s %s: reversal of %.4g %s without a payment on the "
                        "same day — not imported, check the original dividend by hand",
                        ibkr_symbol, dividend["date"], -amount, currency)
        elif dividend["tax"]:
            log.warning("Dividend %s %s: withholding tax %.4g %s without a dividend on the "
                        "same day (tax correction?) — not imported, check by hand",
                        ibkr_symbol, dividend["date"], dividend["tax"], currency)
        return None

    symbol = resolve_symbol(isin, ibkr_symbol, mapping)
    if isin and isin in mapping:
        log.debug("Dividend %s: ISIN %s resolved via mapping -> %s", ibkr_symbol, isin, symbol)
    elif symbol:
        log.debug("Dividend %s: ISIN %s resolved via symbol fallback -> %s", ibkr_symbol, isin or "(none)", symbol)
        if isin:
            # setdefault: keep the description a trade for the same ISIN may have set
            unmapped.setdefault(isin, {"symbol": ibkr_symbol, "description": ""})
    else:
        log.warning("No symbol resolved for dividend (ISIN: %s), skipping", isin)
        return None

    # IBKR reports withholding as a negative amount; a net refund is not a fee
    wht = max(0.0, -dividend["tax"])
    if dividend["tax"] > 0:
        log.warning("Dividend %s %s: net withholding refund %.4g %s — recorded as 0",
                    ibkr_symbol, dividend["date"], dividend["tax"], currency)

    # Quantity and rate from the description ("... USD 0.25 PER SHARE ..."),
    # else book the whole amount as one unit
    match = re.search(r"\b[A-Z]{3}\s+([0-9]+(?:\.[0-9]+)?)\s+PER SHARE", dividend["description"])
    rate = _parse_float(match.group(1)) if match else None
    qty = amount / rate if rate else 1.0
    # amount is rounded to cents: snap to whole shares when within 1 %, and
    # derive the price from the amount so quantity x price equals the payment
    if round(qty) >= 1 and abs(qty - round(qty)) / round(qty) < 0.01:
        qty = float(round(qty))
    qty = round(qty, 6) or 1.0
    unit_price = amount / qty

    # Minor-unit markets (.L GBp, .JO ZAc, .TA ILA): IBKR reports the major
    # unit, YAHOO quotes the sub-cent unit. Scale rate AND withholding tax
    # (single shared activity currency) so the WHT is not read as sub-cents.
    minor_currency, minor_factor = minor_unit_conversion(symbol, currency)
    if minor_factor != 1:
        log.debug("Dividend %s: %s %s->%s, rate+wht x%d", ibkr_symbol, symbol, currency, minor_currency, minor_factor)
    currency = minor_currency
    unit_price *= minor_factor
    wht *= minor_factor

    # Key uses ISIN (stable) rather than the resolved Yahoo symbol (changes with mapping updates).
    # Fallback to the raw IBKR symbol only when ISIN is absent.
    dedup_id = isin if isin else ibkr_symbol
    comment = f"dividend#{dedup_id}#{dividend['date']}"

    return {
        "accountId": ghost_account_id,
        "comment": comment,
        "currency": currency,
        "dataSource": "YAHOO",
        "date": f"{dividend['date']}T00:00:00+00:00",
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
# Main sync logic
# ---------------------------------------------------------------------------

def _match_manual_entry(trade, entries):
    """Compare an IBKR trade with manual Ghostfolio entries of the same side
    (no IBKR# comment).

    Returns (result, entry): ("match", entry) for the closest entry within 2
    days with the same qty (consumed), ("ambiguous", None) for an entry within
    2 days but another qty (e.g. one manual entry for an order IBKR reports as
    several fills), else (None, None).
    Same +/-2 days rule as cleanup_duplicates.py (UTC vs local date shift).
    """
    iso = parse_ibkr_datetime(trade.get("dateTime", ""))
    qty = abs(_parse_float(trade.get("quantity", "0")) or 0.0)
    if not iso or not qty:
        return None, None
    day = datetime.fromisoformat(iso).date()
    best = None
    near = False
    for entry in entries:
        try:
            gap = abs((datetime.strptime(entry[0], "%Y-%m-%d").date() - day).days)
        except ValueError:
            continue
        if gap > 2:
            continue
        near = True
        if abs(entry[1] - qty) < 0.001 and (best is None or gap < best[0]):
            best = (gap, entry)
    if best:
        entries.remove(best[1])
        return "match", best[1]
    return ("ambiguous", None) if near else (None, None)


def filter_trades_by_holdings(trades, positions, ghost_account_id, mapping, existing_trade_ids):
    """Drop trades whose import would duplicate a manual entry or drive a
    Ghostfolio position negative.

    The Flex window is 365 days, so a sell of a position bought earlier comes
    without its buy. Ghostfolio usually already holds that buy (imported by an
    earlier run, or entered manually), so per resolved ticker the check is:
    Ghostfolio net qty + net of window trades not yet imported >= 0.

    Trades already entered by hand (same side and qty, +/-2 days, no IBKR#
    comment) are dropped first: silently for sells, with a WARNING for buys
    (the user can add IBKR#<tradeID> to the manual comment to silence it).
    Grouping is by the ticker the trade will be imported under;
    a position held under another symbol with the same ISIN is not guessed at
    (the sell would land on the wrong symbol) — a mapping entry fixes it.
    """
    qty_by_symbol = positions["qty"]
    manual_recorded = set()
    ambiguous = set()
    split_fills = defaultdict(list)
    groups = defaultdict(lambda: {"pending": 0.0, "symbol": "", "isin": ""})

    def match_one(trade, ticker, isin, side):
        # A manual entry may sit under any symbol sharing this ISIN (duplicate check only)
        manual = positions["manual_sells" if side == "SELL" else "manual_buys"]
        symbols = {ticker} | positions["isin_symbols"].get((ghost_account_id, isin), set())
        result = None
        for sym in sorted(symbols):
            if (ghost_account_id, sym) not in manual:
                continue
            found, entry = _match_manual_entry(trade, manual[(ghost_account_id, sym)])
            if found == "match":
                return found, entry
            result = result or found
        return result, None

    # Chronological order so each IBKR trade claims its own manual entry first
    for trade in sorted(trades, key=lambda t: t.get("dateTime", "")):
        trade_id = trade.get("tradeID", "")
        if not trade_id or trade_id in existing_trade_ids:
            continue
        isin = trade.get("isin", "")
        symbol = trade.get("symbol", "")
        ticker = resolve_symbol(isin, symbol, mapping)
        if not ticker:
            continue
        qty = _parse_float(trade.get("quantity", "0")) or 0.0
        side = "SELL" if qty < 0 else "BUY"
        result, entry = match_one(trade, ticker, isin, side)
        if result == "match":
            manual_recorded.add(trade_id)
            if side == "SELL":
                log.debug("Not importing sell %s of %s: already entered manually in Ghostfolio",
                          trade_id, ticker)
            else:
                log.warning("Not importing buy %s of %s (qty %.4g, %s): matches a manual Ghostfolio "
                            "buy of %.4g on %s — set that entry's comment to IBKR#%s to silence "
                            "this", trade_id, ticker, abs(qty), trade.get("dateTime", ""),
                            entry[1], entry[0], trade_id)
            continue
        if result == "ambiguous":
            # Maybe one order split into several fills: retried as a daily sum below
            split_fills[(side, ticker, isin, trade.get("dateTime", "")[:8])].append(trade)
            continue
        groups[ticker]["pending"] += qty
        groups[ticker]["symbol"] = groups[ticker]["symbol"] or symbol
        groups[ticker]["isin"] = groups[ticker]["isin"] or isin

    for (side, ticker, isin, _), fills in sorted(split_fills.items()):
        total = sum(_parse_float(t.get("quantity", "0")) or 0.0 for t in fills)
        summed = {"dateTime": fills[0].get("dateTime", ""), "quantity": str(total)}
        ids = [t.get("tradeID", "") for t in fills]
        if len(fills) > 1 and match_one(summed, ticker, isin, side)[0] == "match":
            manual_recorded.update(ids)
            log.log(logging.DEBUG if side == "SELL" else logging.WARNING,
                    "Not importing %ss %s of %s: fills sum to a manual Ghostfolio %s",
                    side.lower(), ",".join(ids), ticker, side.lower())
            continue
        ambiguous.update(ids)
        log.warning("Not importing %s(s) %s of %s (qty %.4g, %s): a manual Ghostfolio %s "
                    "within 2 days has another quantity — check for a duplicate by hand",
                    side.lower(), ",".join(ids), ticker, abs(total), fills[0].get("dateTime", ""),
                    side.lower())

    rejected = set()
    closed_elsewhere = 0
    for ticker, info in sorted(groups.items()):
        if info["pending"] >= 0:
            continue
        label = f"{ticker} ({info['isin'] or 'no ISIN'})"
        held = qty_by_symbol.get((ghost_account_id, ticker))
        if held is None:
            others = sorted(sym for sym in positions["isin_symbols"].get((ghost_account_id, info["isin"]), ())
                            if abs(qty_by_symbol.get((ghost_account_id, sym), 0.0)) >= 0.001)
            if others:
                rejected.add(ticker)
                log.warning("Not importing sells for %s: Ghostfolio holds this ISIN under %s — "
                            "add mapping symbol_mapping: '%s: %s'",
                            label, ", ".join(others), info["isin"], others[0])
                continue
            held = 0.0
        if held + info["pending"] >= -0.001:
            log.info("Importing sells for %s: Ghostfolio holds %.4g, net new trades %.4g",
                     label, held, info["pending"])
            continue
        rejected.add(ticker)
        if abs(held) < 0.001:
            closed_elsewhere += 1
            log.debug("Not importing %s: net new trades %.4g but Ghostfolio holds no position "
                      "(sold manually or never tracked)", label, info["pending"])
        else:
            log.error("Not importing %s: Ghostfolio holds %.4g, net new trades %.4g would go "
                      "negative — fix the position in Ghostfolio manually",
                      label, held, info["pending"])

    if closed_elsewhere or manual_recorded:
        log.info("Sells not imported: %d security(ies) with no Ghostfolio position, %d sell(s) "
                 "already entered manually — LOG_LEVEL=DEBUG for the list",
                 closed_elsewhere, len(manual_recorded))
    return [t for t in trades
            if t.get("tradeID", "") not in manual_recorded | ambiguous
            and resolve_symbol(t.get("isin", ""), t.get("symbol", ""), mapping) not in rejected]


def _dividend_date_matches(positions, activity):
    """Return the date of a Ghostfolio dividend of the same account and symbol
    within DIVIDEND_MATCH_DAYS of the activity date (any comment, or none),
    else None."""
    date = datetime.strptime(activity["date"][:10], "%Y-%m-%d")
    for existing in positions["dividend_dates"].get((activity["accountId"], activity["symbol"]), []):
        try:
            if abs((datetime.strptime(existing, "%Y-%m-%d") - date).days) <= DIVIDEND_MATCH_DAYS:
                return existing
        except ValueError:
            continue
    return None


def process_account(config, ibkr_account_id, query_id, ghost_account_name, mapping,
                    existing_trade_ids, existing_dividend_comments, positions):
    """Process a single IBKR account: fetch, parse, and sync to Ghostfolio.

    The two existing_* sets are shared across accounts and updated in place with
    whatever this account imports, so a later account will not re-import them.

    Returns a tuple of (unmapped, ok) where ok is False if any step failed.
    """
    log.info("Processing IBKR account %s (Ghostfolio: %s)", ibkr_account_id, ghost_account_name)
    ok = True

    # Fetch the Flex Query report
    try:
        xml_text = fetch_flex_report(config["ibkr_token"], query_id)
    except Exception as exc:
        log.error("Failed to fetch Flex Query for account %s: %s", ibkr_account_id, exc)
        return {}, False

    # Find the Ghostfolio account
    try:
        ghost_account_id = ghost_find_account_id(config, ghost_account_name)
    except requests.RequestException as exc:
        log.error("Failed to look up Ghostfolio account '%s': %s", ghost_account_name, exc)
        return {}, False
    if ghost_account_id is None:
        return {}, False

    # Parse trades and dividends
    trades = parse_trades(xml_text)
    dividends = parse_cash_dividends(xml_text)
    if dividends is None:
        log.error("Flex Query %s has no Cash Transactions section: dividends not synced. "
                  "Add Cash Transactions (Dividends, Payment In Lieu Of Dividends, "
                  "Withholding Tax) to the query, see README", query_id)
        ok = False
        dividends = []
    log.debug("Found %d trades and %d dividend payments in Flex Query report",
              len(trades), len(dividends))

    # CASH (FX conversions) and OPT are never imported; drop them before any gate
    trades = [t for t in trades if t.get("assetCategory", "") not in SKIP_ASSET_CATEGORIES]

    # Trade gate: Ghostfolio holdings + not-yet-imported trades must not go negative
    trades = filter_trades_by_holdings(trades, positions, ghost_account_id, mapping,
                                       existing_trade_ids)

    # Convert and filter trades
    unmapped = {}
    activities = []
    skipped_dup = 0
    skipped_other = 0

    for trade in trades:
        trade_id = trade.get("tradeID", "")
        if not trade_id:
            log.warning("Skipping trade for %s (%s) — missing tradeID, cannot deduplicate safely",
                        trade.get("symbol") or trade.get("isin") or "unknown",
                        trade.get("dateTime", ""))
            skipped_other += 1
            continue
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

    # Cash Transactions only pay shares actually held, so a symbol without a
    # buy in the 365-day window (long-held, partly sold) still gets its dividends
    for div in dividends:
        activity = convert_dividend_to_activity(div, ghost_account_id, mapping, unmapped)
        if activity:
            date_part = activity["comment"].rsplit("#", 1)[-1]
            old_comment = f"dividend#{activity['symbol']}#{date_part}"
            if (activity["comment"] in existing_dividend_comments
                    or old_comment in existing_dividend_comments):
                div_skipped_dup += 1
                continue
            matched = _dividend_date_matches(positions, activity)
            if matched:
                log.info("Dividend %s %s: Ghostfolio has a dividend of this symbol on %s, "
                         "treated as the same payment (not imported)",
                         activity["symbol"], date_part, matched)
                div_skipped_dup += 1
            else:
                div_activities.append(activity)

    log.info("New dividend activities: %d, duplicates skipped: %d",
             len(div_activities), div_skipped_dup)

    activities.extend(div_activities)

    # Import all activities
    if activities:
        if ghost_import_activities(config, activities):
            for activity in activities:
                comment = activity["comment"]
                if comment.startswith("IBKR#"):
                    tid = comment.split("#", 1)[1]
                    if tid:
                        existing_trade_ids.add(tid)
                    # Keep holdings current for a later account mapped to the same Ghostfolio account
                    sign = -1.0 if activity["type"] == "SELL" else 1.0
                    positions["qty"][(activity["accountId"], activity["symbol"])] += sign * activity["quantity"]
                elif comment.startswith("dividend#"):
                    existing_dividend_comments.add(comment)
                    positions["dividend_dates"][(activity["accountId"], activity["symbol"])].append(
                        activity["date"][:10])
        else:
            ok = False

    # Update cash balance (independent of import success)
    try:
        cash_balance = parse_cash_report(xml_text)
        if cash_balance is not None:
            if not ghost_update_cash_balance(config, ghost_account_id, cash_balance):
                ok = False
        else:
            log.warning("No BASE_SUMMARY cash balance found in report")
    except Exception as exc:
        log.error("Failed to update cash balance: %s", exc)
        ok = False

    return unmapped, ok


def main():
    """Main entry point.  Returns a process exit code (0 = clean, 1 = failure)."""
    log.info("Starting IBKR to Ghostfolio sync (version %s)", os.environ.get("APP_VERSION", "dev"))

    try:
        config = load_config()
    except RuntimeError as exc:
        log.error("Configuration error: %s", exc)
        sys.exit(1)
    if config["dry_run"]:
        log.info("DRY RUN enabled (DRY_RUN) — no writes will be sent to Ghostfolio")
    try:
        mapping = load_mapping(config["mapping_file"])
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1
    log.info("Loaded %d symbol mappings", len(mapping))

    account_ids = config["account_ids"]
    query_ids = config["query_ids"]
    account_names = config["account_names"]

    # If no account names provided, use account IDs as names
    if not account_names:
        account_names = account_ids
        log.warning("No GHOST_ACCOUNT_NAMES provided, using IBKR account IDs as Ghostfolio account names")

    # Fetch existing activities once for the whole run; process_account keeps the
    # sets current as it imports
    try:
        existing_trade_ids, existing_dividend_comments, positions = ghost_get_existing_orders(config)
    except (requests.RequestException, RuntimeError) as exc:
        log.error("Failed to fetch existing Ghostfolio activities: %s", exc)
        return 1
    log.info("Found %d existing trade activities and %d existing dividend activities in Ghostfolio",
             len(existing_trade_ids), len(existing_dividend_comments))

    all_unmapped = {}
    failed_accounts = []

    for ibkr_id, qid, gf_name in zip(account_ids, query_ids, account_names):
        unmapped, ok = process_account(config, ibkr_id, qid, gf_name, mapping,
                                       existing_trade_ids, existing_dividend_comments, positions)
        all_unmapped.update(unmapped)
        if not ok:
            failed_accounts.append(ibkr_id)

    # Log unmapped ISINs: one self-contained line per ISIN so each survives line-based log viewers.
    # Trades are reported only on their import run (deduped before conversion);
    # dividends are converted before dedup, so they repeat on every run.
    for isin, info in sorted(all_unmapped.items()):
        symbol = info.get("symbol") or ""
        desc = info.get("description") or ""
        log.warning("Unmapped ISIN %s (%s) uses IBKR symbol %r as ticker (fallback) — "
                    "verify in Ghostfolio or add to mapping symbol_mapping: '%s: <yahoo ticker>'",
                    isin, desc or "no description", symbol, isin)
    if not all_unmapped:
        log.info("No unmapped ISINs in this run")

    if failed_accounts:
        log.error("Sync completed with errors for %d of %d account(s): %s",
                  len(failed_accounts), len(account_ids), ", ".join(failed_accounts))
        return 1

    log.info("Sync complete")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log.exception("Sync failed with an unhandled error")
        sys.exit(1)
