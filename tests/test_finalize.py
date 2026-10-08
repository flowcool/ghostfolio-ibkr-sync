"""Offline end-to-end tests: failed-run notification gates, summary and isolation."""
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

import pytest

import ibkr_to_ghostfolio as m

URL_SECRET = "CANARY-DEST-a41f"
CANARY = "CANARY-ERR-77c0"
AMOUNT = "123456.78"
URLS = [f"json://user:{URL_SECRET}@notify.invalid/hook"]


@pytest.fixture
def env(monkeypatch):
    for k, v in {"IBKR_TOKEN": "tok", "IBKR_ACCOUNT_IDS": "U111,U222,U333",
                 "IBKR_QUERY_IDS": "q1,q2,q3", "GHOST_TOKEN": "g",
                 "GHOST_HOST": "http://ghost.internal:3333", "MAPPING_FILE": "",
                 "APPRISE_URLS": json.dumps(URLS)}.items():
        monkeypatch.setenv(k, v)
    for k in ("GHOST_ACCESS_TOKEN", "GHOST_ACCOUNT_NAMES", "DRY_RUN", "APPRISE_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def positions():
    return {"qty": defaultdict(float), "isin_symbols": defaultdict(set),
            "manual_sells": defaultdict(list), "manual_buys": defaultdict(list),
            "dividend_dates": defaultdict(list)}


def spy_send(monkeypatch, status="sent"):
    sent = []

    def send(settings, title, body):
        sent.append({"settings": settings, "title": title, "body": body})
        if isinstance(status, BaseException):
            raise status
        return status
    monkeypatch.setattr(m, "send_notification", send)
    return sent


def accounts(monkeypatch, results):
    calls = []
    monkeypatch.setattr(m, "ghost_get_existing_orders", lambda cfg: (set(), set(), positions()))

    def process(cfg, ibkr_id, *a):
        calls.append(ibkr_id)
        result = results[ibkr_id]
        if isinstance(result, BaseException):
            raise result
        return result
    monkeypatch.setattr(m, "process_account", process)
    return calls


ALL_OK = {"U111": ({}, True), "U222": ({}, True), "U333": ({}, True)}


# --- gates: no worker ----------------------------------------------------------

def test_success_sends_nothing(env):
    sent = spy_send(env)
    accounts(env, ALL_OK)
    assert m.main() == 0 and sent == []


def test_warning_only_run_sends_nothing(env):
    sent = spy_send(env)
    accounts(env, {**ALL_OK, "U222": ({"JP1": {"symbol": "X", "description": "Y"}}, True)})
    assert m.main() == 0 and sent == []


def test_disabled_notifications_send_nothing(env):
    env.delenv("APPRISE_URLS")
    sent = spy_send(env)
    accounts(env, {**ALL_OK, "U111": ({}, False)})
    assert m.main() == 1 and sent == []


def test_invalid_settings_warn_send_nothing_and_keep_the_exit_code(env, caplog):
    env.setenv("APPRISE_URLS", f"json://{URL_SECRET}")
    sent = spy_send(env)
    accounts(env, {**ALL_OK, "U111": ({}, False)})
    assert m.main() == 1 and sent == []
    assert any("failure notifications disabled" in r.message for r in caplog.records)
    assert URL_SECRET not in caplog.text


def test_failed_dry_run_sends_nothing(env):
    env.setenv("DRY_RUN", "1")
    sent = spy_send(env)
    accounts(env, {**ALL_OK, "U111": ({}, False)})
    assert m.main() == 1 and sent == []


def test_raw_dry_run_suppresses_before_configuration_validation(env):
    env.setenv("DRY_RUN", " Yes ")
    env.delenv("IBKR_TOKEN")
    sent = spy_send(env)
    env.setattr(m, "load_notification_config", lambda: pytest.fail("settings must not be read"))
    assert m.main() == 1 and sent == []


@pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit])
def test_interrupted_run_is_not_finalized(env, exc):
    sent = spy_send(env)
    accounts(env, {**ALL_OK, "U222": exc()})
    with pytest.raises(exc):
        m.main()
    assert sent == []


# --- one dispatch per failed run ----------------------------------------------

def test_configuration_failure_notifies_once(env):
    env.delenv("IBKR_TOKEN")
    sent = spy_send(env)
    assert m.main() == 1
    assert len(sent) == 1 and "- config: invalid_configuration" in sent[0]["body"]


def test_mapping_failure_notifies_once(env, tmp_path):
    env.setenv("MAPPING_FILE", str(tmp_path / f"{CANARY}.yaml"))
    sent = spy_send(env)
    assert m.main() == 1
    assert len(sent) == 1 and "- mapping: invalid_mapping" in sent[0]["body"]
    assert CANARY not in sent[0]["body"]


def test_login_failure_notifies_once(env):
    env.delenv("GHOST_TOKEN")
    env.setenv("GHOST_ACCESS_TOKEN", CANARY)
    env.setattr(m.requests, "post", lambda *a, **k: (_ for _ in ()).throw(
        m.requests.ConnectionError(CANARY)))
    sent = spy_send(env)
    assert m.main() == 1
    assert len(sent) == 1 and "- ghost_auth: login_failed" in sent[0]["body"]


