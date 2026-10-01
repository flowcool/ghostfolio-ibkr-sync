"""Offline tests: trade gate (filter_trades_by_holdings) and dividend date matching."""
from collections import defaultdict

import pytest

import ibkr_to_ghostfolio as m

ACC = "acc"
ISIN = "US1912161007"


def positions(qty=None, isin_symbols=None, manual_sells=None, dividend_dates=None, manual_buys=None):
    return {"qty": defaultdict(float, qty or {}),
            "isin_symbols": defaultdict(set, isin_symbols or {}),
            "manual_sells": defaultdict(list, manual_sells or {}),
            "manual_buys": defaultdict(list, manual_buys or {}),
            "dividend_dates": defaultdict(list, dividend_dates or {})}


def tr(tid, qty, date="20260801;100000", symbol="KO", isin=ISIN):
    return {"tradeID": tid, "symbol": symbol, "isin": isin, "quantity": str(qty), "dateTime": date}


def gate(trades, pos, mapping=None, existing=()):
    return m.filter_trades_by_holdings(trades, pos, ACC, mapping or {}, set(existing))


def ids(trades):
    return [t["tradeID"] for t in trades]


# --- holdings gate --------------------------------------------------------

def test_sell_of_long_held_position_is_kept():
    pos = positions(qty={(ACC, "KO"): 100})
    assert ids(gate([tr("S1", -50)], pos)) == ["S1"]


def test_sell_without_any_ghostfolio_position_is_dropped():
    assert gate([tr("S1", -50)], positions()) == []


def test_sell_that_would_go_negative_is_dropped():
    pos = positions(qty={(ACC, "KO"): 10})
    assert gate([tr("S1", -50)], pos) == []


def test_round_trip_inside_window_is_kept_even_without_ghostfolio_position():
    trades = [tr("B1", 50, "20260701;100000"), tr("S1", -50, "20260801;100000")]
    assert ids(gate(trades, positions())) == ["B1", "S1"]


def test_net_zero_round_trip_is_kept_even_if_ghostfolio_holds_a_negative_position():
    # a net-zero group never changes the position, so a pre-existing short must not block it
    pos = positions(qty={(ACC, "KO"): -5})
    trades = [tr("B1", 50, "20260701;100000"), tr("S1", -50, "20260801;100000")]
    assert ids(gate(trades, pos)) == ["B1", "S1"]


def test_buys_alone_are_always_kept():
    assert ids(gate([tr("B1", 5)], positions())) == ["B1"]


def test_rejected_ticker_drops_its_buys_too_but_not_other_tickers():
    # KO nets negative (-40) with no Ghostfolio position: both its trades go, PEP stays
    trades = [tr("B1", 10, "20260701;100000"), tr("S1", -50, "20260801;100000"),
              tr("B2", 3, symbol="PEP", isin="US7134481081")]
    assert ids(gate(trades, positions())) == ["B2"]


def test_already_imported_trade_does_not_count_as_pending():
    # Ghostfolio holds 10 AFTER the already-imported sell S0 (-10). If S0 were counted again,
    # held 10 + (-10 - 8) = -8 would reject S1; excluded, 10 - 8 = 2 keeps it.
    pos = positions(qty={(ACC, "KO"): 10})
    trades = [tr("S0", -10, "20260701;100000"), tr("S1", -8, "20260801;100000")]
    assert "S1" in ids(gate(trades, pos, existing={"S0"}))


def test_trade_without_id_passes_the_gate_untouched():
    # by design the gate skips ID-less trades; process_account then refuses them
    # ("missing tradeID, cannot deduplicate safely"), so they are never imported
    assert ids(gate([tr("", -5)], positions())) == [""]


def test_position_held_under_another_symbol_same_isin_is_rejected(caplog):
    pos = positions(qty={(ACC, "OLD"): 100}, isin_symbols={(ACC, ISIN): {"OLD"}})
    assert gate([tr("S1", -50, symbol="NEW")], pos) == []
    assert any("add mapping" in r.message for r in caplog.records)


