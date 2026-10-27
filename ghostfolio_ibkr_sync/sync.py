"""Financial decisions: symbol mapping, activity conversion, holding checks and deduplication.

Pure decisions over parsed IBKR rows and the Ghostfolio positions snapshot; nothing here
performs HTTP or writes. Conversion and filters reject by returning None or dropping rows,
and log why; additive-only imports and DRY_RUN guards live in `ghostfolio`.
"""

import logging
import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, DecimalException, localcontext
from math import isfinite
from typing import Any, Literal, cast

import yaml

from ghostfolio_ibkr_sync.ghostfolio import (
    InvalidActivityIdentityError,
    format_versioned_activity_identity,
)
from ghostfolio_ibkr_sync.ibkr import (
    DIVIDEND_PAYMENT_KEYS,
    SKIP_ASSET_CATEGORIES,
    WITHHOLDING_CASH_TYPE,
    DividendGroup,
    _dividend_cash_sum,
    _dividend_decimal,
    _parse_float,
    parse_ibkr_datetime,
)
from ghostfolio_ibkr_sync.models import DividendContext
from ghostfolio_ibkr_sync.outcome import RunOutcome, record_action

log = logging.getLogger(__name__)

# ISIN -> Yahoo ticker
SymbolMapping = dict[str, str]
# Ghostfolio activity payload as sent to the import endpoint
Activity = dict[str, Any]
# Ghostfolio positions snapshot built by `ghostfolio.ghost_get_existing_orders`
Positions = dict[str, Any]
# ISIN -> {"symbol", "description"} of securities resolved without a mapping entry
Unmapped = dict[str, dict[str, str]]

# An existing Ghostfolio dividend of the same account and symbol within this
# many days counts as the same payment (manual entries, older comment formats)
DIVIDEND_MATCH_DAYS = 3

# (date, gross, currency, fee) of a Ghostfolio dividend without a connector comment
DividendEntry = tuple[str, Decimal | None, str | None, Decimal | None]


# ---------------------------------------------------------------------------
# Symbol mapping
# ---------------------------------------------------------------------------

def load_mapping(path: str) -> SymbolMapping:
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
        with open(path) as fh:
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


def resolve_symbol(isin: str | None, ibkr_symbol: str | None,
                   mapping: Mapping[str, str]) -> str | None:
    """Resolve an ISIN to a Yahoo Finance ticker.

    Returns the mapped ticker, or falls back to the IBKR symbol if no mapping
    exists.  Returns None only when both are empty.
    """
    if isin and isin in mapping:
        return mapping[isin]
    if ibkr_symbol:
        return ibkr_symbol
    return None



DIVIDEND_REJECTION_ACTIONS = {
    'cash partition does not conserve source totals': "dividend_rejected",
    'conflicting payment association keys': "dividend_rejected",
    'conflicting payment day': "dividend_rejected",
    'contradictory cash currencies': "dividend_rejected",
    'contradictory component quantities': "dividend_rejected",
    'contradictory negative-net cash action': "dividend_rejected",
    'contradictory structured quantities': "dividend_rejected",
    'incompatible numeric cash amount': "dividend_rejected",
    'incompatible numeric cash totals': "dividend_rejected",
    'incompatible numeric price': "dividend_rejected",
    'incompatible numeric price or fee after scaling': "dividend_rejected",
    'incompatible numeric quantity': "dividend_rejected",
    'incompatible structured quantity': "dividend_rejected",
    'missing accrual association keys': "dividend_rejected",
    'missing net-positive quantity evidence': "dividend_rejected",
    'missing or conflicting withholding association': "dividend_rejected",
    'missing or contradictory payment reversal evidence': "dividend_rejected",
    'missing payment association keys': "dividend_rejected",
    'missing structured quantity evidence': "dividend_rejected",
    'no symbol resolved': "dividend_rejected",
    'source action split across cash groups': "dividend_rejected",
    "signed zero-net withholding": "dividend_signed_tax",
    "orphan withholding": "dividend_signed_tax",
    "withholding refund": "dividend_signed_tax",
    "orphan reversal": "dividend_reversal",
}


