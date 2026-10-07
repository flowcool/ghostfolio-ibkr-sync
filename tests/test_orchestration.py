"""Offline tests: orchestration (process_account, main, load_config) and the IBKR Flex fetch."""
from collections import defaultdict

import pytest

import ibkr_to_ghostfolio as m

ISIN_KO = "US1912161007"
ISIN_PEP = "US7134481081"
ACC = "gf-acc"
CFG = {"ibkr_token": "SECRET-TOK", "dry_run": False, "ghost_host": "http://g", "ghost_token": "t"}


# --- helpers ----------------------------------------------------------------

def positions(qty=None):
    return {"qty": defaultdict(float, qty or {}), "isin_symbols": defaultdict(set),
            "manual_sells": defaultdict(list), "manual_buys": defaultdict(list),
            "dividend_dates": defaultdict(list)}


def trade_xml(tid, side="BUY", qty=10, symbol="KO", isin=ISIN_KO, date="20260801;100000", **extra):
    q = qty if side == "BUY" else -qty
    attrs = {"tradeID": tid, "symbol": symbol, "isin": isin, "assetCategory": "STK", "buySell": side,
             "quantity": q, "tradePrice": 60, "ibCommission": -1, "currency": "USD", "dateTime": date}
    attrs.update(extra)
    return "<Trade " + " ".join(f'{k}="{v}"' for k, v in attrs.items()) + "/>"


def div_xml(amount="25.00", date="20260715", isin=ISIN_KO, symbol="KO"):
    return (f'<CashTransaction type="Dividends" levelOfDetail="DETAIL" amount="{amount}" dateTime="{date}" '
            f'isin="{isin}" symbol="{symbol}" currency="USD" description="X CASH DIVIDEND USD 0.25 PER SHARE"/>')


def report(trades="", divs="", cash="100.5", cash_section=True):
    cash_xml = (f'<CashReport><CashReportCurrency currency="BASE_SUMMARY" endingCash="{cash}"/></CashReport>'
                if cash is not None else "")
    ct = f"<CashTransactions>{divs}</CashTransactions>" if cash_section else ""
    return (f"<FlexQueryResponse><FlexStatements><FlexStatement><Trades>{trades}</Trades>{ct}{cash_xml}"
            f"</FlexStatement></FlexStatements></FlexQueryResponse>")


class World:
    """Records every side effect so tests can assert on what process_account did."""
    def __init__(self, monkeypatch, xml, find=ACC, import_ok=True, cash_ok=True):
        self.imported, self.cash_calls = [], []
        self.import_ok, self.cash_ok = import_ok, cash_ok
        monkeypatch.setattr(m, "fetch_flex_report", self._fetch(xml))
        monkeypatch.setattr(m, "ghost_find_account_id", self._find(find))
        monkeypatch.setattr(m, "ghost_import_activities", self._import)
        monkeypatch.setattr(m, "ghost_update_cash_balance", self._cash)

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

    def _cash(self, cfg, acc, balance):
        if isinstance(self.cash_ok, Exception):
            raise self.cash_ok
        self.cash_calls.append((acc, balance))
        return self.cash_ok

    def run(self, ids=None, comments=None, pos=None, mapping=None):
        self.ids = set() if ids is None else ids
        self.comments = set() if comments is None else comments
        self.pos = pos or positions()
        self.result = m.process_account(CFG, "U1", "q1", "IBKR", mapping or {}, self.ids, self.comments, self.pos)
        return self.result

    @property
    def activities(self):
        return [a for batch in self.imported for a in batch]


# --- process_account: failure isolation ------------------------------------------

def test_flex_fetch_failure_returns_failed_and_does_nothing_else(monkeypatch):
    w = World(monkeypatch, RuntimeError("IBKR down"))
    assert w.run() == ({}, False)
    assert w.imported == [] and w.cash_calls == []


@pytest.mark.parametrize("find", [m.requests.ConnectionError("net"), None])
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
    assert len(w.imported) == 1                                     # one POST per account
    assert w.ids == {"T1", "T2"}
    assert w.comments == {f"dividend#{ISIN_KO}#2026-07-15"}
    assert w.pos["qty"][(ACC, "KO")] == pytest.approx(10.0)
    assert w.pos["qty"][(ACC, "PEP")] == pytest.approx(6.0)         # 10 - 4
    assert w.pos["dividend_dates"][(ACC, "KO")] == ["2026-07-15"]
    assert set(unmapped) == {ISIN_KO, ISIN_PEP}                     # no mapping given
    assert w.cash_calls == [(ACC, 100.5)]


