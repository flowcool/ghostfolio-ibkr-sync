#!/usr/bin/env python3
"""Sync Interactive Brokers trades and dividends to a self-hosted Ghostfolio instance."""

import base64
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, DecimalException, localcontext
from math import ceil, isfinite
from zoneinfo import ZoneInfo
from urllib.parse import quote, quote_plus, urlsplit

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
IBKR_MAX_XML_BYTES = 10 * 1024 * 1024

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

def dry_run_requested():
    """True when DRY_RUN is truthy; readable even when the rest of the config is invalid."""
    return os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes", "on")


def timezone_preview_reason():
    """Return why TZ forces a whole-run preview, or None when TZ is a valid IANA zone."""
    name = os.environ.get("TZ", "").strip()
    if not name:
        return "TZ is missing"
    try:
        ZoneInfo(name)
    except Exception:
        return "TZ is not a valid IANA timezone"
    return None


def _env_secret(name):
    """Return a credential verbatim, or None when absent, empty or whitespace only."""
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return value


def validate_ghost_host(host):
    """Refuse a GHOST_HOST that could send the access token somewhere unintended.

    The message is fixed: the host may carry userinfo credentials.
    """
    try:
        parts = urlsplit(host)
        port_ok = parts.port is None or parts.port > 0
    except ValueError:
        port_ok = False
    if (not port_ok
            or parts.scheme not in ("http", "https")
            or not parts.hostname
            or "@" in parts.netloc
            or parts.query or parts.fragment or "?" in host or "#" in host
            or any(c.isspace() or ord(c) < 0x20 or ord(c) == 0x7f or c == "\\" for c in host)):
        raise RuntimeError("GHOST_HOST must be an http(s) URL without credentials, "
                           "query, fragment, whitespace or control characters")


def load_config():
    """Load and validate configuration from environment variables.

    Ghostfolio credentials: exactly one of GHOST_TOKEN (a bearer used as is,
    legacy) or GHOST_ACCESS_TOKEN (the security token, exchanged for a bearer
    once per run by main).
    """
    ghost_token = _env_secret("GHOST_TOKEN")
    access_token = _env_secret("GHOST_ACCESS_TOKEN")
    missing = [k for k in ("IBKR_TOKEN", "IBKR_ACCOUNT_IDS", "IBKR_QUERY_IDS") if not os.environ.get(k)]
    if ghost_token is None and access_token is None:
        missing.append("GHOST_TOKEN or GHOST_ACCESS_TOKEN")
    if not os.environ.get("GHOST_HOST"):
        missing.append("GHOST_HOST")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    if ghost_token is not None and access_token is not None:
        raise RuntimeError("Set only one of GHOST_TOKEN or GHOST_ACCESS_TOKEN, not both")
    ghost_host = os.environ["GHOST_HOST"].rstrip("/")
    if access_token is not None:
        validate_ghost_host(ghost_host)

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
        "ghost_token": ghost_token,
        "ghost_access_token": access_token,
        "ghost_host": ghost_host,
        "ghost_platform_id": os.environ.get("GHOST_PLATFORM_ID", ""),
        "mapping_file": os.environ.get("MAPPING_FILE", "mapping.yaml"),
        "dry_run": dry_run_requested(),
    }


def legacy_token_expiry_days(config, now=None):
    """Read an unverified JWT expiry for reminders only, never authentication."""
    if config.get("ghost_access_token") is not None:
        return None
    raw_days = os.environ.get("GHOST_TOKEN_EXPIRY_WARNING_DAYS", "14").strip()
    if not re.fullmatch(r"[0-9]{1,3}", raw_days) or int(raw_days) > 365:
        log.warning("GHOST_TOKEN_EXPIRY_WARNING_DAYS is invalid; using 14 days")
        raw_days = "14"
    warning_days = int(raw_days)
    if warning_days == 0:
        return None
    try:
        token = config.get("ghost_token")
        if not isinstance(token, str) or len(token) > 16384:
            raise ValueError
        parts = token.split(".")
        if (len(parts) != 3 or not parts[0] or not parts[2]
                or not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", parts[1])):
            raise ValueError
        payload = json.loads(base64.b64decode(
            parts[1] + "=" * (-len(parts[1]) % 4), altchars=b"-_", validate=True))
        expiry = payload.get("exp") if isinstance(payload, dict) else None
        if type(expiry) not in (int, float) or not isfinite(expiry):
            raise ValueError
        seconds_left = expiry - (time.time() if now is None else now)
        if seconds_left > warning_days * 86400:
            return None
        return max(0, ceil(seconds_left / 86400))
    except (ValueError, OverflowError, RecursionError):
        log.debug("Legacy GHOST_TOKEN has no usable JWT expiry; reminder skipped")
        return None


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
# SendRequest ErrorCodes that IBKR's Flex v3 error table advises retrying; every
# other code (including missing or unknown) fails at once. Classified by code only.
IBKR_SEND_RETRY_CODES = frozenset(
    {"1001", "1004", "1005", "1006", "1007", "1008", "1009", "1018", "1019", "1021"})
IBKR_SEND_RETRY_DELAYS = (60, 120, 300, 600)


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
            resp = requests.get(url, params=params, timeout=timeout, allow_redirects=False)
            if 300 <= resp.status_code < 400:
                raise RuntimeError("IBKR request redirected")
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


def fetch_flex_report(token, query_id, max_retries=60, retry_delay=5):
    """Fetch a Flex Query report from IBKR (two-step process)."""
    log.debug("Requesting Flex Query %s from IBKR...", query_id)

    # Step 1 - send request, retrying only ErrorCodes IBKR documents as transient
    for attempt in range(len(IBKR_SEND_RETRY_DELAYS) + 1):
        resp = _ibkr_get(IBKR_SEND_URL, {"t": token, "q": query_id, "v": "3"}, timeout=30)
        if len(resp.content) > IBKR_MAX_XML_BYTES:
            raise RuntimeError("IBKR Flex response exceeds XML size limit")
        root = ET.fromstring(resp.text)
        if root.findtext("Status") == "Success":
            break
        error_msg = _redact(root.findtext("ErrorMessage", "unknown error"), token)
        error_code = (root.findtext("ErrorCode") or "").strip()
        if error_code not in IBKR_SEND_RETRY_CODES or attempt == len(IBKR_SEND_RETRY_DELAYS):
            raise RuntimeError(f"IBKR SendRequest failed: {error_msg}")
        delay = IBKR_SEND_RETRY_DELAYS[attempt]
        log.warning("IBKR SendRequest error %s (attempt %d/%d), retrying in %ds: %s",
                    error_code, attempt + 1, len(IBKR_SEND_RETRY_DELAYS) + 1, delay, error_msg)
        time.sleep(delay)

    ref_code = root.findtext("ReferenceCode")
    base_url = root.findtext("Url")
    if not base_url or not base_url.startswith(IBKR_ALLOWED_STMT_PREFIXES):
        raise RuntimeError(f"Unexpected IBKR statement URL: {base_url!r}")
    log.info("Got reference code %s, fetching statement...", ref_code)

    # Step 2 - poll for statement
    for attempt in range(1, max_retries + 1):
        resp = _ibkr_get(base_url, {"q": ref_code, "t": token, "v": "3"}, timeout=60)

        if len(resp.content) > IBKR_MAX_XML_BYTES:
            raise RuntimeError("IBKR Flex response exceeds XML size limit")
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


def parse_base_currency(xml_text):
    """Return the account base currency code from a Flex Query XML.

    Structure: FlexQueryResponse > FlexStatements > FlexStatement > AccountInformation
    Reads the currency attribute of the first AccountInformation entry.
    Returns a string, or None if the entry or the attribute is absent or empty.
    """
    root = ET.fromstring(xml_text)
    for entry in root.iter("AccountInformation"):
        currency = entry.attrib.get("currency", "").strip()
        if currency:
            return currency
    return None


def parse_cash_dividends(xml_text):
    """Parse dividend payments from the Cash Transactions section.

    Structure: FlexQueryResponse > FlexStatements > FlexStatement > CashTransactions > CashTransaction
    Cash establishes payments and monetary totals. Accruals are retained only
    as quantity evidence; they cannot create a payment. No quantity is checked
    here so callers can deduplicate before validating a new candidate.

    Rows are summed per (ISIN or symbol, date): dividends and payments in lieu
    into "amount", withholding tax (negative, refunds positive) into "tax".
    Returns None if the report has no Cash Transactions section, else a list
    of dicts with cash identity/totals plus payment rows and accrual evidence.
    """
    root = ET.fromstring(xml_text)
    if next(root.iter("CashTransactions"), None) is None:
        return None
    accruals = [dict(el.attrib) for el in root.iter("ChangeInDividendAccrual")]
    accrual_section = next(root.iter("ChangeInDividendAccruals"), None) is not None
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
            "amount": 0.0, "tax": 0.0, "description": "",
            "payments": [], "cash_rows": [], "accruals": accruals,
            "accrual_section": accrual_section})
        group["cash_rows"].append(dict(row))
        if tx_type != WITHHOLDING_CASH_TYPE:
            group["payments"].append(dict(row))
            # Retain descriptions for callers; they never establish quantity.
            if amount > 0:
                group["description"] = row.get("description", "")
    for group in groups.values():
        gross = _dividend_cash_sum(group["payments"])
        tax = _dividend_cash_sum([row for row in group["cash_rows"]
                                 if row.get("type") == WITHHOLDING_CASH_TYPE])
        group["gross"] = gross
        group["amount"] = float(gross) if gross is not None else float("nan")
        group["tax"] = float(tax) if tax is not None else float("nan")
    return list(groups.values())


DIVIDEND_PAYMENT_KEYS = ("accountId", "conid", "currency", "actionID", "exDate")
DIVIDEND_ACCRUAL_REQUIRED = DIVIDEND_PAYMENT_KEYS + ("quantity", "code", "date", "payDate", "reportDate")
DIVIDEND_FIELD_NAMES = {
    "accountId": "ClientAccountID", "conid": "ConID (Contract ID)",
    "currency": "CurrencyPrimary", "actionID": "ActionID", "exDate": "Ex Date",
    "quantity": "Quantity", "code": "Code", "date": "Date",
    "payDate": "Pay Date", "reportDate": "Report Date",
}

FLEX_SUFFIX_PATTERN = re.compile(r"^\d{8};\d{6}\s+[A-Za-z]{2,5}$")


def flex_provenance_failures(xml_text):
    """Count DETAIL dividend, payment-in-lieu and withholding rows whose dateTime
    lacks the Flex form "YYYYMMDD;HHmmss TimeZone", keyed by cash type.

    Other cash types and SUMMARY rows are outside the check.
    """
    root = ET.fromstring(xml_text)
    failures = {}
    for el in root.iter("CashTransaction"):
        row = el.attrib
        tx_type = row.get("type", "")
        if tx_type not in DIVIDEND_CASH_TYPES and tx_type != WITHHOLDING_CASH_TYPE:
            continue
        if row.get("levelOfDetail", "DETAIL").upper() != "DETAIL":
            continue
        date_time = row.get("dateTime", "").strip()
        if not FLEX_SUFFIX_PATTERN.match(date_time) or not parse_ibkr_datetime(date_time):
            failures[tx_type] = failures.get(tx_type, 0) + 1
    return failures