def dividend_scope(dividend: Mapping[str, Any]) -> str:
    """Stable private scope shared by repeated observations of a source group."""
    accounts = sorted({row.get("accountId", "") for row in dividend.get("cash_rows", [])})
    return f"{','.join(accounts)}:{dividend.get('isin') or dividend.get('symbol')}:{dividend['date']}"


def report_dividend_rejection(dividend: DividendGroup, reason: str, outcome: RunOutcome | None) -> None:
    """Report an enumerated decision, never infer an action from warning text."""
    record_action(outcome, DIVIDEND_REJECTION_ACTIONS[reason], dividend_scope(dividend))


def dividend_action_quantities(dividend: DividendGroup, quiet: bool = False,
                               outcome: RunOutcome | None = None
                               ) -> dict[tuple[str, str], Decimal] | None:
    """Return exact quantities keyed by source account/action for positive cash.

    Match account/contract/currency/action/ex-date and one payment reversal.
    Revisions of each action must agree; distinct actions can differ. Never
    sum quantities of payment/PIL portions. Cash remains payment authority.
    Zero-net actions contribute no quantity. Any invalid action rejects all.
    """
    def reject(reason: str) -> dict[tuple[str, str], Decimal] | None:
        if not quiet:
            report_dividend_rejection(dividend, reason, outcome)
            log.warning("Dividend %s %s: %s — not imported",
                        dividend["symbol"], dividend["date"], reason)
        return None

    cash_rows = dividend.get("cash_rows", [])
    if len({row.get("currency", "") for row in cash_rows}) > 1:
        return reject("contradictory cash currencies")
    actions = defaultdict(list)
    association_by_action: dict[tuple[str, str], tuple[str, ...]] = {}
    keys = DIVIDEND_PAYMENT_KEYS
    for row in dividend.get("payments", []):
        key = tuple(row.get(field, "") for field in keys)
        if not all(key):
            return reject("missing payment association keys")
        action = key[0], key[3]
        previous = association_by_action.setdefault(action, key)
        if previous != key:
            return reject("conflicting payment association keys")
        actions[key].append(row)
    action_quantities: dict[tuple[str, str], Decimal] = {}
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
                             for field, value in zip(keys, key, strict=True))]
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
        # Keep exact agreement checks above the lossy numeric conversion.
        assert quantity is not None
        numeric_quantity = float(quantity)
        if not isfinite(numeric_quantity) or numeric_quantity <= 0:
            return reject("incompatible numeric quantity")
        action_quantities[key[0], key[3]] = quantity
    if not action_quantities:
        return reject("missing net-positive quantity evidence")
    return action_quantities


def dividend_structured_quantity(dividend: DividendGroup, quiet: bool = False,
                                 outcome: RunOutcome | None = None) -> Decimal | None:
    """Return the common quantity of the historical aggregate projection.

    The action writer calls this only after partitioning each action. Keep the
    scalar helper for historical comparisons, never to combine new actions.
    """
    quantities = dividend_action_quantities(dividend, quiet=quiet, outcome=outcome)
    if quantities is None:
        return None
    common_quantity = next(iter(quantities.values()))
    if any(quantity != common_quantity for quantity in quantities.values()):
        if not quiet:
            report_dividend_rejection(dividend, "contradictory component quantities", outcome)
            log.warning("Dividend %s %s: contradictory component quantities — not imported",
                        dividend["symbol"], dividend["date"])
        return None
    return common_quantity


def _dividend_day(value: str | None) -> str | None:
    parsed = parse_ibkr_datetime(value or "")
    return parsed[:10] if parsed else None


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


def minor_unit_conversion(symbol: str, currency: str) -> tuple[str, int]:
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