def test_second_account_sharing_the_sets_does_not_reimport(monkeypatch):
    w = World(monkeypatch, report(trade_xml("T1"), div_xml()))
    w.run()
    first = len(w.activities)
    w.imported.clear()
    m.process_account(CFG, "U2", "q2", "IBKR", {}, w.ids, w.comments, w.pos)
    assert first == 2 and w.activities == []


def test_trade_without_id_is_skipped_and_warned(monkeypatch, caplog):
    w = World(monkeypatch, report(trade_xml("")))
    w.run()
    assert w.activities == []
    assert any("missing tradeID" in r.message for r in caplog.records)


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


# --- process_account: dividend deduplication ---------------------------------------

@pytest.mark.parametrize("comment", [f"dividend#{ISIN_KO}#2026-07-15", "dividend#KO#2026-07-15"])
def test_dividend_already_present_by_comment_new_or_old_format_is_skipped(monkeypatch, comment):
    w = World(monkeypatch, report(divs=div_xml()))
    w.run(comments={comment})
    assert w.activities == []


@pytest.mark.parametrize("existing,skipped", [("2026-07-17", True), ("2026-07-18", True), ("2026-07-12", True),
                                              ("2026-07-19", False), ("2026-07-11", False)])
def test_dividend_match_window_is_exactly_three_days(monkeypatch, existing, skipped):
    pos = positions()
    pos["dividend_dates"][(ACC, "KO")].append(existing)
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
    for k in ("GHOST_ACCOUNT_NAMES", "DRY_RUN", "GHOST_CURRENCY", "GHOST_PLATFORM_ID"):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def stub_main(monkeypatch, results, existing=None):
    calls = []

    def fake_process(config, ibkr_id, qid, name, mapping, ids, comments, pos):
        calls.append((ibkr_id, qid, name))
        return results[ibkr_id]
    monkeypatch.setattr(m, "process_account", fake_process)
    monkeypatch.setattr(m, "ghost_get_existing_orders",
                        lambda cfg: existing or (set(), set(), positions()))
    return calls


def test_main_all_accounts_clean_exits_zero_and_uses_ids_as_names_without_account_names(env, caplog):
    calls = stub_main(env, {"U1": ({}, True), "U2": ({}, True)})
    assert m.main() == 0
    assert calls == [("U1", "q1", "U1"), ("U2", "q2", "U2")]
    assert any("No GHOST_ACCOUNT_NAMES" in r.message for r in caplog.records)


def test_main_failed_account_exits_one_but_still_processes_the_others(env, caplog):
    calls = stub_main(env, {"U1": ({}, False), "U2": ({}, True)})
    assert m.main() == 1
    assert [c[0] for c in calls] == ["U1", "U2"]
    assert any("1 of 2 account(s): U1" in r.message for r in caplog.records)


def test_main_unmapped_isin_is_reported_but_is_not_a_failure(env, caplog):
    stub_main(env, {"U1": ({"JP1": {"symbol": "1234.T", "description": "ACME"}}, True), "U2": ({}, True)})
    assert m.main() == 0
    assert any("Unmapped ISIN JP1 (ACME)" in r.message for r in caplog.records)


def test_main_unexpected_exception_in_one_account_does_not_stop_the_others(env, caplog):
    # real process_account: the conversion blows up for the first account only
    env.setenv("GHOST_ACCOUNT_NAMES", "A,B")
    fetched, imported, cash = [], [], []
    env.setattr(m, "ghost_get_existing_orders", lambda cfg: (set(), set(), positions()))
    env.setattr(m, "fetch_flex_report", lambda token, qid, *a, **k: fetched.append(qid) or report(trade_xml("T1")))
    env.setattr(m, "ghost_find_account_id", lambda cfg, name: f"gf-{name}")
    env.setattr(m, "ghost_import_activities", lambda cfg, acts: imported.append(list(acts)) or (list(acts), True))
    env.setattr(m, "ghost_update_cash_balance", lambda cfg, acc, bal: cash.append(acc) or True)
    real = m.convert_trade_to_activity
    calls = []
    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise KeyError("unforeseen field")
        return real(*a, **k)
    env.setattr(m, "convert_trade_to_activity", flaky)
    assert m.main() == 1                                            # the run is still flagged
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
    env.setattr(m, "process_account", interrupted)
    with pytest.raises(exc):
        m.main()


