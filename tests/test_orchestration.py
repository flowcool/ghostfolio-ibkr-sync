"""Offline tests: orchestration (process_account, main, load_config) and the IBKR Flex fetch."""
import logging
from collections import defaultdict
import xml.etree.ElementTree as ET
import time

import pytest

import requests
from ghostfolio_ibkr_sync import app, config, ghostfolio, ibkr, notify, sync

original_import = ghostfolio.ghost_import_activities

ISIN_KO = "US1912161007"
ISIN_PEP = "US7134481081"
ACC = "gf-acc"
CFG = {"ibkr_token": "SECRET-TOK", "dry_run": False, "ghost_host": "http://g", "ghost_token": "t"}


# --- helpers ----------------------------------------------------------------

def positions(qty=None, versioned_identities=None):
    return {"qty": defaultdict(float, qty or {}), "isin_symbols": defaultdict(set),
            "manual_sells": defaultdict(list), "manual_buys": defaultdict(list),
            "dividend_dates": defaultdict(list),
            "versioned_identities": set(versioned_identities or ())}


def trade_xml(tid, side="BUY", qty=10, symbol="KO", isin=ISIN_KO, date="20260801;100000", **extra):
    q = qty if side == "BUY" else -qty
    attrs = {"tradeID": tid, "symbol": symbol, "isin": isin, "assetCategory": "STK", "buySell": side,
             "quantity": q, "tradePrice": 60, "ibCommission": -1, "currency": "USD", "dateTime": date}
    attrs.update(extra)
    return "<Trade " + " ".join(f'{k}="{v}"' for k, v in attrs.items()) + "/>"


def flex_datetime(date):
    """Cash rows carry the mandatory Flex form YYYYMMDD;HHmmss TimeZone."""
    return date if ";" in date else f"{date};120000 EST"


def div_xml(amount="25.00", date="20260715", isin=ISIN_KO, symbol="KO"):
    date = flex_datetime(date)
    return (f'<CashTransaction type="Dividends" levelOfDetail="DETAIL" amount="{amount}" dateTime="{date}" '
            'accountId="broker-account" conid="1" actionID="A1" exDate="20260701" '
            f'isin="{isin}" symbol="{symbol}" currency="USD" description="X CASH DIVIDEND USD 0.25 PER SHARE"/>')


def report(trades="", divs="", cash="100.5", cash_section=True, base_currency="USD"):
    cash_xml = (f'<CashReport><CashReportCurrency currency="BASE_SUMMARY" endingCash="{cash}"/></CashReport>'
                if cash is not None else "")
    info = f'<AccountInformation accountId="broker-account" currency="{base_currency}"/>' if base_currency else ""
    ct = f"<CashTransactions>{divs}</CashTransactions>" if cash_section else ""
    # Enrich existing fixtures; input compatibility scenarios belong to task 2.1.
    accruals = []
    for row in ET.fromstring(f"<R>{divs}</R>"):
        if row.get("type") != "Dividends":
            continue
        attrs = {key: row.get(key, "") for key in ("accountId", "conid", "currency", "actionID", "exDate")}
        attrs.update(quantity="100", code="Re", payDate=row.get("dateTime", "")[:8],
                     date=row.get("dateTime", "")[:8], reportDate=row.get("dateTime", "")[:8])
        accruals.append(ET.tostring(ET.Element("ChangeInDividendAccrual", attrs), encoding="unicode"))
    evidence = "<ChangeInDividendAccruals>" + "".join(accruals) + "</ChangeInDividendAccruals>"
    return (f"<FlexQueryResponse><FlexStatements><FlexStatement>{info}<Trades>{trades}</Trades>{ct}{cash_xml}{evidence}"
            f"</FlexStatement></FlexStatements></FlexQueryResponse>")


class World:
    """Records every side effect so tests can assert on what process_account did."""
    def __init__(self, monkeypatch, xml, find=ACC, import_ok=True, cash_ok=True):
        self.imported, self.cash_calls = [], []
        self.import_ok, self.cash_ok = import_ok, cash_ok
        monkeypatch.setattr(app, "fetch_flex_report", self._fetch(xml))
        monkeypatch.setattr(app, "ghost_find_account_id", self._find(find))
        monkeypatch.setattr(app, "ghost_import_activities", self._import)
        monkeypatch.setattr(app, "ghost_update_cash_balance", self._cash)

    @staticmethod
    def _fetch(xml):
        def f(*a, **k):
            if isinstance(xml, Exception):
                raise xml
            return xml
        return f

    @staticmethod
    def _find(result):
        def f(*a):
            if isinstance(result, Exception):
                raise result
            return result
        return f

    def _import(self, cfg, acts):
        self.imported.append(list(acts))
        return (list(acts), True) if self.import_ok else ([], False)

    def _cash(self, cfg, acc, balance, base_currency):
        if isinstance(self.cash_ok, Exception):
            raise self.cash_ok
        self.cash_calls.append((acc, balance))
        return self.cash_ok

    def run(self, ids=None, comments=None, pos=None, mapping=None):
        self.ids = set() if ids is None else ids
        self.comments = set() if comments is None else comments
        self.pos = pos or positions()
        self.result = app.process_account(CFG, "U1", "q1", "IBKR", mapping or {}, self.ids, self.comments, self.pos)
        return self.result

    @property
    def activities(self):
        return [a for batch in self.imported for a in batch]


# --- process_account: failure isolation ------------------------------------------

def test_flex_fetch_failure_returns_failed_and_does_nothing_else(monkeypatch):
    w = World(monkeypatch, RuntimeError("IBKR down"))
    assert w.run() == ({}, False)
    assert w.imported == [] and w.cash_calls == []


def test_oversized_flex_reply_prevents_import_and_cash_update(monkeypatch):
    fetch = ibkr.fetch_flex_report
    w = World(monkeypatch, report(trade_xml("T1")))
    monkeypatch.setattr(app, "fetch_flex_report", fetch)
    response = requests.Response()
    response._content = b"x" * (ibkr.IBKR_MAX_XML_BYTES + 1)
    monkeypatch.setattr(ibkr, "_ibkr_get", lambda *a, **k: response)
    assert w.run() == ({}, False)
    assert w.imported == [] and w.cash_calls == []


@pytest.mark.parametrize("find", [requests.ConnectionError("net"), None])
def test_ghostfolio_account_lookup_failure_or_missing_account_fails_the_account(monkeypatch, find):
    w = World(monkeypatch, report(trade_xml("T1")), find=find)
    assert w.run() == ({}, False)
    assert w.imported == [] and w.cash_calls == []


def test_missing_cash_transactions_section_fails_the_run_but_still_imports_trades(monkeypatch):
    w = World(monkeypatch, report(trade_xml("T1"), cash_section=False))
    _, ok = w.run()
    assert ok is False
    assert [a["comment"] for a in w.activities] == ["IBKR#T1"]


def test_import_failure_fails_the_account_keeps_state_untouched_but_still_updates_cash(monkeypatch):
    w = World(monkeypatch, report(trade_xml("T1")), import_ok=False)
    _, ok = w.run()
    assert ok is False
    assert w.ids == set() and w.pos["qty"][(ACC, "KO")] == 0.0     # nothing recorded as imported
    assert w.cash_calls == [(ACC, 100.5)]                          # cash step is independent


@pytest.mark.parametrize("cash_ok", [False, RuntimeError("PUT failed")])
def test_cash_update_failure_fails_the_account(monkeypatch, cash_ok):
    w = World(monkeypatch, report(trade_xml("T1")), cash_ok=cash_ok)
    assert w.run()[1] is False


def test_report_without_cash_row_is_a_warning_not_a_failure(monkeypatch, caplog):
    w = World(monkeypatch, report(trade_xml("T1"), cash=None))
    assert w.run()[1] is True
    assert w.cash_calls == []
    assert any("No BASE_SUMMARY" in r.message for r in caplog.records)


# --- process_account: what gets imported and remembered ----------------------------

def test_successful_run_imports_and_records_trades_and_dividends(monkeypatch):
    xml = report(trade_xml("T1") + trade_xml("T2", "SELL", 4, "PEP", ISIN_PEP, "20260802;100000"),
                 div_xml())
    w = World(monkeypatch, xml)
    unmapped, ok = w.run(pos=positions({(ACC, "PEP"): 10}))
    assert ok is True
    assert sorted(a["comment"] for a in w.activities) == ["IBKR#T1", "IBKR#T2", f"dividend#{ISIN_KO}#2026-07-15"]
    assert len(w.imported) == 2                                     # buys/dividends before sells
    assert w.ids == {"T1", "T2"}
    assert w.comments == {(ACC, f"dividend#{ISIN_KO}#2026-07-15")}   # keyed by accountId
    assert w.pos["qty"][(ACC, "KO")] == pytest.approx(10.0)
    assert w.pos["qty"][(ACC, "PEP")] == pytest.approx(6.0)         # 10 - 4
    assert w.pos["dividend_dates"][(ACC, "KO")] == []          # imported connector row stays out of the index
    assert set(unmapped) == {ISIN_KO, ISIN_PEP}                     # no mapping given
    assert w.cash_calls == [(ACC, 100.5)]


def test_second_account_sharing_the_sets_does_not_reimport(monkeypatch):
    w = World(monkeypatch, report(trade_xml("T1"), div_xml()))
    w.run()
    first = len(w.activities)
    w.imported.clear()
    app.process_account(CFG, "U2", "q2", "IBKR", {}, w.ids, w.comments, w.pos)
    assert first == 2 and w.activities == []


def test_trade_without_id_is_skipped_and_warned(monkeypatch, caplog):
    w = World(monkeypatch, report(trade_xml("")))
    w.run()
    assert w.activities == []
    assert any("missing tradeID" in r.message for r in caplog.records)


