"""Offline end-to-end tests: failed-run notification gates, summary and isolation."""
import json
import sys
import time
from datetime import datetime, timezone

import pytest

import requests
import logging
from _sync_helpers import (
    World,
    destination,
    div_xml,
    positions,
    read,
    report,
    structured_input_xml,
)
from ghostfolio_ibkr_sync import app, notify, outcome

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
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr(app, "fetch_flex_report", lambda token, query: report(
        source_account={"q1":"U111","q2":"U222","q3":"U333"}[query]))
    monkeypatch.setattr(app, "ghost_find_account_id", lambda cfg, name: name)
    return monkeypatch


def spy_send(monkeypatch, status="sent"):
    sent = []

    def send(settings, title, body):
        sent.append({"settings": settings, "title": title, "body": body})
        if isinstance(status, BaseException):
            raise status
        return status
    monkeypatch.setattr(app, "send_notification", send)
    return sent


def accounts(monkeypatch, results):
    calls = []
    monkeypatch.setattr(app, "ghost_get_existing_orders", lambda cfg: (set(), set(), positions()))

    def process(cfg, ibkr_id, *a):
        calls.append(ibkr_id)
        result = results[ibkr_id]
        if isinstance(result, BaseException):
            raise result
        return result
    monkeypatch.setattr(app, "process_account", process)
    return calls


ALL_OK = {"U111": ({}, True), "U222": ({}, True), "U333": ({}, True)}


def bind_flex_report_to_query_account(monkeypatch, xml):
    """Return the same synthetic report with account evidence bound to each query."""
    accounts_by_query = {"q1": "U111", "q2": "U222", "q3": "U333"}

    def fetch(token, query_id):
        account_id = accounts_by_query[query_id]
        return xml.replace('accountId="U1"', f'accountId="{account_id}"')

    monkeypatch.setattr(app, "fetch_flex_report", fetch)


# --- gates: no worker ----------------------------------------------------------

def test_success_sends_nothing(env):
    sent = spy_send(env)
    accounts(env, ALL_OK)
    assert app.main() == 0 and sent == []


def test_warning_only_run_sends_nothing(env):
    sent = spy_send(env)
    accounts(env, {**ALL_OK, "U222": ({"JP1": {"symbol": "X", "description": "Y"}}, True)})
    assert app.main() == 0 and sent == []


def test_disabled_notifications_send_nothing(env):
    env.delenv("APPRISE_URLS")
    sent = spy_send(env)
    accounts(env, {**ALL_OK, "U111": ({}, False)})
    assert app.main() == 1 and sent == []


def test_invalid_settings_warn_send_nothing_and_keep_the_exit_code(env, caplog):
    env.setenv("APPRISE_URLS", f"json://{URL_SECRET}")
    sent = spy_send(env)
    accounts(env, {**ALL_OK, "U111": ({}, False)})
    assert app.main() == 1 and sent == []
    assert any("failure notifications disabled" in r.message for r in caplog.records)
    assert URL_SECRET not in caplog.text


def test_failed_dry_run_notifies_once(env):
    env.setenv("DRY_RUN", "1")
    sent = spy_send(env)
    accounts(env, {**ALL_OK, "U111": ({}, False)})
    assert app.main() == 1 and len(sent) == 1
    assert sent[0]["title"] == notify.NOTIFY_TITLE


def test_dry_run_configuration_failure_notifies_once(env):
    env.setenv("DRY_RUN", " Yes ")
    env.delenv("IBKR_TOKEN")
    sent = spy_send(env)
    assert app.main() == 1 and len(sent) == 1
    assert "config: invalid_configuration" in sent[0]["body"]


@pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit])
def test_interrupted_run_is_not_finalized(env, exc):
    sent = spy_send(env)
    accounts(env, {**ALL_OK, "U222": exc()})
    with pytest.raises(exc):
        app.main()
    assert sent == []


# --- one dispatch per failed run ----------------------------------------------

