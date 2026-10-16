"""IBKR Flex Web Service access: fetch, response guards, XML parsing, dividend prerequisites.

Reports are parsed with `ET.fromstring`, which does not resolve external entities;
every extracted field is validated by its caller or parser before use. The Flex token
travels in the query string, so it is redacted from every message built here and
never logged.
"""

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, DecimalException, localcontext
from typing import Any, TypedDict
from urllib.parse import quote, quote_plus

import requests

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

IBKR_NETWORK_RETRY_DELAYS = (10, 30)
# SendRequest ErrorCodes that IBKR's Flex v3 error table advises retrying; every
# other code (including missing or unknown) fails at once. Classified by code only.
IBKR_SEND_RETRY_CODES = frozenset(
    {"1001", "1004", "1005", "1006", "1007", "1008", "1009", "1018", "1019", "1021"})
IBKR_SEND_RETRY_DELAYS = (60, 120, 300, 600)

DIVIDEND_PAYMENT_KEYS = ("accountId", "conid", "currency", "actionID", "exDate")
DIVIDEND_ACCRUAL_REQUIRED = DIVIDEND_PAYMENT_KEYS + ("quantity", "code", "date", "payDate", "reportDate")
DIVIDEND_FIELD_NAMES = {
    "accountId": "ClientAccountID", "conid": "ConID (Contract ID)",
    "currency": "CurrencyPrimary", "actionID": "ActionID", "exDate": "Ex Date",
    "quantity": "Quantity", "code": "Code", "date": "Date",
    "payDate": "Pay Date", "reportDate": "Report Date",
}

FLEX_SUFFIX_PATTERN = re.compile(r"^\d{8};\d{6}\s+[A-Za-z]{2,5}$")


class DividendGroup(TypedDict):
    """Cash identity and totals of one (ISIN or symbol, date), plus payment rows and accruals."""

    isin: str
    symbol: str
    currency: str
    date: str
    amount: float
    tax: float
    description: str
    payments: list[dict[str, str]]
    cash_rows: list[dict[str, str]]
    accruals: list[dict[str, str]]
    accrual_section: bool
    gross: Decimal | None


# ---------------------------------------------------------------------------
# IBKR Flex Query fetching
# ---------------------------------------------------------------------------

def _redact(text: str, secret: str | None) -> str:
    if not secret:
        return text
    for form in {secret, quote_plus(secret), quote(secret, safe="")}:
        text = text.replace(form, "***")
    return text


def _ibkr_get(url: str, params: dict[str, str | None], timeout: int) -> requests.Response:
    """GET an IBKR Flex endpoint with retry on transient network errors.

    The token travels in the query string, so requests exception messages
    embed it via the URL. Redact it before re-raising, and drop the exception
    chain so no traceback can leak it either.
    """
    token = params.get("t") or ""
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
    raise AssertionError("unreachable")  # pragma: no cover - the loop returns or raises


def log_lab_evidence(kind: str, value: object) -> None:
    """Expose existing targets at DEBUG without changing financial behavior."""
    if not log.isEnabledFor(logging.DEBUG):
        return
    try:
        message = json.dumps({"kind": kind, "value": value}, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        # Missing evidence fails lab acceptance; it must not change the operation.
        return
    log.debug("LAB_EVIDENCE %s", message)


def historical_dividend_report_window(xml_text: str) -> tuple[str, str] | None:
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


def fetch_flex_report(token: str, query_id: str, max_retries: int = 60, retry_delay: int = 5) -> str:
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
        poll_error_code = root.findtext("ErrorCode")

        # ErrorCode 1019 means statement generation is still in progress
        if status == "Warn" or poll_error_code == "1019":
            log.debug("Statement not ready yet (attempt %d/%d), waiting %ds...",
                      attempt, max_retries, retry_delay)
            time.sleep(retry_delay)
            continue

        # Report is ready when Status is absent or FlexStatements are present
        if status is None or root.find("FlexStatements") is not None:
            log.debug("Flex Query statement received")
            if log.isEnabledFor(logging.DEBUG):
                log_lab_evidence("window", historical_dividend_report_window(resp.text))
            return resp.text

        error_msg = _redact(root.findtext("ErrorMessage", "unknown error"), token)
        raise RuntimeError(f"IBKR GetStatement failed: {error_msg}")

    raise RuntimeError("Timed out waiting for IBKR Flex Query statement")


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

def parse_ibkr_datetime(dt_str: str | None) -> str | None:
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
            return parsed.replace(tzinfo=UTC).isoformat()
        except ValueError:
            continue

    return None


def parse_trades(xml_text: str) -> list[dict[str, str]]:
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


def _parse_float(value: str | None) -> float | None:
    """Return float(value), or None if value cannot be parsed."""
    try:
        return float(value)  # type: ignore[arg-type]  # None raises TypeError, handled below
    except (ValueError, TypeError):
        return None


def parse_cash_report(xml_text: str) -> float | None:
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


def parse_base_currency(xml_text: str) -> str | None:
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


def _dividend_decimal(value: object) -> Decimal | None:
    """Parse exact finite broker evidence without rounding through a float."""
    try:
        number = Decimal(str(value))
    except DecimalException:
        return None
    return number if number.is_finite() else None


def _dividend_cash_sum(rows: Iterable[Mapping[str, str]]) -> Decimal | None:
    """Sum cash exactly and independently of row order within Decimal limits."""
    parsed = [_dividend_decimal(row.get("amount")) for row in rows]
    if any(value is None for value in parsed):
        return None
    values = [value for value in parsed if value]
    if not values:
        return Decimal(0)
    with localcontext() as context:
        # Check Decimal's exponent range before allocating precision. Financial
        # outputs still undergo their separate float checks after conversion.
        if any(abs(value.adjusted()) > context.Emax
               or int(value.as_tuple().exponent) < context.Emin for value in values):
            return None
        context.prec = max(28, max(value.adjusted() for value in values)
                           - min(int(value.as_tuple().exponent) for value in values)
                           + len(str(len(values))) + 2)
        try:
            return sum(values, Decimal(0))
        except DecimalException:
            return None


def parse_cash_dividends(xml_text: str) -> list[DividendGroup] | None:
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
    groups: dict[tuple[str, str], DividendGroup] = {}
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
            "accrual_section": accrual_section, "gross": None})
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


# ---------------------------------------------------------------------------
# Dividend prerequisites
# ---------------------------------------------------------------------------

def flex_provenance_failures(xml_text: str) -> dict[str, int]:
    """Count DETAIL dividend, payment-in-lieu and withholding rows whose dateTime
    lacks the Flex form "YYYYMMDD;HHmmss TimeZone", keyed by cash type.

    Other cash types and SUMMARY rows are outside the check.
    """
    root = ET.fromstring(xml_text)
    failures: dict[str, int] = {}
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


def dividend_field_prerequisites(xml_text: str) -> list[str]:
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

    def label(section: str, field: str) -> str:
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


def dividend_input_compatible(candidates: Iterable[Mapping[str, Any]], quiet: bool = False) -> bool:
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
