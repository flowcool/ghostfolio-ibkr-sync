"""Offline grouped action reminders with private state and a controlled clock."""

import json
import os
from pathlib import Path

import pytest

from ghostfolio_ibkr_sync import action_notifications as reminders
from ghostfolio_ibkr_sync import activity_review as review
from ghostfolio_ibkr_sync import app, corporate_actions as ca
from ghostfolio_ibkr_sync.outcome import new_run_outcome, record_action, record_failure


@pytest.fixture
def delivery(monkeypatch):
    calls = []
    clock = [1_800_000_000]
    monkeypatch.setattr(reminders.time, "time", lambda: clock[0])
    monkeypatch.setenv("APPRISE_URLS", json.dumps(["json://secret@notify.invalid/hook"]))
    monkeypatch.setattr(app, "send_notification", lambda *args: calls.append(args) or "sent")
    return calls, clock


def cycle(groups=None, *, code=0):
    out = new_run_outcome()
    for reason, count in (groups or {}).items():
        for event in range(count):
            record_action(out, reason, f"PRIVATE-EVENT-{event}-123456.78")
    if code:
        record_failure(out, "account", "account_failed", 1)
    app.finalize_run(out, code)
    return out


def state_path():
    return Path(os.environ["CORPORATE_ACTION_STATE_FILE"] + ".required-actions.yaml")


def test_unchanged_then_exact_seven_day_reminder(delivery, caplog):
    calls, clock = delivery
    groups = {"review_approval": 144, "mapping_unverified": 2}
    assert cycle(groups)["delivery"] == "sent"
    saved = state_path().read_bytes()
    clock[0] += reminders.REMINDER_SECONDS - 1
    assert cycle(groups)["delivery"] == "not required"
    assert state_path().read_bytes() == saved
    assert len(calls) == 1
    assert "PRIVATE-EVENT" in caplog.text  # Private per-event proof is retained.
    clock[0] += 1
    assert cycle(groups)["delivery"] == "sent"
    assert len(calls) == 2
    assert "review_approval (144)" in calls[1][2]
    assert "PRIVATE-EVENT" not in calls[1][2] and "123456.78" not in calls[1][2]
    assert state_path().stat().st_mode & 0o777 == 0o600


def test_changes_new_reason_count_up_down_and_all_clear(delivery):
    calls, _ = delivery
    for groups in ({"review_approval": 2}, {"review_approval": 3},
                   {"review_approval": 1}, {"review_approval": 1, "mapping_unverified": 1},
                   {"mapping_unverified": 1}, {}):
        assert cycle(groups)["delivery"] == "sent"
    assert len(calls) == 6
    assert "review_approval (0): resolved" in calls[-2][2]
    assert "mapping_unverified (0): resolved" in calls[-1][2]
    assert cycle()["delivery"] == "not required"
    assert len(calls) == 6


def test_same_count_membership_changes_do_not_change_fingerprint(delivery):
    calls, _ = delivery
    cycle({"review_approval": 1})
    out = new_run_outcome()
    record_action(out, "review_approval", "another-private-event")
    app.finalize_run(out, 0)
    assert len(calls) == 1 and out["delivery"] == "not required"


@pytest.mark.parametrize("status", ["failed", "timeout", RuntimeError("secret")])
def test_unconfirmed_send_keeps_snapshot_and_reminder_due(delivery, monkeypatch, status):
    calls, clock = delivery
    groups = {"review_approval": 1}
    cycle(groups)
    original = state_path().read_bytes()
    clock[0] += reminders.REMINDER_SECONDS
    def send(*args):
        calls.append(args)
        if isinstance(status, Exception):
            raise status
        return status
    monkeypatch.setattr(app, "send_notification", send)
    cycle(groups)
    cycle(groups)
    assert len(calls) == 3 and state_path().read_bytes() == original


def test_failure_stays_immediate_and_never_certifies_resolution(delivery):
    calls, _ = delivery
    groups = {"review_approval": 2}
    cycle(groups)
    saved = state_path().read_bytes()
    cycle(code=1)
    cycle(groups, code=1)
    assert len(calls) == 3
    assert all(call[1] == "ghostfolio-ibkr-sync: run failed" for call in calls[1:])
    assert state_path().read_bytes() == saved
    assert cycle(groups)["delivery"] == "not required"