def test_mapping_resolves_the_ticker_so_the_held_position_is_found():
    pos = positions(qty={(ACC, "KO"): 100})
    assert ids(gate([tr("S1", -50, symbol="KOX")], pos, mapping={ISIN: "KO"})) == ["S1"]


# --- manual sells ---------------------------------------------------------

def test_manual_sell_same_day_same_qty_is_not_reimported():
    pos = positions(qty={(ACC, "KO"): 100}, manual_sells={(ACC, "KO"): [["2026-08-01", 50.0]]})
    assert gate([tr("S1", -50)], pos) == []
    assert pos["manual_sells"][(ACC, "KO")] == []        # entry consumed


def test_manual_sell_two_days_apart_still_matches_three_does_not():
    pos = positions(qty={(ACC, "KO"): 100}, manual_sells={(ACC, "KO"): [["2026-08-03", 50.0]]})
    assert gate([tr("S1", -50)], pos) == []
    pos = positions(qty={(ACC, "KO"): 100}, manual_sells={(ACC, "KO"): [["2026-08-04", 50.0]]})
    assert ids(gate([tr("S1", -50)], pos)) == ["S1"]


def test_each_manual_sell_is_consumed_by_one_ibkr_sell_only():
    pos = positions(qty={(ACC, "KO"): 100}, manual_sells={(ACC, "KO"): [["2026-08-01", 50.0]]})
    trades = [tr("S1", -50, "20260801;090000"), tr("S2", -50, "20260801;150000")]
    assert ids(gate(trades, pos)) == ["S2"]


def test_closest_manual_entry_is_chosen():
    pos = positions(qty={(ACC, "KO"): 100},
                    manual_sells={(ACC, "KO"): [["2026-07-30", 50.0], ["2026-08-01", 50.0]]})
    gate([tr("S1", -50)], pos)
    assert pos["manual_sells"][(ACC, "KO")] == [["2026-07-30", 50.0]]


def test_nearby_manual_sell_with_another_quantity_is_ambiguous_and_warns(caplog):
    pos = positions(qty={(ACC, "KO"): 100}, manual_sells={(ACC, "KO"): [["2026-08-01", 30.0]]})
    assert gate([tr("S1", -50)], pos) == []
    assert any("another quantity" in r.message for r in caplog.records)


def test_split_fills_summing_to_a_manual_sell_are_matched():
    pos = positions(qty={(ACC, "KO"): 100}, manual_sells={(ACC, "KO"): [["2026-08-01", 50.0]]})
    trades = [tr("S1", -20, "20260801;090000"), tr("S2", -30, "20260801;100000")]
    assert gate(trades, pos) == []


def test_manual_sell_under_another_symbol_with_same_isin_is_found():
    pos = positions(qty={(ACC, "OLD"): 100}, isin_symbols={(ACC, ISIN): {"OLD"}},
                    manual_sells={(ACC, "OLD"): [["2026-08-01", 50.0]]})
    assert gate([tr("S1", -50, symbol="NEW")], pos) == []


# --- manual buys (same rule as sells, but never silent) --------------------

def test_manual_buy_same_day_same_qty_is_not_reimported_and_warns(caplog):
    pos = positions(manual_buys={(ACC, "KO"): [["2026-08-01", 10.0]]})
    assert gate([tr("B1", 10)], pos) == []
    msg = " ".join(r.message for r in caplog.records if r.levelname == "WARNING")
    assert "B1" in msg and "2026-08-01" in msg and "IBKR#B1" in msg
    assert pos["manual_buys"][(ACC, "KO")] == []         # entry consumed


def test_manual_buy_window_is_two_days():
    pos = positions(manual_buys={(ACC, "KO"): [["2026-08-03", 10.0]]})
    assert gate([tr("B1", 10)], pos) == []
    pos = positions(manual_buys={(ACC, "KO"): [["2026-08-04", 10.0]]})
    assert ids(gate([tr("B1", 10)], pos)) == ["B1"]


def test_manual_buy_with_another_quantity_is_ambiguous_and_warns(caplog):
    pos = positions(manual_buys={(ACC, "KO"): [["2026-08-01", 7.0]]})
    assert gate([tr("B1", 10)], pos) == []
    assert any("another quantity" in r.message and "buy" in r.message for r in caplog.records)


