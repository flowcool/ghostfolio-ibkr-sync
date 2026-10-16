"""Offline tests: Apprise settings, the isolated worker and its parent lifecycle."""
import dataclasses
import io
import json
import os
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

import requests
import logging
from ghostfolio_ibkr_sync import config, notify
from ghostfolio_ibkr_sync.models import NotificationSettings

ROOT = Path(__file__).resolve().parents[1]
URL_SECRET = "CANARY-DEST-3b9e"          # synthetic credential inside a notify URL
SYNC_SECRET = "CANARY-SYNC-TOKEN-8d21"   # synthetic sync credential in the parent env
URLS = [f"json://user:{URL_SECRET}@notify.invalid/hook"]


@pytest.fixture
def notify_env(monkeypatch):
    for k in ("APPRISE_URLS", "APPRISE_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


# --- settings -----------------------------------------------------------------

@pytest.mark.parametrize("raw", [None, "", "   ", "[]", " [ ] "])
def test_blank_or_empty_list_disables_without_warning(notify_env, caplog, raw):
    if raw is not None:
        notify_env.setenv("APPRISE_URLS", raw)
    assert config.load_notification_config() is None
    assert caplog.records == []


def test_valid_list_with_default_timeout(notify_env):
    notify_env.setenv("APPRISE_URLS", json.dumps(URLS))
    assert config.load_notification_config() == {"urls": URLS, "timeout": 10}


@pytest.mark.parametrize("value,expected", [("1", 1), ("30", 30), (" 7 ", 7)])
def test_timeout_accepts_integers_from_1_to_30(notify_env, value, expected):
    notify_env.setenv("APPRISE_URLS", json.dumps(URLS))
    notify_env.setenv("APPRISE_TIMEOUT", value)
    assert config.load_notification_config()["timeout"] == expected


@pytest.mark.parametrize("urls,timeout", [
    (f"json://{URL_SECRET}", None),                      # not JSON
    (json.dumps({"url": URL_SECRET}), None),              # not a list
    (json.dumps([URL_SECRET, 3]), None),                  # non-string entry
    (json.dumps([URL_SECRET, " "]), None),                # blank entry
    (json.dumps([URL_SECRET] * 11), None),                # too many
    (json.dumps(["x" * 2049]), None),                     # too long
    (json.dumps(URLS), "0"), (json.dumps(URLS), "31"), (json.dumps(URLS), "-5"),
    (json.dumps(URLS), "1.5"), (json.dumps(URLS), "ten"), (json.dumps(URLS), "999"),
])
def test_invalid_settings_disable_delivery_with_a_fixed_warning(notify_env, caplog, urls, timeout):
    notify_env.setenv("APPRISE_URLS", urls)
    if timeout is not None:
        notify_env.setenv("APPRISE_TIMEOUT", timeout)
    assert config.load_notification_config() is None
    assert [r.levelname for r in caplog.records] == ["WARNING"]
    assert URL_SECRET not in caplog.text


def test_oversized_setting_is_rejected_before_parsing(notify_env, monkeypatch):
    notify_env.setenv("APPRISE_URLS", json.dumps(["x" * 100] * 400))
    monkeypatch.setattr(json, "loads", lambda *a: pytest.fail("must not parse"))
    assert config.load_notification_config() is None



def test_typed_settings_are_immutable_and_hide_urls(notify_env):
    notify_env.setenv("APPRISE_URLS", json.dumps(URLS))
    notify_env.setenv("APPRISE_TIMEOUT", "5")
    settings = config.load_notifications()
    assert settings == NotificationSettings(urls=tuple(URLS), timeout=5)
    assert URL_SECRET not in repr(settings)
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.timeout = 1


# --- worker (in process, fake apprise) ----------------------------------------

def run_worker(monkeypatch, payload, apprise_module):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(buffer=io.BytesIO(data)))
    monkeypatch.setitem(sys.modules, "apprise", apprise_module)
    try:
        return notify.notify_worker()
    finally:
        logging.disable(logging.NOTSET)


def fake_apprise(add=True, notify=True):
    sent = []

    class Apprise:  # mimics apprise.Apprise
        def __init__(self):
            self.count = 0

        def add(self, url):
            self.count += 1
            return add

        def __len__(self):
            return self.count

        def notify(self, title, body):
            if isinstance(notify, Exception):
                raise notify
            sent.append((title, body))
            return notify
    return types.SimpleNamespace(Apprise=Apprise, sent=sent)


GOOD = {"urls": URLS, "title": "t", "body": "b"}


@pytest.mark.parametrize("add,notify,code", [(True, True, 0), (True, False, 12), (False, True, 13),
                                             (True, RuntimeError(URL_SECRET), 12)])
