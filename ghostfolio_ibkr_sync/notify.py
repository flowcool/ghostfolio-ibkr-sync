"""Failure notifications: summaries and the isolated Apprise worker process."""

import json
import logging
import os
import signal
import subprocess
import sys
from datetime import UTC, datetime

from ghostfolio_ibkr_sync.config import (
    APPRISE_URLS_MAX,
    NOTIFY_PAYLOAD_MAX,
    NotificationConfigDict,
)
from ghostfolio_ibkr_sync.outcome import OUTCOME_REASONS, RunOutcome

NOTIFY_WORKER_FLAG = "--notify-worker"
# The worker inherits only what Apprise needs to reach a destination: never the
# IBKR or Ghostfolio credentials.
NOTIFY_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR",
                        "REQUESTS_CA_BUNDLE", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                        "http_proxy", "https_proxy", "no_proxy")
# Worker exit code -> delivery status reported by send_notification.  Kept clear
# of the interpreter's own codes (1 uncaught error, 2 cannot open the script).
NOTIFY_EXIT_STATUS = {0: "sent", 10: "invalid_payload", 11: "unavailable", 12: "failed",
                      13: "invalid_destination"}

# Script the worker re-runs; the legacy launcher sets it to its own __file__
# until task 4.2 switches the worker to the installed package.
WORKER_SCRIPT = ""


def notify_worker() -> int:
    """Worker process entry: deliver one notification read from stdin.

    Never runs the sync.  Apprise is imported here only, so the sync never
    loads it.  Exit codes: see NOTIFY_EXIT_STATUS.
    """
    logging.disable(logging.CRITICAL)
    raw = sys.stdin.buffer.read(NOTIFY_PAYLOAD_MAX + 1)
    try:
        payload = json.loads(raw) if len(raw) <= NOTIFY_PAYLOAD_MAX else None
    except ValueError:
        payload = None
    if (not isinstance(payload, dict)
            or not isinstance(payload.get("urls"), list) or not payload["urls"]
            or not all(isinstance(u, str) for u in payload["urls"])
            or not isinstance(payload.get("title"), str)
            or not isinstance(payload.get("body"), str)):
        return 10
    try:
        import apprise
    except ImportError:
        return 11
    notifier = apprise.Apprise()
    # One entry may hold several space- or comma-separated URLs: bound the
    # destinations Apprise actually expanded, not the list entries
    if (not all(notifier.add(url) for url in payload["urls"])
            or len(notifier) > APPRISE_URLS_MAX):
        return 13
    try:
        sent = notifier.notify(title=payload["title"], body=payload["body"])
    except Exception:
        return 12
    return 0 if sent else 12


def _notify_worker_argv() -> list[str]:
    # -I: ignore PYTHON* variables, user site-packages and the current directory
    return [sys.executable, "-I", os.path.abspath(WORKER_SCRIPT), NOTIFY_WORKER_FLAG]


def _stop_worker(proc: subprocess.Popen[bytes]) -> None:
    """Kill the worker (and anything it started) if still running, then reap it."""
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
    proc.wait()


def send_notification(settings: NotificationConfigDict, title: str, body: str) -> str:
    """Deliver one notification through an isolated Apprise worker.

    Apprise plugins can block past any library timeout and can print their
    destination URL.  So the URLs travel on stdin, the worker gets an
    allowlisted environment and no output channel, and one deadline covers its
    whole life (import, setup, send, exit); on expiry it is killed and reaped.
    No retry: a timed-out send may still have been delivered.  Returns a fixed
    status string; SystemExit/KeyboardInterrupt propagate after the kill.
    """
    payload = json.dumps({"urls": settings["urls"], "title": title, "body": body}).encode()
    if len(payload) > NOTIFY_PAYLOAD_MAX:
        return "payload_too_large"
    # The worker re-runs this file: impossible when the script came from stdin
    if not os.path.isfile(os.path.abspath(WORKER_SCRIPT)):
        return "spawn_failed"
    env = {k: os.environ[k] for k in NOTIFY_ENV_ALLOWLIST if k in os.environ}
    try:
        proc = subprocess.Popen(_notify_worker_argv(), stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env=env, close_fds=True, start_new_session=True)
    except (OSError, ValueError):
        return "spawn_failed"
    try:
        proc.communicate(payload, timeout=settings["timeout"])
    except subprocess.TimeoutExpired:
        return "timeout"
    except Exception:
        return "failed"
    finally:
        _stop_worker(proc)
    return NOTIFY_EXIT_STATUS.get(proc.returncode, "failed")


NOTIFY_TITLE = "ghostfolio-ibkr-sync: run failed"
TOKEN_EXPIRY_NOTIFY_TITLE = "ghostfolio-ibkr-sync: token expiring"
FORCED_PREVIEW_NOTIFY_TITLE = "ghostfolio-ibkr-sync: forced preview"


def build_forced_preview_summary(reason: str) -> str:
    """Fixed advisory line: the run wrote nothing because of the TZ prerequisite."""
    return f"- forced DRY_RUN: {reason}; no Ghostfolio writes. Set a valid IANA TZ."


def build_token_expiry_summary(days: int) -> str:
    """Fixed advisory code and remaining-day count; no JWT claims are disclosed."""
    return (f"- ghost_auth: token_expiring (days remaining: {days})\n"
            "Regenerate GHOST_TOKEN or switch to GHOST_ACCESS_TOKEN.")


def build_failure_summary(outcome: RunOutcome, now: datetime | None = None) -> str:
    """Plain-text summary: fixed codes, UTC time, counts and account ordinals only."""
    now = now or datetime.now(UTC)
    lines = [f"Run failed at {now.strftime('%Y-%m-%d %H:%M')} UTC.",
             f"Accounts failed: {int(outcome['accounts_failed'])} of {int(outcome['accounts_total'])}."]
    for failure in outcome["failures"]:
        stage, reason = failure["stage"], failure["reason"]
        if reason not in OUTCOME_REASONS.get(stage, ()):
            stage, reason = "unexpected", "unhandled_error"
        ordinal = failure["ordinal"]
        where = f" (account #{ordinal})" if type(ordinal) is int and ordinal > 0 else ""
        lines.append(f"- {stage}: {reason}{where}")
    if outcome["dropped"]:
        lines.append(f"- and {int(outcome['dropped'])} more")
    if outcome.get("token_expiry_days") is not None:
        lines.append(build_token_expiry_summary(outcome["token_expiry_days"]))
    if outcome.get("forced_preview"):
        lines.append(build_forced_preview_summary(outcome["forced_preview"]))
    lines.append("Details are in the container log.")
    return "\n".join(lines)