@pytest.mark.parametrize("second", [{}, {"symbol": "PEP", "isin": ISIN_PEP}])
def test_every_trade_without_id_is_counted_and_warned(monkeypatch, caplog, second):
    caplog.set_level("INFO")
    w = World(monkeypatch, report(trade_xml("") + trade_xml("", **second)
                                 + trade_xml("T1") + trade_xml("T1")))
    assert w.run()[1] is False
    assert [a["comment"] for a in w.activities] == ["IBKR#T1"]
    assert w.ids == {"T1"}
    assert len([r for r in caplog.records if "missing tradeID" in r.message]) == 2
    assert any("New trade activities: 1, duplicates skipped: 1, other skipped: 2"
               in r.message for r in caplog.records)


def test_already_imported_trade_is_not_reimported(monkeypatch, caplog):
    caplog.set_level("INFO")
    w = World(monkeypatch, report(trade_xml("T1")))
    w.run(ids={"T1"})
    assert w.activities == []
    assert any("duplicates skipped: 1" in r.message for r in caplog.records)


def test_fx_and_option_trades_never_reach_the_import_nor_the_holdings_gate(monkeypatch):
    # a CASH sell of the same symbol would push KO to -40 and get the real buy rejected
    # if it were not dropped before the gate
    xml = report(trade_xml("C1", "SELL", 50, assetCategory="CASH") + trade_xml("O1", assetCategory="OPT")
                 + trade_xml("T1"))
    w = World(monkeypatch, xml)
    w.run()
    assert [a["comment"] for a in w.activities] == ["IBKR#T1"]


@pytest.mark.parametrize("invalid", [{"tradePrice": "invalid"}, {"dateTime": "garbage"},
                                    {"quantity": "invalid"}, {"tradePrice": "nan"},
                                    {"quantity": "inf"}, {"ibCommission": "-inf"}])
def test_invalid_buy_cannot_authorize_unbacked_sell(monkeypatch, invalid):
    w = World(monkeypatch, report(trade_xml("B1", **invalid) + trade_xml("S1", "SELL")))
    _, ok = w.run()
    assert ok is False
    assert w.activities == []
    assert w.ids == set()
    assert w.pos["qty"][(ACC, "KO")] == 0
    assert w.cash_calls == [(ACC, 100.5)]


def test_invalid_trade_does_not_prevent_unrelated_valid_security_import(monkeypatch):
    w = World(monkeypatch, report(trade_xml("B1", tradePrice="invalid") + trade_xml("S1", "SELL")
                                 + trade_xml("P1", symbol="PEP", isin=ISIN_PEP)))
    assert w.run()[1] is False
    assert [a["comment"] for a in w.activities] == ["IBKR#P1"]
    assert w.pos["qty"][(ACC, "KO")] == 0
    assert w.pos["qty"][(ACC, "PEP")] == 10


def test_unknown_trade_side_run_rejects_row_and_imports_valid_rows(monkeypatch, caplog):
    xml = report(trade_xml("B1") + trade_xml("U1", "SELL (Ca.)", 4)
                 + trade_xml("P1", symbol="PEP", isin=ISIN_PEP))
    w = World(monkeypatch, xml)
    _, ok = w.run()
    assert ok is False
    assert [a["comment"] for a in w.activities] == ["IBKR#B1", "IBKR#P1"]
    assert w.ids == {"B1", "P1"}
    # the rejected row never reaches the holdings gate: 10 bought, nothing subtracted
    assert w.pos["qty"][(ACC, "KO")] == 10
    assert any(r.levelname == "ERROR" and "Unknown buySell" in r.message and "U1" in r.message
               for r in caplog.records)


def test_valid_balanced_batch_still_imports_without_existing_holdings(monkeypatch):
    w = World(monkeypatch, report(trade_xml("B1") + trade_xml("S1", "SELL")))
    assert w.run()[1] is True
    assert [a["comment"] for a in w.activities] == ["IBKR#B1", "IBKR#S1"]
    assert w.pos["qty"][(ACC, "KO")] == 0


def test_gate_uses_sell_quantity_as_it_will_be_imported(monkeypatch):
    # Converter uses BUY/SELL and abs(quantity); gate must use that same sign.
    w = World(monkeypatch, report(trade_xml("S1", "SELL", quantity="10")))
    w.run()
    assert w.activities == []
    assert w.pos["qty"][(ACC, "KO")] == 0


def test_manual_buy_remains_deduplicated_after_preconversion(monkeypatch):
    pos = positions({(ACC, "KO"): 10})
    pos["manual_buys"][(ACC, "KO")].append(["2026-08-01", 10])
    w = World(monkeypatch, report(trade_xml("B1")))
    assert w.run(pos=pos)[1] is True
    assert w.activities == []
    assert w.pos["qty"][(ACC, "KO")] == 10


# --- process_account: dividend deduplication ---------------------------------------

@pytest.mark.parametrize("comment", [f"dividend#{ISIN_KO}#2026-07-15", "dividend#KO#2026-07-15"])
def test_dividend_already_present_by_comment_new_or_old_format_is_skipped(monkeypatch, comment):
    w = World(monkeypatch, report(divs=div_xml()))
    w.run(comments={(ACC, comment)})                           # same account -> deduped
    assert w.activities == []


def test_dividend_same_isin_and_date_on_a_different_account_is_not_deduped(monkeypatch):
    """The dedup key is (accountId, comment): a second Ghostfolio account holding
    the same ISIN paid on the same day must still import its own dividend."""
    w = World(monkeypatch, report(divs=div_xml()))             # dividend 2026-07-15 on account ACC
    w.run(comments={("other-gf-account", f"dividend#{ISIN_KO}#2026-07-15")})
    assert [a["type"] for a in w.activities] == ["DIVIDEND"]    # not skipped: different account


@pytest.mark.parametrize("existing,skipped", [("2026-07-17", True), ("2026-07-18", True), ("2026-07-12", True),
                                              ("2026-07-19", False), ("2026-07-11", False)])
def test_dividend_match_window_is_exactly_three_days(monkeypatch, existing, skipped):
    pos = positions()
    pos["dividend_dates"][(ACC, "KO")].append((existing, None, None, None))
    w = World(monkeypatch, report(divs=div_xml()))              # dividend dated 2026-07-15
    w.run(pos=pos)
    assert (w.activities == []) is skipped


def test_new_dividend_is_imported(monkeypatch):
    w = World(monkeypatch, report(divs=div_xml()))
    w.run()
    assert [a["type"] for a in w.activities] == ["DIVIDEND"]


def test_dividend_of_a_partly_sold_long_held_position_is_imported(monkeypatch):
    # regression for the removed window-only filter: only a SELL in the window, still held in Ghostfolio
    xml = report(trade_xml("S1", "SELL", 50), div_xml())
    w = World(monkeypatch, xml)
    w.run(pos=positions({(ACC, "KO"): 100}))
    assert sorted(a["type"] for a in w.activities) == ["DIVIDEND", "SELL"]


# --- main ---------------------------------------------------------------------

@pytest.fixture
def env(monkeypatch):
    for k, v in {"IBKR_TOKEN": "tok", "IBKR_ACCOUNT_IDS": "U1,U2", "IBKR_QUERY_IDS": "q1,q2",
                 "GHOST_TOKEN": "g", "GHOST_HOST": "http://ghost:3333/", "MAPPING_FILE": ""}.items():
        monkeypatch.setenv(k, v)
    for k in ("GHOST_ACCOUNT_NAMES", "DRY_RUN", "GHOST_PLATFORM_ID",
              "GHOST_ACCESS_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DRY_RUN", "false")
    return monkeypatch


def stub_main(monkeypatch, results, existing=None):
    calls = []

    def fake_process(config, ibkr_id, qid, name, mapping, ids, comments, pos):
        calls.append((ibkr_id, qid, name))
        return results[ibkr_id]
    monkeypatch.setattr(app, "process_account", fake_process)
    monkeypatch.setattr(app, "ghost_get_existing_orders",
                        lambda cfg: existing or (set(), set(), positions()))
    return calls


def test_main_all_accounts_clean_exits_zero_and_uses_ids_as_names_without_account_names(env, caplog):
    calls = stub_main(env, {"U1": ({}, True), "U2": ({}, True)})
    assert app.main() == 0
    assert calls == [("U1", "q1", "U1"), ("U2", "q2", "U2")]
    assert any("No GHOST_ACCOUNT_NAMES" in r.message for r in caplog.records)


def test_main_failed_account_exits_one_but_still_processes_the_others(env, caplog):
    calls = stub_main(env, {"U1": ({}, False), "U2": ({}, True)})
    assert app.main() == 1
    assert [c[0] for c in calls] == ["U1", "U2"]
    assert any("1 of 2 account(s): U1" in r.message for r in caplog.records)


def test_main_unmapped_isin_is_reported_but_is_not_a_failure(env, caplog):
    stub_main(env, {"U1": ({"JP1": {"symbol": "1234.T", "description": "ACME"}}, True), "U2": ({}, True)})
    assert app.main() == 0
    assert any("Unmapped ISIN JP1 (ACME)" in r.message for r in caplog.records)