def test_worker_exit_codes(monkeypatch, add, notify, code):
    fake = fake_apprise(add, notify)
    assert run_worker(monkeypatch, GOOD, fake) == code
    assert fake.sent == ([("t", "b")] if code == 0 else fake.sent)


def test_worker_reports_missing_dependency(monkeypatch):
    assert run_worker(monkeypatch, GOOD, None) == 11    # sys.modules None -> ImportError


@pytest.mark.parametrize("payload", [
    b"not json", b"[1]", {"urls": [], "title": "t", "body": "b"},
    {"urls": URL_SECRET, "title": "t", "body": "b"}, {"urls": [1], "title": "t", "body": "b"},
    {"urls": URLS, "body": "b"}, {"urls": URLS, "title": "t", "body": 3},
    b"{" + b" " * config.NOTIFY_PAYLOAD_MAX + b"}"])
def test_worker_rejects_malformed_or_oversized_payloads_before_importing_apprise(monkeypatch, payload):
    assert run_worker(monkeypatch, payload, fake_apprise()) == 10


def test_worker_mode_never_runs_the_sync(tmp_path):
    # The package is importable from the repository root here; the installed
    # `-I` form is proved against the image by scripts/check_container_runtime.sh.
    proc = subprocess.run([sys.executable, "-m", "ghostfolio_ibkr_sync", notify.NOTIFY_WORKER_FLAG],
                          input=b"not json", capture_output=True, timeout=30, cwd=ROOT,
                          env={"IBKR_TOKEN": "x"})
    assert proc.returncode == 10
    assert b"Starting IBKR" not in proc.stdout + proc.stderr


def test_default_worker_argv_is_fixed_and_carries_no_secret():
    argv = notify._notify_worker_argv()
    assert argv == [sys.executable, "-I", "-m", "ghostfolio_ibkr_sync", "--notify-worker"]


# --- parent lifecycle (real processes, synthetic workers) ----------------------

def use_worker(monkeypatch, tmp_path, code):
    script = tmp_path / "worker.py"
    script.write_text(code)
    monkeypatch.setattr(notify, "_notify_worker_argv", lambda: [sys.executable, str(script)])


def track_popen(monkeypatch):
    procs = []
    real = subprocess.Popen

    def popen(*a, **k):
        procs.append(real(*a, **k))
        return procs[-1]
    monkeypatch.setattr(notify.subprocess, "Popen", popen)
    return procs


def test_hanging_worker_is_killed_and_reaped_at_the_deadline(monkeypatch, tmp_path):
    use_worker(monkeypatch, tmp_path, "import time\ntime.sleep(60)\n")
    procs = track_popen(monkeypatch)
    start = time.monotonic()
    assert notify.send_notification({"urls": URLS, "timeout": 1}, "t", "b") == "timeout"
    assert time.monotonic() - start < 10
    assert len(procs) == 1 and procs[0].returncode is not None   # reaped


def test_worker_that_ignores_stdin_and_hangs_in_import_still_times_out(monkeypatch, tmp_path):
    use_worker(monkeypatch, tmp_path, "while True:\n    pass\n")
    assert notify.send_notification({"urls": URLS, "timeout": 1}, "t", "b") == "timeout"


def test_worker_output_is_discarded(monkeypatch, tmp_path, capfd):
    use_worker(monkeypatch, tmp_path,
               "import sys\ndata = sys.stdin.read()\nprint(data)\nprint(data, file=sys.stderr)\n")
    assert notify.send_notification({"urls": URLS, "timeout": 10}, "t", "b") == "sent"
    out, err = capfd.readouterr()
    assert URL_SECRET not in out + err


def test_worker_gets_urls_on_stdin_and_only_allowlisted_environment(monkeypatch, tmp_path):
    dump = tmp_path / "seen.json"
    use_worker(monkeypatch, tmp_path,
               "import json, os, sys\n"
               f"json.dump({{'env': dict(os.environ), 'stdin': sys.stdin.read(), 'argv': sys.argv}}, "
               f"open({str(dump)!r}, 'w'))\n")
    for k, v in {"IBKR_TOKEN": SYNC_SECRET, "GHOST_TOKEN": SYNC_SECRET,
                 "GHOST_ACCESS_TOKEN": SYNC_SECRET, "APPRISE_URLS": json.dumps(URLS),
                 "PYTHONPATH": "/evil", "HTTPS_PROXY": "http://proxy:3128"}.items():
        monkeypatch.setenv(k, v)
    assert notify.send_notification({"urls": URLS, "timeout": 10}, "t", "b") == "sent"
    seen = json.loads(dump.read_text())
    assert set(seen["env"]) <= set(notify.NOTIFY_ENV_ALLOWLIST) | {"LC_CTYPE", "__CF_USER_TEXT_ENCODING"}
    assert seen["env"].get("HTTPS_PROXY") == "http://proxy:3128"
    assert SYNC_SECRET not in json.dumps(seen["env"]) and URL_SECRET not in json.dumps(seen["env"])
    assert json.loads(seen["stdin"]) == {"urls": URLS, "title": "t", "body": "b"}
    assert URL_SECRET not in " ".join(seen["argv"])


