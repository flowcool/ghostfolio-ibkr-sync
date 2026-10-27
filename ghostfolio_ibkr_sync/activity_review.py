"""Persistent one-to-one activity review. No migration or deletion executor.

The operator edits approvals between runs. Locks coordinate runtime writers;
byte checks detect observed edits, not arbitrary-editor compare-and-swap.
"""

import fcntl
import json
import logging
import os
import re
import stat
import tempfile
import time
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, TypedDict, cast
from uuid import uuid4

import yaml

from ghostfolio_ibkr_sync.activity_preservation import preserved_values
from ghostfolio_ibkr_sync.ghostfolio import (
    activity_date_is_current,
    activity_is_active,
    dividend_context,
    format_versioned_activity_identity,
    ghost_get_existing_orders,
    ghost_update_reviewed_activity,
    parse_versioned_activity_identity,
)
from ghostfolio_ibkr_sync.ibkr import (
    SKIP_ASSET_CATEGORIES,
    DividendGroup,
    dividend_field_prerequisites,
    dividend_input_compatible,
    flex_provenance_failures,
    parse_cash_dividends,
    parse_source_account_ids,
    parse_trades,
)
from ghostfolio_ibkr_sync.sync import (
    convert_dividend_actions,
    convert_trade_to_activity,
    dividend_action_conflict,
    unique_trades,
)

log = logging.getLogger(__name__)


class ReviewState(TypedDict):
    path: Path
    journal_path: Path
    inputs: list[Path]
    lock: int
    original: bytes | None
    journal_original: bytes | None
    document: dict[str, Any]
    journal: dict[str, Any]


def read_yaml(data: bytes) -> dict[str, Any]:
    """YAML with duplicate rejection and only true/false boolean tokens.

    Compose scalar nodes directly: this avoids global SafeLoader mutations and
    preserves literal yes without interpreting true as operator authority.
    """
    def value(node: yaml.Node, approval: bool = False) -> Any:
        if isinstance(node, yaml.MappingNode):
            result: dict[str, Any] = {}
            for key_node, item in node.value:
                if not isinstance(key_node, yaml.ScalarNode):
                    raise RuntimeError("Review YAML keys must be strings")
                key = key_node.value
                if key in result:
                    raise RuntimeError("Duplicate review YAML key")
                result[key] = value(item, key == "approve")
            return result
        if isinstance(node, yaml.SequenceNode):
            return [value(item) for item in node.value]
        if not isinstance(node, yaml.ScalarNode):
            raise RuntimeError("Invalid review YAML node")
        if node.tag.endswith(":null"):
            return None
        if node.tag.endswith(":bool"):
            return {"true": True, "false": False}.get(node.value, node.value)
        if node.tag.endswith(":int"):
            if not re.fullmatch(r"[0-9]+", node.value):
                if approval:
                    return node.value
                raise RuntimeError("Unsupported review integer")
            return int(node.value)
        if not node.tag.endswith(":str"):
            if approval and node.tag.endswith((":float", ":timestamp")):
                return node.value
            raise RuntimeError("Review numbers must use quoted plain-decimal text")
        return node.value

    try:
        root = yaml.compose(data, Loader=yaml.SafeLoader)
        result = value(root) if root is not None else None
    except (yaml.YAMLError, RecursionError, ValueError):
        raise RuntimeError("Invalid review YAML") from None
    if not isinstance(result, dict):
        raise RuntimeError("Review must be a keyed YAML document")
    return result


def safe_path(path: Path, inputs: Sequence[Path]) -> None:
    """Reject links, public permissions and any input/output inode alias."""
    if not path.is_absolute():
        path = path.absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise RuntimeError("Review paths must not contain symlinks")
    if not path.parent.is_dir():
        raise RuntimeError("Review parent directory is missing")
    if path.exists():
        info = path.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1
                or not info.st_mode & 0o400 or not info.st_mode & 0o200):
            raise RuntimeError("Review files require private readable writable regular files")
    for source in inputs:
        if path.resolve() == source.resolve() or (
                path.exists() and source.exists() and os.path.samefile(path, source)):
            raise RuntimeError("Review output overlaps an input")