def test_main_unexpected_exception_in_one_account_does_not_stop_the_others(env, caplog):
    # real process_account: the conversion blows up for the first account only
    env.setenv("GHOST_ACCOUNT_NAMES", "A,B")
    fetched, imported, cash = [], [], []
    env.setattr(app, "ghost_get_existing_orders", lambda cfg: (set(), set(), positions()))
    env.setattr(app, "fetch_flex_report", lambda token, qid, *a, **k: fetched.append(qid) or report(trade_xml("T1")))
    env.setattr(app, "ghost_find_account_id", lambda cfg, name: f"gf-{name}")
    env.setattr(app, "ghost_import_activities", lambda cfg, acts: imported.append(list(acts)) or (list(acts), True))
    env.setattr(app, "ghost_update_cash_balance", lambda cfg, acc, bal, cur: cash.append(acc) or True)
    real = sync.convert_trade_to_activity
    calls = []
    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise KeyError("unforeseen field")
        return real(*a, **k)
    env.setattr(app, "convert_trade_to_activity", flaky)
    assert app.main() == 1                                            # the run is still flagged
    assert fetched == ["q1", "q2"]                                  # second account reached
    assert len(imported) == 1 and cash == ["gf-B"]                  # and fully synced
    rec = [r for r in caplog.records if "Unexpected error while processing IBKR account U1" in r.message]
    assert len(rec) == 1 and rec[0].exc_info and rec[0].exc_info[0] is KeyError   # traceback kept
    assert any("1 of 2 account(s): U1" in r.message for r in caplog.records)


@pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit])
def test_main_does_not_swallow_keyboard_interrupt_or_system_exit(env, exc):
    def interrupted(*a, **k):
        raise exc
    stub_main(env, {})
    env.setattr(app, "process_account", interrupted)
    with pytest.raises(exc):
        app.main()


@pytest.mark.parametrize("exc", [RuntimeError("count mismatch"), requests.ConnectionError("down")])
def test_main_untrusted_or_unreadable_existing_activities_stops_before_any_account(env, exc):
    calls = stub_main(env, {})
    def boom(cfg):
        raise exc
    env.setattr(app, "ghost_get_existing_orders", boom)
    assert app.main() == 1
    assert calls == []


def test_versioned_identity_reader_invalid_identity_stops_before_financial_writes(
        env, caplog):
    invalid_identity = "IBKR#v2#PRIVATE-ACCOUNT:TRADE:PRIVATE-ID:extra"
    row = {"type": "BUY", "quantity": 1, "comment": invalid_identity,
           "accountId": "destination", "date": "2026-08-01T00:00:00.000Z",
           "assetProfile": {"symbol": "KO", "isin": ISIN_KO, "dataSource": "YAHOO"}}

    class ExistingActivities:
        status_code = 200
        content = b""

        @staticmethod
        def json():
            return {"activities": [row], "count": 1}

        @staticmethod
        def raise_for_status():
            return None

    env.setattr(requests, "get", lambda *args, **kwargs: ExistingActivities())
    for verb in ("post", "put", "patch", "delete"):
        env.setattr(requests, verb,
                    lambda *args, **kwargs: pytest.fail("financial HTTP write"))
    env.setattr(app, "process_account",
                lambda *args, **kwargs: pytest.fail("account processing"))
    env.setenv("APPRISE_URLS", '["json://notify.invalid/hook"]')
    sent = []
    env.setattr(app, "send_notification",
                lambda settings, title, body: sent.append((title, body)) or "sent")

    assert app.main() == 1
    assert len(sent) == 1
    assert "ghost_startup: invalid_identity" in sent[0][1]
    assert invalid_identity not in sent[0][1]
    assert "PRIVATE-ACCOUNT" not in caplog.text


def test_versioned_identity_reader_partial_dividend_coverage_is_account_local(
        env, caplog):
    env.setenv("GHOST_ACCOUNT_NAMES", "A,B")
    a1 = ("U1", "IBKR#v2#U1:DIVIDEND:A1")
    env.setattr(app, "ghost_get_existing_orders",
                lambda cfg: (set(), set(), positions(versioned_identities={a1})))

    u1_dividends = (
        div_xml(amount="15").replace('accountId="broker-account"', 'accountId="U1"')
        + div_xml(amount="10").replace('accountId="broker-account"', 'accountId="U1"')
        .replace('actionID="A1"', 'actionID="A2"')
    )
    u2_dividend = (div_xml(isin=ISIN_PEP, symbol="PEP")
                   .replace('accountId="broker-account"', 'accountId="U2"')
                   .replace('actionID="A1"', 'actionID="B1"'))
    reports = {
        "q1": report(trade_xml("T1"), u1_dividends),
        "q2": report(trade_xml("T2", symbol="PEP", isin=ISIN_PEP), u2_dividend),
    }
    env.setattr(app, "fetch_flex_report", lambda token, query_id: reports[query_id])
    env.setattr(app, "ghost_find_account_id", lambda cfg, name: f"gf-{name}")
    imported = []
    env.setattr(app, "ghost_import_activities",
                lambda cfg, rows: imported.append(list(rows)) or (list(rows), True))
    cash = []
    env.setattr(app, "ghost_update_cash_balance",
                lambda cfg, account, balance, currency: cash.append(account) or True)

    assert app.main() == 1
    by_account = defaultdict(list)
    for activity in [activity for batch in imported for activity in batch]:
        by_account[activity["accountId"]].append(activity["type"])
    assert by_account == {"gf-A": ["BUY"], "gf-B": ["BUY", "DIVIDEND"]}
    assert cash == ["gf-A", "gf-B"]
    assert "partial versioned action coverage" in caplog.text
    assert "1 of 2 account(s): U1" in caplog.text


def test_versioned_identity_reader_invalid_actions_keep_local_rejection(monkeypatch, caplog):
    rows = (div_xml(amount="30")
            + div_xml(amount="-5").replace('actionID="A1"', 'actionID="A2"'))
    w = World(monkeypatch, report(trade_xml("SAFE-T"), rows))
    a1 = ("broker-account", "IBKR#v2#broker-account:DIVIDEND:A1")
    assert w.run(pos=positions(versioned_identities={a1}))[1] is True
    assert [activity["type"] for activity in w.activities] == ["BUY"]
    assert w.cash_calls == [(ACC, 100.5)]
    assert "contradictory negative-net cash action" in caplog.text


def test_main_invalid_mapping_stops_the_run(env, tmp_path):
    env.setenv("MAPPING_FILE", str(tmp_path / "missing.yaml"))
    calls = stub_main(env, {})
    assert app.main() == 1
    assert calls == []


def test_main_configuration_error_returns_one_without_system_exit(env):
    env.delenv("IBKR_TOKEN")
    assert app.main() == 1


# --- load_config --------------------------------------------------------------

def test_load_config_defaults_and_normalisation(env):
    env.setenv("IBKR_ACCOUNT_IDS", " U1 , U2 ")
    cfg = config.load_config()
    assert cfg["account_ids"] == ["U1", "U2"] and cfg["query_ids"] == ["q1", "q2"]
    assert cfg["ghost_host"] == "http://ghost:3333"                  # trailing slash stripped
    assert (cfg["account_names"], cfg["dry_run"]) == ([], False)


def test_load_config_missing_variables_are_all_named(env):
    env.delenv("IBKR_TOKEN"); env.delenv("GHOST_HOST")
    with pytest.raises(RuntimeError, match="IBKR_TOKEN.*GHOST_HOST"):
        config.load_config()


@pytest.mark.parametrize("var,value", [("IBKR_QUERY_IDS", "q1"), ("GHOST_ACCOUNT_NAMES", "only-one")])
def test_load_config_count_mismatch_is_rejected(env, var, value):
    env.setenv(var, value)
    with pytest.raises(RuntimeError, match="same number|must match"):
        config.load_config()


def test_cash_target_duplicate_names_are_refused(env):
    env.setenv("IBKR_ACCOUNT_IDS", "U1,U2")
    env.setenv("GHOST_ACCOUNT_NAMES", "Shared, Shared ")
    with pytest.raises(RuntimeError, match="Duplicate.*'Shared'"):
        config.load_config()


def test_cash_target_duplicate_ids_without_names_are_refused(env):
    env.setenv("IBKR_ACCOUNT_IDS", "U1, U1")
    env.setenv("IBKR_QUERY_IDS", "q1,q2")
    env.delenv("GHOST_ACCOUNT_NAMES", raising=False)
    with pytest.raises(RuntimeError, match="Duplicate.*'U1'"):
        config.load_config()


def test_cash_target_duplicate_check_makes_no_http_call(env):
    def boom(*a, **k):
        raise AssertionError("no request expected")
    env.setattr(requests, "get", boom)
    env.setattr(requests, "post", boom)
    env.setenv("IBKR_ACCOUNT_IDS", "U1,U2")
    env.setenv("GHOST_ACCOUNT_NAMES", "A,A")
    with pytest.raises(RuntimeError):
        config.load_config()


def test_cash_target_duplicate_check_accepts_distinct_targets(env):
    env.setenv("IBKR_ACCOUNT_IDS", "U1,U2")
    env.setenv("GHOST_ACCOUNT_NAMES", "A,B")
    assert config.load_config()["account_names"] == ["A", "B"]
    env.delenv("GHOST_ACCOUNT_NAMES")
    assert config.load_config()["account_names"] == []


@pytest.mark.parametrize("value,expected", [("1", True), ("true", True), ("yes", True), ("on", True),
                                            ("0", False), ("false", False), ("no", False), ("off", False)])
@pytest.mark.parametrize("padded", [False, True])
def test_dry_run_values_accepted(env, caplog, value, expected, padded):
    env.setenv("DRY_RUN", f" \t{value.upper()} \t" if padded else value)
    assert config.load_config()["dry_run"] is expected
    assert config.dry_run_requested() is expected
    assert "DRY_RUN not set" not in caplog.text