@pytest.mark.parametrize("exit_code,status", [(0, "sent"), (10, "invalid_payload"), (11, "unavailable"),
                                              (12, "failed"), (13, "invalid_destination"),
                                              (1, "failed"), (2, "failed"), (9, "failed")])
def test_worker_exit_code_maps_to_a_fixed_status(monkeypatch, tmp_path, exit_code, status):
    use_worker(monkeypatch, tmp_path, f"import sys\nsys.stdin.read()\nsys.exit({exit_code})\n")
    assert notify.send_notification({"urls": URLS, "timeout": 10}, "t", "b") == status


def test_oversized_payload_spawns_nothing(monkeypatch):
    monkeypatch.setattr(notify.subprocess, "Popen", lambda *a, **k: pytest.fail("no spawn"))
    body = "x" * config.NOTIFY_PAYLOAD_MAX
    assert notify.send_notification({"urls": URLS, "timeout": 10}, "t", body) == "payload_too_large"


def test_spawn_failure_is_a_status_not_an_exception(monkeypatch):
    def boom(*a, **k):
        raise OSError(URL_SECRET)
    monkeypatch.setattr(notify.subprocess, "Popen", boom)
    assert notify.send_notification({"urls": URLS, "timeout": 10}, "t", "b") == "spawn_failed"


@pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit])
def test_interrupt_while_waiting_kills_the_worker_and_propagates(monkeypatch, tmp_path, exc):
    use_worker(monkeypatch, tmp_path, "import time\ntime.sleep(60)\n")
    procs = []

    class Interrupted(subprocess.Popen):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            procs.append(self)

        def communicate(self, *a, **k):
            raise exc
    monkeypatch.setattr(notify.subprocess, "Popen", Interrupted)
    with pytest.raises(exc):
        notify.send_notification({"urls": URLS, "timeout": 10}, "t", "b")
    assert procs[0].returncode is not None                       # killed and reaped


def run_real_apprise_worker(monkeypatch, urls, http):
    # Real Apprise import, parsing and send; only its HTTP transport is mocked
    calls = []

    def request(*a, **k):
        calls.append(k.get("url", a[1] if len(a) > 1 else None))
        return http()
    monkeypatch.setattr(requests, "request", request)
    data = json.dumps({"urls": urls, "title": "t", "body": "b"}).encode()
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(buffer=io.BytesIO(data)))
    try:
        return notify.notify_worker(), calls
    finally:
        logging.disable(logging.NOTSET)


def ok_response():
    resp = requests.Response()
    resp.status_code = 200
    return resp


def test_real_apprise_reports_an_unreachable_destination(monkeypatch):
    def unreachable():
        raise requests.ConnectionError("unreachable")
    code, calls = run_real_apprise_worker(monkeypatch, ["json://notify.invalid/hook"], unreachable)
    assert code == 12 and len(calls) == 1


def test_real_apprise_reports_a_delivered_notification(monkeypatch):
    code, calls = run_real_apprise_worker(monkeypatch, ["json://notify.invalid/hook"], ok_response)
    assert code == 0 and len(calls) == 1


def test_real_apprise_bounds_destinations_expanded_from_one_entry(monkeypatch):
    entry = " ".join(f"json://notify.invalid/{i}" for i in range(config.APPRISE_URLS_MAX + 1))
    code, calls = run_real_apprise_worker(monkeypatch, [entry], ok_response)
    assert code == 13 and calls == []


def test_send_notification_spawns_the_production_argv_without_a_script_guard(monkeypatch):
    spawned = []

    class Worker:
        returncode = 0
        pid = 0

        def __init__(self, argv, **kwargs):
            spawned.append((argv, kwargs))

        def communicate(self, *a, **k):
            return b"", b""

        def poll(self):
            return 0

        def wait(self):
            return 0
    monkeypatch.setattr(notify.subprocess, "Popen", Worker)
    assert notify.send_notification({"urls": URLS, "timeout": 10}, "t", "b") == "sent"
    assert [argv for argv, _ in spawned] == [
        [sys.executable, "-I", "-m", "ghostfolio_ibkr_sync", "--notify-worker"]]