def test_configuration_failure_notifies_once(env):
    env.delenv("IBKR_TOKEN")
    sent = spy_send(env)
    assert app.main() == 1
    assert len(sent) == 1 and "- config: invalid_configuration" in sent[0]["body"]


def test_mapping_failure_notifies_once(env, tmp_path):
    env.setenv("MAPPING_FILE", str(tmp_path / f"{CANARY}.yaml"))
    sent = spy_send(env)
    assert app.main() == 1
    assert len(sent) == 1 and "- mapping: invalid_mapping" in sent[0]["body"]
    assert CANARY not in sent[0]["body"]


def test_login_failure_notifies_once(env):
    env.delenv("GHOST_TOKEN")
    env.setenv("GHOST_ACCESS_TOKEN", CANARY)
    env.setattr(requests, "post", lambda *a, **k: (_ for _ in ()).throw(
        requests.ConnectionError(CANARY)))
    sent = spy_send(env)
    assert app.main() == 1
    assert len(sent) == 1 and "- ghost_auth: login_failed" in sent[0]["body"]


def test_ghostfolio_startup_failure_notifies_once(env):
    sent = spy_send(env)
    env.setattr(app, "ghost_get_existing_orders",
                lambda cfg: (_ for _ in ()).throw(RuntimeError(f"count={AMOUNT}")))
    assert app.main() == 1
    assert len(sent) == 1 and "- ghost_startup: activities_unavailable" in sent[0]["body"]


def test_expired_ghostfolio_token_notifies_token_rejected(env):
    sent = spy_send(env)
    resp = requests.Response()
    resp.status_code = 401
    env.setattr(app, "ghost_get_existing_orders", lambda cfg: (_ for _ in ()).throw(
        requests.HTTPError("401 Unauthorized", response=resp)))
    assert app.main() == 1
    assert len(sent) == 1 and "- ghost_startup: token_rejected" in sent[0]["body"]


def test_unexpected_failure_notifies_once(env):
    sent = spy_send(env)
    env.setattr(app, "run_sync", lambda outcome: (_ for _ in ()).throw(ValueError(CANARY)))
    assert app.main() == 1
    assert len(sent) == 1 and "- unexpected: unhandled_error" in sent[0]["body"]


def test_several_failed_accounts_make_one_dispatch_after_every_account_ran(env):
    sent = spy_send(env)
    calls = accounts(env, {"U111": KeyError(f"{CANARY} {AMOUNT}"), "U222": ({}, True),
                           "U333": ({}, False)})
    assert app.main() == 1
    assert calls == ["U111", "U222", "U333"]
    assert len(sent) == 1
    body = sent[0]["body"]
    assert "Accounts failed: 2 of 3." in body
    assert "- account: unexpected_error (account #1)" in body
    assert "- account: account_failed (account #3)" in body
    assert sent[0]["title"] == notify.NOTIFY_TITLE
    assert sent[0]["settings"] == {"urls": URLS, "timeout": 10}


def test_summary_carries_no_secret_identifier_host_or_amount(env):
    env.setenv("GHOST_ACCOUNT_NAMES", "Main,Joint,Kids")
    sent = spy_send(env)
    accounts(env, {"U111": RuntimeError(f"{CANARY} {AMOUNT} http://ghost.internal:3333"),
                   "U222": ({}, False), "U333": ({}, True)})
    assert app.main() == 1
    text = sent[0]["title"] + sent[0]["body"]
    for leak in (CANARY, AMOUNT, URL_SECRET, "U111", "U222", "Main", "Joint",
                 "ghost.internal", "RuntimeError", "tok"):
        assert leak not in text