def file_bytes(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def validate_document(document: dict[str, Any], collection: str) -> None:
    if (set(document) != {"version", collection} or type(document["version"]) is not int
            or document["version"] != 1 or not isinstance(document[collection], dict)):
        raise RuntimeError("Invalid review document schema")
    if any(not isinstance(key, str) or not isinstance(row, dict)
           for key, row in document[collection].items()):
        raise RuntimeError("Invalid keyed review records")


SECTIONS = ("reference_updates", "activity_corrections")


def decode_review(document: dict[str, Any]) -> dict[str, Any]:
    """Read both public versions; keep the existing journal and internal map."""
    if type(document.get("version")) is int and document["version"] == 1:
        validate_document(document, "proposals")
        result = deepcopy(document)
        for item in result["proposals"].values():
            item["approve"] = None
        return result
    if (set(document) != {"version", *SECTIONS}
            or type(document.get("version")) is not int or document["version"] != 2):
        raise RuntimeError("Invalid review document schema")
    proposals: dict[str, Any] = {}
    for section in SECTIONS:
        records = document[section]
        if not isinstance(records, dict):
            raise RuntimeError("Invalid keyed review section")
        for key, item in records.items():
            if (not isinstance(key, str) or not isinstance(item, dict)
                    or key in proposals or item.get("section") != section):
                raise RuntimeError("Duplicate or misplaced review proposal")
            proposals[key] = item
    return {"version": 1, "proposals": proposals}


def encode_review(document: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"version": 2, **{section: {} for section in SECTIONS}}
    for key, item in document["proposals"].items():
        section = item.get("section", "activity_corrections")
        if section not in SECTIONS:
            raise RuntimeError("Invalid review section")
        result[section][key] = {"section": section,
                                "evidence level": "blocked" if not item.get("actionable") else "probable",
                                "execution path": "normal run", **item}
    return result


def open_review(filename: str, input_files: Sequence[str]) -> ReviewState:
    path = Path(filename).absolute()
    journal_path = Path(str(path) + ".journal.yaml")
    lock_path = Path(str(path) + ".lock")
    inputs = [Path(item).absolute() for item in input_files]
    for target in (path, journal_path, lock_path):
        safe_path(target, inputs)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original, journal_original = file_bytes(path), file_bytes(journal_path)
        document = read_yaml(original) if original is not None else {"version": 1, "proposals": {}}
        journal = (read_yaml(journal_original) if journal_original is not None
                   else {"version": 1, "entries": {}})
        document = decode_review(document)
        validate_document(journal, "entries")
        return {"path": path, "journal_path": journal_path, "inputs": inputs, "lock": fd,
                "original": original, "journal_original": journal_original,
                "document": document, "journal": journal}
    except BaseException:
        os.close(fd)
        raise


def close_review(state: ReviewState) -> None:
    os.close(state["lock"])


def assert_unchanged(state: ReviewState) -> None:
    for target, original in ((state["path"], state["original"]),
                             (state["journal_path"], state["journal_original"])):
        safe_path(target, state["inputs"])
        if file_bytes(target) != original:
            raise RuntimeError("Review or journal changed during this run; writes blocked")


def atomic_yaml(path: Path, document: dict[str, Any]) -> bytes:
    data = yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode()
    fd, temporary = tempfile.mkstemp(prefix=".activity-review-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return data


def publish_review(state: ReviewState, document: dict[str, Any]) -> None:
    assert_unchanged(state)
    state["original"] = atomic_yaml(state["path"], encode_review(document))
    state["document"] = document


def publish_journal(state: ReviewState) -> None:
    assert_unchanged(state)
    state["journal_original"] = atomic_yaml(state["journal_path"], state["journal"])


def plain(value: Any) -> Any:
    """Lossless YAML evidence; transport numbers are explicit decimal strings."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise RuntimeError("Non-finite review number")
        text = format(value, "f")
        return (text.rstrip("0").rstrip(".") if "." in text else text) if value else "0"
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def fingerprint(value: Any) -> str:
    return sha256(json.dumps(plain(value), sort_keys=True, ensure_ascii=True,
                             allow_nan=False).encode()).hexdigest()


def instant(value: Any) -> datetime:
    if (not isinstance(value, str) or not re.search(r"(?:Z|[+-][0-9]{2}:[0-9]{2})$", value)
            or re.search(r"\.[0-9]{7,}", value)):
        raise RuntimeError("Missing timezone or unsupported timestamp precision")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC)
    except ValueError:
        raise RuntimeError("Invalid review timestamp") from None


NUMBERS = ("quantity", "unitPrice", "fee")
REPLACED = ("date", "symbol", "type", "currency", *NUMBERS, "comment")


def wire_values(payload: dict[str, Any]) -> dict[str, Any]:
    """Compare the exact numeric literals requests' normal JSON serializer sends."""
    return json.loads(json.dumps(payload, allow_nan=False), parse_float=Decimal, parse_int=Decimal)  # type: ignore[no-any-return]


def source_events(xml: str, source: str, destination: str,
                  mapping: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Convert validated current source events before existing-reference skips."""
    if (parse_source_account_ids(xml) != {source} or flex_provenance_failures(xml)
            or dividend_field_prerequisites(xml)):
        raise RuntimeError("Incomplete review source account evidence")
    trades = [row for row in parse_trades(xml)
              if row.get("assetCategory", "") not in SKIP_ASSET_CATEGORIES]
    for row in trades:
        if row.get("accountId") != source:
            raise RuntimeError("Review trade account mismatch")
        format_versioned_activity_identity(source, "TRADE", row.get("tradeID", ""))
    unique, _, conflicts = unique_trades(trades)
    result: dict[str, dict[str, Any]] = {}

    def add(payload: dict[str, Any] | None, evidence: Any, isin: str,
            legacy: list[str], legacy_safe: bool) -> None:
        if payload is None or not activity_date_is_current(payload):
            return
        try:
            exact = wire_values(payload)
            if any(not exact[field].is_finite() or exact[field] < 0 for field in NUMBERS):
                return
            if exact["quantity"] <= 0 or exact["unitPrice"] <= 0:
                return
        except (ValueError, OverflowError):
            return
        marker = payload["comment"]
        event = {"source account": source, "destination account": destination,
                 "event": marker, "payload": payload, "values": plain(exact), "isin": isin,
                 "legacy": legacy, "legacy safe": legacy_safe,
                 "source evidence": plain(evidence), "mapping": mapping}
        if marker in result:
            raise RuntimeError("Repeated source event across groups")
        result[marker] = event

    for row in unique:
        if row.get("tradeID") in conflicts:
            continue
        payload = convert_trade_to_activity(row, destination, mapping, {})
        add(payload, row, row.get("isin", ""), ["IBKR#" + row["tradeID"]], False)
    groups = parse_cash_dividends(xml)
    if groups is None:
        # Preserve baseline isolation: ordinary selection reports the missing
        # dividend section while valid trades and independent cash continue.
        return result
    if dividend_input_compatible(groups):
        for group in groups:
            for row in group["payments"]:
                if row.get("accountId") != source:
                    raise RuntimeError("Review dividend account mismatch")
                format_versioned_activity_identity(source, "DIVIDEND", row.get("actionID", ""))
            payloads, ok = convert_dividend_actions(group, destination, mapping, {}, groups)
            if not ok:
                continue
            for payload in payloads:
                # Aggregate legacy markers cannot identify one action from several.
                aliases = sorted({f"dividend#{key}#{group['date']}"
                                  for key in (group["isin"], group["symbol"], payload["symbol"]) if key})
                action = parse_versioned_activity_identity(payload["comment"], "DIVIDEND")
                assert action is not None
                evidence = {key: [row for row in group[key] if row.get("actionID") == action[2]]
                            for key in ("payments", "cash_rows", "accruals")}
                add(payload, evidence, group["isin"], aliases, len(payloads) == 1)
                if payload["comment"] in result:
                    result[payload["comment"]]["dividend scope"] = {
                        "events": sorted(item["comment"] for item in payloads),
                        "date": group["date"], "isin": group["isin"]}
    return result


def profile(row: Mapping[str, Any]) -> dict[str, Any]:
    result = row.get("assetProfile") if "assetProfile" in row else row.get("SymbolProfile")
    if not isinstance(result, dict):
        raise RuntimeError("Unsupported review profile")
    return result


def marker_of(row: Mapping[str, Any]) -> str | None:
    comment = row.get("comment")
    identity = parse_versioned_activity_identity(comment, row.get("type"))
    if identity:
        return str(comment).split("\n", 1)[0]
    if isinstance(comment, str) and (re.fullmatch(r"IBKR#(?!v)[A-Za-z0-9._-]+", comment)
                                     or re.fullmatch(r"dividend#[^#\n]+#[0-9]{4}-[0-9]{2}-[0-9]{2}", comment)):
        return comment
    return None


def replacement_comment(row: dict[str, Any], event: dict[str, Any]) -> str:
    old = row.get("comment") or ""
    recognized = marker_of(row)
    if recognized == event["event"]:
        notes = old.partition("\n\n")[2]
    elif recognized in event["legacy"]:
        notes = ""
    elif recognized or old.startswith(("IBKR#", "dividend#")):
        raise RuntimeError("Ambiguous or unsupported reference")
    else:
        if re.search(r"(?m)^(?:IBKR#|dividend#)", old):
            raise RuntimeError("Multiple reference positions")
        notes = old
    comment = event["event"] + ("\n\n" + notes if notes else "")
    # DTO trim(), JS Unicode length and unsupported surrogate code points.
    if comment != comment.strip() or len(comment.encode("utf-16-le")) // 2 > 2000:
        raise RuntimeError("Comment cannot survive destination trimming or length limit")
    if notes.startswith("\n") or "\r" in comment:
        raise RuntimeError("Comment cannot use the canonical reference position")
    return str(comment)


def numeric(value: Any) -> Decimal:
    if not isinstance(value, (str, Decimal)):
        raise RuntimeError("Missing original decimal evidence")
    try:
        result = Decimal(value)
    except Exception:
        raise RuntimeError("Invalid review decimal evidence") from None
    if not result.is_finite():
        raise RuntimeError("Non-finite review decimal evidence")
    return result


def values_of(row: dict[str, Any]) -> dict[str, Any]:
    """Stable activity-owned evidence from the pinned Order/getActivities schema.

    Account balances, profile enrichment, server timestamps and converted values
    are not activity edits. Compare profile and tag identities, not their labels.
    """
    fields = ("id", "accountId", "accountUserId", "userId", "symbolProfileId", "createdAt", "isDraft")
    result = {key: plain(row[key]) for key in fields if key in row}
    result.update({key: plain(row.get(key)) for key in REPLACED})
    asset = profile(row)
    result["assetProfile"] = {key: plain(asset[key]) for key in
                              ("id", "symbol", "dataSource", "isin", "currency") if key in asset}
    tags = row.get("tags")
    if (not isinstance(tags, list) or any(not isinstance(tag, dict)
            or not isinstance(tag.get("id"), str) or not tag["id"] for tag in tags)
            or len({tag["id"] for tag in tags}) != len(tags)):
        raise RuntimeError("Unproven update tag identities")
    result["tags"] = [{"id": tag_id} for tag_id in sorted(tag["id"] for tag in tags)]
    result["symbol"] = asset.get("symbol")
    for key in NUMBERS:
        result[key] = plain(numeric(row.get(key)))
    result["date"] = instant(result["date"]).isoformat()
    if "createdAt" in result:
        result["createdAt"] = instant(result["createdAt"]).isoformat()
    if "preserved fields" in row:
        if not isinstance(row["preserved fields"], dict):
            raise RuntimeError("Invalid preserved review fields")
        result["preserved fields"] = row["preserved fields"]
    else:
        stable = preserved_values(row)
        known = {*fields, *REPLACED, "assetProfile", "SymbolProfile", "tags", "account"}
        extra = {key: plain(value) for key, value in stable.items() if key not in known}
        for name in ("account", "assetProfile", "SymbolProfile"):
            if name in stable and isinstance(stable[name], dict):
                nested = dict(stable[name])
                if name == "account":
                    # Normal review consent is activity-owned. Independent
                    # cash updates must not invalidate an unchanged proposal.
                    nested.pop("balance", None)
                    nested.pop("balanceInBaseCurrency", None)
                else:
                    for identity in ("id", "symbol", "dataSource", "isin", "currency"):
                        nested.pop(identity, None)
                if nested:
                    extra[name] = plain(nested)
        result["preserved fields"] = extra
    return result


def changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    def equal(key: str) -> bool:
        if key in NUMBERS:
            return numeric(before[key]) == numeric(after[key])
        if key == "date":
            return instant(before[key]) == instant(after[key])
        return bool(before[key] == after[key])
    return sorted(key for key in REPLACED if not equal(key))


def update_payload(row: dict[str, Any], proposed: dict[str, Any]) -> dict[str, Any]:
    """Pinned UpdateOrderDto whitelist. Preserve account and tag identities."""
    if (not row.get("id") or not row.get("accountId") or not row.get("userId")
            or profile(row).get("dataSource") != "YAHOO" or not activity_is_active(row)):
        raise RuntimeError("Unproven update ownership or active profile")
    for field in NUMBERS:
        value = numeric(row.get(field))
        if value < 0 or Decimal(str(float(value))) != value:
            raise RuntimeError("Preserved number cannot survive JSON transport")
    tags = row.get("tags")
    if (not isinstance(tags, list) or any(not isinstance(tag, dict)
            or not isinstance(tag.get("id"), str) or not tag["id"] for tag in tags)
            or len({tag["id"] for tag in tags}) != len(tags)):
        raise RuntimeError("Unproven update tag identities")
    payload = {key: proposed[key] for key in REPLACED}
    payload.update(id=row["id"], accountId=row["accountId"], dataSource="YAHOO",
                   tags=[tag["id"] for tag in tags])
    for field in NUMBERS:
        number = numeric(proposed[field])
        transported = float(number)
        if number < 0 or Decimal(str(transported)) != number:
            raise RuntimeError("Proposed number cannot survive JSON transport")
        payload[field] = transported
    wire_values(payload)
    return payload


def candidate_reason(row: dict[str, Any], event: dict[str, Any], exact_exists: bool) -> str | None:
    reference = marker_of(row)
    if reference == event["event"] or reference in event["legacy"]:
        return "exact reference"
    if exact_exists or reference:
        return None
    target = event["values"]
    asset = profile(row)
    if (row.get("accountId") != event["destination account"] or row.get("type") != target["type"]
            or row.get("currency") != target["currency"] or not activity_is_active(row)
            or asset.get("dataSource") != "YAHOO"
            or (asset.get("isin") and event["isin"] and asset["isin"] != event["isin"])
            or not (asset.get("symbol") == target["symbol"]
                    or (event["isin"] and asset.get("isin") == event["isin"]))):
        return None
    distance = abs((instant(row.get("date")).date() - instant(target["date"]).date()).days)
    return "UTC calendar proximity" if distance <= (3 if target["type"] == "DIVIDEND" else 2) else None


PROPOSAL_FIELDS = {"key", "source account", "source event", "destination account", "activity id",
                   "match reason", "current values", "proposed values", "changed fields", "status",
                   "approve", "actionable", "binding", "date context", "review revision"}
DISPLAY_FIELDS = {"section", "evidence level", "execution path"}


def refresh_proposals(previous: dict[str, Any], events: dict[str, dict[str, Any]],
                      rows: list[dict[str, Any]], accounts: dict[str, str],
                      journal_bindings: set[tuple[str, str, str]] | None = None
                      ) -> tuple[dict[str, Any], set[str]]:
    """Rebuild evidence; file fields never become replacement input."""
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise RuntimeError("Duplicate destination activity IDs")
    for key, old in previous.items():
        if (set(old) not in (PROPOSAL_FIELDS, PROPOSAL_FIELDS | DISPLAY_FIELDS) or old["key"] != key
                or (old["destination account"] != accounts.get(old["source account"])
                    and (old["source event"], old["destination account"], old["activity id"])
                    not in (journal_bindings or set()))
                or not isinstance(old["source event"], str)
                or not old["source event"].startswith(f"IBKR#v2#{old['source account']}:")
                or not isinstance(old["activity id"], str)
                or not isinstance(old["review revision"], str)
                or re.fullmatch(r"[0-9a-f]{32}", old["review revision"]) is None
                or key != fingerprint([old["source event"], old["destination account"], old["activity id"]])):
            raise RuntimeError("Unbound or invalid review proposal")
    result: dict[str, Any] = {}
    satisfied: set[str] = set()
    for event_id, event in sorted(events.items()):
        exact_exists = any(marker_of(row) == event_id or marker_of(row) in event["legacy"] for row in rows)
        occupied = sorted((row["id"], row.get("accountId"), marker_of(row)) for row in rows
                          if marker_of(row) == event_id or marker_of(row) in event["legacy"])
        for row in sorted(rows, key=lambda item: item["id"]):
            try:
                reason = candidate_reason(row, event, exact_exists)
            except RuntimeError:
                continue
            if reason is None:
                continue
            key = fingerprint([event_id, event["destination account"], row["id"]])
            current: dict[str, Any] = {}
            proposed = {key: value for key, value in event["values"].items() if key in REPLACED}
            status, actionable = "pending", True
            try:
                current = values_of(row)
                proposed = {**current, **proposed}
                proposed["comment"] = replacement_comment(row, event)
                payload = update_payload(row, proposed)
                expected_row(row, payload)
                scope = event.get("dividend scope")
                if scope:
                    expected_ids = set(scope["events"])
                    covered = {marker_of(item) for item in rows} & expected_ids
                    if covered and covered != expected_ids:
                        raise RuntimeError("Partial versioned dividend action coverage")
                    others: set[tuple[str, str]] = set()
                    contexts: dict[tuple[str, str], list[Any]] = {}
                    for other_row in rows:
                        identity = parse_versioned_activity_identity(other_row.get("comment"), other_row.get("type"))
                        if identity and identity[1] == "DIVIDEND" and marker_of(other_row) not in expected_ids:
                            other_key = identity[0], str(marker_of(other_row))
                            others.add(other_key)
                            contexts.setdefault(other_key, []).append(dividend_context(profile(other_row), other_row.get("date")))
                    actions = {(event["source account"], identity.rsplit(":", 1)[1]) for identity in expected_ids}
                    if dividend_action_conflict(cast(DividendGroup, scope), event["values"]["symbol"], actions,
                                                {"versioned_identities": others, "versioned_dividend_context": contexts}):
                        raise RuntimeError("Conflicting or unknown dividend action context")
                if row.get("accountId") != event["destination account"]:
                    raise RuntimeError("Conflicting destination account ownership")
                if len(occupied) > 1:
                    raise RuntimeError("Reference occupancy conflict")
                if marker_of(row) in event["legacy"] and not event["legacy safe"]:
                    raise RuntimeError("historical cross-account coverage unavailable" if event["values"]["type"] != "DIVIDEND"
                                       else "legacy aggregate cannot identify one action")
                changes = changed_fields(current, proposed)
                if not changes and marker_of(row) == event_id:
                    satisfied.add(event_id)
                    continue
            except (RuntimeError, ValueError, OverflowError, UnicodeError) as exc:
                actionable, status = False, str(exc)
                changes = sorted(REPLACED) if not current else []
            binding = fingerprint([event, current, occupied])
            item = {"key": key, "source account": event["source account"], "source event": event_id,
                    "destination account": event["destination account"], "activity id": row["id"],
                    "match reason": reason, "current values": current, "proposed values": proposed,
                    "changed fields": changes, "status": status, "approve": None,
                    "actionable": actionable, "binding": binding, "review revision": uuid4().hex,
                    "date context": "Full UTC instants; proximity uses UTC calendar dates"}
            item.update(section="reference_updates" if changes == ["comment"] else "activity_corrections",
                        **{"evidence level": ("blocked" if not actionable else
                                             "exact" if reason == "exact reference" else "probable"),
                           "execution path": "normal run"})
            old = previous.get(key)
            if old:
                comparison = {k: v for k, v in old.items() if k not in ("approve", "status", "review revision")}
                if comparison == {k: v for k, v in item.items() if k not in ("approve", "status", "review revision")}:
                    item["approve"] = old["approve"] if actionable else None
                    item["review revision"] = old["review revision"]
                else:
                    item["status"] = "changed evidence; approval cleared" if actionable else status
            result[key] = item
    # Keep missing targets and unavailable sources; reassignment needs positive evidence.
    for key, old in previous.items():
        event_id = old["source event"]
        if event_id in satisfied or key in result:
            continue
        if event_id not in events:
            result[key] = {**old, "status": "source unavailable"}
            continue
        retained_row = by_id.get(old["activity id"])
        assigned_elsewhere = False
        if retained_row is not None:
            try:
                row = retained_row
                other = marker_of(row)
                assigned_elsewhere = bool(other and other.startswith("IBKR#v2#") and other != event_id
                                          and row.get("accountId") == old["destination account"]
                                          and activity_is_active(row) and profile(row).get("dataSource") == "YAHOO")
                values_of(row)
            except RuntimeError:
                assigned_elsewhere = False
        if not assigned_elsewhere:
            result[key] = {**old, "status": "target missing or unavailable", "actionable": False, "approve": None}
    result = {key: item for key, item in result.items() if item["source event"] not in satisfied}
    return result, {item["source event"] for item in result.values()}



def approved_proposals(proposals: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    blocked: set[str] = set()
    approved = []
    for item in proposals.values():
        choice = item["approve"]
        if choice is None:
            continue
        if type(choice) is str and choice == "yes":
            approved.append(item)
        else:
            log.warning("Review choice skipped for account %s activity %s; only literal yes approves",
                        item["destination account"], item["activity id"])
    for item in approved:
        if (sum(other["source event"] == item["source event"] for other in approved) > 1
                or sum(other["activity id"] == item["activity id"] for other in approved) > 1):
            blocked.add(item["destination account"])
            log.error("Conflicting review approvals for account %s; financial writes blocked", item["destination account"])
    return [item for item in approved if item["destination account"] not in blocked], blocked


# Isolated full-update/readback/background proof covers one correction at a time.
# No intra-run spacing applies with a limit of one. This is not a cross-run
# background-completion guarantee; see docs/releasing.md. ENV cannot override it.
QUALIFIED_EXECUTION: tuple[str, int, float] | None = (
    "ghostfolio/ghostfolio@sha256:929a54a1972c48f3cfb30af2db6f9f2aaeb610a9cc5f53264f1df1629eb43078",
    1,
    0.0,
)
RECOVERY_WAITS = (0, 2, 5, 10)


def snapshot_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = ghost_get_existing_orders(config)[2]["review_snapshot"]
    rows = snapshot.get("activities")
    if (not isinstance(rows, list) or snapshot.get("count") != len(rows)
            or any(not isinstance(row, dict) or not isinstance(row.get("id"), str)
                   or not row["id"] for row in rows)
            or len({row["id"] for row in rows}) != len(rows)):
        raise RuntimeError("Invalid complete review snapshot")
    return rows


def expected_row(row: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    after = deepcopy(row)
    for key in REPLACED:
        if key != "symbol":
            after[key] = payload[key]
    # A different security profile has unknown derived metadata until qualified.
    # Do not invent its id, currency, provider metadata or background effects.
    if profile(row)["symbol"] != payload["symbol"]:
        raise RuntimeError("Changed security profile requires preservation qualification")
    after = plain(after)
    for key in NUMBERS:
        after[key] = plain(wire_values(payload)[key])
    return values_of(dict(after))


def row_matches(row: dict[str, Any], evidence: dict[str, Any]) -> bool:
    """Compare stable pre/post evidence with exact numbers and UTC instants."""
    try:
        actual, expected = values_of(row), values_of(evidence)
        # Already-issued journals retain their original comparison contract.
        # New intents include strict additional stored-field evidence.
        if "preserved fields" not in evidence and "account" not in evidence:
            actual.pop("preserved fields", None)
            expected.pop("preserved fields", None)
        return bool(actual == expected)
    except (RuntimeError, KeyError):
        return False


def recovery_read(config: dict[str, Any], entry: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
    observed = None
    for wait in RECOVERY_WAITS:
        if wait:
            time.sleep(wait)
        try:
            rows = snapshot_rows(config)
            observed = next((row for row in rows if row["id"] == entry["activity id"]), None)
            if observed is not None and row_matches(observed, entry["after"]):
                return True, observed
            # Drift is a conclusive refusal, not a reason to keep polling.
            if observed is not None and not row_matches(observed, entry["before"]):
                break
        except Exception:
            observed = None
    try:
        observed_values = values_of(observed) if observed is not None else None
        expected_values = values_of(entry["after"])
    except (RuntimeError, KeyError):
        observed_values = None
        expected_values = {}
    differences = (sorted(key for key in set(expected_values) | set(observed_values)
                          if observed_values.get(key) != expected_values.get(key))
                   if observed_values is not None else ["unavailable activity evidence"])
    log.error("Review account %s activity %s remains blocked; expected %s; observed differences %s",
              entry["destination account"], entry["activity id"],
              {key: entry["after"].get(key) for key in REPLACED if key != "symbol"}, differences)
    return False, observed


JOURNAL_FIELDS = {"source event", "destination account", "activity id", "host", "binding", "before",
                  "after", "request", "status", "verified result", "proposal key", "review revision"}


def validate_journal(state: ReviewState, config: dict[str, Any]) -> None:
    for key, entry in state["journal"]["entries"].items():
        if (set(entry) != JOURNAL_FIELDS or entry["host"] != config["ghost_host"]
                or entry["status"] not in ("pending", "confirmed")
                or not isinstance(entry["before"], dict) or not isinstance(entry["after"], dict)
                or entry["before"].get("id") != entry["activity id"]
                or entry["after"].get("id") != entry["activity id"]
                or entry["before"].get("accountId") != entry["destination account"]
                or entry["after"].get("accountId") != entry["destination account"]
                or entry["proposal key"] != fingerprint([entry["source event"], entry["destination account"], entry["activity id"]])
                or not isinstance(entry["review revision"], str)
                or re.fullmatch(r"[0-9a-f]{32}", entry["review revision"]) is None
                or key != fingerprint([entry["proposal key"], entry["review revision"]])):
            raise RuntimeError("Invalid or unbound review journal")


def inspect_reverse(entry: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    """Offline guarded reverse evidence only. This function never sends a request."""
    if entry["status"] != "confirmed" or not row_matches(observed, entry["after"]):
        raise RuntimeError("Reverse evidence refused: corrected activity changed or unconfirmed")
    before = entry["before"]
    return update_payload(before, values_of(before))


def process_review(state: ReviewState, config: dict[str, Any], events: dict[str, dict[str, Any]],
                   accounts: dict[str, str]) -> tuple[set[str], set[str]]:
    """Recover, refresh and dispatch sequentially before any ordinary writes."""
    assert_unchanged(state)
    validate_journal(state, config)
    original = state["document"]["proposals"]
    # Journal-owned historical proposals may outlive a configured account.
    # This does not permit dispatch without a fresh source and matching target.
    journal_bindings = {(entry["source event"], entry["destination account"], entry["activity id"])
                        for entry in state["journal"]["entries"].values()}
    rows = snapshot_rows(config)
    # Validate every file binding before any journal completion or correction.
    refreshed, held = refresh_proposals(original, events, rows, accounts, journal_bindings)
    blocked: set[str] = set()
    simulated = bool(config.get("dry_run"))
    unresolved: set[str] = set()
    unresolved_events: set[str] = set()
    for entry in state["journal"]["entries"].values():
        if entry["status"] == "confirmed":
            # A confirmed journal never overrides current source/target evidence.
            continue
        if entry["destination account"] not in accounts.values():
            unresolved.add(entry["destination account"])
            unresolved_events.add(entry["source event"])
            log.error("Pending review activity %s has no configured destination account %s; writes blocked",
                      entry["activity id"], entry["destination account"])
            continue
        matched, _ = recovery_read(config, entry)
        if matched and not simulated:
            entry["status"] = "confirmed"
            entry["verified result"] = entry["after"]
            publish_journal(state)
        else:
            unresolved.add(entry["destination account"])
            unresolved_events.add(entry["source event"])
    blocked |= unresolved
    consumed = {(entry["proposal key"], entry["review revision"])
                for entry in state["journal"]["entries"].values() if entry["status"] == "confirmed"}
    remaining_previous = {key: item for key, item in original.items()
                          if (key, item["review revision"]) not in consumed}
    refreshed, held = refresh_proposals(remaining_previous, events, snapshot_rows(config), accounts, journal_bindings)
    apply_corporate_review_holds(config, refreshed, snapshot_rows(config))
    approved, refreshed_blocked = approved_proposals(refreshed)
    blocked |= refreshed_blocked
    # Simulation cannot consume a proposal whose pending request now appears applied.
    for key, old in original.items():
        if old["source event"] in unresolved_events:
            refreshed[key] = {**old, "status": "unresolved request; account writes blocked"}
    publish_review(state, {"version": 1, "proposals": refreshed})
    executed = 0
    for item in sorted(approved, key=lambda item: item["key"]):
        account = item["destination account"]
        if (account in blocked or item["source event"] not in events or not item["actionable"]
                or item["key"] not in refreshed or item.get("execution path") != "normal run"):
            continue
        if simulated:
            log.info("DRY RUN reviewed correction account %s activity %s: %s", account,
                     item["activity id"], item["proposed values"])
            continue
        qualification = QUALIFIED_EXECUTION
        if qualification is None:
            log.warning("Reviewed correction retained: exact-image execution budget not qualified")
            continue
        image, limit, delay = qualification
        if not image or type(limit) is not int or limit < 1 or not 0 <= delay < float("inf"):
            raise RuntimeError("Invalid qualified correction execution budget")
        if executed >= limit:
            continue
        if executed and delay:
            time.sleep(delay)
        assert_unchanged(state)
        fresh_rows = snapshot_rows(config)
        fresh, _ = refresh_proposals(refreshed, events, fresh_rows, accounts, journal_bindings)
        apply_corporate_review_holds(config, fresh, fresh_rows)
        current = fresh.get(item["key"])
        if current is None or current["approve"] != "yes" or not current["actionable"]:
            log.error("Review evidence changed before dispatch; account %s blocked", account)
            blocked.add(account)
            refreshed = fresh
            continue
        row = next(row for row in fresh_rows if row["id"] == item["activity id"])
        payload = update_payload(row, current["proposed values"])
        try:
            after = expected_row(row, payload)
        except RuntimeError as exc:
            refreshed[item["key"]] = {**current, "actionable": False, "status": str(exc), "approve": None}
            continue
        # The journal key is stable across restarts. No pending logical request is
        # replaced or retried, including after local review deletion.
        request_key = fingerprint([item["key"], current["review revision"]])
        existing = state["journal"]["entries"].get(request_key)
        if existing is not None and existing["status"] != "confirmed":
            blocked.add(account)
            continue
        entry = {"review revision": current["review revision"], "proposal key": item["key"], "source event": item["source event"], "destination account": account,
                 "activity id": row["id"], "host": config["ghost_host"], "binding": current["binding"],
                 "before": values_of(row), "after": after, "request": plain(wire_values(payload)),
                 "status": "pending", "verified result": None}
        state["journal"]["entries"][request_key] = entry
        publish_journal(state)
        assert_unchanged(state)
        try:
            ghost_update_reviewed_activity(config, payload)
        except RuntimeError:
            # A rejected status is still not proof that the destination is unchanged.
            log.error("Review request for account %s activity %s needs readback", account, row["id"])
        executed += 1
        matched, _ = recovery_read(config, entry)
        if not matched:
            blocked.add(account)
            continue
        entry["status"] = "confirmed"
        entry["verified result"] = after
        publish_journal(state)
        refreshed = {key: candidate for key, candidate in refreshed.items()
                     if candidate["source event"] != item["source event"]}
        publish_review(state, {"version": 1, "proposals": refreshed})
    # Rediscover new context and release reassigned alternatives after confirmed PUTs.
    if not simulated and executed:
        refreshed, _ = refresh_proposals(refreshed, events, snapshot_rows(config), accounts, journal_bindings)
    apply_corporate_review_holds(config, refreshed, snapshot_rows(config))
    publish_review(state, {"version": 1, "proposals": refreshed})
    held = {item["source event"] for item in refreshed.values()} | unresolved_events
    from ghostfolio_ibkr_sync.outcome import record_action
    for item in refreshed.values():
        if item.get("approve") == "yes" and item.get("actionable") and item.get("execution path") == "normal run" and QUALIFIED_EXECUTION is not None:
            continue
        record_action(config.get("_corporate_outcome"), "review_approval", item["source event"])
    if held:
        log.warning("Activity review holds %d source event(s); pending approvals remain in %s", len(held), state["path"])
    return blocked, held


def apply_corporate_review_holds(config: dict[str, Any], proposals: dict[str, Any],
                                rows: list[dict[str, Any]]) -> None:
    # Import here because corporate_actions reuses the private-file primitives.
    from ghostfolio_ibkr_sync.corporate_actions import candidate_held

    reconcile = config.get("_corporate_reconcile")
    if reconcile is None:
        return
    reconcile(rows)
    for item in proposals.values():
        decision = config.get("_corporate_decisions", {}).get(item.get("source account"))
        proposed = item.get("proposed values")
        if decision is not None and isinstance(proposed, dict) and candidate_held(decision, proposed):
            item["actionable"] = False
            item["status"] = "corporate-action evidence holds BUY/SELL"