def convert_trade_to_activity(trade: Mapping[str, str], ghost_account_id: str,
                              mapping: Mapping[str, str], unmapped: Unmapped) -> Activity | None:
    """Convert an IBKR trade dict to a Ghostfolio activity dict.

    Returns None if the trade should be skipped.
    Adds unmapped ISINs to the unmapped dict.
    """
    asset_category = trade.get("assetCategory", "")
    if asset_category in SKIP_ASSET_CATEGORIES:
        log.debug("Skipping %s trade: %s", asset_category, trade.get("symbol", ""))
        return None

    try:
        comment = format_versioned_activity_identity(
            trade.get("accountId", ""), "TRADE", trade.get("tradeID", ""))
    except InvalidActivityIdentityError:
        log.error("Unsafe trade identity; trade rejected")
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
    minor_currency, minor_factor = minor_unit_conversion(cast(str, symbol), currency)
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
        "comment": comment,
        "currency": currency,
        "dataSource": "YAHOO",
        "date": iso_date,
        "fee": fee,
        "quantity": qty,
        "symbol": symbol,
        "type": activity_type,
        "unitPrice": unit_price,
    }


def partition_dividend_actions(dividend: DividendGroup,
                               report_dividends: Sequence[DividendGroup] = (),
                               outcome: RunOutcome | None = None
                               ) -> list[DividendGroup] | None:
    """Partition cash exactly before quantity validation or fee clamping.

    None means invalid cash ownership. Quantity/schema rejections remain a
    separate boundary. Keep zero-net actions for cash accounting, not dispatch.
    """
    def reject(reason: str) -> list[DividendGroup] | None:
        report_dividend_rejection(dividend, reason, outcome)
        log.error("Dividend %s %s: %s — no action imported; account failed",
                  dividend["symbol"], dividend["date"], reason)
        return None

    by_action: defaultdict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    associations: dict[tuple[str, str], tuple[str, ...]] = {}
    for row in dividend["payments"]:
        key = tuple(row.get(field, "") for field in DIVIDEND_PAYMENT_KEYS)
        if not all(key):
            return reject("missing payment association keys")
        action = key[0], key[3]
        if associations.setdefault(action, key) != key:
            return reject("conflicting payment association keys")
        if _dividend_day(row.get("dateTime")) != dividend["date"]:
            return reject("conflicting payment day")
        by_action[action].append(row)

    # Each action belongs to exactly one parsed security/day group.
    # report_dividends retains the original parser objects, including dividend.
    for group in report_dividends:
        if group is dividend:
            continue
        if any((row.get("accountId", ""), row.get("actionID", "")) in associations
               for row in group["cash_rows"]):
            return reject("source action split across cash groups")

    if len({row.get("currency", "") for row in dividend["cash_rows"]}) > 1:
        return reject("contradictory cash currencies")
    taxes: defaultdict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in dividend["cash_rows"]:
        if row.get("type") != WITHHOLDING_CASH_TYPE:
            continue
        action = row.get("accountId", ""), row.get("actionID", "")
        tax_key = associations.get(action)
        if (tax_key is None or not all(row.get(field) for field in DIVIDEND_PAYMENT_KEYS[:-1])
                or tuple(row.get(field, "") for field in DIVIDEND_PAYMENT_KEYS[:-1]) != tax_key[:-1]
                or _dividend_day(row.get("dateTime")) != dividend["date"]
                or (row.get("exDate") and row["exDate"] != tax_key[-1])):
            return reject("missing or conflicting withholding association")
        taxes[action].append(row)

    parts: list[DividendGroup] = []
    for action, payments in sorted(by_action.items()):
        gross = _dividend_cash_sum(payments)
        tax = _dividend_cash_sum(taxes[action])
        if gross is None or tax is None:
            return reject("incompatible numeric cash totals")
        if gross < 0:
            return reject("contradictory negative-net cash action")
        parts.append({**dividend, "payments": payments,
                      "cash_rows": payments + taxes[action], "gross": gross,
                      "amount": float(gross), "tax": float(tax)})

    # Exact source totals include zero-net actions and signed refunds.
    for rows, projected_rows in (
            (dividend["payments"], [row for part in parts for row in part["payments"]]),
            (dividend["cash_rows"], [row for part in parts for row in part["cash_rows"]])):
        source = _dividend_cash_sum(rows)
        projected = _dividend_cash_sum(projected_rows)
        if source is None or projected is None or source != projected:
            return reject("cash partition does not conserve source totals")
    return parts


