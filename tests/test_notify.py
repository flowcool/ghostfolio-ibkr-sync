"""Offline tests: Apprise settings, the isolated worker and its parent lifecycle."""
import io
import json
import subprocess
import sys
import time
import types

import pytest

import ibkr_to_ghostfolio as m

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
    assert m.load_notification_config() is None
    assert caplog.records == []


def test_valid_list_with_default_timeout(notify_env):
    notify_env.setenv("APPRISE_URLS", json.dumps(URLS))
    assert m.load_notification_config() == {"urls": URLS, "timeout": 10}


@pytest.mark.parametrize("value,expected", [("1", 1), ("30", 30), (" 7 ", 7)])
def test_timeout_accepts_integers_from_1_to_30(notify_env, value, expected):
    notify_env.setenv("APPRISE_URLS", json.dumps(URLS))
    notify_env.setenv("APPRISE_TIMEOUT", value)
    assert m.load_notification_config()["timeout"] == expected


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
    assert m.load_notification_config() is None
    assert [r.levelname for r in caplog.records] == ["WARNING"]
    assert URL_SECRET not in caplog.text


def test_oversized_setting_is_rejected_before_parsing(notify_env, monkeypatch):
    notify_env.setenv("APPRISE_URLS", json.dumps(["x" * 100] * 400))
    monkeypatch.setattr(m.json, "loads", lambda *a: pytest.fail("must not parse"))
    assert m.load_notification_config() is None


# --- worker (in process, fake apprise) ----------------------------------------

def run_worker(monkeypatch, payload, apprise_module):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(buffer=io.BytesIO(data)))
    monkeypatch.setitem(sys.modules, "apprise", apprise_module)
    try:
        return m.notify_worker()
    finally:
        m.logging.disable(m.logging.NOTSET)


def fake_apprise(add=True, notify=True):
    sent = []

    class Apprise:  # mimics apprise.Apprise
        def add(self, url):
            return add

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
    b"{" + b" " * m.NOTIFY_PAYLOAD_MAX + b"}"])
def test_worker_rejects_malformed_or_oversized_payloads_before_importing_apprise(monkeypatch, payload):
    assert run_worker(monkeypatch, payload, fake_apprise()) == 10


def test_worker_mode_never_runs_the_sync(tmp_path):
    proc = subprocess.run([sys.executable, "-I", m.__file__, m.NOTIFY_WORKER_FLAG],
                          input=b"not json", capture_output=True, timeout=30,
                          env={"IBKR_TOKEN": "x"})
    assert proc.returncode == 10
    assert b"Starting IBKR" not in proc.stdout + proc.stderr


def test_default_worker_argv_is_fixed_and_carries_no_secret():
    argv = m._notify_worker_argv()
    assert argv[1:] == ["-I", m.__file__, m.NOTIFY_WORKER_FLAG]


# --- parent lifecycle (real processes, synthetic workers) ----------------------

def use_worker(monkeypatch, tmp_path, code):
    script = tmp_path / "worker.py"
    script.write_text(code)
    monkeypatch.setattr(m, "_notify_worker_argv", lambda: [sys.executable, str(script)])


def track_popen(monkeypatch):
    procs = []
    real = subprocess.Popen

    def popen(*a, **k):
        procs.append(real(*a, **k))
        return procs[-1]
    monkeypatch.setattr(m.subprocess, "Popen", popen)
    return procs


def test_hanging_worker_is_killed_and_reaped_at_the_deadline(monkeypatch, tmp_path):
    use_worker(monkeypatch, tmp_path, "import time\ntime.sleep(60)\n")
    procs = track_popen(monkeypatch)
    start = time.monotonic()
    assert m.send_notification({"urls": URLS, "timeout": 1}, "t", "b") == "timeout"
    assert time.monotonic() - start < 10
    assert len(procs) == 1 and procs[0].returncode is not None   # reaped


def test_worker_that_ignores_stdin_and_hangs_in_import_still_times_out(monkeypatch, tmp_path):
    use_worker(monkeypatch, tmp_path, "while True:\n    pass\n")
    assert m.send_notification({"urls": URLS, "timeout": 1}, "t", "b") == "timeout"


def test_worker_output_is_discarded(monkeypatch, tmp_path, capfd):
    use_worker(monkeypatch, tmp_path,
               "import sys\ndata = sys.stdin.read()\nprint(data)\nprint(data, file=sys.stderr)\n")
    assert m.send_notification({"urls": URLS, "timeout": 10}, "t", "b") == "sent"
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
    assert m.send_notification({"urls": URLS, "timeout": 10}, "t", "b") == "sent"
    seen = json.loads(dump.read_text())
    assert set(seen["env"]) <= set(m.NOTIFY_ENV_ALLOWLIST) | {"LC_CTYPE", "__CF_USER_TEXT_ENCODING"}
    assert seen["env"].get("HTTPS_PROXY") == "http://proxy:3128"
    assert SYNC_SECRET not in json.dumps(seen["env"]) and URL_SECRET not in json.dumps(seen["env"])
    assert json.loads(seen["stdin"]) == {"urls": URLS, "title": "t", "body": "b"}
    assert URL_SECRET not in " ".join(seen["argv"])


@pytest.mark.parametrize("exit_code,status", [(0, "sent"), (10, "invalid_payload"), (11, "unavailable"),
                                              (12, "failed"), (13, "invalid_destination"),
                                              (1, "failed"), (2, "failed"), (9, "failed")])
def test_worker_exit_code_maps_to_a_fixed_status(monkeypatch, tmp_path, exit_code, status):
    use_worker(monkeypatch, tmp_path, f"import sys\nsys.stdin.read()\nsys.exit({exit_code})\n")
    assert m.send_notification({"urls": URLS, "timeout": 10}, "t", "b") == status


def test_oversized_payload_spawns_nothing(monkeypatch):
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **k: pytest.fail("no spawn"))
    body = "x" * m.NOTIFY_PAYLOAD_MAX
    assert m.send_notification({"urls": URLS, "timeout": 10}, "t", body) == "payload_too_large"


def test_spawn_failure_is_a_status_not_an_exception(monkeypatch):
    def boom(*a, **k):
        raise OSError(URL_SECRET)
    monkeypatch.setattr(m.subprocess, "Popen", boom)
    assert m.send_notification({"urls": URLS, "timeout": 10}, "t", "b") == "spawn_failed"


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
    monkeypatch.setattr(m.subprocess, "Popen", Interrupted)
    with pytest.raises(exc):
        m.send_notification({"urls": URLS, "timeout": 10}, "t", "b")
    assert procs[0].returncode is not None                       # killed and reaped


def test_real_worker_with_real_apprise_reports_an_unreachable_destination(monkeypatch):
    # json:// to a closed local port: real import, setup and send, no network egress
    status = m.send_notification({"urls": ["json://127.0.0.1:9/hook"], "timeout": 20}, "t", "b")
    assert status == "failed"


def test_script_read_from_stdin_cannot_spawn_a_worker(monkeypatch):
    # `python - < ibkr_to_ghostfolio.py` sets __file__ to "<stdin>"
    monkeypatch.setattr(m, "__file__", "<stdin>")
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **k: pytest.fail("no spawn"))
    assert m.send_notification({"urls": URLS, "timeout": 10}, "t", "b") == "spawn_failed"