@pytest.mark.parametrize("exc", [RuntimeError("count mismatch"), m.requests.ConnectionError("down")])
def test_main_untrusted_or_unreadable_existing_activities_stops_before_any_account(env, exc):
    calls = stub_main(env, {})
    def boom(cfg):
        raise exc
    env.setattr(m, "ghost_get_existing_orders", boom)
    assert m.main() == 1
    assert calls == []


def test_main_invalid_mapping_stops_the_run(env, tmp_path):
    env.setenv("MAPPING_FILE", str(tmp_path / "missing.yaml"))
    calls = stub_main(env, {})
    assert m.main() == 1
    assert calls == []


def test_main_configuration_error_exits_one(env):
    env.delenv("IBKR_TOKEN")
    with pytest.raises(SystemExit) as e:
        m.main()
    assert e.value.code == 1


# --- load_config --------------------------------------------------------------

def test_load_config_defaults_and_normalisation(env):
    env.setenv("IBKR_ACCOUNT_IDS", " U1 , U2 ")
    cfg = m.load_config()
    assert cfg["account_ids"] == ["U1", "U2"] and cfg["query_ids"] == ["q1", "q2"]
    assert cfg["ghost_host"] == "http://ghost:3333"                  # trailing slash stripped
    assert (cfg["ghost_currency"], cfg["account_names"], cfg["dry_run"]) == ("USD", [], False)


def test_load_config_missing_variables_are_all_named(env):
    env.delenv("IBKR_TOKEN"); env.delenv("GHOST_HOST")
    with pytest.raises(RuntimeError, match="IBKR_TOKEN.*GHOST_HOST"):
        m.load_config()


@pytest.mark.parametrize("var,value", [("IBKR_QUERY_IDS", "q1"), ("GHOST_ACCOUNT_NAMES", "only-one")])
def test_load_config_count_mismatch_is_rejected(env, var, value):
    env.setenv(var, value)
    with pytest.raises(RuntimeError, match="same number|must match"):
        m.load_config()


@pytest.mark.parametrize("value,expected", [("1", True), ("true", True), ("YES", True), ("on", True),
                                            ("0", False), ("", False), ("nope", False)])
def test_load_config_dry_run_truthy_values(env, value, expected):
    env.setenv("DRY_RUN", value)
    assert m.load_config()["dry_run"] is expected


# --- IBKR Flex fetch ----------------------------------------------------------

SEND_OK = ("<FlexStatementResponse><Status>Success</Status><ReferenceCode>REF1</ReferenceCode>"
           "<Url>https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement</Url>"
           "</FlexStatementResponse>")
READY = "<FlexQueryResponse><FlexStatements/></FlexQueryResponse>"
WARN = "<FlexStatementResponse><Status>Warn</Status><ErrorCode>1019</ErrorCode></FlexStatementResponse>"


class Txt:
    def __init__(self, text):
        self.text = text


def script_flex(monkeypatch, *bodies):
    seq, urls, sleeps = list(bodies), [], []
    def get(url, params, timeout):
        urls.append((url, dict(params)))
        return Txt(seq.pop(0))
    monkeypatch.setattr(m, "_ibkr_get", get)
    monkeypatch.setattr(m.time, "sleep", lambda s: sleeps.append(s))
    return urls, sleeps


def test_flex_fetch_happy_path_sends_token_and_reference_code(monkeypatch):
    urls, sleeps = script_flex(monkeypatch, SEND_OK, READY)
    assert m.fetch_flex_report("TOK", "123") == READY
    assert urls[0][1] == {"t": "TOK", "q": "123", "v": "3"}
    assert urls[1][1] == {"q": "REF1", "t": "TOK", "v": "3"}
    assert sleeps == []


def test_flex_fetch_polls_while_statement_is_not_ready(monkeypatch):
    urls, sleeps = script_flex(monkeypatch, SEND_OK, WARN, WARN, READY)
    assert m.fetch_flex_report("TOK", "1", retry_delay=7) == READY
    assert len(urls) == 4 and sleeps == [7, 7]


def test_flex_fetch_status_warn_without_error_code_also_means_not_ready(monkeypatch):
    urls, sleeps = script_flex(monkeypatch, SEND_OK, "<R><Status>Warn</Status></R>", READY)
    assert m.fetch_flex_report("TOK", "1") == READY and len(sleeps) == 1