def test_summary_format_is_fixed():
    out = outcome.new_run_outcome()
    out.update(accounts_total=3, accounts_failed=1)
    outcome.record_failure(out, "account", "account_failed", 2)
    out["failures"].append({"stage": "account", "reason": f"forged {CANARY}", "ordinal": f"U{CANARY}"})
    out["dropped"] = 4
    body = notify.build_failure_summary(out, datetime(2026, 10, 8, 6, 5, tzinfo=timezone.utc))
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
    assert app.main() == 1
    assert calls == ["U111", "U222", "U333"] and len(sent) == 1
    assert URL_SECRET not in caplog.text


def test_timeout_is_logged_as_uncertain_without_retry(env, caplog):
    sent = spy_send(env, "timeout")
    accounts(env, {**ALL_OK, "U111": ({}, False)})
    assert app.main() == 1 and len(sent) == 1
    assert any("may still arrive; not retried" in r.message for r in caplog.records)


def test_real_hanging_worker_cannot_change_the_outcome(env, tmp_path, caplog):
    script = tmp_path / "hang.py"
    script.write_text("import time\ntime.sleep(60)\n")
    env.setattr(notify, "_notify_worker_argv", lambda: [sys.executable, str(script)])
    env.setenv("APPRISE_TIMEOUT", "1")
    calls = accounts(env, {**ALL_OK, "U222": ({}, False)})
    start = time.monotonic()
    assert app.main() == 1
    assert time.monotonic() - start < 10
    assert calls == ["U111", "U222", "U333"]
    assert any("timed out" in r.message for r in caplog.records)


@pytest.mark.parametrize("mode", ["missing", "empty", "conflict", "short"])
def test_dividend_structured_input_rejections_keep_trades_cash_exit_and_notify(env, mode):

    xml = structured_input_xml(mode)
    w = World(env, xml)
    bind_flex_report_to_query_account(env, xml)
    env.setattr(app, "ghost_get_existing_orders", lambda cfg: (set(), set(), positions()))
    sent = spy_send(env)
    assert app.main() == 0
    assert len(sent) == 1 and "dividend_rejected" in sent[0]["body"]
    assert len(w.cash_calls) == 3
    assert any(a["type"] == "BUY" for a in w.activities)
    dividends = [a for a in w.activities if a["type"] == "DIVIDEND"]
    if mode in ("missing", "empty"):
        assert dividends == []
    else:
        # Local rejections keep the other security's valid payment importable.
        assert len(dividends) == 3 and all(a["symbol"] == "PEP" for a in dividends)
        assert {a["comment"] for a in dividends} == {
            f"IBKR#v2#{account}:DIVIDEND:A2" for account in ("U111", "U222", "U333")}


def test_dividend_structured_input_other_failures_still_notify(env):

    xml = structured_input_xml("old")
    World(env, xml, cash_ok=False)
    bind_flex_report_to_query_account(env, xml)
    env.setattr(app, "ghost_get_existing_orders", lambda cfg: (set(), set(), positions()))
    sent = spy_send(env)
    assert app.main() == 1
    assert len(sent) == 1 and "Accounts failed: 3 of 3." in sent[0]["body"]


@pytest.mark.parametrize("price", [0.25, 0.26])
def test_historical_diagnostic_findings_preserve_success_and_notifications(env, caplog, price):
    env.setenv("DRY_RUN", "1")
    ids, comments, pos = read(env, [destination(unitPrice=price)])
    xml = report(divs=div_xml())
    World(env, xml)
    bind_flex_report_to_query_account(env, xml)
    env.setattr(app, "ghost_get_existing_orders", lambda cfg: (ids, comments, pos))
    sent = spy_send(env)
    for verb in ("post", "put", "patch", "delete"):
        env.setattr(requests, verb, lambda *a, **kw: pytest.fail("financial HTTP write"))
    caplog.set_level(logging.INFO)
    assert app.main() == 0 and len(sent) == 1
    assert "Historical dividends" in caplog.text