def test_buy_without_nearby_manual_entry_is_imported_silently(caplog):
    pos = positions(manual_buys={(ACC, "KO"): [["2026-06-01", 10.0]], (ACC, "PEP"): [["2026-08-01", 10.0]]})
    assert ids(gate([tr("B1", 10)], pos)) == ["B1"]
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_split_buy_fills_summing_to_a_manual_buy_are_matched(caplog):
    pos = positions(manual_buys={(ACC, "KO"): [["2026-08-01", 50.0]]})
    trades = [tr("B1", 20, "20260801;090000"), tr("B2", 30, "20260801;100000")]
    assert gate(trades, pos) == []
    assert any("sum to a manual" in r.message for r in caplog.records)


def test_one_manual_buy_absorbs_only_one_ibkr_buy():
    pos = positions(manual_buys={(ACC, "KO"): [["2026-08-01", 10.0]]})
    trades = [tr("B1", 10, "20260801;090000"), tr("B2", 10, "20260801;150000")]
    assert ids(gate(trades, pos)) == ["B2"]


def test_manual_buy_under_another_symbol_with_same_isin_is_found():
    pos = positions(isin_symbols={(ACC, ISIN): {"OLD"}}, manual_buys={(ACC, "OLD"): [["2026-08-01", 10.0]]})
    assert gate([tr("B1", 10, symbol="NEW")], pos) == []


def test_manual_buy_never_absorbs_an_ibkr_sell_and_vice_versa():
    pos = positions(qty={(ACC, "KO"): 100}, manual_buys={(ACC, "KO"): [["2026-08-01", 10.0]]})
    assert ids(gate([tr("S1", -10)], pos)) == ["S1"]
    pos = positions(manual_sells={(ACC, "KO"): [["2026-08-01", 10.0]]})
    assert ids(gate([tr("B1", 10)], pos)) == ["B1"]


def test_skipped_manual_buy_does_not_count_as_pending_for_later_sells():
    # Ghostfolio already holds the manual buy (qty 10): the sell must be judged on that
    pos = positions(qty={(ACC, "KO"): 10}, manual_buys={(ACC, "KO"): [["2026-07-30", 10.0]]})
    trades = [tr("B1", 10, "20260730;100000"), tr("S1", -10, "20260801;100000")]
    assert ids(gate(trades, pos)) == ["S1"]


def test_skipped_buys_are_not_counted_as_sells_in_the_summary(caplog):
    caplog.set_level("INFO")
    pos = positions(qty={(ACC, "KO"): 100}, manual_buys={(ACC, "KO"): [["2026-08-01", 10.0]]},
                    manual_sells={(ACC, "KO"): [["2026-08-02", 5.0]]})
    gate([tr("B1", 10), tr("S1", -5, "20260802;100000")], pos)
    summary = [r.message for r in caplog.records if "Sells not imported" in r.message]
    assert len(summary) == 1 and "1 sell(s) already entered manually" in summary[0]
    only_buy = positions(manual_buys={(ACC, "KO"): [["2026-08-01", 10.0]]})
    caplog.clear()
    gate([tr("B1", 10)], only_buy)
    assert not [r for r in caplog.records if "Sells not imported" in r.message]


# --- dividend date matching ----------------------------------------------

def act(date="2026-07-15", symbol="KO"):
    return {"date": f"{date}T00:00:00+00:00", "accountId": ACC, "symbol": symbol}


@pytest.mark.parametrize("existing,expected", [
    ("2026-07-15", "2026-07-15"), ("2026-07-12", "2026-07-12"), ("2026-07-18", "2026-07-18"),
    ("2026-07-11", None), ("2026-07-19", None), ("not-a-date", None),
])
def test_dividend_date_matches_within_three_days(existing, expected):
    pos = positions(dividend_dates={(ACC, "KO"): [existing]})
    assert m._dividend_date_matches(pos, act()) == expected


def test_dividend_date_match_is_per_account_and_symbol():
    pos = positions(dividend_dates={("other", "KO"): ["2026-07-15"], (ACC, "PEP"): ["2026-07-15"]})
    assert m._dividend_date_matches(pos, act()) is None