def test_flex_fetch_other_error_code_such_as_too_many_requests_fails_immediately(monkeypatch):
    urls, sleeps = script_flex(monkeypatch, SEND_OK, "<R><Status>Fail</Status><ErrorCode>1018</ErrorCode>"
                                                     "<ErrorMessage>Too many requests</ErrorMessage></R>")
    with pytest.raises(RuntimeError, match="GetStatement failed: Too many requests"):
        m.fetch_flex_report("TOK", "1")
    assert sleeps == []


def test_flex_fetch_error_code_1019_alone_also_means_not_ready(monkeypatch):
    pending = "<R><Status>Fail</Status><ErrorCode>1019</ErrorCode></R>"
    urls, sleeps = script_flex(monkeypatch, SEND_OK, pending, READY)
    assert m.fetch_flex_report("TOK", "1") == READY and len(sleeps) == 1


def test_flex_fetch_gives_up_after_max_retries(monkeypatch):
    urls, sleeps = script_flex(monkeypatch, SEND_OK, WARN, WARN, WARN)
    with pytest.raises(RuntimeError, match="Timed out"):
        m.fetch_flex_report("TOK", "1", max_retries=3)
    assert len(urls) == 4 and len(sleeps) == 3


def test_flex_fetch_send_request_failure_is_reported(monkeypatch):
    script_flex(monkeypatch, "<R><Status>Fail</Status><ErrorMessage>Invalid token</ErrorMessage></R>")
    with pytest.raises(RuntimeError, match="SendRequest failed: Invalid token"):
        m.fetch_flex_report("TOK", "1")


def test_flex_fetch_statement_error_status_is_reported(monkeypatch):
    script_flex(monkeypatch, SEND_OK, "<R><Status>Fail</Status><ErrorCode>1003</ErrorCode>"
                                      "<ErrorMessage>Statement unavailable</ErrorMessage></R>")
    with pytest.raises(RuntimeError, match="GetStatement failed: Statement unavailable"):
        m.fetch_flex_report("TOK", "1")


def test_flex_fetch_foreign_statement_host_is_rejected_before_the_token_is_sent(monkeypatch):
    evil = SEND_OK.replace("ndcdyn.interactivebrokers.com", "evil.example")
    urls, _ = script_flex(monkeypatch, evil)
    with pytest.raises(RuntimeError, match="Unexpected IBKR statement URL"):
        m.fetch_flex_report("TOK", "1")
    assert len(urls) == 1                                           # step 2 (with the token) never sent


# --- _ibkr_get: retry and redaction --------------------------------------------

class HttpResp:
    def __init__(self, status=200):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise m.requests.HTTPError(f"{self.status_code} for url: https://x/?t=SECRET-TOK")


def test_ibkr_get_retries_network_errors_then_succeeds(monkeypatch):
    attempts, sleeps = [], []
    def get(url, params, timeout):
        attempts.append(1)
        if len(attempts) < 3:
            raise m.requests.ConnectionError("reset")
        return HttpResp()
    monkeypatch.setattr(m.requests, "get", get)
    monkeypatch.setattr(m.time, "sleep", lambda s: sleeps.append(s))
    assert isinstance(m._ibkr_get("https://x", {"t": "SECRET-TOK"}, 5), HttpResp)
    assert len(attempts) == 3 and sleeps == [10, 30]


def test_ibkr_get_gives_up_after_the_last_retry_and_never_leaks_the_token(monkeypatch):
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: (_ for _ in ()).throw(
        m.requests.ConnectionError("GET https://x/?t=SECRET-TOK failed")))
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError) as e:
        m._ibkr_get("https://x", {"t": "SECRET-TOK"}, 5)
    assert "SECRET-TOK" not in str(e.value) and "***" in str(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__   # no chained traceback with the URL


def test_ibkr_get_redacts_url_encoded_forms_of_the_token(monkeypatch):
    token = "a+b/c="
    leaked = f"GET https://x/?t={m.quote_plus(token)} raw {token} and {m.quote(token, safe='')}"
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: (_ for _ in ()).throw(m.requests.ConnectionError(leaked)))
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError) as e:
        m._ibkr_get("https://x", {"t": token}, 5)
    msg = str(e.value)
    assert token not in msg and m.quote_plus(token) not in msg and m.quote(token, safe="") not in msg


