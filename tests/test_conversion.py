"""Offline tests: IBKR trade/dividend -> Ghostfolio activity conversion."""
import pytest

from ghostfolio_ibkr_sync import sync

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
    quantity = kw.pop("quantity", "100")
    d.update(kw)
    keys = {"accountId": "broker-account", "conid": "1", "currency": d["currency"],
            "actionID": "A1", "exDate": "20260701"}
    payment = dict(keys, type="Dividends", amount=str(d["amount"]))
    d["payments"] = [payment]
    d["cash_rows"] = [payment, {"type": "Withholding Tax", "currency": d["currency"],
                               "amount": str(d["tax"])}]
    d["accruals"] = [dict(keys, code="Re", quantity=quantity, payDate=d["date"],
                          date=d["date"], reportDate=d["date"])]
    return d


# --- trades ---------------------------------------------------------------

def test_buy_trade_converts():
    unmapped = {}
    a = sync.convert_trade_to_activity(trade(), "acc", {ISIN: "KO"}, unmapped)
    assert a == {"accountId": "acc", "comment": "IBKR#T1", "currency": "USD", "dataSource": "YAHOO",
                 "date": "2026-08-01T10:00:00+00:00", "fee": pytest.approx(1.2), "quantity": 10.0,
                 "symbol": "KO", "type": "BUY", "unitPrice": 60.5}
    assert unmapped == {}


def test_sell_has_positive_quantity_and_sell_type():
    a = sync.convert_trade_to_activity(trade(buySell="SELL", quantity="-4"), "acc", {}, {})
    assert (a["type"], a["quantity"]) == ("SELL", 4.0)


def test_unmapped_isin_falls_back_to_ibkr_symbol_and_is_reported():
    unmapped = {}
    a = sync.convert_trade_to_activity(trade(), "acc", {}, unmapped)
    assert a["symbol"] == "KO"
    assert unmapped == {ISIN: {"symbol": "KO", "description": ""}}


def test_commission_rebate_is_clamped_to_zero_fee():
    a = sync.convert_trade_to_activity(trade(ibCommission="0.7"), "acc", {}, {})
    assert a["fee"] == 0.0


def test_pence_market_scales_price_and_fee_together():
    t = trade(currency="GBP", tradePrice="12.5", ibCommission="-1.5")
    a = sync.convert_trade_to_activity(t, "acc", {ISIN: "XYZ.L"}, {})
    assert a["currency"] == "GBp"
    assert a["unitPrice"] == pytest.approx(1250.0)
    assert a["fee"] == pytest.approx(150.0)


def test_pence_factor_only_applies_to_matching_currency():
    t = trade(currency="USD")
    a = sync.convert_trade_to_activity(t, "acc", {ISIN: "XYZ.L"}, {})
    assert (a["currency"], a["unitPrice"]) == ("USD", 60.5)


@pytest.mark.parametrize("cat", ["CASH", "OPT"])
def test_cash_and_options_are_skipped(cat):
    assert sync.convert_trade_to_activity(trade(assetCategory=cat), "acc", {}, {}) is None


@pytest.mark.parametrize("override", [
    {"quantity": "abc"}, {"tradePrice": "x"}, {"dateTime": "garbage"}, {"isin": "", "symbol": ""},
])
def test_invalid_trade_is_skipped(override):
    assert sync.convert_trade_to_activity(trade(**override), "acc", {}, {}) is None


@pytest.mark.parametrize("commission", ["n/a", "nan", "inf", "-inf", None])
def test_invalid_commission_excludes_trade(commission):
    assert sync.convert_trade_to_activity(trade(ibCommission=commission), "acc", {}, {}) is None


# --- dividends ------------------------------------------------------------

def test_dividend_structured_quantity_and_cash_price():
    a = sync.convert_dividend_to_activity(div(), "acc", {ISIN: "KO"}, {})
    assert a["type"] == "DIVIDEND"
    assert a["quantity"] == pytest.approx(100.0)
    assert a["unitPrice"] == pytest.approx(0.25)
    assert a["quantity"] * a["unitPrice"] == pytest.approx(25.0)
    assert a["comment"] == f"dividend#{ISIN}#2026-07-15"
    assert a["date"] == "2026-07-15T00:00:00+00:00"


def test_dividend_structured_quantity_preserves_broker_shares_despite_rounded_cash():
    a = sync.convert_dividend_to_activity(div(amount=24.99), "acc", {}, {})
    assert a["quantity"] == 100.0
    assert a["quantity"] * a["unitPrice"] == pytest.approx(24.99)


def test_dividend_structured_quantity_without_description_rate():
    a = sync.convert_dividend_to_activity(div(description="SPECIAL"), "acc", {}, {})
    assert (a["quantity"], a["unitPrice"]) == (100.0, 0.25)


def test_withholding_tax_becomes_fee_and_refund_becomes_zero():
    assert sync.convert_dividend_to_activity(div(tax=-3.75), "acc", {}, {})["fee"] == pytest.approx(3.75)
    assert sync.convert_dividend_to_activity(div(tax=2.0), "acc", {}, {})["fee"] == 0.0


def test_dividend_pence_market_scales_price_and_tax():
    d = div(currency="GBP", amount=10.0, tax=-2.0, description="X CASH DIVIDEND GBP 0.10 PER SHARE")
    a = sync.convert_dividend_to_activity(d, "acc", {ISIN: "PAF.L"}, {})
    assert a["currency"] == "GBp"
    assert a["unitPrice"] == pytest.approx(10.0)      # 0.10 GBP x 100
    assert a["fee"] == pytest.approx(200.0)


@pytest.mark.parametrize("amount,tax", [(0.0, 0.0), (-25.0, 0.0), (0.0, -3.0)])
def test_non_positive_dividend_is_not_imported(amount, tax):
    assert sync.convert_dividend_to_activity(div(amount=amount, tax=tax), "acc", {}, {}) is None