@pytest.mark.parametrize("value", ["nope", "2", "tru", "false true", "CANARY-INVALID-DRY-RUN"])
@pytest.mark.parametrize("configured", [False, True])
def test_dry_run_values_invalid_rejected_before_http(env, caplog, value, configured):
    env.setenv("DRY_RUN", value)
    if configured:
        env.setenv("APPRISE_URLS", '["json://notify.invalid/hook"]')
    sent = []

    def no_http(*args, **kwargs):
        pytest.fail("invalid DRY_RUN must reject before IBKR/Ghostfolio HTTP")

    env.setattr(requests.sessions.Session, "request", no_http)
    with pytest.raises(RuntimeError, match="DRY_RUN"):
        config.load_config()
    assert config.dry_run_requested() is True

    def send(settings, title, body):
        assert any("Configuration error:" in r.getMessage() and "DRY_RUN" in r.getMessage()
                   for r in caplog.records)
        sent.append((settings, title, body))
        return "sent"

    env.setattr(app, "send_notification", send)
    caplog.clear()
    assert app.main() == 1
    assert len(sent) == int(configured)
    if configured:
        settings, title, body = sent[0]
        assert settings["urls"] == ["json://notify.invalid/hook"]
        assert title == "ghostfolio-ibkr-sync: run failed"
        assert "config: invalid_configuration" in body
    assert "CANARY-INVALID-DRY-RUN" not in caplog.text


# --- IBKR Flex fetch ----------------------------------------------------------

SEND_OK = ("<FlexStatementResponse><Status>Success</Status><ReferenceCode>REF1</ReferenceCode>"
           "<Url>https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement</Url>"
           "</FlexStatementResponse>")
READY = "<FlexQueryResponse><FlexStatements/></FlexQueryResponse>"
WARN = "<FlexStatementResponse><Status>Warn</Status><ErrorCode>1019</ErrorCode></FlexStatementResponse>"


class Txt:
    def __init__(self, text):
        self.text = text
        self.content = text.encode("utf-8")


def script_flex(monkeypatch, *bodies):
    seq, urls, sleeps = list(bodies), [], []
    def get(url, params, timeout):
        urls.append((url, dict(params)))
        return Txt(seq.pop(0))
    monkeypatch.setattr(ibkr, "_ibkr_get", get)
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    return urls, sleeps


def test_flex_fetch_happy_path_sends_token_and_reference_code(monkeypatch):
    urls, sleeps = script_flex(monkeypatch, SEND_OK, READY)
    assert ibkr.fetch_flex_report("TOK", "123") == READY
    assert urls[0][1] == {"t": "TOK", "q": "123", "v": "3"}
    assert urls[1][1] == {"q": "REF1", "t": "TOK", "v": "3"}
    assert sleeps == []


def test_flex_fetch_polls_while_statement_is_not_ready(monkeypatch):
    urls, sleeps = script_flex(monkeypatch, SEND_OK, WARN, WARN, READY)
    assert ibkr.fetch_flex_report("TOK", "1", retry_delay=7) == READY
    assert len(urls) == 4 and sleeps == [7, 7]


def test_flex_fetch_status_warn_without_error_code_also_means_not_ready(monkeypatch):
    urls, sleeps = script_flex(monkeypatch, SEND_OK, "<R><Status>Warn</Status></R>", READY)
    assert ibkr.fetch_flex_report("TOK", "1") == READY and len(sleeps) == 1


def test_flex_fetch_other_error_code_such_as_too_many_requests_fails_immediately(monkeypatch):
    urls, sleeps = script_flex(monkeypatch, SEND_OK, "<R><Status>Fail</Status><ErrorCode>1018</ErrorCode>"
                                                     "<ErrorMessage>Too many requests</ErrorMessage></R>")
    with pytest.raises(RuntimeError, match="GetStatement failed: Too many requests"):
        ibkr.fetch_flex_report("TOK", "1")
    assert sleeps == []


def test_flex_fetch_error_code_1019_alone_also_means_not_ready(monkeypatch):
    pending = "<R><Status>Fail</Status><ErrorCode>1019</ErrorCode></R>"
    urls, sleeps = script_flex(monkeypatch, SEND_OK, pending, READY)
    assert ibkr.fetch_flex_report("TOK", "1") == READY and len(sleeps) == 1


def test_flex_fetch_gives_up_after_max_retries(monkeypatch):
    urls, sleeps = script_flex(monkeypatch, SEND_OK, WARN, WARN, WARN)
    with pytest.raises(RuntimeError, match="Timed out"):
        ibkr.fetch_flex_report("TOK", "1", max_retries=3)
    assert len(urls) == 4 and len(sleeps) == 3


def test_flex_fetch_default_polling_recovers_after_more_than_ten_pending_responses(monkeypatch):
    urls, sleeps = script_flex(monkeypatch, SEND_OK, *[WARN] * 11, READY)
    assert ibkr.fetch_flex_report("TOK", "1") == READY
    assert len(urls) == 13 and sleeps == [5] * 11


def test_flex_transient_polling_default_exhausts_after_sixty_pending_responses(monkeypatch):
    urls, sleeps = script_flex(monkeypatch, SEND_OK, *[WARN] * 60)
    with pytest.raises(RuntimeError, match="Timed out"):
        ibkr.fetch_flex_report("TOK", "1")
    assert len(urls) == 61 and sleeps == [5] * 60 and sum(sleeps) == 300


def test_flex_fetch_send_request_failure_is_reported(monkeypatch):
    script_flex(monkeypatch, "<R><Status>Fail</Status><ErrorMessage>Invalid token</ErrorMessage></R>")
    with pytest.raises(RuntimeError, match="SendRequest failed: Invalid token"):
        ibkr.fetch_flex_report("TOK", "1")


def send_error(code, msg="boom"):
    code_xml = "" if code is None else f"<ErrorCode>{code}</ErrorCode>"
    return f"<R><Status>Fail</Status>{code_xml}<ErrorMessage>{msg}</ErrorMessage></R>"


RETRY_CODES = ["1001", "1004", "1005", "1006", "1007", "1008", "1009", "1018", "1019", "1021"]
IMMEDIATE_CODES = ["1003", "1010", "1011", "1012", "1013", "1014", "1015", "1016", "1017", "1020",
                   None, "9999", "abc"]


def test_flex_transient_send_recovery(monkeypatch):
    urls, sleeps = script_flex(monkeypatch, send_error("1004"), SEND_OK, READY)
    assert ibkr.fetch_flex_report("TOK", "1") == READY
    assert sleeps == [60]
    assert [u[0] for u in urls] == [ibkr.IBKR_SEND_URL, ibkr.IBKR_SEND_URL,
                                    "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"]
    assert urls[2][1] == {"q": "REF1", "t": "TOK", "v": "3"}


def test_flex_transient_send_exhaustion(monkeypatch):
    msg = "Server busy TOK"
    urls, sleeps = script_flex(monkeypatch, *[send_error("1018", msg)] * 5)
    with pytest.raises(RuntimeError) as exc:
        ibkr.fetch_flex_report("TOK", "1")
    assert "SendRequest failed: Server busy ***" in str(exc.value) and "TOK" not in str(exc.value)
    assert len(urls) == 5 and all(u[0] == ibkr.IBKR_SEND_URL for u in urls)
    assert sleeps == [60, 120, 300, 600]


@pytest.mark.parametrize("code", RETRY_CODES)
def test_flex_transient_send_classification_retries(monkeypatch, code):
    urls, sleeps = script_flex(monkeypatch, send_error(code, "Please try again later"), SEND_OK, READY)
    assert ibkr.fetch_flex_report("TOK", "1") == READY
    assert sleeps == [60] and len(urls) == 3


@pytest.mark.parametrize("code", IMMEDIATE_CODES)
def test_flex_transient_send_classification_immediate(monkeypatch, code):
    # the message advises retrying, but only the ErrorCode may decide
    urls, sleeps = script_flex(monkeypatch, send_error(code, "Please try again shortly"))
    with pytest.raises(RuntimeError, match="SendRequest failed: Please try again shortly"):
        ibkr.fetch_flex_report("TOK", "1")
    assert len(urls) == 1 and sleeps == []


def test_flex_fetch_statement_error_status_is_reported(monkeypatch):
    script_flex(monkeypatch, SEND_OK, "<R><Status>Fail</Status><ErrorCode>1003</ErrorCode>"
                                      "<ErrorMessage>Statement unavailable</ErrorMessage></R>")
    with pytest.raises(RuntimeError, match="GetStatement failed: Statement unavailable"):
        ibkr.fetch_flex_report("TOK", "1")


def test_flex_fetch_statement_error_redacts_token(monkeypatch):
    script_flex(monkeypatch, SEND_OK, "<R><Status>Fail</Status><ErrorCode>1003</ErrorCode>"
                                      "<ErrorMessage>Token TOK is invalid</ErrorMessage></R>")
    with pytest.raises(RuntimeError) as exc:
        ibkr.fetch_flex_report("TOK", "1")
    assert "GetStatement failed: Token *** is invalid" in str(exc.value)
    assert "TOK" not in str(exc.value)


def test_flex_fetch_foreign_statement_host_is_rejected_before_the_token_is_sent(monkeypatch):
    evil = SEND_OK.replace("ndcdyn.interactivebrokers.com", "evil.example")
    urls, _ = script_flex(monkeypatch, evil)
    with pytest.raises(RuntimeError, match="Unexpected IBKR statement URL"):
        ibkr.fetch_flex_report("TOK", "1")
    assert len(urls) == 1                                           # step 2 (with the token) never sent


# --- _ibkr_get: retry and redaction --------------------------------------------

class HttpResp:
    def __init__(self, status=200):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for url: https://x/?t=SECRET-TOK")


def test_ibkr_get_retries_network_errors_then_succeeds(monkeypatch):
    attempts, sleeps = [], []
    def get(url, params, timeout, **kwargs):
        attempts.append(1)
        if len(attempts) < 3:
            raise requests.ConnectionError("reset")
        return HttpResp()
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    assert isinstance(ibkr._ibkr_get("https://x", {"t": "SECRET-TOK"}, 5), HttpResp)
    assert len(attempts) == 3 and sleeps == [10, 30]


