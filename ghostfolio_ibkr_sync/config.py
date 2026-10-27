"""ENV configuration: run settings and failure-notification settings.

`load` and `load_notifications` return immutable records. `load_config` and
`load_notification_config` keep the dictionary shape the runtime still consumes.
"""

import json
import logging
import os
import re
from typing import TypedDict
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from ghostfolio_ibkr_sync.models import NotificationSettings, Settings

log = logging.getLogger(__name__)

NOTIFY_PAYLOAD_MAX = 32 * 1024
APPRISE_URLS_MAX = 10
APPRISE_URL_MAX_LEN = 2048
APPRISE_TIMEOUT_DEFAULT = 10
APPRISE_TIMEOUT_MAX = 30


class ConfigDict(TypedDict):
    ibkr_token: str
    account_ids: list[str]
    query_ids: list[str]
    account_names: list[str]
    ghost_token: str | None
    ghost_access_token: str | None
    ghost_host: str
    ghost_platform_id: str
    mapping_file: str
    dry_run: bool
    activity_review_file: str | None
    corporate_action_state_file: str | None
    corporate_action_evidence_file: str | None


class NotificationConfigDict(TypedDict):
    urls: list[str]
    timeout: int


def dry_run_requested() -> bool:
    """Default to simulation; safe to read even after configuration rejection."""
    return os.environ.get("DRY_RUN", "").strip().lower() not in ("0", "false", "no", "off")


def invalid_dry_run_value() -> bool:
    """Validate the mode without echoing potentially sensitive ENV contents."""
    value = os.environ.get("DRY_RUN", "").strip().lower()
    return value not in ("", "1", "true", "yes", "on", "0", "false", "no", "off")


def timezone_preview_reason() -> str | None:
    """Return why TZ forces a whole-run preview, or None when TZ is a valid IANA zone."""
    name = os.environ.get("TZ", "").strip()
    if not name:
        return "TZ is missing"
    try:
        ZoneInfo(name)
    except Exception:
        return "TZ is not a valid IANA timezone"
    return None


def _env_secret(name: str) -> str | None:
    """Return a credential verbatim, or None when absent, empty or whitespace only."""
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return value


def validate_ghost_host(host: str) -> None:
    """Refuse a GHOST_HOST that could send the access token somewhere unintended.

    The message is fixed: the host may carry userinfo credentials.
    """
    try:
        parts = urlsplit(host)
        port_ok = parts.port is None or parts.port > 0
    except ValueError:
        port_ok = False
    if (not port_ok
            or parts.scheme not in ("http", "https")
            or not parts.hostname
            or "@" in parts.netloc
            or parts.query or parts.fragment or "?" in host or "#" in host
            or any(c.isspace() or ord(c) < 0x20 or ord(c) == 0x7f or c == "\\" for c in host)):
        raise RuntimeError("GHOST_HOST must be an http(s) URL without credentials, "
                           "query, fragment, whitespace or control characters")


def load() -> Settings:
    """Load and validate configuration from environment variables.

    Ghostfolio credentials: exactly one of GHOST_TOKEN (a bearer used as is,
    legacy) or GHOST_ACCESS_TOKEN (the security token, exchanged for a bearer
    once per run by main).
    """
    if invalid_dry_run_value():
        raise RuntimeError("DRY_RUN must be blank or one of 1/true/yes/on/0/false/no/off")
    ghost_token = _env_secret("GHOST_TOKEN")
    access_token = _env_secret("GHOST_ACCESS_TOKEN")
    missing = [k for k in ("IBKR_TOKEN", "IBKR_ACCOUNT_IDS", "IBKR_QUERY_IDS") if not os.environ.get(k)]
    if ghost_token is None and access_token is None:
        missing.append("GHOST_TOKEN or GHOST_ACCESS_TOKEN")
    if not os.environ.get("GHOST_HOST"):
        missing.append("GHOST_HOST")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    if ghost_token is not None and access_token is not None:
        raise RuntimeError("Set only one of GHOST_TOKEN or GHOST_ACCESS_TOKEN, not both")
    ghost_host = os.environ["GHOST_HOST"].rstrip("/")
    if access_token is not None:
        validate_ghost_host(ghost_host)

    account_ids = os.environ["IBKR_ACCOUNT_IDS"].split(",")
    query_ids = os.environ["IBKR_QUERY_IDS"].split(",")
    account_names = os.environ.get("GHOST_ACCOUNT_NAMES", "").split(",")

    if len(account_ids) != len(query_ids):
        raise RuntimeError("IBKR_ACCOUNT_IDS and IBKR_QUERY_IDS must have the same number of entries")
    if account_names != [""] and len(account_names) != len(account_ids):
        raise RuntimeError("GHOST_ACCOUNT_NAMES must match the number of IBKR_ACCOUNT_IDS")

    # Effective targets: the names, or the IBKR ids when no names are set (run_sync)
    targets = [n.strip() for n in account_names] if account_names != [""] else [a.strip() for a in account_ids]
    for target in targets:
        if targets.count(target) > 1:
            raise RuntimeError(f"Duplicate Ghostfolio target '{target}': each IBKR account needs its own target")

    review_file = os.environ.get("ACTIVITY_REVIEW_FILE", "").strip() or None
    if review_file and len({account.strip() for account in account_ids}) != len(account_ids):
        raise RuntimeError("Activity review requires distinct configured source accounts")

    return Settings(
        ibkr_token=os.environ["IBKR_TOKEN"],
        account_ids=tuple(a.strip() for a in account_ids),
        query_ids=tuple(q.strip() for q in query_ids),
        account_names=tuple(n.strip() for n in account_names) if account_names != [""] else (),
        ghost_token=ghost_token,
        ghost_access_token=access_token,
        ghost_host=ghost_host,
        ghost_platform_id=os.environ.get("GHOST_PLATFORM_ID", ""),
        mapping_file=os.environ.get("MAPPING_FILE", "mapping.yaml"),
        dry_run=dry_run_requested(),
        activity_review_file=review_file,
        corporate_action_state_file=os.environ.get("CORPORATE_ACTION_STATE_FILE", "").strip() or None,
        corporate_action_evidence_file=os.environ.get("CORPORATE_ACTION_EVIDENCE_FILE", "").strip() or None,
    )