def convert_dividend_actions(dividend: DividendGroup, ghost_account_id: str,
                             mapping: Mapping[str, str], unmapped: Unmapped,
                             report_dividends: Sequence[DividendGroup] = (),
                             outcome: RunOutcome | None = None
                             ) -> tuple[list[Activity], bool]:
    """Prepare the complete historical group; never expose a partial proposal.

    The bool reports cash-partition validity only. Existing quantity/numeric
    rejections keep their local outcome. The scalar converter below remains
    the historical projection used to compare old financial values.
    """
    parts = partition_dividend_actions(dividend, report_dividends, outcome=outcome)
    if parts is None:
        return [], False
    activities = []
    for part in parts:
        if part["gross"] == 0:
            tax = _dividend_cash_sum([row for row in part["cash_rows"]
                                      if row.get("type") == WITHHOLDING_CASH_TYPE])
            if tax:
                report_dividend_rejection(part, "signed zero-net withholding", outcome)
                log.warning("Dividend %s %s: action %s nets to zero but carries signed "
                            "withholding %s %s — not imported, check by hand",
                            dividend["symbol"], dividend["date"],
                            part["payments"][0]["actionID"], tax, dividend["currency"])
            continue
        activity = convert_dividend_to_activity(part, ghost_account_id, mapping, unmapped, outcome=outcome)
        if activity is None:
            return [], True
        row = part["payments"][0]
        activity["comment"] = format_versioned_activity_identity(
            row["accountId"], "DIVIDEND", row["actionID"])
        activities.append(activity)
    return activities, True


def convert_dividend_to_activity(dividend: DividendGroup, ghost_account_id: str,
                                 mapping: Mapping[str, str], unmapped: Unmapped,
                                 outcome: RunOutcome | None = None) -> Activity | None:
    """Convert a parse_cash_dividends() entry to a Ghostfolio DIVIDEND activity.

    Returns None if the dividend cannot be processed.
    Adds unmapped ISINs to the unmapped dict.
    """
    isin = dividend["isin"]
    ibkr_symbol = dividend["symbol"]
    currency = dividend["currency"]
    amount: Decimal | float | None = dividend.get("gross")
    if amount is None:
        amount = dividend["amount"]

    if amount <= 0:
        if amount < 0:
            report_dividend_rejection(dividend, "orphan reversal", outcome)
            # a reversal dated apart from its payment: the original stays in Ghostfolio
            log.warning("Dividend %s %s: reversal of %.4g %s without a payment on the "
                        "same day — not imported, check the original dividend by hand",
                        ibkr_symbol, dividend["date"], -amount, currency)
        elif dividend["tax"]:
            report_dividend_rejection(dividend, "orphan withholding", outcome)
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
        report_dividend_rejection(dividend, "no symbol resolved", outcome)
        log.warning("No symbol resolved for dividend (ISIN: %s), skipping", isin)
        return None

    # IBKR reports withholding as a negative amount; a net refund is not a fee
    if dividend["tax"] > 0:
        report_dividend_rejection(dividend, "withholding refund", outcome)
        log.warning("Dividend %s %s: net withholding refund %.4g %s — recorded as 0",
                    ibkr_symbol, dividend["date"], dividend["tax"], currency)

    quantity = dividend_structured_quantity(dividend, outcome=outcome)
    if quantity is None:
        return None
    qty = float(quantity)
    if not isfinite(qty) or qty <= 0:
        report_dividend_rejection(dividend, "incompatible numeric quantity", outcome)
        log.warning("Dividend %s %s: incompatible numeric quantity — not imported",
                    ibkr_symbol, dividend["date"])
        return None
    # Cash totals, not accrual gross/tax/rate, establish price and fee.
    cash_rows = dividend.get("cash_rows", [])
    gross = _dividend_cash_sum(dividend.get("payments", []))
    tax = _dividend_cash_sum([row for row in cash_rows
                             if row.get("type") == WITHHOLDING_CASH_TYPE])
    if gross is None or tax is None or gross <= 0:
        report_dividend_rejection(dividend, "incompatible numeric cash totals", outcome)
        log.warning("Dividend %s %s: incompatible numeric cash totals — not imported",
                    ibkr_symbol, dividend["date"])
        return None
    try:
        with localcontext() as context:
            context.prec = 50
            unit_price_decimal = gross / quantity
    except DecimalException:
        report_dividend_rejection(dividend, "incompatible numeric price", outcome)
        log.warning("Dividend %s %s: incompatible numeric price — not imported",
                    ibkr_symbol, dividend["date"])
        return None
    unit_price = float(unit_price_decimal)
    fee_decimal = tax.copy_negate() if tax < 0 else Decimal(0)
    wht = float(fee_decimal)

    # Minor-unit markets (.L GBp, .JO ZAc, .TA ILA): IBKR reports the major
    # unit, YAHOO quotes the sub-cent unit. Scale rate AND withholding tax
    # (single shared activity currency) so the WHT is not read as sub-cents.
    minor_currency, minor_factor = minor_unit_conversion(cast(str, symbol), currency)
    if minor_factor != 1:
        log.debug("Dividend %s: %s %s->%s, rate+wht x%d", ibkr_symbol, symbol, currency, minor_currency, minor_factor)
    currency = minor_currency
    unit_price *= minor_factor
    wht *= minor_factor

    if (not isfinite(unit_price) or unit_price <= 0
            or not isfinite(wht) or wht < 0 or (fee_decimal > 0 and wht == 0)):
        report_dividend_rejection(dividend, "incompatible numeric price or fee after scaling", outcome)
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


