"""Offline legacy JWT reminders; expiry is advisory and never authentication."""
import base64
import json
import logging

import pytest

import ibkr_to_ghostfolio as m

NOW = 1800000000
DAY = 86400
SECRET = "CANARY-JWT-CLAIM-57ea"


def jwt(payload):
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


@pytest.fixture
def env(monkeypatch):
    for key, value in {"IBKR_TOKEN": "synthetic", "IBKR_ACCOUNT_IDS": "U1,U2",
                       "IBKR_QUERY_IDS": "q1,q2", "GHOST_TOKEN": jwt({"exp": NOW + 3 * DAY,
                                                                          "sub": SECRET}),
                       "GHOST_HOST": "http://ghost.invalid", "GHOST_ACCOUNT_NAMES": "One,Two",
                       "MAPPING_FILE": ""}.items():
        monkeypatch.setenv(key, value)
    for key in ("GHOST_ACCESS_TOKEN", "GHOST_TOKEN_EXPIRY_WARNING_DAYS", "DRY_RUN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(m.time, "time", lambda: NOW)
    monkeypatch.setattr(m, "ghost_get_existing_orders", lambda cfg: (set(), set(), {}))
    monkeypatch.setattr(m, "process_account", lambda *args: ({}, True))
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: pytest.fail("no real HTTP"))
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: pytest.fail("no real HTTP"))
    return monkeypatch


@pytest.mark.parametrize("seconds,expected", [(-DAY, 0), (0, 0), (1, 1),
                                             (DAY + 1, 2), (14 * DAY, 14),
                                             (14 * DAY + 1, None), (90 * DAY, None)])
def test_expiry_window_and_day_rounding(env, seconds, expected):
    cfg = {"ghost_token": jwt({"exp": NOW + seconds})}
    assert m.legacy_token_expiry_days(cfg, now=NOW) == expected


@pytest.mark.parametrize("payload", [{}, [], None, {"exp": None}, {"exp": True},
                                     {"exp": "1800000001"}, {"exp": []},
                                     {"exp": float("nan")}, {"exp": float("inf")},
                                     {"exp": 10 ** 1000}])
def test_unusable_claims_are_debug_only_and_do_not_leak(env, caplog, payload):
    token = jwt(payload)
    caplog.set_level(logging.DEBUG)
    assert m.legacy_token_expiry_days({"ghost_token": token}) is None
    assert "reminder skipped" in caplog.text
    assert all(record.levelno == logging.DEBUG for record in caplog.records)
    assert token not in caplog.text


@pytest.mark.parametrize("token", ["not-jwt", "a.b", "a.b.c.d", "a.@@@.c", "a.e30.c",
                                   "a._w.c", "a.eA.c", ".e30.", "a." + "x" * 17000 + ".c"])
def test_malformed_tokens_never_fail_or_log_token(env, caplog, token):
    caplog.set_level(logging.DEBUG)
    assert m.legacy_token_expiry_days({"ghost_token": token}) is None
    assert "reminder skipped" in caplog.text
    assert token not in caplog.text


@pytest.mark.parametrize("value,expected", [("1", None), ("3", 3), (" 30 ", 3),
                                          ("0", None), ("365", 3)])
def test_configured_threshold(env, value, expected):
    env.setenv("GHOST_TOKEN_EXPIRY_WARNING_DAYS", value)
    assert m.legacy_token_expiry_days(m.load_config()) == expected


@pytest.mark.parametrize("value", ["", "-1", "14.5", "366", "999999", SECRET])
def test_invalid_threshold_uses_default_without_logging_value(env, caplog, value):
    env.setenv("GHOST_TOKEN_EXPIRY_WARNING_DAYS", value)
    assert m.legacy_token_expiry_days(m.load_config()) == 3
    assert "invalid; using 14 days" in caplog.text
    assert SECRET not in caplog.text


def test_access_mode_skips_token_and_threshold_inspection(env, caplog):
    env.setenv("GHOST_TOKEN_EXPIRY_WARNING_DAYS", SECRET)
    cfg = {"ghost_access_token": SECRET, "ghost_token": jwt({"exp": NOW + DAY})}
    assert m.legacy_token_expiry_days(cfg) is None
    assert caplog.text == ""