@pytest.mark.parametrize("dry", [True, False])
def test_historical_diagnostic_read_failure_keeps_exit_and_notification_contract(env, dry):
    env.setenv("DRY_RUN", "1" if dry else "0")
    sent = spy_send(env)
    env.setattr(app, "ghost_get_existing_orders", lambda cfg: (_ for _ in ()).throw(
        requests.ConnectionError("synthetic activity GET failure")))
    env.setattr(app, "process_account", lambda *a: pytest.fail("account after failed reader"))
    assert app.main() == 1
    assert len(sent) == 1
    assert sent[0]["title"] == notify.NOTIFY_TITLE


# --- TZ prerequisite: whole-run forced preview ---------------------------------

@pytest.mark.parametrize("tz", [None, "", "  ", "Not/AZone", "../etc/passwd", "Europe"])
def test_historical_diagnostic_preflight_invalid_tz_forces_whole_run_preview(env, caplog, tz):
    if tz is None:
        env.delenv("TZ")
    else:
        env.setenv("TZ", tz)
    sent = spy_send(env)
    seen = []
    env.setattr(app, "ghost_get_existing_orders", lambda cfg: (set(), set(), positions()))
    env.setattr(app, "process_account",
                lambda cfg, ibkr_id, *a: seen.append((ibkr_id, cfg["dry_run"])) or ({}, True))
    assert app.main() == 0
    assert seen == [("U111", True), ("U222", True), ("U333", True)]
    warnings = [r.getMessage() for r in caplog.records
                if r.levelname == "WARNING" and "forced to DRY_RUN" in r.getMessage()]
    assert len(warnings) == 1
    assert len(sent) == 1 and "forced DRY_RUN" in sent[0]["body"]
    assert sent[0]["body"].split(";")[0].endswith(("TZ is missing", "TZ is not a valid IANA timezone"))


def test_historical_diagnostic_preflight_forced_preview_failure_notification_names_reason(env):
    env.setenv("TZ", "Not/AZone")
    sent = spy_send(env)
    accounts(env, {**ALL_OK, "U222": ({}, False)})
    assert app.main() == 1
    assert len(sent) == 1
    assert "Accounts failed: 1 of 3" in sent[0]["body"]
    assert "TZ is not a valid IANA timezone" in sent[0]["body"]


def test_historical_diagnostic_preflight_valid_tz_keeps_live_run_silent(env, caplog):
    env.setenv("TZ", "Europe/Paris")
    sent = spy_send(env)
    seen = []
    env.setattr(app, "ghost_get_existing_orders", lambda cfg: (set(), set(), positions()))
    env.setattr(app, "process_account", lambda cfg, *a: seen.append(cfg["dry_run"]) or ({}, True))
    assert app.main() == 0
    assert seen == [False] * 3 and sent == []
    assert "forced to DRY_RUN" not in caplog.text


def test_historical_diagnostic_preflight_raw_dry_run_reports_timezone(env):
    env.delenv("TZ")
    env.setenv("DRY_RUN", "1")
    sent = spy_send(env)
    accounts(env, ALL_OK)
    assert app.main() == 0 and len(sent) == 1


def test_historical_diagnostic_actionable_blocks_join_notifications(env, caplog):
    env.setenv("DRY_RUN", "1")
    ids, comments, pos = read(env, [destination(comment="legacy", date="2026-07-17T00:00:00Z")])
    xml = report(divs=div_xml())
    World(env, xml)
    bind_flex_report_to_query_account(env, xml)
    env.setattr(app, "ghost_get_existing_orders", lambda cfg: (ids, comments, pos))
    sent = spy_send(env)
    caplog.set_level(logging.INFO)
    assert app.main() == 0 and len(sent) == 1
    assert "skipped by proximity" in caplog.text and "failed_checks=" in caplog.text