def _match_manual_entry(trade: Mapping[str, Any], entries: list[list[Any]]
                        ) -> tuple[str | None, Any]:
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


def filter_trades_by_holdings(trades: list[dict[str, Any]], positions: Positions,
                              ghost_account_id: str, mapping: Mapping[str, str],
                              existing_trade_ids: set[str], *, source_account: str,
                              outcome: RunOutcome | None = None) -> list[dict[str, Any]]:
    """Drop trades whose import would duplicate a manual entry or drive a
    Ghostfolio position negative.

    The Flex window is 365 days, so a sell of a position bought earlier comes
    without its buy. Ghostfolio usually already holds that buy (imported by an
    earlier run, or entered manually), so per resolved ticker the check is:
    Ghostfolio net qty + net of window trades not yet imported >= 0.

    Trades already entered by hand (same side and qty, +/-2 days, no IBKR#
    comment) are dropped first: silently for sells, with a WARNING for buys
    (the user can set the manual comment to the proposed v2 identity).
    Manual matches remain ephemeral and scoped to the verified source account.
    Grouping is by the ticker the trade will be imported under;
    a position held under another symbol with the same ISIN is not guessed at
    (the sell would land on the wrong symbol) — a mapping entry fixes it.
    """
    qty_by_symbol = positions["qty"]
    manual_trade_ids: set[tuple[str, str]] = positions.setdefault("manual_trade_ids", set())
    manual_recorded: set[str] = set()   # sells already entered by hand
    manual_buys: set[str] = set()       # buys already entered by hand (always warned about)
    ambiguous = set()
    split_fills = defaultdict(list)
    groups: defaultdict[str, dict[str, Any]] = defaultdict(
        lambda: {"pending": 0.0, "symbol": "", "isin": ""})

    def match_one(trade: Mapping[str, Any], ticker: str, isin: str,
                  side: str) -> tuple[str | None, Any]:
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
        if (not trade_id or trade_id in existing_trade_ids
                or (source_account, trade_id) in manual_trade_ids):
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
                record_action(outcome, "trade_manual", f"{source_account}:{trade_id}")
                log.warning("Not importing buy %s of %s (qty %.4g, %s): matches a manual Ghostfolio "
                            "buy of %.4g on %s — set that entry's comment to %s to silence "
                            "this", trade_id, ticker, abs(qty), trade.get("dateTime", ""),
                            entry[1], entry[0],
                            format_versioned_activity_identity(source_account, "TRADE", trade_id))
            continue
        if result == "ambiguous":
            # Maybe one order split into several fills: retried as a daily sum below
            raw_date = trade.get("dateTime", "")
            parsed_date = parse_ibkr_datetime(raw_date)
            day = parsed_date[:10] if parsed_date else raw_date[:8]
            split_fills[(side, ticker, isin, day)].append(trade)
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
            if side == "BUY":
                for trade_id in ids:
                    record_action(outcome, "trade_manual", f"{source_account}:{trade_id}")
            log.log(logging.DEBUG if side == "SELL" else logging.WARNING,
                    "Not importing %ss %s of %s: fills sum to a manual Ghostfolio %s",
                    side.lower(), ",".join(ids), ticker, side.lower())
            continue
        for trade_id in ids:
            record_action(outcome, "trade_manual", f"{source_account}:{trade_id}")
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
                record_action(outcome, "mapping_conflict", f"{source_account}:{info['isin']}")
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
            record_action(outcome, "trade_position", f"{source_account}:{ticker}")
            log.error("Not importing %s: Ghostfolio holds %.4g, net new trades %.4g would go "
                      "negative — fix the position in Ghostfolio manually",
                      label, held, info["pending"])

    if closed_elsewhere or manual_recorded:
        log.info("Sells not imported: %d security(ies) with no Ghostfolio position, %d sell(s) "
                 "already entered manually — LOG_LEVEL=DEBUG for the list",
                 closed_elsewhere, len(manual_recorded))
    manual_trade_ids.update((source_account, tid) for tid in manual_recorded | manual_buys)
    return [t for t in trades
            if (source_account, t.get("tradeID", "")) not in manual_trade_ids
            and t.get("tradeID", "") not in ambiguous
            and resolve_symbol(t.get("isin", ""), t.get("symbol", ""), mapping) not in rejected]