def notifications(env, status="sent"):
    env.setenv("APPRISE_URLS", '["json://notify.invalid/hook"]')
    sent = []

    def send(settings, title, body):
        sent.append((title, body))
        if isinstance(status, Exception):
            raise status
        return status
    env.setattr(m, "send_notification", send)
    return sent


def test_success_notifies_once_after_both_accounts_and_preserves_exit(env, caplog):
    events = []
    env.setattr(m, "process_account", lambda cfg, account, *args: (events.append(account) or {}, True))
    sent = notifications(env)
    assert m.main() == 0
    assert events == ["U1", "U2"]
    assert len(sent) == 1 and sent[0][0] == m.TOKEN_EXPIRY_NOTIFY_TITLE
    assert "ghost_auth: token_expiring (days remaining: 3)" in sent[0][1]
    assert "expires in 3 day(s)" in caplog.text
    for leak in (SECRET, m.os.environ["GHOST_TOKEN"], "U1", "ghost.invalid"):
        assert leak not in sent[0][1]
    assert SECRET not in caplog.text and m.os.environ["GHOST_TOKEN"] not in caplog.text


def test_expired_token_is_advisory_and_server_still_decides(env, caplog):
    env.setenv("GHOST_TOKEN", jwt({"exp": NOW - DAY}))
    sent = notifications(env)
    assert m.main() == 0 and len(sent) == 1
    assert "has expired" in caplog.text and "days remaining: 0" in sent[0][1]


def test_rejected_token_and_reminder_share_one_failure_notification(env):
    sent = notifications(env)
    response = m.requests.Response()
    response.status_code = 401

    def rejected(cfg):
        raise m.requests.HTTPError("synthetic rejection", response=response)
    env.setattr(m, "ghost_get_existing_orders", rejected)
    assert m.main() == 1 and len(sent) == 1
    assert sent[0][0] == m.NOTIFY_TITLE
    assert "ghost_startup: token_rejected" in sent[0][1]
    assert "ghost_auth: token_expiring" in sent[0][1]


@pytest.mark.parametrize("status", ["timeout", "failed", "unavailable", RuntimeError(SECRET)])
def test_reminder_delivery_problem_does_not_fail_sync_or_leak(env, caplog, status):
    sent = notifications(env, status)
    assert m.main() == 0 and len(sent) == 1
    assert SECRET not in caplog.text


def test_dry_run_warns_but_never_notifies(env, caplog):
    env.setenv("DRY_RUN", "1")
    sent = notifications(env)
    assert m.main() == 0 and sent == []
    assert "expires in 3 day(s)" in caplog.text


def test_without_apprise_warning_still_appears(env, caplog):
    env.setattr(m, "send_notification", lambda *a: pytest.fail("notifications are off"))
    assert m.main() == 0 and "expires in 3 day(s)" in caplog.text


def test_access_mode_has_no_reminder_even_for_short_lived_exchanged_jwt(env, caplog):
    sent = notifications(env)
    env.delenv("GHOST_TOKEN")
    env.setenv("GHOST_ACCESS_TOKEN", SECRET)
    env.setattr(m, "ghost_exchange_access_token", lambda *a: jwt({"exp": NOW + DAY}))
    assert m.main() == 0 and sent == []
    assert "Legacy GHOST_TOKEN" not in caplog.text


def test_reminder_is_run_local_and_multiple_runs_can_repeat_it(env):
    sent = notifications(env)
    assert m.main() == 0 and m.main() == 0 and len(sent) == 2
    env.setenv("GHOST_TOKEN", jwt({"exp": NOW + 100 * DAY}))
    assert m.main() == 0 and len(sent) == 2


def test_interrupted_run_does_not_send_reminder(env):
    sent = notifications(env)

    def interrupted(*args):
        raise KeyboardInterrupt
    env.setattr(m, "process_account", interrupted)
    with pytest.raises(KeyboardInterrupt):
        m.main()
    assert sent == []