def test_dividend_dedup_key_uses_isin_then_symbol():
    assert sync.convert_dividend_to_activity(div(), "a", {}, {})["comment"].startswith(f"dividend#{ISIN}#")
    no_isin = sync.convert_dividend_to_activity(div(isin=""), "a", {}, {})
    assert no_isin["comment"] == "dividend#KO#2026-07-15"


def test_dividend_unmapped_isin_is_reported_without_overwriting_trade_description():
    unmapped = {ISIN: {"symbol": "KO", "description": "COCA COLA"}}
    sync.convert_dividend_to_activity(div(), "acc", {}, unmapped)
    assert unmapped[ISIN]["description"] == "COCA COLA"


@pytest.mark.parametrize("quantity,amount", [("3", 1.5), ("450", 45.1), ("0.00000001", 1), ("1", 5)])
def test_dividend_structured_quantity_has_no_inference_rounding_or_fallback(quantity, amount):
    activity = sync.convert_dividend_to_activity(div(quantity=quantity, amount=amount,
                                                 description="USD 0.1 PER SHARE"), "acc", {}, {})
    assert activity["quantity"] == float(quantity)
    assert activity["quantity"] * activity["unitPrice"] == pytest.approx(amount)


def test_dividend_structured_quantity_does_not_use_description_when_evidence_is_missing():
    dividend = div()
    dividend["accruals"] = []
    assert sync.convert_dividend_to_activity(dividend, "acc", {}, {}) is None


@pytest.mark.parametrize("quantity,amount,tax,currency,symbol", [
    ("1e-400", 1, 0, "USD", "KO"), ("1e400", 1, 0, "USD", "KO"),
    ("1e-308", 1e308, 0, "USD", "KO"), ("1e308", 1e-308, 0, "USD", "KO"),
    ("1", 1e307, 0, "GBP", "PAF.L"), ("1", 1, -1e307, "GBP", "PAF.L"),
    ("100", float("inf"), 0, "USD", "KO"), ("100", 25, float("nan"), "USD", "KO"),
    ("100", 25, float("-inf"), "USD", "KO"),
])
def test_dividend_structured_numeric_rejects_unsafe_final_values(quantity, amount, tax, currency, symbol, caplog):
    dividend = div(quantity=quantity, amount=amount, tax=tax, currency=currency)
    assert sync.convert_dividend_to_activity(dividend, "acc", {ISIN: symbol}, {}) is None
    assert any("numeric" in record.message for record in caplog.records)


@pytest.mark.parametrize("field", ["amount", "tax"])
def test_dividend_structured_numeric_rejects_positive_underflow_in_cash(field):
    dividend = div()
    if field == "amount":
        dividend["payments"][0]["amount"] = "1e-400"
    else:
        dividend["cash_rows"][1]["amount"] = "-1e-400"
    assert sync.convert_dividend_to_activity(dividend, "acc", {}, {}) is None


def test_dividend_structured_numeric_normal_pence_scaling_preserves_cash_and_quantity():
    dividend = div(quantity="450", amount=45.1, tax=-2, currency="GBP")
    dividend["accruals"][0].update(grossAmount="999", tax="-999", rate="0.1")
    activity = sync.convert_dividend_to_activity(dividend, "acc", {ISIN: "PAF.L"}, {})
    assert activity["quantity"] == 450
    assert activity["currency"] == "GBp"
    assert activity["quantity"] * activity["unitPrice"] / 100 == pytest.approx(45.1)
    assert activity["fee"] / 100 == 2


def test_dividend_structured_numeric_valid_subnormal_price_is_not_rounded_to_zero():
    activity = sync.convert_dividend_to_activity(div(quantity="1", amount=1e-310), "acc", {}, {})
    assert activity["unitPrice"] == 1e-310
    assert activity["quantity"] == 1


def test_dividend_structured_numeric_large_cash_can_produce_representable_price():
    dividend = div(quantity="1e308")
    dividend["payments"][0]["amount"] = "1e400"
    activity = sync.convert_dividend_to_activity(dividend, "acc", {}, {})
    assert activity["quantity"] == 1e308
    assert activity["unitPrice"] == 1e92


@pytest.mark.parametrize("amount", ["1e1000000000", "1e-1000000000"])
def test_dividend_structured_numeric_extreme_cash_exponents_reject_without_unbounded_arithmetic(amount):
    dividend = div()
    dividend["payments"][0]["amount"] = amount
    assert sync.convert_dividend_to_activity(dividend, "acc", {}, {}) is None


@pytest.mark.parametrize("quantity,amount,copies", [("1e-308", "1e999999", 1),
                                                    ("1", "1e999999", 10)])
def test_dividend_structured_numeric_decimal_arithmetic_overflow_stays_local(quantity, amount, copies):
    dividend = div(quantity=quantity)
    dividend["payments"] = [dict(dividend["payments"][0], amount=amount) for _ in range(copies)]
    assert sync.convert_dividend_to_activity(dividend, "acc", {}, {}) is None


@pytest.mark.parametrize("side", ["SELL (Ca.)", "", "sell", "Buy", " BUY", None])
def test_unknown_trade_side_conversion_rejected(side):
    assert sync.convert_trade_to_activity(trade(buySell=side), "acc", {}, {}) is None


def test_unknown_trade_side_conversion_keeps_buy_and_sell():
    buy = sync.convert_trade_to_activity(trade(buySell="BUY"), "acc", {}, {})
    sell = sync.convert_trade_to_activity(trade(buySell="SELL", quantity="-4"), "acc", {}, {})
    assert (buy["type"], sell["type"], sell["quantity"]) == ("BUY", "SELL", 4.0)