def dividend_field_prerequisites(xml_text):
    """List the required dividend attributes or section absent from the whole report.

    Without DETAIL dividend, payment-in-lieu or withholding cash rows nothing is
    required. An attribute is missing when no row of its section carries it; an
    empty value on one row stays a local rejection. Returns a list of
    "Section.attribute (IBKR field)" strings, empty when the report passes.
    """
    root = ET.fromstring(xml_text)
    rows = [el.attrib for el in root.iter("CashTransaction")
            if (el.attrib.get("type", "") in DIVIDEND_CASH_TYPES
                or el.attrib.get("type", "") == WITHHOLDING_CASH_TYPE)
            and el.attrib.get("levelOfDetail", "DETAIL").upper() == "DETAIL"]
    if not rows:
        return []

    def label(section, field):
        return f"{section}.{field} ({DIVIDEND_FIELD_NAMES[field]})"

    gaps = [label("CashTransaction", field) for field in DIVIDEND_PAYMENT_KEYS
            if not any(field in row for row in rows)]
    section = next(root.iter("ChangeInDividendAccruals"), None)
    if section is None:
        gaps.append("ChangeInDividendAccruals section (Change in Dividend Accruals)")
    else:
        accruals = [el.attrib for el in root.iter("ChangeInDividendAccrual")]
        if accruals:
            gaps += [label("ChangeInDividendAccrual", field) for field in DIVIDEND_ACCRUAL_REQUIRED
                     if not any(field in row for row in accruals)]
    return gaps


def _dividend_decimal(value):
    """Parse exact finite broker evidence without rounding through a float."""
    try:
        number = Decimal(str(value))
    except DecimalException:
        return None
    return number if number.is_finite() else None


def _dividend_cash_sum(rows):
    """Sum cash exactly and independently of row order within Decimal limits."""
    values = [_dividend_decimal(row.get("amount")) for row in rows]
    if any(value is None for value in values):
        return None
    values = [value for value in values if value]
    if not values:
        return Decimal(0)
    with localcontext() as context:
        # Check Decimal's exponent range before allocating precision. Financial
        # outputs still undergo their separate float checks after conversion.
        if any(abs(value.adjusted()) > context.Emax
               or value.as_tuple().exponent < context.Emin for value in values):
            return None
        context.prec = max(28, max(value.adjusted() for value in values)
                           - min(value.as_tuple().exponent for value in values)
                           + len(str(len(values))) + 2)
        try:
            return sum(values, Decimal(0))
        except DecimalException:
            return None


def dividend_input_compatible(candidates, quiet=False):
    """Check schema only for new payments and potentially associated accruals.

    Attribute absence blocks account dividends. Empty values remain local
    quantity rejections. A nonempty mismatching key proves a row unrelated.
    """
    keys = DIVIDEND_PAYMENT_KEYS
    required = DIVIDEND_ACCRUAL_REQUIRED
    for dividend in candidates:
        if not dividend.get("accrual_section"):
            if not quiet:
                log.warning("Incompatible dividend input: missing ChangeInDividendAccruals section "
                            "— account dividends not imported; enrich the Flex query")
            return False
        for payment in dividend["payments"]:
            if any(field not in payment for field in keys):
                if not quiet:
                    log.warning("Incompatible dividend input: missing payment attributes "
                                "— account dividends not imported; enrich the Flex query")
                return False
            for row in dividend["accruals"]:
                if any(row.get(field) and payment.get(field)
                       and row[field] != payment[field] for field in keys):
                    continue
                if any(field not in row for field in required):
                    if not quiet:
                        log.warning("Incompatible dividend input: missing relevant accrual attributes "
                                    "— account dividends not imported; enrich the Flex query")
                    return False
    return True


def dividend_structured_quantity(dividend, quiet=False):
    """Return the common exact quantity for net-positive cash actions, or None.

    Match account/contract/currency/action/ex-date, then require one payment
    reversal and agreement across all associated revisions and components.
    Cash totals stay authoritative. Validation is separate from cash parsing.
    """
    def reject(reason):
        if not quiet:
            log.warning("Dividend %s %s: %s — not imported",
                        dividend["symbol"], dividend["date"], reason)
        return None

    cash_rows = dividend.get("cash_rows", [])
    if len({row.get("currency", "") for row in cash_rows}) > 1:
        return reject("contradictory cash currencies")
    actions = defaultdict(list)
    keys = DIVIDEND_PAYMENT_KEYS
    for row in dividend.get("payments", []):
        key = tuple(row.get(field, "") for field in keys)
        if not all(key):
            return reject("missing payment association keys")
        actions[key].append(row)
    common_quantity = None
    for key, payments in actions.items():
        net = _dividend_cash_sum(payments)
        if net is None:
            return reject("incompatible numeric cash amount")
        if net < 0:
            return reject("contradictory negative-net cash action")
        if net == 0:
            continue
        associated = [row for row in dividend.get("accruals", [])
                      if all(not row.get(field) or row[field] == value
                             for field, value in zip(keys, key))]
        if not associated:
            return reject("missing structured quantity evidence")
        if any(not all(row.get(field) for field in keys) for row in associated):
            return reject("missing accrual association keys")
        reversals = [row for row in associated if row.get("code") == "Re"
                     and _dividend_day(row.get("payDate")) == dividend["date"]
                     and dividend["date"] in (_dividend_day(row.get("date")),
                                               _dividend_day(row.get("reportDate")))]
        if len(reversals) != 1:
            return reject("missing or contradictory payment reversal evidence")
        quantities = [_dividend_decimal(row.get("quantity")) for row in associated]
        if any(quantity is None or quantity <= 0 for quantity in quantities):
            return reject("incompatible structured quantity")
        quantity = quantities[0]
        if any(other != quantity for other in quantities[1:]):
            return reject("contradictory structured quantities")
        if common_quantity is not None and common_quantity != quantity:
            return reject("contradictory component quantities")
        common_quantity = quantity
    if common_quantity is None:
        return reject("missing net-positive quantity evidence")
    return common_quantity


def _dividend_day(value):
    parsed = parse_ibkr_datetime(value or "")
    return parsed[:10] if parsed else None


# ---------------------------------------------------------------------------
# Ghostfolio API helpers
# ---------------------------------------------------------------------------

def ghost_headers(token):
    """Return common headers for Ghostfolio API calls."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


GHOST_REDIRECT_ERROR = "Ghostfolio request redirected"


def ghost_response_is_redirect(resp):
    """Return whether a Ghostfolio response is a redirect."""
    return 300 <= resp.status_code < 400


# (connect, read) inactivity timeouts for the login exchange
GHOST_AUTH_TIMEOUT = (10, 30)
# The bearer becomes an Authorization header value: printable ASCII, no space
_HEADER_SAFE_TOKEN_RE = re.compile(r"[\x21-\x7e]+")


def ghost_exchange_access_token(host, access_token):
    """Exchange the Ghostfolio security token for a session bearer.

    One POST /api/v1/auth/anonymous, no redirects (a redirect would carry the
    security token elsewhere) and no retry.  Every failure raises a fixed
    message: neither the request exception nor the response body is surfaced,
    as either could echo a credential.
    """
    validate_ghost_host(host)
    try:
        resp = requests.post(f"{host}/api/v1/auth/anonymous",
                             json={"accessToken": access_token},
                             timeout=GHOST_AUTH_TIMEOUT, allow_redirects=False)
    except requests.RequestException:
        raise RuntimeError("Ghostfolio login failed: network error") from None
    if not 200 <= resp.status_code < 300:
        raise RuntimeError(f"Ghostfolio login failed: HTTP {resp.status_code}")
    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError("Ghostfolio login failed: response is not JSON") from None
    token = body.get("authToken") if isinstance(body, dict) else None
    if not isinstance(token, str) or not _HEADER_SAFE_TOKEN_RE.fullmatch(token):
        raise RuntimeError("Ghostfolio login failed: response has no usable authToken")
    return token


def activity_date_is_current(activity):
    """Conservatively refuse future instants (server drafts use local end of day)."""
    try:
        instant = datetime.fromisoformat(activity["date"].replace("Z", "+00:00"))
        return instant.tzinfo is not None and instant <= datetime.now(timezone.utc)
    except (KeyError, TypeError, AttributeError, ValueError):
        return False


def activity_is_active(activity):
    """Follow Ghostfolio draft/exclusion tags; refuse malformed active context."""
    if not isinstance(activity, dict):
        raise RuntimeError("Invalid activity eligibility context")
    account = activity.get("account")
    if account is None:
        account = {}
    if not isinstance(account, dict):
        raise RuntimeError("Invalid account eligibility context")
    for context in (activity, account):
        for flag in ("isDraft", "isExcluded"):
            if flag in context and not isinstance(context[flag], bool):
                raise RuntimeError("Invalid activity eligibility flag")
        tags = context.get("tags", [])
        if (not isinstance(tags, list)
                or any(not isinstance(tag, dict) or not isinstance(tag.get("id"), str)
                       or not tag["id"].strip() for tag in tags)):
            raise RuntimeError("Invalid activity eligibility tags")
    inactive_tags = {"0c077abd-eca2-4cbb-818c-6cefbf2d169a",
                     "f2e868af-8333-459f-b161-cbc6544c24bd"}
    return not (activity.get("isDraft") or activity.get("isExcluded")
                or account.get("isDraft") or account.get("isExcluded")
                or any(tag["id"] in inactive_tags
                       for context in (activity, account) for tag in context.get("tags", [])))


def ghost_get_accounts(config):
    """Fetch all accounts from Ghostfolio."""
    url = f"{config['ghost_host']}/api/v1/account"
    resp = requests.get(url, headers=ghost_headers(config["ghost_token"]), timeout=30,
                        allow_redirects=False)
    if ghost_response_is_redirect(resp):
        raise RuntimeError(GHOST_REDIRECT_ERROR)
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
            if not activity_is_active({"account": acc}):
                raise RuntimeError("Ghostfolio target account is excluded; refusing sync")
            return acc["id"]
    log.error("Ghostfolio account '%s' not found. Available: %s",
              account_name, [a["name"] for a in accounts])
    return None


def ghost_get_existing_orders(config):
    """Fetch all existing activities from Ghostfolio.

    Uses one GET /api/v1/activities (no paging).  The /api/v1/order
    endpoints were deprecated in Ghostfolio 2.248.0 and removed in 3.5.0.

    Prefers assetProfile; accepts legacy SymbolProfile only when the current
    key is absent. BUY, SELL and DIVIDEND require a nonempty string symbol.
    Raises RuntimeError on incomplete, redacted or invalid profile context,
    before reconciliation can import activities or update cash balances.

    Returns a tuple of (trade_ids, dividend_comments, positions):
    - trade_ids: set of tradeIDs extracted from "IBKR#..." comments
    - dividend_comments: set of (accountId, comment) tuples, e.g.
      ("acc-id", "dividend#SPY#2024-01-15"). Keyed by account so two accounts
      holding the same ISIN paid on the same day do not dedup against each other
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
    resp = requests.get(url, headers=headers, timeout=60, allow_redirects=False)
    if ghost_response_is_redirect(resp):
        raise RuntimeError(GHOST_REDIRECT_ERROR)
    resp.raise_for_status()
    # Keep the original JSON numbers before the normal float-based reader runs.
    # A mock/adapter without wire bytes cannot establish exact numeric evidence.
    exact_data = None
    if config.get("dry_run"):
        wire = getattr(resp, "content", None)
        if isinstance(wire, (str, bytes)) and wire:
            try:
                exact_data = json.loads(wire, parse_float=Decimal, parse_int=Decimal)
            except (ValueError, UnicodeError, DecimalException):
                pass  # The existing decoder below owns technical failures.
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
            "disable restricted view for the Ghostfolio user, or use a token "
            "with the portfolio:read:values scope; refusing to sync without "
            "existing IBKR# IDs (duplicates risk)")

    if config.get("dry_run"):
        exact_rows = exact_data.get("activities") if isinstance(exact_data, dict) else None
        exact_available = isinstance(exact_rows, list) and len(exact_rows) == len(activities)
        positions["dividend_evidence"] = []

    for index, order in enumerate(activities):
        profile = {}
        if order.get("type") in ("BUY", "SELL", "DIVIDEND"):
            # Current API wins even if malformed: never hide an invalid current
            # profile behind a stale legacy value. Legacy-only responses remain
            # supported for Ghostfolio versions before 3.78.0.
            profile = (order["assetProfile"] if "assetProfile" in order
                       else order.get("SymbolProfile"))
            if (not isinstance(profile, dict)
                    or not isinstance(profile.get("symbol"), str)
                    or not profile["symbol"].strip()):
                raise RuntimeError(
                    f"Ghostfolio activity at index {index} has a missing or invalid "
                    "asset profile symbol (assetProfile / legacy SymbolProfile); "
                    "refusing to sync without position and reconciliation context")
        # comment is nullable in Ghostfolio, so JSON null arrives as None
        comment = order.get("comment") or ""
        if comment.startswith("IBKR#"):
            tid = comment.split("#", 1)[1]
            if tid:
                trade_ids.add(tid)
        elif comment.startswith("dividend#"):
            dividend_comments.add((order.get("accountId") or "", comment))

        active = activity_is_active(order)
        if config.get("dry_run") and order.get("type") == "DIVIDEND":
            raw = exact_rows[index] if exact_available else None
            exact = (isinstance(raw, dict)
                     and all(raw.get(key) == order.get(key)
                             for key in ("id", "type", "accountId", "comment", "date")))
            positions["dividend_evidence"].append({
                "activity": raw if exact else order, "exact_json": exact,
                "active": active, "index": index})
        if order.get("type") in ("BUY", "SELL", "DIVIDEND"):
            source = profile.get("dataSource")
            if not isinstance(source, str) or not source.strip():
                raise RuntimeError("Ghostfolio activity has missing data source; refusing sync")
            if not active or source != "YAHOO":
                continue

        if order.get("type") == "DIVIDEND":
            symbol = profile["symbol"]
            if symbol:
                positions["dividend_dates"][(order.get("accountId") or "", symbol)].append(
                    (order.get("date") or "")[:10])

        if order.get("type") in ("BUY", "SELL"):
            qty = _parse_float(order.get("quantity"))
            if qty is None or not isfinite(qty) or qty < 0:
                raise RuntimeError("Ghostfolio has invalid holding quantity; refusing sync")
            if order["type"] == "SELL":
                qty = -qty
            account_id = order.get("accountId") or ""
            symbol = profile["symbol"]
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