def _dividend_date_matches(positions: Positions, activity: Mapping[str, Any]) -> DividendEntry | None:
    """Return the (date, gross, currency, fee) entry of a Ghostfolio dividend of
    the same account and symbol within DIVIDEND_MATCH_DAYS of the activity date
    (no connector comment), else None."""
    date = datetime.strptime(activity["date"][:10], "%Y-%m-%d")
    for existing in positions["dividend_dates"].get((activity["accountId"], activity["symbol"]), []):
        try:
            if abs((datetime.strptime(existing[0], "%Y-%m-%d") - date).days) <= DIVIDEND_MATCH_DAYS:
                return cast(DividendEntry, existing)
        except ValueError:
            continue
    return None


def _proximity_amounts(div: DividendGroup, entry: DividendEntry) -> tuple[str, str, bool | None]:
    """Compare the exact source gross with an existing row's gross.

    Returns (source_text, existing_text, agree): agree is True or False, or None
    when not comparable. Both sides go to a common major unit, rounded to its minor unit.
    """
    _, gross, currency, _ = entry
    source = div.get("gross")
    source_unit = _historical_currency(div.get("currency"))
    unit = _historical_currency(currency)
    source_text = f"{source} {div.get('currency')}" if source is not None else "not comparable"
    text = f"{gross} {currency}" if gross is not None else "not comparable"
    if source is None or gross is None or source_unit is None or unit is None or source_unit[0] != unit[0]:
        return source_text, text, None
    step = cast(Decimal, _historical_minor_unit(unit[0]))
    try:
        return (source_text, text,
                (source * source_unit[1]).quantize(step) == (gross * unit[1]).quantize(step))
    except DecimalException:
        return source_text, text, None


def _source_dividend_fee(div: DividendGroup) -> Decimal | None:
    """Source fee by the import convention: max(0, -cash withholding)."""
    tax = _dividend_cash_sum([row for row in div.get("cash_rows", [])
                              if row.get("type") == WITHHOLDING_CASH_TYPE])
    return None if tax is None else max(Decimal(0), tax.copy_negate())


def log_dividend_proximity_skip(symbol: str, div: DividendGroup, entry: DividendEntry,
                                outcome: RunOutcome | None = None) -> None:
    """Make a proximity skip visible: INFO when gross agrees, else one WARNING."""
    source_text, text, agree = _proximity_amounts(div, entry)
    fees = f"source fee {_source_dividend_fee(div)}, existing fee {entry[3]}"
    if agree:
        log.info("Dividend %s %s: Ghostfolio has a dividend of this symbol on %s, treated as "
                 "the same payment (not imported); amounts agree (%s; %s)",
                 symbol, div["date"], entry[0], text, fees)
        return
    record_action(outcome, "dividend_check", dividend_scope(div))
    log.warning("Dividend %s %s: Ghostfolio has a dividend of this symbol on %s, skipped as "
                "the same payment (not imported), but gross differs: source %s, existing %s; %s. "
                "Check IBKR; if the payment is distinct, add it by hand in Ghostfolio",
                symbol, div["date"], entry[0], source_text, text, fees)