def test_ibkr_get_gives_up_after_the_last_retry_and_never_leaks_the_token(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(
        requests.ConnectionError("GET https://x/?t=SECRET-TOK failed")))
    monkeypatch.setattr(time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError) as e:
        ibkr._ibkr_get("https://x", {"t": "SECRET-TOK"}, 5)
    assert "SECRET-TOK" not in str(e.value) and "***" in str(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__   # no chained traceback with the URL


def test_ibkr_get_redacts_url_encoded_forms_of_the_token(monkeypatch):
    token = "a+b/c="
    leaked = f"GET https://x/?t={ibkr.quote_plus(token)} raw {token} and {ibkr.quote(token, safe='')}"
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError(leaked)))
    monkeypatch.setattr(time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError) as e:
        ibkr._ibkr_get("https://x", {"t": token}, 5)
    msg = str(e.value)
    assert token not in msg and ibkr.quote_plus(token) not in msg and ibkr.quote(token, safe="") not in msg


def test_ibkr_get_http_error_is_not_retried_and_is_redacted(monkeypatch):
    attempts = []
    def get(url, params, timeout, **kwargs):
        attempts.append(1)
        return HttpResp(503)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(time, "sleep", lambda s: pytest.fail("HTTP errors are not retried"))
    with pytest.raises(RuntimeError) as e:
        ibkr._ibkr_get("https://x", {"t": "SECRET-TOK"}, 5)
    assert len(attempts) == 1 and "SECRET-TOK" not in str(e.value)


def test_ibkr_get_rejects_redirects_without_following_them(monkeypatch):
    calls = []

    def get(*args, **kwargs):
        calls.append(kwargs)
        return HttpResp(302)

    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(RuntimeError, match="IBKR request redirected") as error:
        ibkr._ibkr_get("https://x", {"t": "SECRET-TOK"}, 5)
    assert str(error.value) == "IBKR request redirected"
    assert calls == [{"params": {"t": "SECRET-TOK"}, "timeout": 5, "allow_redirects": False}]


# --- end to end through the real functions ------------------------------------

class ReadOnlyHttp:
    """requests stand-in: only the cash step's account GET is allowed; any other call fails the test."""
    def get(self, url, **k):
        assert url.endswith(f"/api/v1/account/{ACC}")
        return type("R", (), {"status_code": 200, "raise_for_status": lambda self: None,
                              "json": lambda self: {"currency": "USD", "name": "IBKR"}})()

    def __getattr__(self, name):
        def call(*a, **k):
            pytest.fail(f"unexpected HTTP {name} in dry run")
        return call


def test_dry_run_sends_nothing_but_still_updates_the_in_memory_state(monkeypatch):
    # real ghost_import_activities / ghost_update_cash_balance, only the account GET allowed
    monkeypatch.setattr(app, "fetch_flex_report", lambda *a, **k: report(trade_xml("T1"), div_xml()))
    monkeypatch.setattr(app, "ghost_find_account_id", lambda *a: ACC)
    monkeypatch.setattr(ghostfolio, "requests", ReadOnlyHttp())
    ids, comments, pos = set(), set(), positions()
    _, ok = app.process_account({**CFG, "dry_run": True}, "U1", "q1", "IBKR", {}, ids, comments, pos)
    assert ok is True and ids == {"T1"} and comments == {(ACC, f"dividend#{ISIN_KO}#2026-07-15")}


def test_main_shares_the_existing_sets_between_accounts_through_the_real_process_account(env, monkeypatch):
    env.setenv("GHOST_ACCOUNT_NAMES", "A,B")
    imported = []
    env.setattr(app, "ghost_get_existing_orders", lambda cfg: (set(), set(), positions()))
    env.setattr(app, "fetch_flex_report", lambda *a, **k: report(trade_xml("T1")))        # same trade for both
    env.setattr(app, "ghost_find_account_id", lambda cfg, name: "same-gf-account")       # both map to one account
    env.setattr(app, "ghost_import_activities", lambda cfg, acts: imported.append(list(acts)) or (list(acts), True))
    env.setattr(app, "ghost_update_cash_balance", lambda *a: True)
    assert app.main() == 0
    assert len(imported) == 1 and imported[0][0]["comment"] == "IBKR#T1"               # B sees A's import


def test_malformed_flex_report_fails_only_that_account(monkeypatch):
    script_flex(monkeypatch, SEND_OK, "<not-xml")
    monkeypatch.setattr(app, "ghost_find_account_id", lambda *a: pytest.fail("must not be reached"))
    assert app.process_account(CFG, "U1", "q1", "IBKR", {}, set(), set(), positions()) == ({}, False)


@pytest.mark.parametrize("profile_key", ["assetProfile", "SymbolProfile"])
def test_api_profiles_drive_holdings_manual_alias_and_dividend_reconciliation(monkeypatch, profile_key):
    """Both profile formats preserve account holdings and suppress reconciled imports."""
    from types import SimpleNamespace

    def row(kind, qty, date, symbol="KO", comment=None, account=ACC):
        """Build an account activity using the profile format under test."""
        return {"type": kind, "quantity": qty, "date": date, "comment": comment,
                "accountId": account, profile_key: {"symbol": symbol, "isin": ISIN_KO, "dataSource": "YAHOO"}}

    rows = [row("BUY", 20, "2026-01-01", comment="IBKR#OLD"),
            row("BUY", 10, "2026-08-01"),
            row("SELL", 3, "2026-08-02", symbol="KO.A"),
            row("DIVIDEND", 100, "2026-07-16"),
            row("BUY", 99, "2026-01-01", account="other-account")]
    monkeypatch.setattr(requests, "get", lambda *a, **k: SimpleNamespace(
        status_code=200, raise_for_status=lambda: None,
        json=lambda: {"activities": rows, "count": len(rows)}))
    ids, comments, pos = ghostfolio.ghost_get_existing_orders(CFG)
    assert pos["qty"][(ACC, "KO")] == 30
    assert pos["qty"][("other-account", "KO")] == 99
    xml = report(trade_xml("OLD", date="20260101;100000")
                 + trade_xml("MANUAL-BUY", qty=10)
                 + trade_xml("MANUAL-SELL", "SELL", 3, date="20260802;100000")
                 + trade_xml("VALID-SELL", "SELL", 5, date="20260901;100000"), div_xml())
    w = World(monkeypatch, xml)
    assert w.run(ids=ids, comments=comments, pos=pos)[1] is True
    assert [a["comment"] for a in w.activities] == ["IBKR#VALID-SELL"]


def test_main_invalid_api_profile_stops_before_fetch_or_write(monkeypatch):
    """Abort startup on an invalid profile before account processing or API writes."""
    from types import SimpleNamespace

    monkeypatch.setattr(app, "load_config", lambda: {
        **CFG, "mapping_file": "unused", "account_ids": ["U1"],
        "query_ids": ["q1"], "account_names": ["IBKR"]})
    monkeypatch.setattr(app, "load_mapping", lambda path: {})
    monkeypatch.setattr(requests, "get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"activities": [{"type": "BUY", "quantity": 1}], "count": 1}))
    monkeypatch.setattr(app, "process_account", lambda *a, **k: pytest.fail("no account processing"))
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("no POST"))
    monkeypatch.setattr(requests, "put", lambda *a, **k: pytest.fail("no PUT"))
    assert app.main() == 1


def test_identical_report_id_is_only_one_candidate_and_cannot_back_double_sell(monkeypatch):
    w = World(monkeypatch, report(trade_xml("B") + trade_xml("B") + trade_xml("S", "SELL", 20)))
    w.run()
    assert w.activities == []
    assert w.pos["qty"][(ACC, "KO")] == 0


def test_conflicting_report_id_is_excluded_instead_of_arbitrarily_chosen(monkeypatch):
    w = World(monkeypatch, report(trade_xml("B") + trade_xml("B", qty=20)))
    assert w.run()[1] is False
    assert w.activities == []


def test_manual_match_trade_id_remembered_across_sequential_queries(monkeypatch):
    pos = positions({(ACC, "KO"): 10})
    pos["manual_buys"][(ACC, "KO")].append(["2026-08-01", 10])
    w = World(monkeypatch, report(trade_xml("B")))
    w.run(pos=pos)
    w.run(ids=w.ids, pos=pos)
    assert w.activities == []
    assert w.ids == {"B"}
    assert pos["qty"][(ACC, "KO")] == 10


@pytest.mark.parametrize("commission", ["nan", "inf", "n/a"])
def test_invalid_commission_buy_cannot_authorize_sell(monkeypatch, commission):
    w = World(monkeypatch, report(trade_xml("B", ibCommission=commission) + trade_xml("S", "SELL")))
    assert w.run()[1] is False
    assert w.activities == []


def test_server_skipped_buy_cannot_authorize_sell_in_same_batch(monkeypatch):
    from types import SimpleNamespace
    w = World(monkeypatch, report(trade_xml("B") + trade_xml("S", "SELL", 15)))
    monkeypatch.setattr(app, "ghost_import_activities", original_import)
    sent = []
    monkeypatch.setattr(requests, "post", lambda *a, **kw:
                        sent.append(kw["json"]["activities"]) or
                        SimpleNamespace(status_code=201, json=lambda: {"activities": []}))
    assert w.run(pos=positions({(ACC, "KO"): 10}))[1] is False
    assert [[a["comment"] for a in batch] for batch in sent] == [["IBKR#B"]]
    assert w.ids == set()
    assert w.pos["qty"][(ACC, "KO")] == 10


