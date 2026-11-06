"""Private grouped action delivery state; never an authority for financial work."""

import fcntl
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, TypedDict

from ghostfolio_ibkr_sync.activity_review import (
    atomic_yaml,
    file_bytes,
    fingerprint,
    read_yaml,
    safe_path,
)
from ghostfolio_ibkr_sync.corporate_actions import private_directory
from ghostfolio_ibkr_sync.outcome import ACTION_INSTRUCTIONS, RunOutcome

log = logging.getLogger(__name__)
REMINDER_SECONDS = 7 * 24 * 60 * 60


class ActionNotificationPlan(TypedDict):
    path: Path | None
    original: bytes | None
    inputs: list[Path]
    document: dict[str, Any]
    cleared: list[str]
    due: bool


def action_groups(outcome: RunOutcome) -> dict[str, int]:
    return {reason: len(keys) for reason, keys in sorted(outcome["actions"].items())
            if reason in ACTION_INSTRUCTIONS and reason != "processing_failure" and keys}


def delivery_document(data: bytes) -> dict[str, Any]:
    document = read_yaml(data)
    if (set(document) != {"version", "context", "groups", "fingerprint", "sent_at"}
            or type(document["version"]) is not int or document["version"] != 1
            or not isinstance(document["context"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", document["context"])
            or not isinstance(document["groups"], dict)
            or any(reason not in ACTION_INSTRUCTIONS or reason == "processing_failure"
                   or type(count) is not int or count < 1
                   for reason, count in document["groups"].items())
            or document["fingerprint"] != fingerprint(document["groups"])
            or type(document["sent_at"]) is not int or document["sent_at"] < 0):
        raise RuntimeError("Invalid required-action delivery state")
    return document


def plan_action_notification(outcome: RunOutcome, filename: str | None,
                             context: str, now: int | None = None, *,
                             inputs: list[Path] | None = None) -> ActionNotificationPlan:
    """Compare reason/count groups, never event IDs or changing diagnostic text."""
    now = int(time.time()) if now is None else now
    groups = action_groups(outcome)
    document = {"version": 1, "context": context, "groups": groups,
                "fingerprint": fingerprint(groups), "sent_at": now}
    protected = inputs or []
    plan: ActionNotificationPlan = {"path": None, "original": None, "inputs": protected, "document": document,
                                    "cleared": [], "due": bool(groups)}
    if not filename:
        if groups:
            log.warning("Required-action delivery state unavailable; notices remain eligible")
        return plan
    path = Path(filename + ".required-actions.yaml").absolute()
    try:
        private_directory(path.parent)
        safe_path(path, protected)
        original = file_bytes(path)
        plan["original"] = original
        previous = delivery_document(original) if original is not None else None
        plan["path"] = path
        if previous is None:
            if groups:
                log.warning("Required-action delivery state missing; notices remain eligible")
        elif previous["context"] == context:
            plan["cleared"] = sorted(set(previous["groups"]) - set(groups))
            plan["due"] = (previous["fingerprint"] != document["fingerprint"]
                           or bool(groups) and (now < previous["sent_at"]
                                                or now - previous["sent_at"] >= REMINDER_SECONDS))
    except (RuntimeError, OSError, ValueError):
        log.warning("Required-action delivery state unavailable; notices remain eligible")
        # A corrupt regular file can be replaced after a confirmed delivery.
        # Unsafe paths never become a confirmation target.
        try:
            private_directory(path.parent)
            safe_path(path, protected)
            plan["path"] = path
        except (RuntimeError, OSError):
            pass
    return plan


def confirm_action_notification(plan: ActionNotificationPlan) -> bool:
    """Record only a sent snapshot; refuse concurrent state replacement."""
    path = plan["path"]
    if path is None:
        return False
    lock = Path(str(path) + ".lock")
    fd: int | None = None
    try:
        private_directory(path.parent)
        safe_path(path, plan["inputs"])
        safe_path(lock, plan["inputs"])
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if file_bytes(path) != plan["original"]:
            raise RuntimeError("Required-action delivery generation changed")
        atomic_yaml(path, {**plan["document"], "sent_at": int(time.time())})
        return True
    except (RuntimeError, OSError):
        log.warning("Required-action delivery was not recorded; notices remain eligible")
        return False
    finally:
        if fd is not None:
            os.close(fd)