CURRENCY_MINOR_UNITS = {
    "USD": Decimal("0.01"), "EUR": Decimal("0.01"), "GBP": Decimal("0.01"),
    "CHF": Decimal("0.01"), "JPY": Decimal("1"), "KRW": Decimal("1"),
    "CAD": Decimal("0.01"), "AUD": Decimal("0.01"), "NZD": Decimal("0.01"),
    "HKD": Decimal("0.01"), "SGD": Decimal("0.01"), "SEK": Decimal("0.01"),
    "NOK": Decimal("0.01"), "DKK": Decimal("0.01"), "PLN": Decimal("0.01"),
    "CZK": Decimal("0.01"), "HUF": Decimal("0.01"), "ILS": Decimal("0.01"),
    "ZAR": Decimal("0.01"),
}


def _historical_currency(currency: str | None) -> tuple[str, Decimal] | None:
    """Return common denomination and exact scale; unknown context stays unknown."""
    if currency in CURRENCY_MINOR_UNITS:
        return currency, Decimal(1)
    for base, minor, factor in MINOR_UNIT_MARKETS.values():
        if currency == minor:
            return base, Decimal(1) / Decimal(factor)
    return None


def _historical_minor_unit(currency: str) -> Decimal | None:
    """Return the explicit smallest amount of a supported major currency."""
    return CURRENCY_MINOR_UNITS.get(currency)


# ---------------------------------------------------------------------------
# Account decisions (pure; the orchestration loop performs the I/O and logging)
# ---------------------------------------------------------------------------

# Why a dividend group leaves the candidate list, or "new" when it stays
DividendDecision = Literal["not_payable", "existing", "partial", "action_conflict", "proximity", "new"]
# Why a trade row is not converted, or "new" when it is a conversion candidate
TradeIdDecision = Literal["missing", "conflict", "existing", "new"]


def unique_trades(trades: Sequence[dict[str, str]]) -> tuple[list[dict[str, str]], int, set[str]]:
    """Collapse repeated trade IDs; return (rows, repeated count, conflicting IDs).

    A repeated ID with an identical row counts only as a duplicate; with a
    different row the ID is also reported as a conflict. A row without ID is
    kept so rejection diagnostics stay complete.
    """
    skipped_dup = 0
    unique: dict[str | tuple[str, int], dict[str, str]] = {}
    conflicts: set[str] = set()
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
    return list(unique.values()), skipped_dup, conflicts


def trade_id_decision(trade_id: str, source_account: str, conflicts: set[str],
                      existing_trade_ids: set[str], positions: Positions) -> TradeIdDecision:
    """Classify one trade using legacy-global and v2 account-scoped identities."""
    if not trade_id:
        return "missing"
    if trade_id in conflicts:
        return "conflict"
    if trade_id in existing_trade_ids:
        return "existing"
    if (source_account, trade_id) in positions.get("manual_trade_ids", set()):
        return "existing"
    versioned_comment = f"IBKR#v2#{source_account}:TRADE:{trade_id}"
    if (source_account, versioned_comment) in positions.get("versioned_identities", set()):
        return "existing"
    return "new"


def dividend_positive_actions(dividend: DividendGroup) -> set[tuple[str, str]] | None:
    """Return exact net-positive ``(accountId, actionID)`` pairs.

    Zero-net actions do not need destination coverage. Missing association keys,
    one action with conflicting association evidence, non-decimal money and
    negative-net actions make the evidence unusable for versioned deduplication.
    The existing quantity validation remains responsible for logging and rejecting
    such a candidate.
    """
    rows_by_action: defaultdict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    association_by_action: dict[tuple[str, str], tuple[str, ...]] = {}
    for row in dividend.get("payments", []):
        association = tuple(row.get(field, "") for field in DIVIDEND_PAYMENT_KEYS)
        if not all(association):
            return None
        action = association[0], association[3]
        previous = association_by_action.setdefault(action, association)
        if previous != association:
            return None
        rows_by_action[action].append(row)

    positive = set()
    for action, rows in rows_by_action.items():
        net = _dividend_cash_sum(rows)
        if net is None or net < 0:
            return None
        if net > 0:
            positive.add(action)
    return positive