def test_short_acceptance_does_not_inflate_later_account_holdings(monkeypatch):
    from types import SimpleNamespace
    reports = iter([report(trade_xml("B")), report(trade_xml("S", "SELL", 20))])
    w = World(monkeypatch, report())
    monkeypatch.setattr(app, "fetch_flex_report", lambda *a: next(reports))
    monkeypatch.setattr(app, "ghost_import_activities", original_import)
    sent = []
    monkeypatch.setattr(requests, "post", lambda *a, **kw:
                        sent.append(kw["json"]["activities"]) or
                        SimpleNamespace(status_code=201, json=lambda: {"activities": []}))
    w.run(pos=positions({(ACC, "KO"): 10}))
    w.run(ids=w.ids, pos=w.pos)
    assert len(sent) == 1
    assert w.pos["qty"][(ACC, "KO")] == 10


def test_short_import_acceptance_keeps_proven_buys_and_continues_safely(
        env, caplog):
    from types import SimpleNamespace

    env.setenv("GHOST_ACCOUNT_NAMES", "A,B")
    env.setenv("TZ", "Europe/Zurich")
    env.setenv("APPRISE_URLS", '["json://notify.invalid/hook"]')
    env.setattr(app, "load_mapping", lambda path: {})
    shared_positions = positions()
    env.setattr(app, "ghost_get_existing_orders",
                lambda cfg: (set(), set(), shared_positions))
    reports = {
        "q1": report(trade_xml("B1") + trade_xml("B2")
                     + trade_xml("S1", "SELL", 15)),
        "q2": report(trade_xml("LATER", symbol="PEP", isin=ISIN_PEP)),
    }
    env.setattr(app, "fetch_flex_report", lambda token, query_id: reports[query_id])
    env.setattr(app, "ghost_find_account_id", lambda cfg, name: f"gf-{name}")

    batches = []

    def post(*args, **kwargs):
        activities = kwargs["json"]["activities"]
        batches.append(activities)
        accepted = activities[:1] if len(batches) == 1 else activities
        rows = [
            {**activity, "id": f"created-{activity['comment']}",
             "assetProfile": {"symbol": activity["symbol"],
                              "dataSource": activity["dataSource"]}}
            for activity in accepted
        ]
        return SimpleNamespace(status_code=201, text="", json=lambda: {"activities": rows})

    env.setattr(requests, "post", post)
    cash = []
    env.setattr(app, "ghost_update_cash_balance",
                lambda cfg, account, balance, currency: cash.append(account) or True)
    notifications = []
    env.setattr(app, "send_notification",
                lambda settings, title, body: notifications.append((title, body)) or "sent")

    assert app.main() == 1
    assert [[activity["comment"] for activity in batch] for batch in batches] == [
        ["IBKR#B1", "IBKR#B2"], ["IBKR#LATER"],
    ]
    assert shared_positions["qty"][("gf-A", "KO")] == 10
    assert shared_positions["qty"][("gf-B", "PEP")] == 10
    assert cash == ["gf-A", "gf-B"]
    assert "IBKR#B2" in caplog.text
    assert "inspect Ghostfolio before rerun" in caplog.text
    assert len(notifications) == 1
    assert "account: account_failed (account #1)" in notifications[0][1]
    for identifier in ("IBKR#B2", "U1", "gf-A", "KO"):
        assert identifier not in notifications[0][1]


def test_uncertain_import_blocks_further_writes_only_to_same_target(monkeypatch):
    from types import SimpleNamespace
    w = World(monkeypatch, report(trade_xml("B") + trade_xml("S", "SELL")))
    monkeypatch.setattr(app, "ghost_import_activities", original_import)
    calls = []
    monkeypatch.setattr(requests, "post", lambda *a, **kw:
                        calls.append(kw["json"]["activities"]) or
                        SimpleNamespace(status_code=201, json=lambda: {}))
    cfg = {**CFG}
    assert app.process_account(cfg, "U1", "q1", "IBKR", {}, set(), set(), positions())[1] is False
    cash_count = len(w.cash_calls)
    assert app.process_account(cfg, "U2", "q2", "IBKR", {}, set(), set(), positions())[1] is False
    assert len(calls) == 1 and len(w.cash_calls) == cash_count


@pytest.mark.parametrize("change", ["source", "date", "missing-id"])
def test_wrong_accepted_identity_cannot_back_sale(monkeypatch, change):
    from types import SimpleNamespace
    w = World(monkeypatch, report(trade_xml("B") + trade_xml("S", "SELL")))
    monkeypatch.setattr(app, "ghost_import_activities", original_import)
    calls = []
    def post(*args, **kwargs):
        candidates = kwargs["json"]["activities"]
        calls.append(candidates)
        row = {**candidates[0], "id": "new-row", "assetProfile": {"symbol": "KO", "dataSource": "YAHOO"}}
        if change == "source":
            row["assetProfile"]["dataSource"] = "MANUAL"
        elif change == "date":
            row["date"] = "2026-09-01T00:00:00Z"
        else:
            del row["id"]
        return SimpleNamespace(status_code=201, json=lambda: {"activities": [row]})
    monkeypatch.setattr(requests, "post", post)
    cfg = {**CFG}
    assert app.process_account(cfg, "U1", "q1", "IBKR", {}, set(), set(), positions())[1] is False
    assert len(calls) == 1 and all(a["type"] == "BUY" for a in calls[0])


@pytest.mark.parametrize("inactive", ["draft", "excluded", "other-source"])
def test_inactive_existing_buy_cannot_authorize_active_sell(monkeypatch, inactive):
    from types import SimpleNamespace
    row = {"type": "BUY", "quantity": 10, "comment": "IBKR#OLD", "accountId": ACC,
           "date": "2026-08-01T00:00:00Z", "assetProfile": {"symbol": "KO", "dataSource": "YAHOO"}}
    if inactive == "other-source":
        row["assetProfile"]["dataSource"] = "MANUAL"
    else:
        row["tags"] = [{"id": "0c077abd-eca2-4cbb-818c-6cefbf2d169a" if inactive == "draft"
                        else "f2e868af-8333-459f-b161-cbc6544c24bd"}]
    monkeypatch.setattr(requests, "get", lambda *a, **k: SimpleNamespace(
        status_code=200, raise_for_status=lambda: None,
        json=lambda: {"activities": [row], "count": 1}))
    ids, comments, pos = ghostfolio.ghost_get_existing_orders(CFG)
    w = World(monkeypatch, report(trade_xml("S", "SELL")))
    w.run(ids=ids, comments=comments, pos=pos)
    assert w.activities == [] and w.ids == {"OLD"}


def test_canonical_accepted_buy_cannot_back_sale_under_original_ticker(monkeypatch):
    from types import SimpleNamespace
    w = World(monkeypatch, report(trade_xml("B") + trade_xml("S", "SELL")))
    monkeypatch.setattr(app, "ghost_import_activities", original_import)
    calls = []
    def post(*args, **kwargs):
        rows = kwargs["json"]["activities"]
        calls.append(rows)
        row = {**rows[0], "id": "created", "assetProfile": {"symbol": "KO.CANONICAL", "dataSource": "YAHOO"}}
        return SimpleNamespace(status_code=201, json=lambda: {"activities": [row]})
    monkeypatch.setattr(requests, "post", post)
    assert w.run()[1] is False
    assert len(calls) == 1
    assert w.pos["qty"][(ACC, "KO")] == 0
    assert w.pos["qty"][(ACC, "KO.CANONICAL")] == 10



def test_future_buy_cannot_back_current_sell(monkeypatch):
    w = World(monkeypatch, report(trade_xml("B", date="20990801;100000") + trade_xml("S", "SELL")))
    assert w.run()[1] is False
    assert w.activities == []


def test_future_dividend_is_not_created_as_draft(monkeypatch):
    w = World(monkeypatch, report(divs=div_xml(date="20990801")))
    assert w.run()[1] is False
    assert w.activities == []


# --- structured input: schema scope, dedup order and retries ------------------

def structured_input_xml(mode="valid", field="quantity"):
    root = ET.fromstring(report(trade_xml("INPUT-T"),
                                div_xml() + div_xml(isin=ISIN_PEP, symbol="PEP")))
    section = root.find(".//ChangeInDividendAccruals")
    # Distinct securities must have distinct broker contract/action identities.
    root.findall(".//CashTransaction")[1].set("conid", "2")
    section[1].set("conid", "2")
    first = section[0]
    if mode == "old":
        root.find(".//FlexStatement").remove(section)
    elif mode == "empty":
        section.clear()
    elif mode == "missing":
        del first.attrib[field]
    elif mode == "blank":
        first.set(field, "")
    elif mode == "payment_missing":
        del root.find(".//CashTransaction").attrib[field]
    elif mode == "payment_blank":
        root.find(".//CashTransaction").set(field, "")
    elif mode == "conflict":
        row = ET.SubElement(section, "ChangeInDividendAccrual", dict(first.attrib))
        row.set("code", "Po")
        row.set("quantity", "99")
    elif mode == "short":
        first.set("date", "20260701")
        first.set("reportDate", "20260701")
    elif mode == "unrelated":
        ET.SubElement(section, "ChangeInDividendAccrual", {field: "unrelated"})
        ET.SubElement(root.find(".//CashTransactions"), "CashTransaction", {
            "type": "Other Fees", "amount": "bad"})
    return ET.tostring(root, encoding="unicode")