# Ghostfolio aborts the whole import on the first activity whose symbol the
# data provider cannot resolve, returning a 400 whose message names that symbol
# (data-provider.service.ts validateActivities, confirmed at 3.80.2). The symbol
# is quoted; the backslashes tolerate both the decoded message and the raw
# escaped JSON text.
_UNRESOLVED_SYMBOL_RE = re.compile(
    r'symbol \(\\?"([^"\\]+)\\?"\) cannot be resolved by the data source')


def parse_unresolved_symbol(body, text=""):
    """Return the ticker Ghostfolio could not resolve from an import 400, else None.

    None means the 400 is not a per-symbol resolution error (too many
    activities, premium required, invalid data source, ...) and must not be
    retried.  body is the parsed JSON (dict or None); text is the raw fallback.
    """
    messages = []
    if isinstance(body, dict):
        msg = body.get("message")
        if isinstance(msg, list):
            messages = [str(x) for x in msg]
        elif msg:
            messages = [str(msg)]
    haystack = " ".join(messages) if messages else (text or "")
    match = _UNRESOLVED_SYMBOL_RE.search(haystack)
    return match.group(1) if match else None


def accepted_import_subset(submitted, body):
    """Map server-created rows to unique submitted identities, never sent counts."""
    if not isinstance(body, dict) or not isinstance(body.get("activities"), list):
        raise RuntimeError("Import response has no accepted activity list")
    by_key = {}
    for activity in submitted:
        key = (activity.get("accountId"), activity.get("comment"))
        if any(not isinstance(v, str) or not v for v in key) or key in by_key:
            raise RuntimeError("Ambiguous submitted import identity")
        by_key[key] = activity
    accepted = []
    seen = set()
    created_ids = set()
    for row in body["activities"]:
        if not isinstance(row, dict) or row.get("error"):
            raise RuntimeError("Invalid accepted import activity")
        key = (row.get("accountId"), row.get("comment"))
        if any(not isinstance(v, str) or not v for v in key) or key not in by_key or key in seen:
            raise RuntimeError("Unmatched or repeated accepted import identity")
        original = by_key[key]
        if not activity_is_active(row) or not activity_date_is_current(row):
            raise RuntimeError("Created activity is inactive; cannot update active holdings")
        # Preserve listing compatibility: current key wins, even if invalid.
        profile = (row["assetProfile"] if "assetProfile" in row
                   else row.get("SymbolProfile"))
        if (not isinstance(row.get("id"), str) or not row["id"].strip()
                or row["id"] in created_ids
                or not isinstance(profile, dict)
                or not isinstance(profile.get("symbol"), str) or not profile["symbol"].strip()
                or profile.get("dataSource") != original.get("dataSource")):
            raise RuntimeError("Accepted activity lacks created identity or matching data source")
        try:
            returned_date = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
            submitted_date = datetime.fromisoformat(original["date"].replace("Z", "+00:00"))
        except (KeyError, AttributeError, TypeError, ValueError):
            raise RuntimeError("Accepted activity lacks a valid date") from None
        if (returned_date.tzinfo is None or submitted_date.tzinfo is None
                or returned_date != submitted_date):
            raise RuntimeError("Accepted activity has a different date")
        for field in ("quantity", "unitPrice", "fee"):
            for value in (row.get(field), original.get(field)):
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or not isfinite(value) or value < 0):
                    raise RuntimeError("Accepted activity has invalid financial evidence")
        for field in ("type", "quantity", "unitPrice", "fee", "currency"):
            if row.get(field) != original.get(field):
                raise RuntimeError("Accepted activity differs from submitted financial evidence")
        seen.add(key)
        created_ids.add(row["id"])
        accepted.append({**original, "symbol": profile["symbol"]})
    return accepted


def mark_import_uncertain(config, activities):
    """A POST may have written records; block later queries to these accounts."""
    config.setdefault("_uncertain_import_accounts", set()).update(
        a["accountId"] for a in activities if a.get("accountId"))