@pytest.mark.parametrize("mode", [None, "", "  ", "1", "true", "yes", "on", " YES ", "false", "invalid"])
@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize("configured", [False, True])
@pytest.mark.parametrize("tz", ["UTC", None, "Not/AZone"])
def test_dry_run_modes_notification_compatibility(env, mode, failed, configured, tz):
    if mode is None:
        env.delenv("DRY_RUN")
    else:
        env.setenv("DRY_RUN", mode)
    if tz is None:
        env.delenv("TZ")
    else:
        env.setenv("TZ", tz)
    if not configured:
        env.delenv("APPRISE_URLS")
    # Expiry and forced preview must share a failure dispatch or stay silent
    # during successful simulation.
    import base64
    payload = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + 86400}).encode()).decode()
    env.setenv("GHOST_TOKEN", f"header.{payload}.signature")
    calls = accounts(env, {**ALL_OK, "U111": ({}, not failed)})
    sent = spy_send(env)
    invalid = mode == "invalid"
    assert app.main() == int(failed or invalid)
    assert calls == ([] if invalid else ["U111", "U222", "U333"])
    should_notify = configured
    assert len(sent) == int(should_notify)
    if sent:
        title = notify.NOTIFY_TITLE if failed or invalid else (
            notify.TOKEN_EXPIRY_NOTIFY_TITLE if tz == "UTC" else notify.FORCED_PREVIEW_NOTIFY_TITLE)
        assert sent[0]["title"] == title
        if not invalid:
            assert "ghost_auth: token_expiring" in sent[0]["body"]
        if tz != "UTC" and not invalid:
            assert "forced DRY_RUN" in sent[0]["body"]


@pytest.mark.parametrize("mode", [None, "", "true", "invalid"])
@pytest.mark.parametrize("status", ["timeout", "failed", "unavailable", RuntimeError(URL_SECRET)])
def test_dry_run_modes_delivery_failure_keeps_exit(env, caplog, mode, status):
    if mode is None:
        env.delenv("DRY_RUN")
    else:
        env.setenv("DRY_RUN", mode)
    calls = accounts(env, {**ALL_OK, "U111": ({}, False)})
    sent = spy_send(env, status)
    assert app.main() == 1 and len(sent) == 1
    assert calls == ([] if mode == "invalid" else ["U111", "U222", "U333"])
    assert URL_SECRET not in caplog.text


@pytest.mark.parametrize("mode", [None, "", "true", "false"])
def test_operator_action_reminders_repeat_then_resolve(env, mode, caplog):
    if mode is None:
        env.delenv("DRY_RUN")
    else:
        env.setenv("DRY_RUN", mode)
    sent = spy_send(env)
    caplog.set_level(logging.INFO)
    for _ in range(2):
        out = outcome.new_run_outcome()
        outcome.record_action(out, "review_approval", "private-event")
        outcome.record_action(out, "review_approval", "private-event")
        app.finalize_run(out, 0)
    assert len(sent) == 2
    assert "review_approval (1)" in sent[0]["body"]
    assert "private-event" not in sent[0]["body"]
    app.finalize_run(outcome.new_run_outcome(), 0)
    assert len(sent) == 2
    assert "Notification result: not required" in caplog.text


def test_operator_action_summary_redacts_and_keeps_failure_priority(env):
    sent = spy_send(env)
    out = outcome.new_run_outcome()
    for reason in ("review_approval", "mapping_unverified", "dividend_check"):
        outcome.record_action(out, reason, CANARY + AMOUNT)
    outcome.record_failure(out, "account", "account_failed", 1)
    app.finalize_run(out, 1)
    assert len(sent) == 1 and sent[0]["title"] == notify.NOTIFY_TITLE
    assert all(reason in sent[0]["body"] for reason in out["actions"])
    assert CANARY not in sent[0]["body"] and AMOUNT not in sent[0]["body"]