@pytest.mark.parametrize("mode,reason", [
    ("missing", "missing relevant accrual attributes"),
    ("payment_missing", "missing payment attributes"),
])
def test_dividend_structured_input_schema_blocks_account_only(monkeypatch, caplog, mode, reason):
    field = "actionID" if mode == "payment_missing" else "quantity"
    w = World(monkeypatch, structured_input_xml(mode, field))
    assert w.run()[1] is True
    assert [a["comment"] for a in w.activities] == ["IBKR#INPUT-T"]
    assert w.comments == set() and dict(w.pos["dividend_dates"]) == {}
    assert w.cash_calls == [(ACC, 100.5)]
    assert reason in caplog.text and "account dividends not imported" in caplog.text


@pytest.mark.parametrize("field", ["accountId", "conid", "currency", "actionID", "exDate",
                                   "quantity", "code", "date", "payDate", "reportDate"])
def test_dividend_structured_input_all_relevant_attributes_required(monkeypatch, field):
    w = World(monkeypatch, structured_input_xml("missing", field))
    assert w.run()[1] is True
    assert [a["type"] for a in w.activities] == ["BUY"]


@pytest.mark.parametrize("mode,field,reason", [
    ("blank", "quantity", "incompatible structured quantity"),
    ("blank", "actionID", "missing accrual association keys"),
    ("payment_blank", "actionID", "missing payment association keys"),
    ("conflict", "quantity", "contradictory structured quantities"),
    ("short", "quantity", "missing or contradictory payment reversal evidence"),
])
def test_dividend_structured_input_local_rejection(monkeypatch, caplog, mode, field, reason):
    w = World(monkeypatch, structured_input_xml(mode, field))
    assert w.run()[1] is True
    assert [a["type"] for a in w.activities] == ["BUY", "DIVIDEND"]
    assert w.comments == {(ACC, f"dividend#{ISIN_PEP}#2026-07-15")}
    assert w.cash_calls == [(ACC, 100.5)] and reason in caplog.text


@pytest.mark.parametrize("field", ["accountId", "conid", "currency", "actionID", "exDate"])
def test_dividend_structured_input_nonempty_mismatch_excludes_unrelated(monkeypatch, field):
    w = World(monkeypatch, structured_input_xml("unrelated", field))
    assert w.run()[1] is True
    assert [a["type"] for a in w.activities] == ["BUY", "DIVIDEND", "DIVIDEND"]


@pytest.mark.parametrize("mode", ["missing", "conflict", "blank"])
@pytest.mark.parametrize("dedup", ["comment", "legacy", "proximity"])
def test_dividend_structured_input_dedup_before_evidence(monkeypatch, caplog, mode, dedup):
    root = ET.fromstring(structured_input_xml(mode))
    # Keep only the invalid KO payment, so no new candidate requires schema.
    root.find(".//CashTransactions").remove(root.findall(".//CashTransaction")[1])
    w = World(monkeypatch, ET.tostring(root, encoding="unicode"))
    pos = positions()
    comments = set()
    if dedup == "proximity":
        pos["dividend_dates"][(ACC, "KO")].append(("2026-07-17", None, None, None))
    else:
        key = ISIN_KO if dedup == "comment" else "KO"
        comments.add((ACC, f"dividend#{key}#2026-07-15"))
    monkeypatch.setattr("ghostfolio_ibkr_sync.sync.dividend_structured_quantity", lambda div: pytest.fail("dedup must run first"))
    assert w.run(comments=comments, pos=pos)[1] is True
    assert [a["type"] for a in w.activities] == ["BUY"]
    assert "Incompatible dividend input" not in caplog.text


def test_dividend_structured_input_empty_evidence_and_retry(monkeypatch, caplog):
    w = World(monkeypatch, structured_input_xml("empty"))
    assert w.run()[1] is True
    assert w.comments == set() and "missing structured quantity evidence" in caplog.text
    ids, comments, pos = w.ids, w.comments, w.pos
    monkeypatch.setattr(app, "fetch_flex_report", w._fetch(structured_input_xml()))
    w.imported.clear()
    assert w.run(ids=ids, comments=comments, pos=pos)[1] is True
    assert [a["type"] for a in w.activities] == ["DIVIDEND", "DIVIDEND"]
    assert len(w.comments) == 2


@pytest.mark.parametrize("section", [True, False])
def test_dividend_structured_input_no_payments_is_valid(monkeypatch, section):
    root = ET.fromstring(report(trade_xml("EMPTY-T")))
    if not section:
        root.find(".//FlexStatement").remove(root.find(".//ChangeInDividendAccruals"))
    w = World(monkeypatch, ET.tostring(root, encoding="unicode"))
    assert w.run()[1] is True
    assert [a["type"] for a in w.activities] == ["BUY"]


def test_dividend_structured_input_withholding_needs_no_accrual_keys(monkeypatch):
    root = ET.fromstring(report(divs=div_xml()))
    ET.SubElement(root.find(".//CashTransactions"), "CashTransaction", {
        "type": "Withholding Tax", "amount": "-5", "dateTime": "20260715;120000 EST",
        "isin": ISIN_KO, "symbol": "KO", "currency": "USD"})
    w = World(monkeypatch, ET.tostring(root, encoding="unicode"))
    assert w.run()[1] is True
    assert w.activities[0]["fee"] == 5


@pytest.mark.parametrize("price,category", [(0.25, "coherent_single"), (0.26, "differences")])
def test_historical_diagnostic_coherent_dry_run_before_dedup_zero_writes(monkeypatch, caplog, price, category):
    from test_dividend_diagnostics import destination, read
    import logging

    ids, comments, pos = read(monkeypatch, [destination(unitPrice=price)])
    monkeypatch.setattr(app, "fetch_flex_report", lambda *args: report(divs=div_xml()))
    monkeypatch.setattr(app, "ghost_find_account_id", lambda *args: ACC)
    for verb in ("post", "put", "patch", "delete"):
        monkeypatch.setattr(requests, verb, lambda *args, **kwargs: pytest.fail("financial HTTP write"))
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(app, "ghost_update_cash_balance", lambda *a: True)  # cash guard has its own tests
    assert app.process_account({**CFG, "dry_run": True}, "U1", "q1", "IBKR", {}, ids, comments, pos) == ({}, True)
    assert category in caplog.text
    assert "Historical dividends" in caplog.text
    assert "duplicates skipped: 1" in caplog.text
    assert comments == {(ACC, f"dividend#{ISIN_KO}#2026-07-15")}
    assert ids == set()
    if category == "differences":
        assert "Difference (Ghostfolio minus IBKR)" in caplog.text and "dividend-1" in caplog.text


def test_coherent_dividend_import_summary_links_dry_run_report_counts(monkeypatch, caplog):
    from test_dividend_diagnostics import destination, read

    ids, comments, pos = read(monkeypatch, [destination(unitPrice=0.2501)])
    monkeypatch.setattr(app, "fetch_flex_report", lambda *args: report(divs=div_xml()))
    monkeypatch.setattr(app, "ghost_find_account_id", lambda *args: ACC)
    monkeypatch.setattr(app, "ghost_update_cash_balance", lambda *args: True)
    caplog.set_level(logging.INFO)
    assert app.process_account({**CFG, "dry_run": True}, "U1", "q1", "IBKR", {},
                             ids, comments, pos) == ({}, True)
    assert "Dividend report: 1 to check, 0 informational, 0 noise" in caplog.text
    assert ("New dividend activities: 0, duplicates skipped: 1; dividend report: "
            "1 to check, 0 informational, 0 noise") in caplog.text


def test_coherent_dividend_import_summary_live_line_stays_unchanged(monkeypatch, caplog):
    w = World(monkeypatch, report(divs=div_xml()))
    caplog.set_level(logging.INFO)
    assert w.run()[1] is True
    lines = [record.getMessage() for record in caplog.records
             if record.getMessage().startswith("New dividend activities:")]
    assert lines == ["New dividend activities: 1, duplicates skipped: 0"]


def test_historical_diagnostic_coherent_live_pipeline_unchanged(monkeypatch):
    monkeypatch.setattr(app, "historical_dividend_comparison", lambda *args: pytest.fail("live diagnostic"))
    w = World(monkeypatch, report(divs=div_xml()))
    assert w.run()[1] is True
    assert w.activities[0]["quantity"] == 100.0
    assert w.activities[0]["unitPrice"] == 0.25
    assert w.cash_calls == [(ACC, 100.5)]


def test_historical_diagnostic_report_window_and_unmatched_coverage(monkeypatch, caplog):
    from test_dividend_diagnostics import destination, read
    import logging
    rows = [destination(), destination(id="older", comment="legacy dividend",
                                      date="2025-07-15T00:00:00Z")]
    ids, comments, pos = read(monkeypatch, rows)
    xml = report(divs=div_xml()).replace("<FlexStatement>",
        '<FlexStatement fromDate="20260701" toDate="20260731">')
    monkeypatch.setattr(app, "fetch_flex_report", lambda *args: xml)
    monkeypatch.setattr(app, "ghost_find_account_id", lambda *args: ACC)
    for verb in ("post", "put", "patch", "delete"):
        monkeypatch.setattr(requests, verb, lambda *args, **kwargs: pytest.fail("financial HTTP write"))
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(app, "ghost_update_cash_balance", lambda *a: True)  # cash guard has its own tests
    assert app.process_account({**CFG, "dry_run": True}, "U1", "q1", "IBKR", {}, ids, comments, pos) == ({}, True)
    assert "outside report window" in caplog.text and "older" in caplog.text
    assert "source_groups=1 unmatched_destination=1" in caplog.text