def test_ghostfolio_startup_failure_notifies_once(env):
    sent = spy_send(env)
    env.setattr(m, "ghost_get_existing_orders",
                lambda cfg: (_ for _ in ()).throw(RuntimeError(f"count={AMOUNT}")))
    assert m.main() == 1
    assert len(sent) == 1 and "- ghost_startup: activities_unavailable" in sent[0]["body"]


def test_expired_ghostfolio_token_notifies_token_rejected(env):
    sent = spy_send(env)
    resp = m.requests.Response()
    resp.status_code = 401
    env.setattr(m, "ghost_get_existing_orders", lambda cfg: (_ for _ in ()).throw(
        m.requests.HTTPError("401 Unauthorized", response=resp)))
    assert m.main() == 1
    assert len(sent) == 1 and "- ghost_startup: token_rejected" in sent[0]["body"]


def test_unexpected_failure_notifies_once(env):
    sent = spy_send(env)
    env.setattr(m, "run_sync", lambda outcome: (_ for _ in ()).throw(ValueError(CANARY)))
    assert m.main() == 1
    assert len(sent) == 1 and "- unexpected: unhandled_error" in sent[0]["body"]


def test_several_failed_accounts_make_one_dispatch_after_every_account_ran(env):
    sent = spy_send(env)
    calls = accounts(env, {"U111": KeyError(f"{CANARY} {AMOUNT}"), "U222": ({}, True),
                           "U333": ({}, False)})
    assert m.main() == 1
    assert calls == ["U111", "U222", "U333"]
    assert len(sent) == 1
    body = sent[0]["body"]
    assert "Accounts failed: 2 of 3." in body
    assert "- account: unexpected_error (account #1)" in body
    assert "- account: account_failed (account #3)" in body
    assert sent[0]["title"] == m.NOTIFY_TITLE
    assert sent[0]["settings"] == {"urls": URLS, "timeout": 10}


def test_summary_carries_no_secret_identifier_host_or_amount(env):
    env.setenv("GHOST_ACCOUNT_NAMES", "Main,Joint,Kids")
    sent = spy_send(env)
    accounts(env, {"U111": RuntimeError(f"{CANARY} {AMOUNT} http://ghost.internal:3333"),
                   "U222": ({}, False), "U333": ({}, True)})
    assert m.main() == 1
    text = sent[0]["title"] + sent[0]["body"]
    for leak in (CANARY, AMOUNT, URL_SECRET, "U111", "U222", "Main", "Joint",
                 "ghost.internal", "RuntimeError", "tok"):
        assert leak not in text


def test_summary_format_is_fixed():
    out = m.new_run_outcome()
    out.update(accounts_total=3, accounts_failed=1)
    m.record_failure(out, "account", "account_failed", 2)
    out["failures"].append({"stage": "account", "reason": f"forged {CANARY}", "ordinal": f"U{CANARY}"})
    out["dropped"] = 4
    body = m.build_failure_summary(out, datetime(2026, 10, 8, 6, 5, tzinfo=timezone.utc))
    assert body == ("Run failed at 2026-10-08 06:05 UTC.\n"
                    "Accounts failed: 1 of 3.\n"
                    "- account: account_failed (account #2)\n"
                    "- unexpected: unhandled_error\n"
                    "- and 4 more\n"
                    "Details are in the container log.")


# --- notification problems never change the run -------------------------------

@pytest.mark.parametrize("status", ["timeout", "failed", "unavailable", "spawn_failed",
                                    RuntimeError(URL_SECRET)])
def test_notification_problems_keep_exit_code_and_account_processing(env, caplog, status):
    sent = spy_send(env, status)
    calls = accounts(env, {**ALL_OK, "U111": ({}, False)})
    assert m.main() == 1
    assert calls == ["U111", "U222", "U333"] and len(sent) == 1
    assert URL_SECRET not in caplog.text


def test_timeout_is_logged_as_uncertain_without_retry(env, caplog):
    sent = spy_send(env, "timeout")
    accounts(env, {**ALL_OK, "U111": ({}, False)})
    assert m.main() == 1 and len(sent) == 1
    assert any("may still arrive; not retried" in r.message for r in caplog.records)


def test_real_hanging_worker_cannot_change_the_outcome(env, tmp_path, caplog):
    script = tmp_path / "hang.py"
    script.write_text("import time\ntime.sleep(60)\n")
    env.setattr(m, "_notify_worker_argv", lambda: [sys.executable, str(script)])
    env.setenv("APPRISE_TIMEOUT", "1")
    calls = accounts(env, {**ALL_OK, "U222": ({}, False)})
    start = time.monotonic()
    assert m.main() == 1
    assert time.monotonic() - start < 10
    assert calls == ["U111", "U222", "U333"]
    assert any("timed out" in r.message for r in caplog.records)