@pytest.mark.parametrize("raw,status,expected", [
    (None, "sent", "disabled"), ("[]", "sent", "disabled"),
    ("invalid-SECRET", "sent", "invalid configuration"),
    (json.dumps(URLS), "sent", "sent"),
    (json.dumps(URLS), "failed", "failed"),
    (json.dumps(URLS), "timeout", "timeout, delivery unconfirmed"),
    (json.dumps(URLS), "invalid_destination", "invalid configuration"),
    (json.dumps(URLS), RuntimeError(URL_SECRET), "failed"),
])
def test_operator_action_delivery_explicit(env, caplog, raw, status, expected):
    caplog.set_level(logging.INFO)
    if raw is None:
        env.delenv("APPRISE_URLS")
    else:
        env.setenv("APPRISE_URLS", raw)
    sent = spy_send(env, status)
    out = outcome.new_run_outcome()
    outcome.record_action(out, "review_approval", "private")
    app.finalize_run(out, 0)
    assert f"Notification result: {expected}" in caplog.text
    assert len(sent) == int(raw == json.dumps(URLS))
    assert URL_SECRET not in caplog.text and "invalid-SECRET" not in caplog.text
    assert out["delivery"] == expected


@pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit])
def test_operator_action_delivery_interrupted(env, caplog, exc):
    sent = spy_send(env, exc())
    out = outcome.new_run_outcome()
    outcome.record_action(out, "review_approval", "private")
    with pytest.raises(exc):
        app.finalize_run(out, 0)
    assert len(sent) == 1 and "Notification result:" not in caplog.text


@pytest.mark.parametrize("mode", [None, "", "true", "false"])
def test_operator_action_prerequisite_timezone_in_simulation(env, mode):
    if mode is None:
        env.delenv("DRY_RUN")
    else:
        env.setenv("DRY_RUN", mode)
    env.delenv("TZ")
    sent = spy_send(env)
    accounts(env, ALL_OK)
    assert app.main() == 0 and len(sent) == 1
    assert "timezone_correction (1)" in sent[0]["body"]



@pytest.mark.parametrize("failed", [False, True])
def test_operator_action_integrated_cycles_keep_financial_requests_and_resolve(env, caplog, failed):
    from _sync_helpers import CFG, ACC, ISIN_KO, trade_xml
    from ghostfolio_ibkr_sync import corporate_actions as ca
    caplog.set_level(logging.INFO)
    sent = spy_send(env, "failed")
    xml = report(trade_xml("T1"), div_xml())
    world = World(env, xml)
    for resolved in (False, False, True):
        ids, comments, pos = read(env, [destination(unitPrice=0.25 if resolved else 0.26)])
        out = outcome.new_run_outcome()
        out["review_held"] = set() if resolved else {"IBKR#v2#U1:TRADE:T1"}
        out["deferred"] = set()
        if not resolved:
            outcome.record_action(out, "review_approval", "IBKR#v2#U1:TRADE:T1")
            ca.prepare_notifications(out, None, {"U1": {
                "account_held": False, "symbols": set(), "effective": {}, "dates": {}, "normalized": set(),
                "findings": {"private-event": {"held": False, "reasons": [],
                    "conclusions": {"history": "bounded_cost_dates_differ"}, "symbols": ["KO"]}}}})
            if failed:
                outcome.record_failure(out, "account", "account_failed", 1)
        cfg = {**CFG, "dry_run": True, "_corporate_outcome": out, "_review_holds": out["review_held"]}
        _, ok = app.process_account(cfg, "U1", "q1", "IBKR", {ISIN_KO: "KO"} if resolved else {},
                                    {"T1"}, comments, pos)
        assert ok
        app.finalize_run(out, int(failed and not resolved))
        assert world.activities == []
        if not resolved:
            assert {"review_approval", "mapping_unverified", "dividend_check", "corporate_action"} <= set(out["actions"])
            assert out["delivery"] == "failed"
        else:
            assert out["actions"] == {} and out["delivery"] == "not required"
    assert len(sent) == 2 and len(world.cash_calls) == 3
    assert all("U1" not in item["body"] and ISIN_KO not in item["body"] for item in sent)
    assert ("Cycle result: failure" if failed else "success with user action required") in caplog.text
