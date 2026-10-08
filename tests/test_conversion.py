"""Offline tests: IBKR trade/dividend -> Ghostfolio activity conversion."""
import pytest

import ibkr_to_ghostfolio as m

ISIN = "US1912161007"


def trade(**kw):
    t = {"assetCategory": "STK", "isin": ISIN, "symbol": "KO", "tradeID": "T1", "currency": "USD",
         "buySell": "BUY", "quantity": "10", "tradePrice": "60.5", "ibCommission": "-1.2",
         "dateTime": "20260801;100000"}
    t.update(kw)
    return t


def div(**kw):
    d = {"isin": ISIN, "symbol": "KO", "currency": "USD", "date": "2026-07-15", "amount": 25.0,
         "tax": 0.0, "description": "KO CASH DIVIDEND USD 0.25 PER SHARE"}
    d.update(kw)
    return d


# --- trades ---------------------------------------------------------------

def test_buy_trade_converts():
    unmapped = {}
    a = m.convert_trade_to_activity(trade(), "acc", {ISIN: "KO"}, unmapped)
    assert a == {"accountId": "acc", "comment": "IBKR#T1", "currency": "USD", "dataSource": "YAHOO",
                 "date": "2026-08-01T10:00:00+00:00", "fee": pytest.approx(1.2), "quantity": 10.0,
                 "symbol": "KO", "type": "BUY", "unitPrice": 60.5}
    assert unmapped == {}


def test_sell_has_positive_quantity_and_sell_type():
    a = m.convert_trade_to_activity(trade(buySell="SELL", quantity="-4"), "acc", {}, {})
    assert (a["type"], a["quantity"]) == ("SELL", 4.0)


def test_unmapped_isin_falls_back_to_ibkr_symbol_and_is_reported():
    unmapped = {}
    a = m.convert_trade_to_activity(trade(), "acc", {}, unmapped)
    assert a["symbol"] == "KO"
    assert unmapped == {ISIN: {"symbol": "KO", "description": ""}}


def test_commission_rebate_is_clamped_to_zero_fee():
    a = m.convert_trade_to_activity(trade(ibCommission="0.7"), "acc", {}, {})
    assert a["fee"] == 0.0


def test_pence_market_scales_price_and_fee_together():
    t = trade(currency="GBP", tradePrice="12.5", ibCommission="-1.5")
    a = m.convert_trade_to_activity(t, "acc", {ISIN: "XYZ.L"}, {})
    assert a["currency"] == "GBp"
    assert a["unitPrice"] == pytest.approx(1250.0)
    assert a["fee"] == pytest.approx(150.0)


def test_pence_factor_only_applies_to_matching_currency():
    t = trade(currency="USD")
    a = m.convert_trade_to_activity(t, "acc", {ISIN: "XYZ.L"}, {})
    assert (a["currency"], a["unitPrice"]) == ("USD", 60.5)


@pytest.mark.parametrize("cat", ["CASH", "OPT"])
def test_cash_and_options_are_skipped(cat):
    assert m.convert_trade_to_activity(trade(assetCategory=cat), "acc", {}, {}) is None


@pytest.mark.parametrize("override", [
    {"quantity": "abc"}, {"tradePrice": "x"}, {"dateTime": "garbage"}, {"isin": "", "symbol": ""},
])
def test_invalid_trade_is_skipped(override):
    assert m.convert_trade_to_activity(trade(**override), "acc", {}, {}) is None


@pytest.mark.parametrize("commission", ["n/a", "nan", "inf", "-inf", None])
def test_invalid_commission_excludes_trade(commission):
    assert m.convert_trade_to_activity(trade(ibCommission=commission), "acc", {}, {}) is None


# --- dividends ------------------------------------------------------------

def test_dividend_quantity_and_price_from_per_share_rate():
    a = m.convert_dividend_to_activity(div(), "acc", {ISIN: "KO"}, {})
    assert a["type"] == "DIVIDEND"
    assert a["quantity"] == pytest.approx(100.0)
    assert a["unitPrice"] == pytest.approx(0.25)
    assert a["quantity"] * a["unitPrice"] == pytest.approx(25.0)
    assert a["comment"] == f"dividend#{ISIN}#2026-07-15"
    assert a["date"] == "2026-07-15T00:00:00+00:00"


def test_dividend_quantity_snaps_to_whole_shares_within_one_percent():
    a = m.convert_dividend_to_activity(div(amount=24.99), "acc", {}, {})
    assert a["quantity"] == 100.0
    assert a["quantity"] * a["unitPrice"] == pytest.approx(24.99)


def test_dividend_without_rate_is_booked_as_one_unit():
    a = m.convert_dividend_to_activity(div(description="SPECIAL"), "acc", {}, {})
    assert (a["quantity"], a["unitPrice"]) == (1.0, 25.0)


def test_withholding_tax_becomes_fee_and_refund_becomes_zero():
    assert m.convert_dividend_to_activity(div(tax=-3.75), "acc", {}, {})["fee"] == pytest.approx(3.75)
    assert m.convert_dividend_to_activity(div(tax=2.0), "acc", {}, {})["fee"] == 0.0


def test_dividend_pence_market_scales_price_and_tax():
    d = div(currency="GBP", amount=10.0, tax=-2.0, description="X CASH DIVIDEND GBP 0.10 PER SHARE")
    a = m.convert_dividend_to_activity(d, "acc", {ISIN: "PAF.L"}, {})
    assert a["currency"] == "GBp"
    assert a["unitPrice"] == pytest.approx(10.0)      # 0.10 GBP x 100
    assert a["fee"] == pytest.approx(200.0)


@pytest.mark.parametrize("amount,tax", [(0.0, 0.0), (-25.0, 0.0), (0.0, -3.0)])
def test_non_positive_dividend_is_not_imported(amount, tax):
    assert m.convert_dividend_to_activity(div(amount=amount, tax=tax), "acc", {}, {}) is None


def test_dividend_dedup_key_uses_isin_then_symbol():
    assert m.convert_dividend_to_activity(div(), "a", {}, {})["comment"].startswith(f"dividend#{ISIN}#")
    no_isin = m.convert_dividend_to_activity(div(isin=""), "a", {}, {})
    assert no_isin["comment"] == "dividend#KO#2026-07-15"


def test_dividend_unmapped_isin_is_reported_without_overwriting_trade_description():
    unmapped = {ISIN: {"symbol": "KO", "description": "COCA COLA"}}
    m.convert_dividend_to_activity(div(), "acc", {}, unmapped)
    assert unmapped[ISIN]["description"] == "COCA COLA"
