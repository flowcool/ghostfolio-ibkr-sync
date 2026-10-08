"""Offline tests: structured run outcomes and the main/run_sync boundary."""
import inspect
import json
from collections import defaultdict

import pytest

import ibkr_to_ghostfolio as m

CANARY = "CANARY-SECRET-5e1d"
AMOUNT = "987654.32"


@pytest.fixture
def env(monkeypatch):
    for k, v in {"IBKR_TOKEN": "tok", "IBKR_ACCOUNT_IDS": "U111,U222,U333",
                 "IBKR_QUERY_IDS": "q1,q2,q3", "GHOST_TOKEN": "g",
                 "GHOST_HOST": "http://ghost:3333", "MAPPING_FILE": ""}.items():
        monkeypatch.setenv(k, v)
    for k in ("GHOST_ACCESS_TOKEN", "GHOST_ACCOUNT_NAMES", "DRY_RUN"):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def positions():
    return {"qty": defaultdict(float), "isin_symbols": defaultdict(set),
            "manual_sells": defaultdict(list), "manual_buys": defaultdict(list),
            "dividend_dates": defaultdict(list)}


def capture_outcome(monkeypatch):
    """Make main use an outcome the test can inspect afterwards."""
    holder = {}
    original = m.new_run_outcome

    def new():
        holder["outcome"] = original()
        return holder["outcome"]
    monkeypatch.setattr(m, "new_run_outcome", new)
    return holder


def stub_accounts(monkeypatch, results):
    monkeypatch.setattr(m, "ghost_get_existing_orders", lambda cfg: (set(), set(), positions()))

    def process(cfg, ibkr_id, *a):
        result = results[ibkr_id]
        if isinstance(result, BaseException):
            raise result
        return result
    monkeypatch.setattr(m, "process_account", process)


# --- record_failure -----------------------------------------------------------

def test_record_failure_keeps_only_controlled_codes():
    out = m.new_run_outcome()
    m.record_failure(out, "account", "account_failed", 2)
    m.record_failure(out, "account", f"raw error {CANARY}", 3)
    m.record_failure(out, f"http://h/{CANARY}", "invalid_mapping")
    assert out["failures"] == [
        {"stage": "account", "reason": "account_failed", "ordinal": 2},
        {"stage": "unexpected", "reason": "unhandled_error", "ordinal": 3},
        {"stage": "unexpected", "reason": "unhandled_error", "ordinal": None}]


@pytest.mark.parametrize("ordinal", [0, -1, True, "1", 1.0, "U123"])
def test_record_failure_drops_anything_but_a_positive_ordinal(ordinal):
    out = m.new_run_outcome()
    m.record_failure(out, "account", "account_failed", ordinal)
    assert out["failures"][0]["ordinal"] is None


def test_record_failure_is_bounded_and_counts_what_it_drops():
    out = m.new_run_outcome()
    for i in range(m.MAX_OUTCOME_FAILURES + 7):
        m.record_failure(out, "account", "account_failed", i + 1)
    assert len(out["failures"]) == m.MAX_OUTCOME_FAILURES and out["dropped"] == 7


# --- main / run_sync ----------------------------------------------------------

def test_main_is_callable_without_arguments():
    assert list(inspect.signature(m.main).parameters) == []


def test_process_account_contract_is_unchanged():
    assert list(inspect.signature(m.process_account).parameters) == [
        "config", "ibkr_account_id", "query_id", "ghost_account_name", "mapping",
        "existing_trade_ids", "existing_dividend_comments", "positions"]


def test_clean_run_records_no_failure(env):
    holder = capture_outcome(env)
    stub_accounts(env, {"U111": ({}, True), "U222": ({}, True), "U333": ({}, True)})
    assert m.main() == 0
    assert holder["outcome"] == {"failures": [], "dropped": 0, "accounts_total": 3, "accounts_failed": 0}


def test_warning_only_run_records_no_failure(env):
    holder = capture_outcome(env)
    stub_accounts(env, {"U111": ({"JP1": {"symbol": "X", "description": "Y"}}, True),
                        "U222": ({}, True), "U333": ({}, True)})
    assert m.main() == 0
    assert holder["outcome"]["failures"] == []


def test_configuration_error_returns_one_and_records_the_stage(env):
    holder = capture_outcome(env)
    env.delenv("IBKR_TOKEN")
    assert m.main() == 1
    assert holder["outcome"]["failures"] == [
        {"stage": "config", "reason": "invalid_configuration", "ordinal": None}]


def test_mapping_error_is_recorded(env, tmp_path):
    holder = capture_outcome(env)
    env.setenv("MAPPING_FILE", str(tmp_path / "missing.yaml"))
    assert m.main() == 1
    assert [f["stage"] for f in holder["outcome"]["failures"]] == ["mapping"]


def test_login_failure_is_recorded(env):
    holder = capture_outcome(env)
    env.delenv("GHOST_TOKEN")
    env.setenv("GHOST_ACCESS_TOKEN", CANARY)

    def refuse(host, token):
        raise RuntimeError("Ghostfolio login failed: HTTP 403")
    env.setattr(m, "ghost_exchange_access_token", refuse)
    assert m.main() == 1
    assert holder["outcome"]["failures"] == [
        {"stage": "ghost_auth", "reason": "login_failed", "ordinal": None}]


def test_ghostfolio_startup_failure_is_recorded(env):
    holder = capture_outcome(env)

    def down(cfg):
        raise m.requests.ConnectionError(f"http://ghost:3333/?t={CANARY}")
    env.setattr(m, "ghost_get_existing_orders", down)
    assert m.main() == 1
    assert holder["outcome"]["failures"] == [
        {"stage": "ghost_startup", "reason": "activities_unavailable", "ordinal": None}]


def test_failed_and_crashing_accounts_record_ordinals_and_the_others_still_run(env):
    holder = capture_outcome(env)
    calls = []
    env.setattr(m, "ghost_get_existing_orders", lambda cfg: (set(), set(), positions()))

    def process(cfg, ibkr_id, *a):
        calls.append(ibkr_id)
        if ibkr_id == "U111":
            raise KeyError(f"{CANARY} {AMOUNT}")
        return {}, ibkr_id != "U333"
    env.setattr(m, "process_account", process)
    assert m.main() == 1
    assert calls == ["U111", "U222", "U333"]
    out = holder["outcome"]
    assert out["failures"] == [
        {"stage": "account", "reason": "unexpected_error", "ordinal": 1},
        {"stage": "account", "reason": "account_failed", "ordinal": 3}]
    assert (out["accounts_total"], out["accounts_failed"]) == (3, 2)
    text = json.dumps(out)
    for leak in (CANARY, AMOUNT, "U111", "U333", "ghost:3333", "KeyError"):
        assert leak not in text


def test_unexpected_error_outside_accounts_is_recorded_and_returns_one(env, caplog):
    holder = capture_outcome(env)

    def broken(outcome):
        raise ValueError(CANARY)
    env.setattr(m, "run_sync", broken)
    assert m.main() == 1
    assert holder["outcome"]["failures"] == [
        {"stage": "unexpected", "reason": "unhandled_error", "ordinal": None}]
    assert any("unhandled error" in r.message for r in caplog.records)


@pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit])
def test_interrupts_propagate_from_main(env, exc):
    stub_accounts(env, {"U111": exc(), "U222": ({}, True), "U333": ({}, True)})
    with pytest.raises(exc):
        m.main()
