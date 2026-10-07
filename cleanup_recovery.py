"""Shared offline-testable cleanup journal and explicit recovery; no live auto-retry."""

import fcntl
import logging
import os
import tempfile
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import uuid4

import requests
import yaml

log = logging.getLogger(__name__)


def tool_name(tool):
    name = Path(tool.__file__).stem
    if name not in ("cleanup_duplicates", "cleanup_dividends"):
        raise RuntimeError("Unknown cleanup tool")
    return name


def journal_host(config):
    host = config["ghost_host"].rstrip("/")
    url = urlsplit(host)
    if (url.scheme not in ("http", "https") or not url.netloc or url.username
            or url.password or url.query or url.fragment):
        raise RuntimeError("Journal requires a credential-free Ghostfolio base URL")
    return host


def write_journal(path, journal, create=False):
    """Persist each transition before HTTP; never truncate the last durable state."""
    data = yaml.safe_dump(journal, sort_keys=False, allow_unicode=True).encode()
    if create:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        fd, temporary = tempfile.mkstemp(prefix=".cleanup-journal-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def lock_journal(path):
    """A stable companion inode protects atomic journal replacements."""
    if path.is_symlink():
        raise RuntimeError("Symlink journal refused")
    fd = os.open(str(path) + ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise RuntimeError("Cleanup journal already in use") from None
    return fd


def validate_pair(tool, manual, synced, new_comment):
    for row in (manual, synced):
        tool.validate_financial_evidence(row)
        if tool.inactive(row):
            raise RuntimeError("Inactive recovery pair refused")
        if not isinstance(row.get("userId"), str) or not row["userId"].strip():
            raise RuntimeError("Missing cleanup owner; refusing uncertain recovery ownership")
    if (manual["id"] == synced["id"] or manual["userId"] != synced["userId"]
            or tool.identity_of(manual) != tool.identity_of(synced)
            or manual["type"] != synced["type"]
            or manual["type"] not in (("DIVIDEND",) if tool_name(tool) == "cleanup_dividends" else ("BUY", "SELL"))
            or any(manual[f] != synced[f] for f in ("quantity", "unitPrice", "fee"))
            or abs(tool.parse_date(manual["date"]) - tool.parse_date(synced["date"])) > tool.DATE_TOLERANCE):
        raise RuntimeError("Invalid recovery pair identity or financial evidence")
    prefix = "dividend#" if tool_name(tool) == "cleanup_dividends" else "IBKR#"
    if (not isinstance(new_comment, str) or not new_comment.startswith(prefix)
            or len(new_comment) <= len(prefix) or synced.get("comment") != new_comment
            or (manual.get("comment") or "").startswith(prefix)):
        raise RuntimeError("Invalid recovery comment provenance")


def read_current(tool, config, planned):
    url = f"{config['ghost_host']}/api/v1/activities/{quote(planned['id'], safe='')}"
    try:
        response = requests.get(url, headers=tool.headers(config["ghost_token"]), timeout=10)
        if response.status_code == 404:
            return None
        if not 200 <= response.status_code < 300:
            raise RuntimeError("Cannot read current recovery activity")
        row = response.json()
        tool.validate_financial_evidence(row)
        if tool.inactive(row) or row.get("userId") != planned["userId"]:
            raise RuntimeError("Recovery activity ownership or eligibility changed")
        return row
    except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
        raise RuntimeError("Cannot establish recovery activity state") from exc


def pair_state(tool, config, pair):
    """Only fresh evidence decides a safe next action; recorded status is advisory."""
    manual, synced = pair["manual_preimage"], pair["synced_preimage"]
    m = read_current(tool, config, manual)
    ib = read_current(tool, config, synced)
    if m is None:
        raise RuntimeError("Retained manual activity missing; recovery refused")
    tagged = {**manual, "comment": pair["new_comment"]}
    is_original = tool.snapshot_matches(m, manual)
    is_tagged = tool.snapshot_matches(m, tagged)
    if not is_original and not is_tagged:
        raise RuntimeError("Retained manual activity changed; recovery refused")
    if ib is None:
        if is_tagged:
            return "complete", m
        raise RuntimeError("Synced row absent but retained row untagged; recovery refused")
    if not tool.snapshot_matches(ib, synced):
        raise RuntimeError("Synced activity changed; recovery refused")
    return ("delete" if is_tagged else "put_then_delete"), m


def execute_pairs(tool, config, path, journal, apply):
    """Inspect all pairs before mutations; stop on any uncertain mutation."""
    # Validate all fresh evidence before touching the first pair.
    for key, pair in journal["pairs"].items():
        action, _ = pair_state(tool, config, pair)
        log.info("Recovery pair %s: %s", key, action)
    if not apply:
        log.info("Inspection only; no PUT or DELETE sent")
        return
    for pair in journal["pairs"].values():
        action, current = pair_state(tool, config, pair)
        if action == "complete":
            pair["put"] = pair["delete"] = "succeeded"
            write_journal(path, journal)
            continue
        if action == "put_then_delete":
            pair["put"] = "unknown"
            write_journal(path, journal)
            if not tool.put_comment(config, current, pair["new_comment"], dry_run=False):
                raise RuntimeError("PUT outcome unresolved; inspect journal before explicit resume")
            pair["put"] = "succeeded"
            write_journal(path, journal)
        # Reread both rows after PUT, before DELETE. No conditional API exists:
        # operators must quiesce other writers for both normal apply and resume.
        action, _ = pair_state(tool, config, pair)
        if action == "complete":
            pair["delete"] = "succeeded"
            write_journal(path, journal)
            continue
        if action != "delete":
            raise RuntimeError("Tagged retained row not verified; refusing DELETE")
        # A tagged preimage proves a prior PUT committed even after timeout.
        pair["put"] = "succeeded"
        pair["delete"] = "unknown"
        write_journal(path, journal)
        if not tool.delete_activity(config, pair["synced_preimage"]["id"], dry_run=False):
            raise RuntimeError("DELETE outcome unresolved; inspect journal before explicit resume")
        pair["delete"] = "succeeded"
        write_journal(path, journal)


def process_pairs(tool, config, pairs, journal_path=None):
    if not pairs:
        return
    host = journal_host(config)
    records = {}
    used_ids = set()
    for synced, manual in pairs:
        comment = synced["comment"]
        validate_pair(tool, manual, synced, comment)
        if manual["id"] in used_ids or synced["id"] in used_ids:
            raise RuntimeError("Repeated recovery identity")
        used_ids.update((manual["id"], synced["id"]))
        # Capture exact fresh preimages before creating the durable journal.
        m = tool.fetch_fresh(config, manual)
        if m is None:
            raise RuntimeError("Cannot verify manual cleanup preimage")
        ib = tool.fetch_fresh(config, synced)
        if ib is None:
            raise RuntimeError("Cannot verify synced cleanup preimage")
        validate_pair(tool, m, ib, comment)
        records[synced["id"]] = {"manual_preimage": m, "synced_preimage": ib,
                                 "new_comment": comment, "put": "not_attempted", "delete": "not_attempted"}
    path = Path(journal_path) if journal_path else Path(f"{tool_name(tool)}_{uuid4().hex}.yaml")
    journal = {"schema": 1, "tool": tool_name(tool), "host": host, "pairs": records}
    lock = lock_journal(path)
    try:
        write_journal(path, journal, create=True)
        log.info("Private recovery journal: %s", path)
        execute_pairs(tool, config, path, journal, apply=True)
    finally:
        os.close(lock)


def resume_cleanup(tool, config, journal_path, apply=False):
    path = Path(journal_path)
    lock = lock_journal(path)
    try:
        if path.stat().st_mode & 0o077:
            raise RuntimeError("Cleanup journal must have private permissions (chmod 600)")
        try:
            journal = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError) as exc:
            raise RuntimeError("Unreadable cleanup journal") from exc
        if (not isinstance(journal, dict) or type(journal.get("schema")) is not int
                or journal.get("schema") != 1
                or journal.get("tool") != tool_name(tool) or journal.get("host") != journal_host(config)
                or not isinstance(journal.get("pairs"), dict) or not journal["pairs"]):
            raise RuntimeError("Journal schema, tool or host mismatch")
        used_ids = set()
        for key, pair in journal["pairs"].items():
            if not isinstance(pair, dict):
                raise RuntimeError("Invalid cleanup journal pair")
            m, ib = pair.get("manual_preimage"), pair.get("synced_preimage")
            validate_pair(tool, m, ib, pair.get("new_comment"))
            if key != ib["id"] or any(i in used_ids for i in (m["id"], ib["id"])):
                raise RuntimeError("Repeated or mismatched journal identity")
            used_ids.update((m["id"], ib["id"]))
            if any(pair.get(field) not in ("not_attempted", "unknown", "succeeded") for field in ("put", "delete")):
                raise RuntimeError("Invalid journal operation state")
        execute_pairs(tool, config, path, journal, apply)
    finally:
        os.close(lock)