def dividend_dedup_decision(div: DividendGroup, ghost_account_id: str, mapping: Mapping[str, str],
                            positions: Positions, existing_dividend_comments: set[tuple[str, str]],
                            ) -> tuple[DividendDecision, str | None, DividendEntry | None]:
    """Decide whether a dividend group is a candidate, before any quantity or schema check.

    Returns (decision, resolved symbol, nearby Ghostfolio entry for "proximity").
    "existing" matches the current comment form or the older symbol-based form.
    """
    if not div["payments"] or div["amount"] <= 0:
        # Preserve existing diagnostics for reversals and tax-only rows.
        return "not_payable", None, None
    symbol = resolve_symbol(div["isin"], div["symbol"], mapping)
    identity = {
        "accountId": ghost_account_id, "symbol": symbol,
        "date": f"{div['date']}T00:00:00+00:00",
        "comment": f"dividend#{div['isin'] or div['symbol']}#{div['date']}",
    }
    old_comment = f"dividend#{symbol}#{div['date']}"
    raw_comment = f"dividend#{div['symbol']}#{div['date']}"
    if ((ghost_account_id, identity["comment"]) in existing_dividend_comments
            or (ghost_account_id, old_comment) in existing_dividend_comments
            or (ghost_account_id, raw_comment) in existing_dividend_comments):
        return "existing", symbol, None

    actions = dividend_positive_actions(div)
    if actions:
        expected = {(account_id, f"IBKR#v2#{account_id}:DIVIDEND:{action_id}")
                    for account_id, action_id in actions}
        covered = expected & positions.get("versioned_identities", set())
        if covered == expected:
            return "existing", symbol, None
        if covered:
            return "partial", symbol, None
        if dividend_action_conflict(div, symbol, actions, positions):
            return "action_conflict", symbol, None

    matched = _dividend_date_matches(positions, identity) if symbol else None
    if matched:
        return "proximity", symbol, matched
    return "new", symbol, None


def dividend_action_conflict(div: DividendGroup, symbol: str | None,
                            actions: set[tuple[str, str]], positions: Positions) -> bool:
    """Refuse no-coverage groups unless stored same-source events are disjoint.

    This is exact security/day context, never proximity or financial comparison.
    Missing context is unknown; an occupied identity is not an absent event.
    """
    accounts = {account for account, _ in actions}
    for key in positions.get("versioned_identities", set()):
        account, comment = key
        if account not in accounts or not comment.startswith(f"IBKR#v2#{account}:DIVIDEND:"):
            continue
        contexts = positions.get("versioned_dividend_context", {}).get(key)
        if not contexts:
            return True
        for context in cast(list[DividendContext], contexts):
            if context.day is not None and context.day != div["date"]:
                continue
            same_symbol = bool(symbol and context.symbol and symbol == context.symbol)
            same_isin = bool(div["isin"] and context.isin and div["isin"] == context.isin)
            if same_symbol or same_isin:
                return True
            if div["isin"] and context.isin:
                continue  # Distinct ISINs prove disjoint security; symbols can change.
            return True
    return False


def split_import_phases(activities: Sequence[Activity]) -> list[list[Activity]]:
    """Buys and dividends first, sells second, so a sell is checked after its buys."""
    return [[a for a in activities if a["type"] != "SELL"],
            [a for a in activities if a["type"] == "SELL"]]


def rejected_sell_symbols(sells: Sequence[Activity], positions: Positions,
                          ghost_account_id: str) -> set[str]:
    """Symbols whose total sell quantity exceeds the accepted holdings of the account."""
    totals: defaultdict[str, float] = defaultdict(float)
    for a in sells:
        totals[a["symbol"]] += a["quantity"]
    return {symbol for symbol, qty in totals.items()
            if positions["qty"].get((ghost_account_id, symbol), 0) - qty < -0.001}