def ghost_import_activities(config, activities):
    """Import activities into Ghostfolio.  Returns (imported, ok).

    imported — the activities Ghostfolio accepted, for the caller's dedup
               bookkeeping; only rows identified in the server response.
               Dry-run returns the proposed rows for simulation only.
    ok       — True for a clean run, False when the run is degraded (a symbol
               was dropped) or failed, so the caller exits non-zero.

    Ghostfolio validates the whole /api/v1/import batch and aborts on the first
    activity whose symbol the data provider cannot resolve, failing trades and
    dividends alike with a single 400.  To stop one bad ticker from costing the
    whole account, such a 400 drops that symbol's activities, warns, and retries
    the reduced batch; the run still ends non-zero so the skipped symbol stays
    visible.  Other 400s (too many activities, premium, ...) are not per-symbol
    and fail hard without retrying.

    Ghostfolio reports its own duplicate detection per activity in a 2xx and
    silently skips those, so a short accepted count is not a failure.
    """
    if not activities:
        log.info("No new activities to import")
        return [], True
    if config.get("dry_run"):
        log.info("[DRY RUN] would import %d activities (no POST sent):", len(activities))
        for a in activities:
            log.info("[DRY RUN]   %-8s %-14s qty=%s price=%s %s fee=%s  %s",
                     a.get("type"), a.get("symbol"), a.get("quantity"),
                     a.get("unitPrice"), a.get("currency"), a.get("fee"),
                     a.get("comment"))
        return list(activities), True
    url = f"{config['ghost_host']}/api/v1/import"
    remaining = list(activities)
    dropped_symbols = []
    # Each iteration drops one symbol, so the loop can never run more times than
    # there are distinct symbols (+1 for the final accepting POST).
    max_attempts = len({a.get("symbol") for a in activities}) + 1

    for _ in range(max_attempts):
        try:
            resp = requests.post(url, headers=ghost_headers(config["ghost_token"]),
                                 json={"activities": remaining}, timeout=60,
                                 allow_redirects=False)
        except requests.RequestException as exc:
            log.error("Import request failed: %s", exc)
            mark_import_uncertain(config, remaining)
            return [], False

        if ghost_response_is_redirect(resp):
            mark_import_uncertain(config, remaining)
            log.error(GHOST_REDIRECT_ERROR)
            return [], False

        try:
            body = resp.json()
        except ValueError:
            body = None

        if 200 <= resp.status_code < 300:
            try:
                imported = accepted_import_subset(remaining, body)
            except RuntimeError as exc:
                log.error("Cannot establish accepted import outcome: %s; inspect Ghostfolio before retry", exc)
                mark_import_uncertain(config, remaining)
                return [], False
            log.info("Ghostfolio created %d of %d submitted activities", len(imported), len(remaining))
            if dropped_symbols:
                log.warning("Imported without %d unresolved symbol(s): %s — add a mapping entry "
                            "(symbol_mapping) so they are recognised next run",
                            len(dropped_symbols), ", ".join(dropped_symbols))
            return imported, not dropped_symbols

        symbol = parse_unresolved_symbol(body, resp.text)
        if symbol is None:
            mark_import_uncertain(config, remaining)
            log.error("Import failed (%d): %s", resp.status_code, resp.text)
            log.error("Check your mapping file - a symbol may not be recognised by Ghostfolio")
            return [], False

        before = len(remaining)
        remaining = [a for a in remaining if a.get("symbol") != symbol]
        if before == len(remaining):
            # The named symbol matches no activity we can drop (e.g. a
            # server-side resolved name); retrying would loop forever.
            log.error("Ghostfolio rejected symbol %r but no matching activity was found to drop; "
                      "aborting import for this account. Response: %s", symbol, resp.text)
            return [], False
        dropped_symbols.append(symbol)
        log.warning("Ghostfolio cannot resolve symbol %r (%d activity/ies dropped); retrying without it",
                    symbol, before - len(remaining))
        if not remaining:
            log.warning("All activities were dropped as unresolved; nothing imported for this account")
            return [], False

    log.error("Import did not converge after dropping %d symbol(s): %s",
              len(dropped_symbols), ", ".join(dropped_symbols))
    return [], False


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
    resp = requests.get(url, headers=ghost_headers(config["ghost_token"]), timeout=30,
                        allow_redirects=False)
    if ghost_response_is_redirect(resp):
        raise RuntimeError(GHOST_REDIRECT_ERROR)
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
                        json=payload, timeout=30, allow_redirects=False)
    if ghost_response_is_redirect(resp):
        log.error(GHOST_REDIRECT_ERROR)
        return False
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

    raw_commission = _parse_float(commission)
    if raw_commission is None or not isfinite(raw_commission):
        log.warning("Invalid ibCommission for trade %s; skipping trade", trade_id)
        return None
    if raw_commission > 0:
        log.warning("Trade %s: positive ibCommission %.4g (rebate) — clamped to 0, not recorded",
                    trade_id, raw_commission)
    fee = max(0.0, -raw_commission)

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
    if buy_sell not in ("BUY", "SELL"):
        log.error("Unknown buySell '%s' for trade %s; trade rejected", buy_sell, trade_id)
        return None
    activity_type = buy_sell

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
    amount = dividend.get("gross")
    if amount is None:
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
    if dividend["tax"] > 0:
        log.warning("Dividend %s %s: net withholding refund %.4g %s — recorded as 0",
                    ibkr_symbol, dividend["date"], dividend["tax"], currency)

    quantity = dividend_structured_quantity(dividend)
    if quantity is None:
        return None
    qty = float(quantity)
    if not isfinite(qty) or qty <= 0:
        log.warning("Dividend %s %s: incompatible numeric quantity — not imported",
                    ibkr_symbol, dividend["date"])
        return None
    # Cash totals, not accrual gross/tax/rate, establish price and fee.
    cash_rows = dividend.get("cash_rows", [])
    gross = _dividend_cash_sum(dividend.get("payments", []))
    tax = _dividend_cash_sum([row for row in cash_rows
                             if row.get("type") == WITHHOLDING_CASH_TYPE])
    if gross is None or tax is None or gross <= 0:
        log.warning("Dividend %s %s: incompatible numeric cash totals — not imported",
                    ibkr_symbol, dividend["date"])
        return None
    try:
        with localcontext() as context:
            context.prec = 50
            unit_price_decimal = gross / quantity
    except DecimalException:
        log.warning("Dividend %s %s: incompatible numeric price — not imported",
                    ibkr_symbol, dividend["date"])
        return None
    unit_price = float(unit_price_decimal)
    fee_decimal = tax.copy_negate() if tax < 0 else Decimal(0)
    wht = float(fee_decimal)

    # Minor-unit markets (.L GBp, .JO ZAc, .TA ILA): IBKR reports the major
    # unit, YAHOO quotes the sub-cent unit. Scale rate AND withholding tax
    # (single shared activity currency) so the WHT is not read as sub-cents.
    minor_currency, minor_factor = minor_unit_conversion(symbol, currency)
    if minor_factor != 1:
        log.debug("Dividend %s: %s %s->%s, rate+wht x%d", ibkr_symbol, symbol, currency, minor_currency, minor_factor)
    currency = minor_currency
    unit_price *= minor_factor
    wht *= minor_factor

    if (not isfinite(unit_price) or unit_price <= 0
            or not isfinite(wht) or wht < 0 or (fee_decimal > 0 and wht == 0)):
        log.warning("Dividend %s %s: incompatible numeric price or fee after scaling — not imported",
                    ibkr_symbol, dividend["date"])
        return None

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

    # Flex may append a timezone name ("20260801;143000 EST"); the wall time
    # keeps the existing UTC labelling, the suffix is not converted.
    dt_str = re.sub(r"(?<=\d)\s+[A-Za-z]{2,5}$", "", dt_str.strip())

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
    manual_recorded = set()   # sells already entered by hand
    manual_buys = set()       # buys already entered by hand (always warned about)
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
            (manual_recorded if side == "SELL" else manual_buys).add(trade_id)
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
            (manual_recorded if side == "SELL" else manual_buys).update(ids)
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
    existing_trade_ids.update(manual_recorded | manual_buys)
    return [t for t in trades
            if t.get("tradeID", "") not in manual_recorded | manual_buys | ambiguous
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


ZERO_DECIMAL_CURRENCIES = {"JPY"}


def _historical_currency(currency):
    """Return common denomination and exact scale; unknown context stays unknown."""
    major = {"USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD", "NZD", "HKD",
             "SGD", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "ILS", "ZAR"}
    if currency in major:
        return currency, Decimal(1)
    for base, minor, factor in MINOR_UNIT_MARKETS.values():
        if currency == minor:
            return base, Decimal(1) / Decimal(factor)
    return None


def _historical_minor_unit(currency):
    """Smallest amount of a major currency: 1 for zero-decimal currencies, else 0.01."""
    return Decimal(1) if currency in ZERO_DECIMAL_CURRENCIES else Decimal("0.01")


def classify_dividend_deltas(currency, quantity_deltas, gross_deltas, fee_deltas):
    """Classify destination-minus-source deltas (major units) of one comparison.

    Returns "none", "noise", "minimal", "other" or "quantity", strongest first:
    any quantity delta is "quantity" (never noise); a gross/fee delta of half a
    minor unit or more other than exactly one minor unit is "other"; exactly one
    minor unit is "minimal"; below half a minor unit is "noise".
    """
    if any(quantity_deltas):
        return "quantity"
    unit = _historical_minor_unit(currency)
    classes = set()
    for delta in list(gross_deltas) + list(fee_deltas):
        size = abs(delta)
        if not size:
            continue
        classes.add("noise" if size < unit / 2 else "minimal" if size == unit else "other")
    for name in ("other", "minimal", "noise"):
        if name in classes:
            return name
    return "none"


def _historical_destination_currency(evidence):
    """Observed destination currency value and where it was read from."""
    row = evidence["activity"]
    profile = row["assetProfile"] if "assetProfile" in row else row.get("SymbolProfile", {})
    currency = row.get("currency")
    provenance = "activity"
    if "currency" in row and currency is None:
        currency = profile.get("currency")
        provenance = "assetProfile" if "assetProfile" in row else "SymbolProfile"
    return currency, provenance


def _historical_currency_context(dividend, candidates):
    """Observed source and destination currency values for a currency-blocked finding."""
    observed = [_historical_destination_currency(item) for item in candidates]
    return {"source": dividend.get("currency"),
            "destination": [currency for currency, _ in observed],
            "provenance": [provenance for _, provenance in observed]}


def _historical_values(evidence):
    """Read quantity/gross/fee only from original JSON, with currency provenance."""
    currency, provenance = _historical_destination_currency(evidence)
    row = evidence["activity"]
    unit = _historical_currency(currency) if isinstance(currency, str) else None
    if unit is None:
        return None, "missing or unsupported currency context"
    if not evidence["exact_json"]:
        return None, "original JSON numeric evidence unavailable"
    numbers = [row.get(field) for field in ("quantity", "unitPrice", "fee")]
    if any(not isinstance(value, Decimal) or not value.is_finite() for value in numbers):
        return None, "missing or invalid exact numeric evidence"
    quantity, price, fee = numbers
    if quantity <= 0 or price <= 0 or fee < 0:
        return None, "unsupported quantity, price or fee"
    with localcontext() as context:
        context.prec = max(28, sum(len(value.as_tuple().digits) for value in numbers) + 4)
        try:
            gross = quantity * price * unit[1]
            fee = fee * unit[1]
        except DecimalException:
            return None, "unsupported decimal range"
    return {"quantity": quantity, "gross": gross, "fee": fee, "currency": unit[0],
            "denomination": currency, "currency_provenance": provenance}, None


def _historical_representations(candidates, components):
    """Partition only independently identified evidence, never by amount.

    Optional component/representation identities belong to retained diagnostic
    evidence, not the API activity or its comment. The reader does not invent
    these identities for ordinary historical rows.
    """
    if len(candidates) == 1 and "representation" not in candidates[0]:
        return [candidates], None
    partitions = defaultdict(list)
    for item in candidates:
        representation = item.get("representation")
        if not isinstance(representation, str) or not representation:
            return [], "component partition identity not proven"
        partitions[representation].append(item)
    complete = []
    for rows in partitions.values():
        identities = [row.get("component") for row in rows]
        if len(rows) == 1 and identities == [None]:
            complete.append(rows)
        elif (all(isinstance(key, tuple) and key in components for key in identities)
              and len(identities) == len(set(identities)) == len(components)):
            complete.append(rows)
        else:
            return [], "incomplete or conflicting component coverage"
    return complete, None


def historical_dividend_report_window(xml_text):
    """Use explicit, consistent statement bounds; never infer them from payments."""
    windows = []
    for statement in ET.fromstring(xml_text).iter("FlexStatement"):
        bounds = [statement.get(key, "") for key in ("fromDate", "toDate")]
        if any(len(value) != 8 or not value.isascii() or not value.isdigit() for value in bounds):
            return None
        try:
            start, end = [datetime.strptime(value, "%Y%m%d").date().isoformat() for value in bounds]
        except ValueError:
            return None
        if start > end:
            return None
        windows.append((start, end))
    return windows[0] if windows and len(set(windows)) == 1 else None


def _historical_identity_checks(item, dividend, symbol):
    """Evaluate the six identity checks with expected/observed values.

    The source YYYYMMDD stays the IBKR business day; it is compared with the
    destination instant's calendar day in the local IANA TZ. An absent profile
    ISIN is unavailable evidence and does not block; a nonempty conflict fails.
    """
    row = item["activity"]
    profile = row["assetProfile"] if "assetProfile" in row else row.get("SymbolProfile", {})
    observed_date = {"utc": None, "local": None}
    tz_reason = timezone_preview_reason()
    try:
        instant = datetime.fromisoformat(row.get("date", "").replace("Z", "+00:00"))
        if instant.tzinfo is not None:
            observed_date["utc"] = instant.astimezone(timezone.utc).date().isoformat()
            if tz_reason is None:
                observed_date["local"] = instant.astimezone(
                    ZoneInfo(os.environ.get("TZ", "").strip())).date().isoformat()
    except Exception:
        pass
    profile_isin = profile.get("isin")
    if not dividend["isin"] or not profile_isin:
        isin_status = "unavailable"
    else:
        isin_status = "pass" if profile_isin == dividend["isin"] else "fail"
    rows = [
        ("active", bool(item["active"]), True, item["active"]),
        ("id", bool(row.get("id")), "nonempty", row.get("id")),
        ("data_source", profile.get("dataSource") == "YAHOO", "YAHOO", profile.get("dataSource")),
        ("symbol", profile.get("symbol") == symbol, symbol, profile.get("symbol")),
        ("date", observed_date["local"] == dividend["date"], dividend["date"], observed_date),
    ]
    checks = [{"activity_id": row.get("id"), "check": name, "status": "pass" if ok else "fail",
               "expected": expected, "observed": observed} for name, ok, expected, observed in rows]
    if tz_reason is not None:
        # No local calendar can be computed: the date is unavailable evidence, not a mismatch
        checks[-1].update({"status": "unavailable", "reason": f"{tz_reason}; forced preview"})
    checks.append({"activity_id": row.get("id"), "check": "isin", "status": isin_status,
                   "expected": dividend["isin"] or None, "observed": profile_isin or None})
    return checks


def _historical_destination(item, checks=None):
    """Describe one destination activity for private reports: security, dates, values."""
    row = item["activity"]
    profile = row["assetProfile"] if "assetProfile" in row else row.get("SymbolProfile", {})
    dates = {"utc": None, "local": None}
    for check in checks or []:
        if check["check"] == "date" and check["activity_id"] == row.get("id"):
            dates = check["observed"]
    if dates["utc"] is None:
        try:
            instant = datetime.fromisoformat(row.get("date", "").replace("Z", "+00:00"))
            if instant.tzinfo is not None:
                local = None
                if timezone_preview_reason() is None:
                    local = instant.astimezone(ZoneInfo(os.environ.get("TZ", "").strip())).date().isoformat()
                dates = {"utc": instant.astimezone(timezone.utc).date().isoformat(), "local": local}
        except (ValueError, TypeError, AttributeError):
            pass
    values, reason = _historical_values(item)
    return {"activity_id": row.get("id"), "symbol": profile.get("symbol"), "isin": profile.get("isin") or None,
            "utc_date": dates["utc"], "local_date": dates["local"],
            "values": values if values is not None else {"unavailable": reason}}


def _historical_source_values(dividend):
    """Source-only quantity/gross/fee, available whatever the identity checks say."""
    unit = _historical_currency(dividend.get("currency"))
    gross = _dividend_cash_sum(dividend["payments"])
    tax = _dividend_cash_sum([row for row in dividend.get("cash_rows", [])
                              if row.get("type") == WITHHOLDING_CASH_TYPE])
    if unit is None or gross is None or tax is None:
        return {}
    quantity = (dividend_structured_quantity(dividend, quiet=True)
                if dividend_input_compatible([dividend], quiet=True) else None)
    try:
        return {"source_quantity": quantity, "source_gross": gross * unit[1],
                "source_fee": max(Decimal(0), tax.copy_negate()) * unit[1], "source_currency": unit[0]}
    except DecimalException:
        return {}


def _historical_proximity(positions, account_id, evidence, symbol, dividend):
    """Weak candidates that make the import path skip an absent group by proximity.

    Mirrors the import-time proximity check; never certifies identity.
    """
    if not symbol:
        return None
    source_day = datetime.strptime(dividend["date"], "%Y-%m-%d")
    matched = _dividend_date_matches(positions, {"accountId": account_id, "symbol": symbol,
                                                 "date": f"{dividend['date']}T00:00:00+00:00"})
    if not matched:
        return None
    candidates = []
    for item in evidence:
        row = item["activity"]
        profile = row["assetProfile"] if "assetProfile" in row else row.get("SymbolProfile", {})
        if not (item["active"] and profile.get("dataSource") == "YAHOO" and profile.get("symbol") == symbol
                and row.get("accountId") == account_id):
            continue
        try:
            near = abs((datetime.strptime((row.get("date") or "")[:10], "%Y-%m-%d") - source_day).days)
        except ValueError:
            continue
        if near <= DIVIDEND_MATCH_DAYS:
            candidates.append({**_historical_destination(item), "comment": row.get("comment") or None})
    return {"matched_date": matched, "window_days": DIVIDEND_MATCH_DAYS, "candidates": candidates}


def historical_dividend_comparison(dividends, account_id, mapping, positions, report_window=None,
                                   existing_dividend_comments=()):
    """Compare retained history conservatively, independently of import selection.

    A canonical comment proves group identity only with matching security/date.
    It cannot partition several activities into ordinary/bonus or PIL components.
    Never use matching amounts to manufacture that missing component identity.
    existing_dividend_comments is the unmutated set import selection reads.
    """
    findings = []
    evidence = [item for item in positions.get("dividend_evidence", [])
                if item["activity"].get("accountId") == account_id]
    # Resolve all claims first. Neither input order nor repeated IDs may allow
    # one destination activity to certify several source groups.
    owners = defaultdict(set)
    for group_index, dividend in enumerate(dividends):
        if dividend.get("payments"):
            reference = f"dividend#{dividend['isin'] or dividend['symbol']}#{dividend['date']}"
            for item in evidence:
                if item["activity"].get("comment") == reference:
                    owners[item["activity"].get("id")].add(group_index)
    claimed = set()
    for dividend in dividends:
        if not dividend.get("payments"):
            continue
        reference = f"dividend#{dividend['isin'] or dividend['symbol']}#{dividend['date']}"
        candidates = [item for item in evidence if item["activity"].get("comment") == reference]
        symbol = resolve_symbol(dividend["isin"], dividend["symbol"], mapping)
        finding = {"source": reference, "activity_ids": [item["activity"].get("id") for item in candidates],
                   "category": "uncertain", "reason": "destination identity not proven",
                   "security": {"symbol": symbol, "isin": dividend["isin"] or None},
                   "source_date": dividend["date"], **_historical_source_values(dividend)}
        findings.append(finding)
        if not candidates:
            finding["category"] = "absent"
            finding["reason"] = "no canonical destination identity; weak matches cannot certify absence"
            # Same predicate and order as import selection: comment first, then proximity.
            comments = {reference, f"dividend#{symbol}#{dividend['date']}"}
            if any((account_id, comment) in existing_dividend_comments for comment in comments):
                finding["historical_comment"] = [
                    {**_historical_destination(item), "comment": item["activity"].get("comment"),
                     "active": item["active"]}
                    for item in evidence if item["activity"].get("comment") in comments]
                finding["reason"] += "; skipped by historical comment (non-certifying)"
                continue
            proximity = _historical_proximity(positions, account_id, evidence, symbol, dividend)
            if proximity:
                finding["proximity"] = proximity
                finding["reason"] += "; skipped by proximity (non-certifying)"
            continue
        claimed.update(item["index"] for item in candidates)
        checks = [check for item in candidates for check in _historical_identity_checks(item, dividend, symbol)]
        finding["identity_checks"] = checks
        finding["destination"] = [_historical_destination(item, checks) for item in candidates]
        if any(len(owners[item["activity"].get("id")]) != 1 for item in candidates):
            finding["reason"] = "contested destination ownership"
            continue
        if len({item["activity"].get("id") for item in candidates}) != len(candidates):
            finding["reason"] = "duplicate destination activity identity"
            continue
        valid = not any(check["status"] == "fail" for check in checks)
        if not valid:
            finding["reason"] = "inactive, unsupported or conflicting security/date identity"
            continue
        if not dividend_input_compatible([dividend], quiet=True):
            finding["reason"] = "incompatible source quantity schema"
            continue
        quantity = dividend_structured_quantity(dividend, quiet=True)
        if quantity is None:
            finding["reason"] = "missing or conflicting source quantity evidence"
            continue
        keys = DIVIDEND_PAYMENT_KEYS
        components = defaultdict(list)
        for row in dividend["payments"]:
            components[tuple(row.get(key, "") for key in keys)].append(row)
        representations, reason = _historical_representations(candidates, components)
        if reason:
            finding["reason"] = reason
            continue
        decoded = {}
        for item in candidates:
            values, reason = _historical_values(item)
            if reason:
                break
            decoded[item["index"]] = values
        if reason:
            finding["reason"] = reason
            if reason == "missing or unsupported currency context":
                finding["currency_context"] = _historical_currency_context(dividend, candidates)
            continue
        unit = _historical_currency(dividend.get("currency"))
        gross = _dividend_cash_sum(dividend["payments"])
        tax_rows = [row for row in dividend.get("cash_rows", [])
                    if row.get("type") == WITHHOLDING_CASH_TYPE]
        tax = _dividend_cash_sum(tax_rows)
        if (unit is None or any(unit[0] != value["currency"] for value in decoded.values())
                or gross is None or tax is None or gross <= 0):
            finding["reason"] = "missing, conflicting or unsupported source money evidence"
            if unit is None or any(unit[0] != value["currency"] for value in decoded.values()):
                finding["currency_context"] = _historical_currency_context(dividend, candidates)
            continue
        with localcontext() as context:
            numbers = [gross, tax, quantity] + [value[field] for value in decoded.values()
                                               for field in ("gross", "fee", "quantity")]
            context.prec = max(28, max(value.adjusted() for value in numbers)
                               - min(value.as_tuple().exponent for value in numbers) + 4)
            try:
                source_gross = gross * unit[1]
                source_fee = max(Decimal(0), tax.copy_negate()) * unit[1]
                signed_tax_total = tax * unit[1]
                comparisons = []
                for rows in representations:
                    values = [decoded[item["index"]] for item in rows]
                    differences = {"quantity_deltas": [value["quantity"] - quantity for value in values],
                                   "gross_delta": sum(value["gross"] for value in values) - source_gross,
                                   "fee_delta": sum(value["fee"] for value in values) - source_fee}
                    component_deltas = []
                    for item, value in zip(rows, values):
                        key = item.get("component")
                        if key is not None:
                            component_gross = _dividend_cash_sum(components[key]) * unit[1]
                            component_tax = _dividend_cash_sum([row for row in tax_rows
                                if tuple(row.get(field, "") for field in keys) == key])
                            component_deltas.append({"component": key,
                                "gross_delta": value["gross"] - component_gross,
                                "fee_delta": value["fee"] - max(Decimal(0), -component_tax) * unit[1]})
                    coherent = (not any(differences["quantity_deltas"])
                                and not differences["gross_delta"] and not differences["fee_delta"]
                                and not any(delta["gross_delta"] or delta["fee_delta"]
                                            for delta in component_deltas))
                    comparisons.append({"activity_ids": [item["activity"].get("id") for item in rows],
                                        "kind": "single" if len(rows) == 1 and rows[0].get("component") is None else "components",
                                        "coherent": coherent, **differences,
                                        "delta_class": classify_dividend_deltas(
                                            unit[0], differences["quantity_deltas"],
                                            [differences["gross_delta"]]
                                            + [delta["gross_delta"] for delta in component_deltas],
                                            [differences["fee_delta"]]
                                            + [delta["fee_delta"] for delta in component_deltas]),
                                        "component_deltas": component_deltas,
                                        "values": values})
            except DecimalException:
                finding["reason"] = "unsupported decimal range"
                continue
        finding["representations"] = comparisons
        finding["signed_tax_rows"] = [dict(row) for row in tax_rows]
        finding["signed_tax_total"] = signed_tax_total
        if len(comparisons) == 1:
            finding.update({key: value for key, value in comparisons[0].items()
                            if key in ("gross_delta", "fee_delta", "quantity_deltas", "delta_class")})
            if len(comparisons[0]["values"]) == 1:
                finding.update(comparisons[0]["values"][0])
                finding["quantity_delta"] = comparisons[0]["quantity_deltas"][0]
        finding["source_quantity"] = quantity
        finding["source_gross"] = source_gross
        finding["source_fee"] = source_fee
        finding["category"] = ("probable_repetition" if len(comparisons) > 1 else
                               "coherent_" + comparisons[0]["kind"] if comparisons[0]["coherent"] else "differences")
        finding["reason"] = "exact identity-proven representation comparison"
    for item in evidence:
        if item["index"] not in claimed:
            row = item["activity"]
            category = "uncertain"
            reason = "destination outside proven source coverage"
            try:
                date = datetime.fromisoformat(row.get("date", "").replace("Z", "+00:00"))
                utc_day = (date.date().isoformat() if date.tzinfo is not None
                           and date.utcoffset().total_seconds() == 0 else None)
            except (ValueError, TypeError, AttributeError):
                utc_day = None
            if utc_day and report_window and not report_window[0] <= utc_day <= report_window[1]:
                category = "outside_window"
                reason = "destination UTC date outside explicit report window; source evidence unavailable"
            elif not item["active"]:
                reason = "inactive destination outside proven source coverage"
            elif not utc_day:
                reason = "timezone or invalid destination date cannot prove source identity"
            elif not (row.get("comment") or "").startswith("dividend#"):
                reason = "legacy destination comment cannot prove source identity"
            findings.append({"source": None, "activity_ids": [item["activity"].get("id")],
                             "category": category, "reason": reason,
                             "destination": [_historical_destination(item)]})
    return classify_dividend_findings(findings)


def _readable_values(destination):
    """Gross/fee/currency of one destination row, or None when unavailable."""
    values = destination["values"]
    if "unavailable" in values:
        return None
    return values["gross"], values["fee"], values["currency"]


def _readable_set(label, kind, reason=None, related=()):
    return {"class": kind, "label": label, "reason": reason, "related": list(related)}


def classify_dividend_findings(findings):
    """Attach finding["readable"] (class, label, reason, related ids) to every finding.

    Classes: coherent, outside_window, noise, information, to_check. Pair detection
    (probable duplicate, equal-total split, absent/outside-coverage pair) needs the
    whole list; it never changes a finding's category. Every finding that is not
    coherent, outside window, information or noise is "to_check" with its reason.
    """
    compared = [f for f in findings if f["source"] is not None and "representations" in f]
    twins = defaultdict(list)
    for finding in findings:
        if (finding["source"] is not None or finding["category"] != "uncertain"
                or finding["reason"] != "legacy destination comment cannot prove source identity"):
            continue
        row = finding["destination"][0]
        for group in compared:
            if row["symbol"] == group["security"]["symbol"] and row["local_date"] == group["source_date"]:
                twins[id(group)].append(finding)
                finding["readable"] = _readable_set(
                    "probable duplicate", "to_check",
                    "legacy-comment row with the same security and day as a compared dividend",
                    group["activity_ids"])
                break
    outside = {}
    for finding in findings:
        if (finding["source"] is None and finding["category"] == "uncertain"
                and "readable" not in finding):
            outside[finding["activity_ids"][0]] = finding
    for finding in findings:
        if "readable" in finding:
            continue
        category = finding["category"]
        if category in ("coherent_single", "coherent_components"):
            result = _readable_set("coherent", "coherent")
        elif category == "outside_window":
            result = _readable_set("outside window", "outside_window", finding["reason"])
        elif category == "differences" or category == "probable_repetition":
            delta = finding.get("delta_class")
            if category == "probable_repetition":
                result = _readable_set("repeated representation", "to_check", finding["reason"])
            elif delta == "noise":
                result = _readable_set("rounding noise", "noise")
            elif delta == "quantity":
                result = _readable_set("quantity difference", "to_check")
            elif delta == "minimal":
                result = _readable_set("minimal difference, cause unknown", "to_check")
            else:
                result = _readable_set("amount difference", "to_check")
        elif category == "absent":
            result = _readable_set("possibly missing in Ghostfolio", "to_check", finding["reason"])
            carriers = {item["activity_id"] for item in finding.get("historical_comment", [])}
            for activity_id in carriers:
                row = outside.get(activity_id)
                if row is None or "readable" in row or "source_gross" not in finding:
                    continue
                values = _readable_values(row["destination"][0])
                if (values is not None and row["destination"][0]["symbol"] == finding["security"]["symbol"]
                        and row["destination"][0]["local_date"] == finding["source_date"]
                        and values == (finding["source_gross"], finding["source_fee"],
                                       finding["source_currency"])):
                    reason = "skipped by historical comment; matching destination row outside proven coverage"
                    result = _readable_set("absent source paired with outside-coverage row",
                                           "information", reason, [activity_id])
                    row["readable"] = _readable_set("outside-coverage row paired with absent source",
                                                    "information", reason, [finding["source"]])
                    break
        elif category == "uncertain" and finding["source"] is not None:
            context = finding.get("currency_context")
            destination = finding.get("destination", [])
            values = [_readable_values(row) for row in destination]
            if context and context["source"] and _historical_currency(context["source"]) is None:
                result = _readable_set("unsupported currency", "information", finding["reason"])
            elif (len(destination) > 1 and "source_gross" in finding and all(values)
                  and not any(check["status"] == "fail" for check in finding.get("identity_checks", []))
                  and finding["reason"] not in ("contested destination ownership",
                                                "duplicate destination activity identity")
                  and {v[2] for v in values} == {finding["source_currency"]}
                  and sum(v[0] for v in values) == finding["source_gross"]
                  and sum(v[1] for v in values) == finding["source_fee"]):
                result = _readable_set(f"total equal to IBKR, split over {len(destination)} rows",
                                       "information", finding["reason"])
            else:
                result = _readable_set("uncertain", "to_check", finding["reason"])
        else:
            result = _readable_set("uncertain", "to_check", finding["reason"])
        finding["readable"] = result
    for group in compared:
        if twins[id(group)]:
            group["readable"]["related"] = [tid for twin in twins[id(group)] for tid in twin["activity_ids"]]
    return findings


def _plain(value):
    """Plain decimal text: no Decimal(...), no exponent."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format(Decimal(str(value)), "f")
    return "unknown" if value is None else str(value)


def _plain_signed(value):
    text = _plain(value)
    return text if text.startswith("-") or text == "unknown" else "+" + text


def _plain_values(values):
    if "unavailable" in values:
        return f"values unavailable ({values['unavailable']})"
    return (f"quantity {_plain(values['quantity'])}, gross {_plain(values['gross'])} {values['currency']}, "
            f"fee {_plain(values['fee'])} {values['currency']}")


def _plain_deltas(row):
    quantities = ", ".join(_plain_signed(delta) for delta in row["quantity_deltas"])
    return (f"quantity {quantities}, gross {_plain_signed(row['gross_delta'])}, "
            f"fee {_plain_signed(row['fee_delta'])}")


READABLE_ACTIONS = {
    "quantity difference": "Compare the quantity in Ghostfolio with the IBKR statement; fix the activity by hand if IBKR is right.",
    "minimal difference, cause unknown": "Check whether IBKR revised the amount after the import; the gap is one minor unit.",
    "amount difference": "Compare the amounts with the IBKR statement; fix the activity by hand if IBKR is right.",
    "repeated representation": "Compare each representation with the IBKR statement; delete by hand only the ones confirmed as duplicates.",
    "probable duplicate": "Check whether this row repeats the IBKR dividend; delete it by hand if it does.",
    "possibly missing in Ghostfolio": "Check whether the dividend is missing in Ghostfolio; add it by hand if it is.",
    "uncertain": "Read the reason and compare both sides by hand.",
}


def _readable_action(readable):
    if readable["class"] == "information":
        return "No action needed."
    if readable["class"] in ("coherent", "outside_window", "noise"):
        return "No action needed."
    return READABLE_ACTIONS.get(readable["label"], READABLE_ACTIONS["uncertain"])


def format_historical_dividend_finding(finding, account_id):
    """Render one finding as plain English lines (no repair, no selection, nothing written)."""
    readable = finding["readable"]
    kind = {"to_check": "to check", "information": "information", "noise": "noise",
            "coherent": "coherent", "outside_window": "outside report window"}[readable["class"]]
    lines = [f"[DRY RUN] Dividend {kind}: {readable['label']} (account {account_id})"]
    if finding["source"] is not None:
        security = finding["security"]
        lines.append(f"  Security: {security['symbol']} (ISIN {security['isin'] or 'unknown'}), "
                     f"dividend date {finding['source_date']}, reference {finding['source']}")
        if "source_gross" in finding:
            lines.append(f"  IBKR: quantity {_plain(finding['source_quantity'])}, "
                         f"gross {_plain(finding['source_gross'])} {finding['source_currency']}, "
                         f"fee {_plain(finding['source_fee'])} {finding['source_currency']}")
        else:
            lines.append(f"  IBKR: {finding['source']}")
    else:
        lines.append("  IBKR: no dividend of the report is tied to this Ghostfolio row")
    for item in finding.get("destination", []):
        lines.append(f"  Ghostfolio: activity {item['activity_id']} ({item['symbol']}) on "
                     f"{item['utc_date']}, " + _plain_values(item["values"]))
    if "gross_delta" in finding:
        lines.append("  Difference (Ghostfolio minus IBKR): " + _plain_deltas(finding))
    elif len(finding.get("representations", [])) > 1:
        for number, row in enumerate(finding["representations"], 1):
            lines.append(f"  Difference of representation {number} (Ghostfolio minus IBKR): "
                         + _plain_deltas(row))
    lines.append(f"  Reason: {readable['reason'] or readable['label']}")
    if readable["label"] == "probable duplicate":
        lines.append("  This row looks like a duplicate: legacy comment, same security and same day as the "
                     "IBKR dividend (activity " + ", ".join(map(str, readable["related"])) + ").")
    elif readable["related"] and readable["class"] == "to_check" and finding["source"] is not None:
        lines.append("  Probable duplicates: legacy-comment rows with the same security and day "
                     "(activity " + ", ".join(map(str, readable["related"])) + ").")
    for check in finding.get("identity_checks", []):
        if check["status"] != "pass":
            observed = check["observed"]
            if isinstance(observed, dict):
                observed = (f"local date {_plain(observed.get('local'))} "
                            f"(UTC date {_plain(observed.get('utc'))})")
            lines.append(f"  Identity check {check['check']} {check['status']} for activity "
                         f"{check['activity_id']}: expected {check['expected']}, found {observed}"
                         + (f" ({check['reason']})" if check.get("reason") else ""))
    context = finding.get("currency_context")
    if context:
        lines.append(f"  Currency: IBKR {context['source']}, Ghostfolio "
                     f"{', '.join(map(str, context['destination']))} "
                     f"(from {', '.join(context['provenance'])})")
    for item in finding.get("historical_comment") or []:
        lines.append(f"  Skipped by historical comment: activity {item['activity_id']} "
                     f"(comment {item['comment']}, {item['utc_date']}), " + _plain_values(item["values"]))
    proximity = finding.get("proximity")
    if proximity:
        lines.append(f"  Skipped by proximity: same symbol within {proximity['window_days']} days of "
                     f"{proximity['matched_date']}; weak candidates do not certify identity")
        for item in proximity["candidates"]:
            lines.append(f"    Weak candidate: activity {item['activity_id']} (comment {item['comment']}, "
                         f"{item['utc_date']}), " + _plain_values(item["values"]))
    lines.append(f"  Action: {_readable_action(readable)}")
    lines.append("  Nothing was written.")
    return "\n".join(lines)


def log_historical_dividend_comparison(findings, account_id):
    """Report private diagnostic evidence without changing outcomes or persistence.

    Information blocks come first, then the summary line, then each item to check.
    Coherent, outside-window and noise findings log at DEBUG only.
    """
    counts = defaultdict(int)
    classes = defaultdict(int)
    failed = defaultdict(int)
    unavailable = defaultdict(int)
    to_check = []
    for finding in findings:
        counts[finding["category"]] += 1
        classes[finding["readable"]["class"]] += 1
        for check in finding.get("identity_checks", []):
            if check["status"] == "fail":
                failed[check["check"]] += 1
            elif check["status"] == "unavailable":
                unavailable[check["check"]] += 1
        klass = finding["readable"]["class"]
        if klass == "to_check":
            to_check.append(finding)
        elif klass == "information":
            log.info("%s", format_historical_dividend_finding(finding, account_id))
        else:
            log.debug("%s", format_historical_dividend_finding(finding, account_id))
    log.info("[DRY RUN] Dividend report: %d to check, %d informational, %d noise",
             classes["to_check"], classes["information"], classes["noise"])
    for finding in to_check:
        log.info("%s", format_historical_dividend_finding(finding, account_id))
    log.info("[DRY RUN] Historical dividends account=%s coverage=%d source_groups=%d "
             "unmatched_destination=%d categories=%s failed_checks=%s unavailable_checks=%s",
             account_id, len(findings),
             sum(finding["source"] is not None for finding in findings),
             sum(finding["source"] is None for finding in findings), dict(sorted(counts.items())),
             dict(sorted(failed.items())), dict(sorted(unavailable.items())))


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
    except (requests.RequestException, RuntimeError) as exc:
        log.error("Failed to look up Ghostfolio account '%s': %s", ghost_account_name, exc)
        return {}, False
    if ghost_account_id is None:
        return {}, False

    if ghost_account_id in config.get("_uncertain_import_accounts", set()):
        log.error("Account %s has an uncertain earlier import outcome; refusing further writes", ghost_account_id)
        return {}, False

    # Flex provenance is a prerequisite: fail before any import, cash or platform write
    provenance = flex_provenance_failures(xml_text)
    if provenance:
        log.error("Flex Query %s: cash rows without a valid 'YYYYMMDD;HHmmss TimeZone' dateTime "
                  "(%s); account failed before any write. Add Date/Time with time zone to the "
                  "query, see README", query_id,
                  ", ".join(f"{kind}: {count}" for kind, count in sorted(provenance.items())))
        return {}, False

    # Required dividend fields are a prerequisite too, even with no new dividend
    gaps = dividend_field_prerequisites(xml_text)
    if gaps:
        log.error("Flex Query %s: required dividend fields missing from the report (%s); account "
                  "failed before any write. Tick these fields in the query, see README",
                  query_id, ", ".join(gaps))
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

    # Prepare actual import candidates before calculating their position impact.
    unmapped = {}
    prepared_trades = []
    skipped_dup = 0
    skipped_other = 0

    unique = {}
    conflicts = set()
    for index, trade in enumerate(trades):
        tid = trade.get("tradeID", "")
        if not tid:
            # Keep each unidentified row so rejection diagnostics remain complete.
            unique[("missing", index)] = trade
        elif tid in unique:
            skipped_dup += 1
            if trade != unique[tid]:
                conflicts.add(tid)
        else:
            unique[tid] = trade
    if conflicts:
        log.error("Conflicting repeated trade IDs excluded: %s", ", ".join(sorted(conflicts)))
        ok = False

    for trade in unique.values():
        trade_id = trade.get("tradeID", "")
        if not trade_id:
            log.warning("Skipping trade for %s (%s) — missing tradeID, cannot deduplicate safely",
                        trade.get("symbol") or trade.get("isin") or "unknown",
                        trade.get("dateTime", ""))
            skipped_other += 1
            ok = False
            continue
        if trade_id in conflicts:
            skipped_other += 1
            continue
        if trade_id in existing_trade_ids:
            skipped_dup += 1
            continue

        trade_unmapped = {}
        activity = convert_trade_to_activity(trade, ghost_account_id, mapping, trade_unmapped)
        if activity is None or not activity_date_is_current(activity) or not all(isfinite(activity[field]) for field in ("quantity", "unitPrice", "fee")):
            log.error("Trade %s cannot be converted safely; excluded before holdings checks", trade_id)
            skipped_other += 1
            ok = False
            continue
        # The gate must use the same signed quantity the converted BUY/SELL will
        # add to Ghostfolio, while retaining raw fields for manual-entry matching.
        prepared_trades.append({**trade,
                                "quantity": (-1 if activity["type"] == "SELL" else 1) * activity["quantity"],
                                "_activity": activity, "_unmapped": trade_unmapped})

    trades = filter_trades_by_holdings(prepared_trades, positions, ghost_account_id, mapping,
                                      existing_trade_ids)
    activities = []
    for trade in trades:
        activities.append(trade["_activity"])
        unmapped.update(trade["_unmapped"])

    log.info("New trade activities: %d, duplicates skipped: %d, other skipped: %d",
             len(activities), skipped_dup, skipped_other)

    # Establish identity and deduplicate before checking quantity or schema.
    if config.get("dry_run"):
        findings = historical_dividend_comparison(dividends, ghost_account_id, mapping, positions,
                                                 historical_dividend_report_window(xml_text),
                                                 existing_dividend_comments)
        log_historical_dividend_comparison(findings, ghost_account_id)
    div_activities = []
    div_skipped_dup = 0
    candidates = []
    for div in dividends:
        if not div["payments"] or div["amount"] <= 0:
            # Preserve existing diagnostics for reversals and tax-only rows.
            convert_dividend_to_activity(div, ghost_account_id, mapping, unmapped)
            continue
        symbol = resolve_symbol(div["isin"], div["symbol"], mapping)
        identity = {
            "accountId": ghost_account_id, "symbol": symbol,
            "date": f"{div['date']}T00:00:00+00:00",
            "comment": f"dividend#{div['isin'] or div['symbol']}#{div['date']}",
        }
        old_comment = f"dividend#{symbol}#{div['date']}"
        if ((ghost_account_id, identity["comment"]) in existing_dividend_comments
                or (ghost_account_id, old_comment) in existing_dividend_comments):
            div_skipped_dup += 1
            continue
        matched = _dividend_date_matches(positions, identity) if symbol else None
        if matched:
            log.info("Dividend %s %s: Ghostfolio has a dividend of this symbol on %s, "
                     "treated as the same payment (not imported)", symbol, div["date"], matched)
            div_skipped_dup += 1
            continue
        candidates.append(div)

    # A schema mismatch blocks only account dividends, not trades or cash.
    if dividend_input_compatible(candidates):
        for div in candidates:
            activity = convert_dividend_to_activity(div, ghost_account_id, mapping, unmapped)
            if activity and not activity_date_is_current(activity):
                log.error("Future or invalid dividend date; deferred until a later run")
                ok = False
                continue
            if activity:
                div_activities.append(activity)

    log.info("New dividend activities: %d, duplicates skipped: %d",
             len(div_activities), div_skipped_dup)

    activities.extend(div_activities)

    # Create buys/dividends first. A server-skipped BUY cannot back a later SELL,
    # even in this account's batch. Dry-run uses proposed buys for simulation.
    phases = [[a for a in activities if a["type"] != "SELL"],
              [a for a in activities if a["type"] == "SELL"]]
    for phase in phases:
        if not phase:
            continue
        if ghost_account_id in config.get("_uncertain_import_accounts", set()):
            ok = False
            break
        if phase[0]["type"] == "SELL":
            totals = defaultdict(float)
            for a in phase:
                totals[a["symbol"]] += a["quantity"]
            rejected = {symbol for symbol, qty in totals.items()
                        if positions["qty"].get((ghost_account_id, symbol), 0) - qty < -0.001}
            if rejected:
                log.warning("Sells excluded after accepted-buy check: %s", ", ".join(sorted(rejected)))
                phase = [a for a in phase if a["symbol"] not in rejected]
                ok = False
        if not phase:
            continue
        imported, import_ok = ghost_import_activities(config, phase)
        for activity in imported:
            comment = activity["comment"]
            if comment.startswith("IBKR#"):
                existing_trade_ids.add(comment.split("#", 1)[1])
                sign = -1.0 if activity["type"] == "SELL" else 1.0
                positions["qty"][(activity["accountId"], activity["symbol"])] += sign * activity["quantity"]
            elif comment.startswith("dividend#"):
                existing_dividend_comments.add((activity["accountId"], comment))
                positions["dividend_dates"][(activity["accountId"], activity["symbol"])].append(
                    activity["date"][:10])
        if not import_ok:
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


# ---------------------------------------------------------------------------
# Run outcome
# ---------------------------------------------------------------------------

# Allowed failure reasons per stage.  An outcome holds only these fixed codes,
# counts and 1-based account ordinals - never an error text, URL, identifier or
# amount - so it can be summarised outside the logs.
OUTCOME_REASONS = {
    "config": ("invalid_configuration",),
    "mapping": ("invalid_mapping",),
    "ghost_auth": ("login_failed",),
    "ghost_startup": ("activities_unavailable", "token_rejected"),
    "account": ("account_failed", "unexpected_error"),
    "unexpected": ("unhandled_error",),
}
MAX_OUTCOME_FAILURES = 20


def is_token_rejection(exc):
    """True when Ghostfolio answered 401/403, i.e. the bearer token is expired or invalid."""
    response = getattr(exc, "response", None)
    return (isinstance(exc, requests.HTTPError) and response is not None
            and response.status_code in (401, 403))


def new_run_outcome():
    """Return an empty run-local outcome."""
    return {"failures": [], "dropped": 0, "accounts_total": 0, "accounts_failed": 0}


def record_failure(outcome, stage, reason, ordinal=None):
    """Record one failure; unknown codes collapse to unexpected/unhandled_error."""
    if reason not in OUTCOME_REASONS.get(stage, ()):
        stage, reason = "unexpected", "unhandled_error"
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
        ordinal = None
    if len(outcome["failures"]) >= MAX_OUTCOME_FAILURES:
        outcome["dropped"] += 1
        return
    outcome["failures"].append({"stage": stage, "reason": reason, "ordinal": ordinal})


# ---------------------------------------------------------------------------
# Failure notifications (Apprise, isolated worker process)
# ---------------------------------------------------------------------------

NOTIFY_WORKER_FLAG = "--notify-worker"
NOTIFY_PAYLOAD_MAX = 32 * 1024
APPRISE_URLS_MAX = 10
APPRISE_URL_MAX_LEN = 2048
APPRISE_TIMEOUT_DEFAULT = 10
APPRISE_TIMEOUT_MAX = 30
# The worker inherits only what Apprise needs to reach a destination: never the
# IBKR or Ghostfolio credentials.
NOTIFY_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR",
                        "REQUESTS_CA_BUNDLE", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                        "http_proxy", "https_proxy", "no_proxy")
# Worker exit code -> delivery status reported by send_notification.  Kept clear
# of the interpreter's own codes (1 uncaught error, 2 cannot open the script).
NOTIFY_EXIT_STATUS = {0: "sent", 10: "invalid_payload", 11: "unavailable", 12: "failed",
                      13: "invalid_destination"}


def load_notification_config():
    """Parse APPRISE_URLS and APPRISE_TIMEOUT; None means notifications are off.

    APPRISE_URLS is a JSON list of Apprise URL strings (blank or [] = off);
    APPRISE_TIMEOUT an integer number of seconds, 1..30 (default 10).  Never
    raises: invalid settings only disable delivery, with a fixed warning since
    the values carry destination credentials.
    """
    raw = os.environ.get("APPRISE_URLS", "")
    if not raw.strip():
        return None
    try:
        urls = json.loads(raw) if len(raw) <= NOTIFY_PAYLOAD_MAX else None
    except ValueError:
        urls = None
    raw_timeout = os.environ.get("APPRISE_TIMEOUT", "").strip()
    timeout = APPRISE_TIMEOUT_DEFAULT
    if raw_timeout:
        timeout = int(raw_timeout) if re.fullmatch(r"[0-9]{1,2}", raw_timeout) else 0
    if (not isinstance(urls, list) or len(urls) > APPRISE_URLS_MAX
            or not all(isinstance(u, str) and u.strip() and len(u) <= APPRISE_URL_MAX_LEN
                       for u in urls)
            or not 1 <= timeout <= APPRISE_TIMEOUT_MAX):
        log.warning("APPRISE_URLS or APPRISE_TIMEOUT is invalid: failure notifications disabled")
        return None
    if not urls:
        return None
    return {"urls": urls, "timeout": timeout}


def notify_worker():
    """Worker process entry: deliver one notification read from stdin.

    Never runs the sync.  Apprise is imported here only, so the sync never
    loads it.  Exit codes: see NOTIFY_EXIT_STATUS.
    """
    logging.disable(logging.CRITICAL)
    raw = sys.stdin.buffer.read(NOTIFY_PAYLOAD_MAX + 1)
    try:
        payload = json.loads(raw) if len(raw) <= NOTIFY_PAYLOAD_MAX else None
    except ValueError:
        payload = None
    if (not isinstance(payload, dict)
            or not isinstance(payload.get("urls"), list) or not payload["urls"]
            or not all(isinstance(u, str) for u in payload["urls"])
            or not isinstance(payload.get("title"), str)
            or not isinstance(payload.get("body"), str)):
        return 10
    try:
        import apprise
    except ImportError:
        return 11
    notifier = apprise.Apprise()
    # One entry may hold several space- or comma-separated URLs: bound the
    # destinations Apprise actually expanded, not the list entries
    if (not all(notifier.add(url) for url in payload["urls"])
            or len(notifier) > APPRISE_URLS_MAX):
        return 13
    try:
        sent = notifier.notify(title=payload["title"], body=payload["body"])
    except Exception:
        return 12
    return 0 if sent else 12


def _notify_worker_argv():
    # -I: ignore PYTHON* variables, user site-packages and the current directory
    return [sys.executable, "-I", os.path.abspath(__file__), NOTIFY_WORKER_FLAG]


def _stop_worker(proc):
    """Kill the worker (and anything it started) if still running, then reap it."""
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
    proc.wait()


def send_notification(settings, title, body):
    """Deliver one notification through an isolated Apprise worker.

    Apprise plugins can block past any library timeout and can print their
    destination URL.  So the URLs travel on stdin, the worker gets an
    allowlisted environment and no output channel, and one deadline covers its
    whole life (import, setup, send, exit); on expiry it is killed and reaped.
    No retry: a timed-out send may still have been delivered.  Returns a fixed
    status string; SystemExit/KeyboardInterrupt propagate after the kill.
    """
    payload = json.dumps({"urls": settings["urls"], "title": title, "body": body}).encode()
    if len(payload) > NOTIFY_PAYLOAD_MAX:
        return "payload_too_large"
    # The worker re-runs this file: impossible when the script came from stdin
    if not os.path.isfile(os.path.abspath(__file__)):
        return "spawn_failed"
    env = {k: os.environ[k] for k in NOTIFY_ENV_ALLOWLIST if k in os.environ}
    try:
        proc = subprocess.Popen(_notify_worker_argv(), stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env=env, close_fds=True, start_new_session=True)
    except (OSError, ValueError):
        return "spawn_failed"
    try:
        proc.communicate(payload, timeout=settings["timeout"])
    except subprocess.TimeoutExpired:
        return "timeout"
    except Exception:
        return "failed"
    finally:
        _stop_worker(proc)
    return NOTIFY_EXIT_STATUS.get(proc.returncode, "failed")


NOTIFY_TITLE = "ghostfolio-ibkr-sync: run failed"
TOKEN_EXPIRY_NOTIFY_TITLE = "ghostfolio-ibkr-sync: token expiring"
FORCED_PREVIEW_NOTIFY_TITLE = "ghostfolio-ibkr-sync: forced preview"


def build_forced_preview_summary(reason):
    """Fixed advisory line: the run wrote nothing because of the TZ prerequisite."""
    return f"- forced DRY_RUN: {reason}; no Ghostfolio writes. Set a valid IANA TZ."


def build_token_expiry_summary(days):
    """Fixed advisory code and remaining-day count; no JWT claims are disclosed."""
    return (f"- ghost_auth: token_expiring (days remaining: {days})\n"
            "Regenerate GHOST_TOKEN or switch to GHOST_ACCESS_TOKEN.")


def build_failure_summary(outcome, now=None):
    """Plain-text summary: fixed codes, UTC time, counts and account ordinals only."""
    now = now or datetime.now(timezone.utc)
    lines = [f"Run failed at {now.strftime('%Y-%m-%d %H:%M')} UTC.",
             f"Accounts failed: {int(outcome['accounts_failed'])} of {int(outcome['accounts_total'])}."]
    for failure in outcome["failures"]:
        stage, reason = failure["stage"], failure["reason"]
        if reason not in OUTCOME_REASONS.get(stage, ()):
            stage, reason = "unexpected", "unhandled_error"
        ordinal = failure["ordinal"]
        where = f" (account #{ordinal})" if type(ordinal) is int and ordinal > 0 else ""
        lines.append(f"- {stage}: {reason}{where}")
    if outcome["dropped"]:
        lines.append(f"- and {int(outcome['dropped'])} more")
    if outcome.get("token_expiry_days") is not None:
        lines.append(build_token_expiry_summary(outcome["token_expiry_days"]))
    if outcome.get("forced_preview"):
        lines.append(build_forced_preview_summary(outcome["forced_preview"]))
    lines.append("Details are in the container log.")
    return "\n".join(lines)


def finalize_run(outcome, code):
    """Send at most one notification for failures or a legacy-token reminder.

    Ordinary warnings remain silent. Dry runs (DRY_RUN read raw, even when
    configuration is invalid) never notify. Delivery never changes the exit
    code. A reminder on a failed run is included in its failure notification.
    """
    days = outcome.get("token_expiry_days")
    preview = outcome.get("forced_preview")
    if (code == 0 and days is None and not preview) or dry_run_requested():
        return
    label = "Failure" if code else ("Forced preview" if preview else "Token expiry")
    try:
        settings = load_notification_config()
        if settings is None:
            return
        if code:
            title, body = NOTIFY_TITLE, build_failure_summary(outcome)
        elif preview:
            title, body = FORCED_PREVIEW_NOTIFY_TITLE, build_forced_preview_summary(preview)
            if days is not None:
                body += "\n" + build_token_expiry_summary(days)
        else:
            title, body = TOKEN_EXPIRY_NOTIFY_TITLE, build_token_expiry_summary(days)
        status = send_notification(settings, title, body)
    except Exception:
        log.warning("%s notification could not be sent: internal error", label)
        return
    if status == "sent":
        log.info("%s notification sent", label)
    elif status == "timeout":
        log.warning("%s notification timed out (it may still arrive; not retried)", label)
    else:
        log.warning("%s notification not delivered: %s", label, status)


def run_sync(outcome):
    """Run one sync.  Returns the exit code; every exit 1 is recorded in outcome."""
    try:
        config = load_config()
    except RuntimeError as exc:
        log.error("Configuration error: %s", exc)
        record_failure(outcome, "config", "invalid_configuration")
        return 1
    reason = timezone_preview_reason()
    if reason:
        config["dry_run"] = True
        outcome["forced_preview"] = reason
        log.warning("%s: whole run forced to DRY_RUN, no Ghostfolio writes", reason)
    if config["dry_run"]:
        log.info("DRY RUN enabled (DRY_RUN) — no writes will be sent to Ghostfolio")
    try:
        mapping = load_mapping(config["mapping_file"])
    except RuntimeError as exc:
        log.error("%s", exc)
        record_failure(outcome, "mapping", "invalid_mapping")
        return 1
    log.info("Loaded %d symbol mappings", len(mapping))

    days = legacy_token_expiry_days(config)
    if days is not None:
        outcome["token_expiry_days"] = days
        if days:
            log.warning("Legacy GHOST_TOKEN expires in %d day(s); regenerate it or "
                        "switch to GHOST_ACCESS_TOKEN", days)
        else:
            log.warning("Legacy GHOST_TOKEN has expired; regenerate it or "
                        "switch to GHOST_ACCESS_TOKEN")

    # Access mode: one fresh bearer per run, after local validation and before
    # any Ghostfolio or IBKR call (dry-run included: a login writes nothing).
    # Never re-authenticated mid-run.
    if config.get("ghost_access_token") is not None:
        try:
            config["ghost_token"] = ghost_exchange_access_token(
                config["ghost_host"], config.pop("ghost_access_token"))
        except RuntimeError as exc:
            log.error("%s", exc)
            record_failure(outcome, "ghost_auth", "login_failed")
            return 1
        log.info("Authenticated to Ghostfolio with GHOST_ACCESS_TOKEN")

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
        if is_token_rejection(exc):
            log.error("Ghostfolio rejected the token: an expired GHOST_TOKEN must be "
                      "regenerated, or switch to GHOST_ACCESS_TOKEN")
            record_failure(outcome, "ghost_startup", "token_rejected")
        else:
            record_failure(outcome, "ghost_startup", "activities_unavailable")
        return 1
    log.info("Found %d existing trade activities and %d existing dividend activities in Ghostfolio",
             len(existing_trade_ids), len(existing_dividend_comments))

    all_unmapped = {}
    failed_accounts = []
    outcome["accounts_total"] = len(account_ids)

    for ordinal, (ibkr_id, qid, gf_name) in enumerate(zip(account_ids, query_ids, account_names), 1):
        # process_account handles the failures it expects; an unforeseen error in one
        # account must cost that account, not the accounts still to be processed
        reason = "account_failed"
        try:
            unmapped, ok = process_account(config, ibkr_id, qid, gf_name, mapping,
                                           existing_trade_ids, existing_dividend_comments, positions)
        except Exception:
            log.exception("Unexpected error while processing IBKR account %s", ibkr_id)
            unmapped, ok, reason = {}, False, "unexpected_error"
        all_unmapped.update(unmapped)
        if not ok:
            failed_accounts.append(ibkr_id)
            outcome["accounts_failed"] += 1
            record_failure(outcome, "account", reason, ordinal)

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


def main():
    """Main entry point.  Returns a process exit code (0 = clean, 1 = failure).

    SystemExit and KeyboardInterrupt propagate untouched: an interrupted run is
    not a completed run and sends no notification.
    """
    log.info("Starting IBKR to Ghostfolio sync (version %s)", os.environ.get("APP_VERSION", "dev"))
    outcome = new_run_outcome()
    try:
        code = run_sync(outcome)
    except Exception:
        log.exception("Sync failed with an unhandled error")
        record_failure(outcome, "unexpected", "unhandled_error")
        code = 1
    finalize_run(outcome, code)
    return code


if __name__ == "__main__":
    if sys.argv[1:] == [NOTIFY_WORKER_FLAG]:
        sys.exit(notify_worker())
    sys.exit(main())