def test_clock_rollback_and_context_change_remain_eligible(delivery, monkeypatch):
    calls, clock = delivery
    groups = {"review_approval": 1}
    cycle(groups)
    clock[0] -= 1
    cycle(groups)
    monkeypatch.setenv("GHOST_HOST", "http://different.invalid")
    cycle(groups)
    assert len(calls) == 3


@pytest.mark.parametrize("case", ["missing", "corrupt", "symlink", "public", "write_failed"])
def test_unavailable_state_does_not_suppress_actions(delivery, monkeypatch, tmp_path, case):
    calls, _ = delivery
    groups = {"review_approval": 1}
    cycle(groups)
    path = state_path()
    if case == "missing":
        path.unlink()
    elif case == "corrupt":
        path.write_text("broken: [")
    elif case == "symlink":
        target = tmp_path / "protected"
        path.rename(target)
        path.symlink_to(target)
        saved = target.read_bytes()
    elif case == "public":
        path.chmod(0o644)
    else:
        path.unlink()
        monkeypatch.setattr(reminders, "atomic_yaml", lambda *args: (_ for _ in ()).throw(OSError()))
    cycle(groups)
    assert len(calls) == 2
    if case == "symlink":
        assert target.read_bytes() == saved and path.is_symlink()
    if case == "corrupt":
        reminders.delivery_document(path.read_bytes())  # A confirmed send repairs only delivery state.


def test_generation_drift_is_not_overwritten(delivery):
    cycle({"review_approval": 1})
    out = new_run_outcome()
    record_action(out, "review_approval", "private")
    filename = os.environ["CORPORATE_ACTION_STATE_FILE"]
    plan = reminders.plan_action_notification(out, filename, "a" * 64)
    state_path().write_bytes(state_path().read_bytes() + b"\n")
    changed = state_path().read_bytes()
    assert not reminders.confirm_action_notification(plan)
    assert state_path().read_bytes() == changed


def test_delivery_state_cannot_replace_a_configured_input(delivery, monkeypatch):
    calls, _ = delivery
    path = state_path()
    path.write_text("private mapping input")
    path.chmod(0o600)
    monkeypatch.setenv("MAPPING_FILE", str(path))
    cycle({"review_approval": 1})
    assert len(calls) == 1 and path.read_text() == "private mapping input"


@pytest.mark.parametrize("qualification", [None, (1, 0)])
@pytest.mark.parametrize("authority", ["manual", "profile"])
def test_budget_or_qualification_deferred_approvals_never_notify(delivery, monkeypatch,
                                                               qualification, authority):
    calls, _ = delivery
    monkeypatch.setattr(review, "QUALIFIED_EXECUTION", qualification)
    out = new_run_outcome()
    proposals = {str(i): {"source event": f"private-{i}", "actionable": True,
                         "approve": "yes" if authority == "manual" else None,
                         "automatic eligible": authority == "profile",
                         "execution path": "normal run", "status": "automatic work deferred"}
                 for i in range(144)}
    review.report_review_outcome({"path": "private.yaml"}, {"_corporate_outcome": out},
                                 proposals, {item["source event"] for item in proposals.values()}, set())
    assert out["actions"] == {} and len(out["deferred"]) == 144
    app.finalize_run(out, 0)
    assert calls == [] and out["delivery"] == "not required"


def test_unchanged_corporate_action_does_not_bypass_grouped_schedule(delivery):
    calls, _ = delivery
    decision = {"account_held": True, "findings": {}}
    for _ in range(2):
        out = new_run_outcome()
        ca.prepare_notifications(out, os.environ["CORPORATE_ACTION_STATE_FILE"], {"private": decision})
        app.finalize_run(out, 0)
    assert len(calls) == 1
    # The grouped send must also retain the corporate delivery proof needed
    # to recognize a later verified resumption.
    out = new_run_outcome()
    ca.prepare_notifications(out, os.environ["CORPORATE_ACTION_STATE_FILE"],
                             {"private": {"account_held": False, "findings": {}}})
    assert out["corporate_notification"]["counts"]["resumptions"] == 1
    app.finalize_run(out, 0)
    assert len(calls) == 2 and "resumptions (1)" in calls[-1][2]