def test_ibkr_get_http_error_is_not_retried_and_is_redacted(monkeypatch):
    attempts = []
    def get(url, params, timeout):
        attempts.append(1)
        return HttpResp(503)
    monkeypatch.setattr(m.requests, "get", get)
    monkeypatch.setattr(m.time, "sleep", lambda s: pytest.fail("HTTP errors are not retried"))
    with pytest.raises(RuntimeError) as e:
        m._ibkr_get("https://x", {"t": "SECRET-TOK"}, 5)
    assert len(attempts) == 1 and "SECRET-TOK" not in str(e.value)


# --- end to end through the real functions ------------------------------------

class ForbiddenHttp:
    """requests stand-in that fails the test on any Ghostfolio call."""
    def __getattr__(self, name):
        def call(*a, **k):
            pytest.fail(f"unexpected HTTP {name} in dry run")
        return call


def test_dry_run_sends_nothing_but_still_updates_the_in_memory_state(monkeypatch):
    # real ghost_import_activities / ghost_update_cash_balance, HTTP forbidden
    monkeypatch.setattr(m, "fetch_flex_report", lambda *a, **k: report(trade_xml("T1"), div_xml()))
    monkeypatch.setattr(m, "ghost_find_account_id", lambda *a: ACC)
    monkeypatch.setattr(m, "requests", ForbiddenHttp())
    ids, comments, pos = set(), set(), positions()
    _, ok = m.process_account({**CFG, "dry_run": True}, "U1", "q1", "IBKR", {}, ids, comments, pos)
    assert ok is True and ids == {"T1"} and comments == {f"dividend#{ISIN_KO}#2026-07-15"}


def test_main_shares_the_existing_sets_between_accounts_through_the_real_process_account(env, monkeypatch):
    env.setenv("GHOST_ACCOUNT_NAMES", "A,B")
    imported = []
    env.setattr(m, "ghost_get_existing_orders", lambda cfg: (set(), set(), positions()))
    env.setattr(m, "fetch_flex_report", lambda *a, **k: report(trade_xml("T1")))        # same trade for both
    env.setattr(m, "ghost_find_account_id", lambda cfg, name: "same-gf-account")       # both map to one account
    env.setattr(m, "ghost_import_activities", lambda cfg, acts: imported.append(list(acts)) or (list(acts), True))
    env.setattr(m, "ghost_update_cash_balance", lambda *a: True)
    assert m.main() == 0
    assert len(imported) == 1 and imported[0][0]["comment"] == "IBKR#T1"               # B sees A's import


def test_malformed_flex_report_fails_only_that_account(monkeypatch):
    script_flex(monkeypatch, SEND_OK, "<not-xml")
    monkeypatch.setattr(m, "ghost_find_account_id", lambda *a: pytest.fail("must not be reached"))
    assert m.process_account(CFG, "U1", "q1", "IBKR", {}, set(), set(), positions()) == ({}, False)


@pytest.mark.parametrize("profile_key", ["assetProfile", "SymbolProfile"])
def test_api_profiles_drive_holdings_manual_alias_and_dividend_reconciliation(monkeypatch, profile_key):
    """Both profile formats preserve account holdings and suppress reconciled imports."""
    from types import SimpleNamespace

    def row(kind, qty, date, symbol="KO", comment=None, account=ACC):
        """Build an account activity using the profile format under test."""
        return {"type": kind, "quantity": qty, "date": date, "comment": comment,
                "accountId": account, profile_key: {"symbol": symbol, "isin": ISIN_KO}}

    rows = [row("BUY", 20, "2026-01-01", comment="IBKR#OLD"),
            row("BUY", 10, "2026-08-01"),
            row("SELL", 3, "2026-08-02", symbol="KO.A"),
            row("DIVIDEND", 100, "2026-07-16"),
            row("BUY", 99, "2026-01-01", account="other-account")]
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"activities": rows, "count": len(rows)}))
    ids, comments, pos = m.ghost_get_existing_orders(CFG)
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

    monkeypatch.setattr(m, "load_config", lambda: {
        **CFG, "mapping_file": "unused", "account_ids": ["U1"],
        "query_ids": ["q1"], "account_names": ["IBKR"]})
    monkeypatch.setattr(m, "load_mapping", lambda path: {})
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"activities": [{"type": "BUY", "quantity": 1}], "count": 1}))
    monkeypatch.setattr(m, "process_account", lambda *a, **k: pytest.fail("no account processing"))
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: pytest.fail("no POST"))
    monkeypatch.setattr(m.requests, "put", lambda *a, **k: pytest.fail("no PUT"))
    assert m.main() == 1