def load_config() -> ConfigDict:
    """`load` as the mutable dictionary the runtime still consumes."""
    settings = load()
    return {
        "ibkr_token": settings.ibkr_token,
        "account_ids": list(settings.account_ids),
        "query_ids": list(settings.query_ids),
        "account_names": list(settings.account_names),
        "ghost_token": settings.ghost_token,
        "ghost_access_token": settings.ghost_access_token,
        "ghost_host": settings.ghost_host,
        "ghost_platform_id": settings.ghost_platform_id,
        "mapping_file": settings.mapping_file,
        "dry_run": settings.dry_run,
        "activity_review_file": settings.activity_review_file,
        "corporate_action_state_file": settings.corporate_action_state_file,
        "corporate_action_evidence_file": settings.corporate_action_evidence_file,
    }


def notification_configuration() -> tuple[NotificationSettings | None, str]:
    """Parse APPRISE_URLS and APPRISE_TIMEOUT; None means notifications are off.

    APPRISE_URLS is a JSON list of Apprise URL strings (blank or [] = off);
    APPRISE_TIMEOUT an integer number of seconds, 1..30 (default 10).  Never
    raises: invalid settings only disable delivery, with a fixed warning since
    the values carry destination credentials.
    """
    raw = os.environ.get("APPRISE_URLS", "")
    if not raw.strip():
        return None, "disabled"
    try:
        urls = json.loads(raw) if len(raw) <= NOTIFY_PAYLOAD_MAX else None
    except ValueError:
        urls = None
    raw_timeout = os.environ.get("APPRISE_TIMEOUT", "").strip()
    timeout = APPRISE_TIMEOUT_DEFAULT
    if raw_timeout:
        timeout = int(raw_timeout) if re.fullmatch(r"[0-9]{1,2}", raw_timeout) else 0
    if (not isinstance(urls, list) or len(urls) > APPRISE_URLS_MAX
            or not all(isinstance(u, str) and u.strip() and len(u) <= APPRISE_URL_MAX_LEN
                       for u in urls)
            or not 1 <= timeout <= APPRISE_TIMEOUT_MAX):
        log.warning("APPRISE_URLS or APPRISE_TIMEOUT is invalid: failure notifications disabled")
        return None, "invalid configuration"
    if not urls:
        return None, "disabled"
    return NotificationSettings(urls=tuple(urls), timeout=timeout), "configured"



def load_notifications() -> NotificationSettings | None:
    """Return validated settings; invalid and disabled settings both disable send."""
    return notification_configuration()[0]


def load_notification_delivery() -> tuple[NotificationConfigDict | None, str]:
    """Expose validation state without disclosing destination values."""
    settings, status = notification_configuration()
    return ({"urls": list(settings.urls), "timeout": settings.timeout}
            if settings is not None else None), status


def load_notification_config() -> NotificationConfigDict | None:
    """`load_notifications` as the dictionary the runtime still consumes."""
    settings = load_notifications()
    if settings is None:
        return None
    return {"urls": list(settings.urls), "timeout": settings.timeout}