@pytest.mark.parametrize("mode", ["schema", "quantity"])
@pytest.mark.parametrize("existing", [True, False])
def test_historical_diagnostic_coherent_import_warnings_only_for_candidates(monkeypatch, caplog, mode, existing):
    from test_dividend_diagnostics import destination, read
    import logging

    ids, comments, pos = read(monkeypatch, [destination()] if existing else [])
    root = ET.fromstring(report(divs=div_xml()))
    accrual = root.find(".//ChangeInDividendAccrual")
    if mode == "schema":
        # Same attribute on a second accrual row: the field exists, one row lacks it.
        ET.SubElement(root.find(".//ChangeInDividendAccruals"), "ChangeInDividendAccrual",
                      {**accrual.attrib, "conid": "other"})
        del accrual.attrib["quantity"]
    else:
        accrual.set("quantity", "bad")
    monkeypatch.setattr(app, "fetch_flex_report", lambda *args: ET.tostring(root, encoding="unicode"))
    monkeypatch.setattr(app, "ghost_find_account_id", lambda *args: ACC)
    for verb in ("post", "put", "patch", "delete"):
        monkeypatch.setattr(requests, verb, lambda *args, **kwargs: pytest.fail("financial HTTP write"))
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(app, "ghost_update_cash_balance", lambda *a: True)  # cash guard has its own tests
    assert app.process_account({**CFG, "dry_run": True}, "U1", "q1", "IBKR", {ISIN_KO: "KO"}, ids, comments, pos) == ({}, True)
    warnings = [record for record in caplog.records if record.levelno >= logging.WARNING]
    assert len(warnings) == (0 if existing else 1)
    assert "Historical dividends" in caplog.text
    if existing:
        assert "uncertain" in caplog.text and "not imported" not in caplog.text
    else:
        assert "not imported" in caplog.text


# --- Flex provenance: mandatory "YYYYMMDD;HHmmss TimeZone" on cash rows ------------

def _cash_row(type_, date_time, **extra):
    attrs = {"type": type_, "levelOfDetail": "DETAIL", "amount": "25" if type_ != "Withholding Tax" else "-5",
             "isin": ISIN_KO, "symbol": "KO", "currency": "USD", "description": "X"}
    if date_time is not None:
        attrs["dateTime"] = date_time
    attrs.update(extra)
    return "<CashTransaction " + " ".join(f'{k}="{v}"' for k, v in attrs.items()) + "/>"


@pytest.mark.parametrize("type_", ["Dividends", "Payment In Lieu Of Dividends", "Withholding Tax"])
@pytest.mark.parametrize("bad", [None, "", "20260715", "20260715;120000", "20260715;120000 ", "20260715;120000 E S T",
                                 "20260715;120000 EST5EDT1", "20261301;120000 EST", "20260715;256100 EST", "20260715 120000 EST"])
def test_historical_diagnostic_preflight_bad_suffix_fails_account_before_any_write(monkeypatch, type_, bad):
    xml = report(trades=trade_xml("T1"), divs=_cash_row(type_, bad))
    w = World(monkeypatch, xml)
    assert w.run() == ({}, False)
    assert w.imported == [] and w.cash_calls == []
    assert CFG.get("dry_run") is not True


@pytest.mark.parametrize("type_", ["Dividends", "Payment In Lieu Of Dividends", "Withholding Tax"])
def test_historical_diagnostic_preflight_valid_suffix_is_accepted(type_):
    xml = report(divs=_cash_row(type_, "20260715;120000 EDT"))
    assert ibkr.flex_provenance_failures(xml) == {}


def test_historical_diagnostic_preflight_other_cash_types_and_summary_rows_are_exempt():
    xml = report(divs=_cash_row("Deposits/Withdrawals", "20260715")
                 + _cash_row("Dividends", "20260715", levelOfDetail="SUMMARY"))
    assert ibkr.flex_provenance_failures(xml) == {}


def test_historical_diagnostic_preflight_failure_counts_per_type():
    xml = report(divs=_cash_row("Dividends", "20260715") + _cash_row("Dividends", None)
                 + _cash_row("Withholding Tax", "20260715;120000 EST")
                 + _cash_row("Payment In Lieu Of Dividends", "x"))
    assert ibkr.flex_provenance_failures(xml) == {"Dividends": 2, "Payment In Lieu Of Dividends": 1}


def test_historical_diagnostic_preflight_bad_suffix_does_not_enable_dry_run_and_other_accounts_run(monkeypatch):
    bad = World(monkeypatch, report(trades=trade_xml("T1"), divs=_cash_row("Dividends", "20260715")))
    assert bad.run() == ({}, False)
    good = World(monkeypatch, report(trades=trade_xml("T1"), divs=div_xml()))
    good_result = good.run()
    assert good_result[1] is True and good.imported and good.cash_calls


# --- dividend field prerequisites: whole-report absence fails the account -------

def _prerequisite_xml(mutate=None, divs=None):
    root = ET.fromstring(report(trade_xml("PRE-T"), div_xml() if divs is None else divs))
    if mutate:
        mutate(root)
    return ET.tostring(root, encoding="unicode")


def _drop(tag, field):
    def mutate(root):
        for el in root.iter(tag):
            el.attrib.pop(field, None)
    return mutate


@pytest.mark.parametrize("dry_run", [False, True])
def test_dividend_field_prerequisites_missing_cash_field_fails_account(monkeypatch, caplog, dry_run):
    w = World(monkeypatch, _prerequisite_xml(_drop("CashTransaction", "conid")))
    assert app.process_account({**CFG, "dry_run": dry_run}, "U1", "q1", "IBKR", {ISIN_KO: "KO"},
                             set(), set(), positions()) == ({}, False)
    assert w.imported == [] and w.cash_calls == []
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1 and "CashTransaction.conid (ConID (Contract ID))" in errors[0].getMessage()
    assert "actionID" not in errors[0].getMessage()
    assert CFG.get("dry_run") is not True


def test_dividend_field_prerequisites_lists_every_gap_in_one_error(monkeypatch, caplog):
    def mutate(root):
        _drop("CashTransaction", "exDate")(root)
        _drop("ChangeInDividendAccrual", "payDate")(root)
    w = World(monkeypatch, _prerequisite_xml(mutate))
    assert w.run() == ({}, False)
    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert "CashTransaction.exDate" in errors[0] and "ChangeInDividendAccrual.payDate" in errors[0]


def test_dividend_field_prerequisites_missing_accrual_section_fails_account(monkeypatch, caplog):
    def mutate(root):
        root.find(".//FlexStatement").remove(root.find(".//ChangeInDividendAccruals"))
    w = World(monkeypatch, _prerequisite_xml(mutate))
    assert w.run() == ({}, False)
    assert w.imported == [] and "ChangeInDividendAccruals section" in caplog.text


def test_dividend_field_prerequisites_complete_empty_and_no_cash_rows_pass(monkeypatch, caplog):
    assert ibkr.dividend_field_prerequisites(_prerequisite_xml()) == []
    # No relevant cash rows: nothing required, even without the accrual section.
    assert ibkr.dividend_field_prerequisites(report(trade_xml("T"))) == []
    only_other = report(divs=_cash_row("Deposits/Withdrawals", "20260715"))
    assert ibkr.dividend_field_prerequisites(only_other) == []
    # Present but empty accrual section, cash keys all present.
    def mutate(root):
        section = root.find(".//ChangeInDividendAccruals")
        for child in list(section):
            section.remove(child)
    assert ibkr.dividend_field_prerequisites(_prerequisite_xml(mutate)) == []
    assert "required dividend fields missing" not in caplog.text


def test_dividend_field_prerequisites_isolated_bad_row_keeps_local_rejection(monkeypatch, caplog):
    def mutate(root):
        root.findall(".//CashTransaction")[0].set("conid", "")
    xml = _prerequisite_xml(mutate, divs=div_xml() + div_xml(isin=ISIN_PEP, symbol="PEP"))
    assert ibkr.dividend_field_prerequisites(xml) == []
    w = World(monkeypatch, xml)
    assert w.run()[1] is True
    assert "required dividend fields missing" not in caplog.text


@pytest.mark.parametrize("value", [None, "", " \t "])
@pytest.mark.parametrize("invalid_config", [False, True])
def test_dry_run_default_warns_on_every_invocation(env, caplog, value, invalid_config):
    if value is None:
        env.delenv("DRY_RUN", raising=False)
    else:
        env.setenv("DRY_RUN", value)
    if invalid_config:
        env.delenv("IBKR_TOKEN")
    else:
        assert config.load_config()["dry_run"] is True
    # A synthetic empty portfolio and Flex reports exercise the real pipeline.
    reads = []
    def response(body):
        result = requests.Response()
        result.status_code = 200
        result._content = body.encode("utf-8")
        return result

    def get(url, **kwargs):
        if "/api/v1/activities" in url:
            reads.append("activities")
            return response('{"activities": [], "count": 0}')
        if url.endswith("/api/v1/account"):
            reads.append("accounts")
            return response('{"accounts": [{"id": "gf-1", "name": "U1"}, '
                            '{"id": "gf-2", "name": "U2"}]}')
        if url.endswith(("/api/v1/account/gf-1", "/api/v1/account/gf-2")):
            reads.append("cash")
            return response('{"currency": "USD"}')
        if "SendRequest" in url:
            reads.append("flex-request")
            return response(SEND_OK)
        if "GetStatement" in url:
            reads.append("flex-report")
            return response(report(trade_xml("DEFAULT-T")))
        pytest.fail("unexpected HTTP read")
    env.setattr(requests, "get", get)
    for verb in ("post", "put", "patch", "delete"):
        env.setattr(requests, verb, lambda *a, **k: pytest.fail("financial HTTP write"))
    for _ in range(2):
        caplog.clear()
        reads.clear()
        assert app.main() == (1 if invalid_config else 0)
        assert reads == ([] if invalid_config else [
            "activities", "flex-request", "flex-report", "accounts", "cash",
            "flex-request", "flex-report", "accounts", "cash"])
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings.count("DRY_RUN not set: simulation, nothing written") == 1
