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

from ghostfolio_ibkr_sync import activity_reconciliation as reconciliation_rules
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
    state_path: Path
    state_original: bytes | None
    evidence: dict[str, Any]


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
                result[key] = value(item, key in ("approve", "decision"))
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


def proposal_key(event: str, destination: str, activity: str, execution: str = "normal run") -> str:
    return fingerprint([event, destination, activity, execution])


def qualify_proposals(document: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for item in document["proposals"].values():
        key = proposal_key(item["source event"], item["destination account"], item["activity id"],
                           item.get("execution path", "normal run"))
        if key in result:
            raise RuntimeError("Duplicate execution-path review key")
        result[key] = {**item, "key": key, "approve": None}
    return {"version": 1, "proposals": result}


def decode_review(document: dict[str, Any], evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read both public versions; keep the existing journal and internal map."""
    if document.get("version") == 3:
        return decode_compact(document, evidence)
    if type(document.get("version")) is int and document["version"] == 1:
        validate_document(document, "proposals")
        result = deepcopy(document)
        for item in result["proposals"].values():
            item["approve"] = None
        return qualify_proposals(result)
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
            proposals[key] = {**item, "approve": None}
    return qualify_proposals({"version": 1, "proposals": proposals})


def encode_review(document: dict[str, Any]) -> dict[str, Any]:
    proposals = document["proposals"]
    summary = {"source events": len({item["source event"] for item in proposals.values()}),
               "destination activities": len({item["activity id"] for item in proposals.values()}),
               "candidates": len(proposals), **document.get("summary", {})}
    result: dict[str, Any] = {"version": 3, "summary": summary, "groups": document.get("groups", {}),
                              "consistent": document.get("consistent", {}), **{section: {} for section in SECTIONS}}
    for key, item in document["proposals"].items():
        section = "reference_updates" if item["changed fields"] == ["comment"] else "activity_corrections"
        common = {"date", "symbol", "type", "currency", *NUMBERS, "comment", *item["changed fields"]}
        result[section][key] = {"key": key, "revision": item["review revision"],
            "source event": item["source event"], "destination activity": item["activity id"],
            "security": item["proposed values"].get("symbol"), "type": item["proposed values"].get("type"),
            "execution path": item.get("execution path", "normal run"),
            "match evidence": ("profile match" if item.get("automatic eligible") and item["match reason"] == "local calendar proximity"
                               else item["match reason"]), "profile authority": item.get("profile", "off"),
            "automatic eligible": item.get("automatic eligible", False),
            "status": item["status"], "operation fields": item["changed fields"],
            "current": {field: value for field, value in item["current values"].items() if field in common},
            "proposed": {field: value for field, value in item["proposed values"].items() if field in common},
            "numeric evidence": item.get("numeric evidence", {}),
            "observed differences": item.get("diagnostic differences", {}),
            "date context": item.get("profile date context") or item["date context"],
            "queue position": item.get("queue position"),
            "remaining eligible runs": item.get("remaining eligible runs"),
            "held scope": item["source event"] if proposal_holds(item) else None,
            "required action": ("Inspect or repair the reference that still claims this source; rejection grants no cleanup authority"
                if item.get("rejected") and item.get("recognized claim") else
                "Restore the missing or conflicting proof shown in status; yes cannot make a blocked proposal executable"
                if not item["actionable"] else
                "Use the documented historical preparation and separate operation authority"
                if item.get("execution path") == "historical maintenance" else
                "Wait for a later normal cycle; eligibility is re-evaluated"
                if item.get("automatic eligible") or item["approve"] == "yes" else
                "Association rejected; ordinary import checks still apply"
                if item.get("rejected") else "Read exact values; edit only decision to yes or reject between runs"),
            "decision": item["approve"]}
    unsigned = deepcopy(result)
    for section in SECTIONS:
        for item in unsigned[section].values():
            item["decision"] = None
    result["generation"] = fingerprint(unsigned)
    return result


def decode_compact(document: dict[str, Any], evidence: dict[str, Any] | None) -> dict[str, Any]:
    if (set(document) != {"version", "generation", "summary", "groups", "consistent", *SECTIONS}
            or any(not isinstance(document[name], dict) for name in ("summary", "groups", "consistent", *SECTIONS))):
        raise RuntimeError("Invalid compact review schema")
    if (not evidence or set(evidence) != {"version", "current", "previous", "aliases", "rebuild cooldown"}
            or evidence["version"] != 1 or not isinstance(evidence["aliases"], dict)):
        raise RuntimeError("Missing or invalid private review state")
    matched = None
    for generation in (evidence["current"], evidence["previous"]):
        if generation is None:
            continue
        if (not isinstance(generation, dict) or set(generation) != {"view", "document"}
                or encode_review(generation["document"]) != generation["view"]):
            raise RuntimeError("Corrupted private review state")
        if generation["view"]["generation"] == document["generation"]:
            matched = generation
    if matched is None:
        raise RuntimeError("Unknown review generation; preserve review and state")
    result = cast(dict[str, Any], deepcopy(evidence["current"]["document"]))
    for item in result["proposals"].values():
        item["approve"] = None
    seen: set[str] = set()
    for section in SECTIONS:
        for key, displayed in document[section].items():
            expected = matched["view"][section].get(key)
            if key in seen or expected is None or not isinstance(displayed, dict) or set(displayed) != set(expected):
                raise RuntimeError("Unknown or misplaced compact review proposal")
            seen.add(key)
            old = matched["document"]["proposals"][key]
            current = result["proposals"].get(key)
            same_view = {k: v for k, v in displayed.items() if k != "decision"} == {k: v for k, v in expected.items() if k != "decision"}
            if (current and same_view and old["review revision"] == current["review revision"]
                    and old["binding"] == current["binding"] and old["actionable"] == current["actionable"]
                    and old.get("execution path") == current.get("execution path")):
                current["approve"] = displayed["decision"]
    return result


def load_review(path: Path, inputs: Sequence[Path] = ()) -> dict[str, Any]:
    """Read bound compact decisions without a write or lock side effect."""
    state_path = Path(str(path) + ".state.yaml")
    for target in (path, state_path):
        safe_path(target, inputs)
    raw = read_yaml(path.read_bytes())
    evidence = read_yaml(state_path.read_bytes()) if state_path.exists() else None
    return decode_review(raw, evidence)


def open_review(filename: str, input_files: Sequence[str], *, rebuild: bool = False) -> ReviewState:
    path = Path(filename).absolute()
    journal_path = Path(str(path) + ".journal.yaml")
    state_path = Path(str(path) + ".state.yaml")
    lock_path = Path(str(path) + ".lock")
    inputs = [Path(item).absolute() for item in input_files]
    for target in (path, state_path, journal_path, lock_path):
        safe_path(target, inputs)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original, journal_original = file_bytes(path), file_bytes(journal_path)
        state_original = file_bytes(state_path)
        evidence: dict[str, Any] = read_yaml(state_original) if state_original is not None and not rebuild else {
            "version": 1, "current": None, "previous": None, "aliases": {}, "rebuild cooldown": 0}
        if state_original is not None and not rebuild and set(evidence) != {
                "version", "current", "previous", "aliases", "rebuild cooldown"}:
            raise RuntimeError("Invalid private review state")
        if original is None and state_original is not None and not rebuild:
            raise RuntimeError("Review view missing with existing private state")
        document: dict[str, Any] = read_yaml(original) if original is not None and not rebuild else {"version": 1, "proposals": {}}
        journal = (read_yaml(journal_original) if journal_original is not None
                   else {"version": 1, "entries": {}})
        document = decode_review(document, evidence)
        if journal.get("version") not in (1, 2):
            raise RuntimeError("Invalid review journal version")
        validate_document({**journal, "version": 1}, "entries")
        if rebuild:
            evidence["rebuild cooldown"] = 2
        for key in document["proposals"]:
            evidence["aliases"].setdefault(key, key)
        for item in document["proposals"].values():
            legacy_key = fingerprint([item["source event"], item["destination account"], item["activity id"]])
            evidence["aliases"].setdefault(legacy_key, item["key"])
        return {"path": path, "journal_path": journal_path, "inputs": inputs, "lock": fd,
                "original": original, "journal_original": journal_original,
                "document": document, "journal": journal, "state_path": state_path,
                "state_original": state_original, "evidence": evidence}
    except BaseException:
        os.close(fd)
        raise


def close_review(state: ReviewState) -> None:
    os.close(state["lock"])


def assert_unchanged(state: ReviewState) -> None:
    for target, original in ((state["path"], state["original"]),
                             (state["state_path"], state["state_original"]),
                             (state["journal_path"], state["journal_original"])):
        safe_path(target, state["inputs"])
        if file_bytes(target) != original:
            raise RuntimeError("Review or journal changed during this run; writes blocked")


def atomic_bytes(path: Path, data: bytes) -> bytes:
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


def atomic_yaml(path: Path, document: dict[str, Any]) -> bytes:
    return atomic_bytes(path, yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode())


def publish_review(state: ReviewState, document: dict[str, Any]) -> None:
    assert_unchanged(state)
    view = encode_review(document)
    previous = state["evidence"]["current"]
    # Keep the prior view until its successor is durable. A crash can leave
    # the operator view one generation behind, with recoverable decisions.
    if previous and previous["view"]["generation"] == view["generation"]:
        previous = state["evidence"]["previous"]
    evidence = {**state["evidence"], "previous": previous,
                "current": {"view": view, "document": deepcopy(document)}}
    state["state_original"] = atomic_yaml(state["state_path"], evidence)
    state["evidence"] = evidence
    assert_unchanged(state)
    state["original"] = atomic_yaml(state["path"], view)
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


def candidate_reason(row: dict[str, Any], event: dict[str, Any], exact_exists: bool,
                     timezone: str = "UTC") -> str | None:
    reference = marker_of(row)
    if reference == event["event"]:
        return "exact reference"
    if reference in event["legacy"]:
        return "legacy alias" if row.get("accountId") == event["destination account"] else None
    if exact_exists or reference:
        return None
    target = event["values"]
    asset = profile(row)
    if (row.get("accountId") != event["destination account"] or row.get("type") != target["type"]
            or reconciliation_rules.denomination(row.get("currency", ""))[0] != reconciliation_rules.denomination(target["currency"])[0]
            or not activity_is_active(row)
            or asset.get("dataSource") != "YAHOO"
            or (asset.get("isin") and event["isin"] and asset["isin"] != event["isin"])
            or not (asset.get("symbol") == target["symbol"]
                    or (event["isin"] and asset.get("isin") == event["isin"]))):
        return None
    instant(row.get("date"))
    instant(target["date"])
    eligible, _ = reconciliation_rules.date_eligible("permissive", target["date"], row["date"], target["type"], timezone)
    return "local calendar proximity" if eligible else None


def automatic_pairs(events: dict[str, dict[str, Any]], rows: list[dict[str, Any]],
                    name: str, timezone: str, rejected: set[tuple[str, str]] | None = None
                    ) -> dict[tuple[str, str], dict[str, Any]]:
    """Build all eligible edges before selecting mutually unique pairs."""
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for event_id, event in events.items():
        exact = any(marker_of(row) == event_id or marker_of(row) in event["legacy"] for row in rows)
        for row in rows:
            if (event_id, row["id"]) in (rejected or set()):
                continue
            try:
                reason = candidate_reason(row, event, exact, timezone)
                reference = marker_of(row)
                asset, source = profile(row), event["values"]
                recognized = reference == event_id or (reference in event["legacy"]
                              and (source["type"] != "DIVIDEND" or event["legacy safe"]))
                if (reason is None or name == "off" or (name == "conservative" and not recognized)
                        or row.get("accountId") != event["destination account"]
                        or row.get("type") != source["type"] or not activity_is_active(row)
                        or asset.get("dataSource") != "YAHOO"
                        or asset.get("symbol") != source["symbol"]
                        or (asset.get("isin") and event["isin"] and asset["isin"] != event["isin"])
                        or (reference and reference.startswith("IBKR#v2#") and reference != event_id)):
                    continue
                current = values_of(row)
                if reference in event["legacy"] and source["type"] != "DIVIDEND":
                    # Mapping authorizes identity only. No financial tolerance
                    # can be used to fold a later correction into migration.
                    edges[event_id, row["id"]] = {"numeric evidence": {}, "profile date context": {"timezone": timezone}}
                    continue
                date_ok, date_context = reconciliation_rules.date_eligible(name, source["date"], current["date"], source["type"], timezone)
                numbers = reconciliation_rules.numeric_evidence(event, current)
                quantity_ok = (numeric(source["quantity"]) == numeric(current["quantity"])
                               or source["type"] == "DIVIDEND")
                amount_ok = reconciliation_rules.gross_within_limits(name,
                    Decimal(numbers["source gross"]), Decimal(numbers["destination gross"]), numbers["currency"])
                if date_ok and quantity_ok and (amount_ok or numbers["calculation residue"]):
                    edges[event_id, row["id"]] = {"numeric evidence": numbers, "profile date context": date_context}
            except (RuntimeError, ValueError, ArithmeticError, KeyError):
                continue
    return {pair: evidence for pair, evidence in edges.items()
            if sum(other[0] == pair[0] for other in edges) == 1
            and sum(other[1] == pair[1] for other in edges) == 1}


PROPOSAL_FIELDS = {"key", "source account", "source event", "destination account", "activity id",
                   "match reason", "current values", "proposed values", "changed fields", "status",
                   "approve", "actionable", "binding", "date context", "review revision"}
DISPLAY_FIELDS = {"section", "evidence level", "execution path"}
AUTOMATIC_FIELDS = {"automatic eligible", "profile", "numeric evidence", "profile date context"}
EVIDENCE_FIELDS = {"source evidence", "diagnostic differences"}
REJECTION_FIELDS = {"rejection binding", "rejected", "rejection cooldown", "recognized claim"}
QUEUE_FIELDS = {"first eligible", "queue position", "remaining eligible runs"}


def association_binding(event: dict[str, Any], current: dict[str, Any],
                        occupied: list[Any], reference: str | None) -> str:
    fields = ("id", "accountId", "accountUserId", "userId", "symbolProfileId", "assetProfile",
              "date", "quantity", "unitPrice", "currency", "symbol", "type")
    target = {field: current.get(field) for field in fields}
    source = {field: value for field, value in event["values"].items() if field not in ("fee", "tags")}
    raw = event["source evidence"]
    if event["values"]["type"] in ("BUY", "SELL"):
        raw = {field: raw.get(field) for field in ("quantity", "tradePrice", "dateTime", "currency",
                "buySell", "tradeID", "accountId", "symbol", "isin", "assetCategory")}
    else:
        raw = {"payments": raw.get("payments"), "quantities": [row.get("quantity") for row in raw.get("accruals", [])]}
    return fingerprint([event["source account"], event["destination account"], source, raw,
                        target, reference, event["mapping"], occupied])


def proposal_holds(item: dict[str, Any]) -> bool:
    if not item.get("rejected"):
        return True
    if item.get("recognized claim") or item["status"] == "source unavailable":
        return True
    return item["status"] not in ("rejected association", "rejected target absent")


def refresh_proposals(previous: dict[str, Any], events: dict[str, dict[str, Any]],
                      rows: list[dict[str, Any]], accounts: dict[str, str],
                      journal_bindings: set[tuple[str, str, str]] | None = None,
                      *, reconciliation: str = "off", timezone: str = "UTC",
                      held_events: set[str] | None = None
                      ) -> tuple[dict[str, Any], set[str]]:
    """Rebuild evidence; file fields never become replacement input."""
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise RuntimeError("Duplicate destination activity IDs")
    for key, old in previous.items():
        if (set(old) - AUTOMATIC_FIELDS - EVIDENCE_FIELDS - REJECTION_FIELDS - QUEUE_FIELDS not in (PROPOSAL_FIELDS, PROPOSAL_FIELDS | DISPLAY_FIELDS) or old["key"] != key
                or (old["destination account"] != accounts.get(old["source account"])
                    and (old["source event"], old["destination account"], old["activity id"])
                    not in (journal_bindings or set()))
                or not isinstance(old["source event"], str)
                or not old["source event"].startswith(f"IBKR#v2#{old['source account']}:")
                or not isinstance(old["activity id"], str)
                or not isinstance(old["review revision"], str)
                or re.fullmatch(r"[0-9a-f]{32}", old["review revision"]) is None
                or key != proposal_key(old["source event"], old["destination account"], old["activity id"], old.get("execution path", "normal run"))):
            raise RuntimeError("Unbound or invalid review proposal")
    result: dict[str, Any] = {}
    satisfied: set[str] = set()
    automatic = automatic_pairs(events, rows, reconciliation, timezone)
    migration_pairs = automatic_pairs(events, rows, "permissive", timezone)
    historical_pairs = {(item["source event"], item["destination account"], item["activity id"])
                        for item in previous.values() if item.get("execution path") == "historical maintenance"}
    for event_id, event in sorted(events.items()):
        exact_exists = any(marker_of(row) == event_id or (marker_of(row) in event["legacy"]
                           and row.get("accountId") == event["destination account"]) for row in rows)
        occupied = sorted((row["id"], row.get("accountId"), marker_of(row)) for row in rows
                          if marker_of(row) == event_id or (marker_of(row) in event["legacy"]
                          and row.get("accountId") == event["destination account"]))
        for row in sorted(rows, key=lambda item: item["id"]):
            try:
                reason = candidate_reason(row, event, exact_exists, timezone)
            except RuntimeError:
                continue
            if reason is None:
                continue
            if (event_id, event["destination account"], row["id"]) in historical_pairs:
                continue
            key = proposal_key(event_id, event["destination account"], row["id"])
            current: dict[str, Any] = {}
            proposed = {key: value for key, value in event["values"].items() if key in REPLACED}
            status, actionable = "pending", True
            changes: list[str] = []
            diagnostics: dict[str, Any] = {}
            try:
                current = values_of(row)
                proposed = {**current, **proposed}
                proposed["comment"] = replacement_comment(row, event)
                diagnostics = {field: {"current": current[field], "source": proposed[field]}
                               for field in changed_fields(current, proposed)}
                legacy_trade = marker_of(row) in event["legacy"] and event["values"]["type"] != "DIVIDEND"
                legacy_dividend = (marker_of(row) in event["legacy"] and event["values"]["type"] == "DIVIDEND"
                                   and (event["legacy safe"] or (event_id, row["id"]) in migration_pairs))
                if legacy_trade or legacy_dividend:
                    proposed = {**current, "comment": proposed["comment"]}
                changes = changed_fields(current, proposed)
                payload = update_payload(row, proposed)
                expected_row(row, payload)
                scope = event.get("dividend scope")
                if scope:
                    expected_ids = set(scope["events"])
                    covered = {marker_of(item) for item in rows} & expected_ids
                    if covered and covered != expected_ids:
                        raise RuntimeError("Partial versioned dividend action coverage")
                    conflicting: list[str] = []
                    for other_row in rows:
                        identity = parse_versioned_activity_identity(other_row.get("comment"), other_row.get("type"))
                        if identity and identity[1] == "DIVIDEND" and marker_of(other_row) not in expected_ids:
                            other_key = identity[0], str(marker_of(other_row))
                            contexts = {other_key: [dividend_context(profile(other_row), other_row.get("date"))]}
                            actions = {(event["source account"], identity.rsplit(":", 1)[1]) for identity in expected_ids}
                            if dividend_action_conflict(cast(DividendGroup, scope), event["values"]["symbol"], actions,
                                                        {"versioned_identities": {other_key}, "versioned_dividend_context": contexts}):
                                conflicting.append(str(other_row["id"]) + " (" + str(marker_of(other_row)) + ")")
                    if conflicting:
                        raise RuntimeError("Conflicting or unknown dividend action context: " + ", ".join(sorted(conflicting)))
                if row.get("accountId") != event["destination account"]:
                    raise RuntimeError("Conflicting destination account ownership")
                if len(occupied) > 1 and not (legacy_dividend and (event_id, row["id"]) in migration_pairs
                                             and not any(item[2] == event_id for item in occupied)):
                    raise RuntimeError("Reference occupancy conflict")
                if legacy_trade and sum(other["destination account"] == event["destination account"]
                                        and marker_of(row) in other["legacy"] for other in events.values()) != 1:
                    raise RuntimeError("Conflicting current source claims to legacy activity")
                if marker_of(row) in event["legacy"] and not legacy_trade and not legacy_dividend:
                    raise RuntimeError("legacy aggregate cannot identify one action")
                changes = changed_fields(current, proposed)
                if not changes and marker_of(row) == event_id:
                    if event_id in (held_events or set()):
                        raise RuntimeError("Relevant corporate-action evidence holds this activity")
                    satisfied.add(event_id)
                    continue
            except (RuntimeError, ValueError, OverflowError, UnicodeError) as exc:
                actionable, status = False, str(exc)
                changes = sorted(REPLACED) if not current else changes
            binding = fingerprint([event, current, occupied])
            item = {"key": key, "source account": event["source account"], "source event": event_id,
                    "destination account": event["destination account"], "activity id": row["id"],
                    "match reason": reason, "current values": current, "proposed values": proposed,
                    "changed fields": changes, "status": status, "approve": None,
                    "actionable": actionable, "binding": binding, "review revision": uuid4().hex,
                    "source evidence": plain({**event, "payload": wire_values(event["payload"])}),
                    "diagnostic differences": diagnostics,
                    "date context": "Full instants; proximity uses local calendar dates"}
            item.update(section="reference_updates" if changes == ["comment"] else "activity_corrections",
                        **{"evidence level": ("blocked" if not actionable else
                                             "exact" if reason == "exact reference" else "probable"),
                           "execution path": "normal run"})
            old = previous.get(key)
            if old:
                ignored = {"approve", "status", "review revision", *AUTOMATIC_FIELDS, *EVIDENCE_FIELDS, *REJECTION_FIELDS, *QUEUE_FIELDS}
                comparison = {k: v for k, v in old.items() if k not in ignored}
                if comparison == {k: v for k, v in item.items() if k not in ignored}:
                    item["approve"] = old["approve"] if actionable else None
                    item["review revision"] = old["review revision"]
                else:
                    item["status"] = "changed evidence; approval cleared" if actionable else status
            auto = automatic.get((event_id, row["id"]))
            try:
                numbers = reconciliation_rules.numeric_evidence(event, current)
            except (RuntimeError, KeyError, ArithmeticError, ValueError):
                numbers = {"cause": "Missing or unsupported exact financial evidence"}
            item.update({"automatic eligible": bool(auto and actionable), "profile": reconciliation,
                         "numeric evidence": numbers,
                         "profile date context": auto["profile date context"] if auto else {}})
            association = association_binding(event, current, occupied, marker_of(row)) if current else None
            item.update({"rejection binding": association, "rejected": False, "rejection cooldown": 0,
                         "recognized claim": marker_of(row) == event_id or marker_of(row) in event["legacy"]})
            if old and (old.get("approve") == "reject" or (old.get("rejected") and old.get("approve") is None)):
                if association and association == old.get("rejection binding") and activity_is_active(row):
                    item.update({"approve": "reject", "rejected": True, "automatic eligible": False,
                                 "status": "rejected association"})
                else:
                    item.update({"approve": None, "rejection cooldown": 1, "automatic eligible": False,
                                 "status": "association changed; rejection cleared"})
            elif old and old.get("rejection cooldown"):
                # This blank candidate was published during the prior cycle.
                item["rejection cooldown"] = 0
            result[key] = item
    # Keep missing targets and unavailable sources; reassignment needs positive evidence.
    for key, old in previous.items():
        event_id = old["source event"]
        if event_id in satisfied or key in result:
            continue
        if old.get("execution path") == "historical maintenance":
            result[key] = {**old, "automatic eligible": False}
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
            if retained_row is None and old.get("rejected"):
                result[key].update({"status": "rejected target absent", "approve": "reject"})
        elif old.get("rejected"):
            result[key] = {**old, "status": "association changed; rejection cleared", "rejected": False,
                           "approve": None, "actionable": False, "automatic eligible": False}
    result = {key: item for key, item in result.items() if item["source event"] not in satisfied}
    rejected = {(item["source event"], item["activity id"]) for item in result.values() if item.get("rejected")}
    automatic = automatic_pairs(events, rows, reconciliation, timezone, rejected)
    for item in result.values():
        item["automatic eligible"] = bool(item.get("execution path") == "normal run"
            and item["actionable"] and not item.get("rejection cooldown")
            and item["source event"] in events and (item["source event"], item["activity id"]) in automatic)
        old = previous.get(item["key"])
        retained = old.get("first eligible") if old and old["review revision"] == item["review revision"] else None
        eligible = item.get("automatic eligible") or (item["approve"] == "yes" and item["actionable"])
        item["first eligible"] = retained or (datetime.now(UTC).isoformat() if eligible else None)
    return result, {item["source event"] for item in result.values() if proposal_holds(item)}



def approved_proposals(proposals: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    blocked: set[str] = set()
    approved = []
    for item in proposals.values():
        choice = item["approve"]
        if choice is None:
            continue
        if type(choice) is str and choice == "yes":
            approved.append(item)
        elif choice == "reject" and item.get("rejected"):
            continue
        else:
            log.warning("Review choice skipped for account %s activity %s; only literal yes approves",
                        item["destination account"], item["activity id"])
    for item in approved:
        if (sum(other["source event"] == item["source event"] for other in approved) > 1
                or sum(other["activity id"] == item["activity id"] for other in approved) > 1):
            blocked.add(item["destination account"])
            log.error("Conflicting review approvals for account %s; financial writes blocked", item["destination account"])
    return [item for item in approved if item["destination account"] not in blocked], blocked


def selected_proposals(proposals: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    manual, blocked = approved_proposals(proposals)
    selected = manual + [item for item in proposals.values() if item.get("automatic eligible")
                          and item["approve"] is None and item["actionable"]
                          and item.get("execution path") == "normal run"]
    for item in selected:
        if (sum(other["source event"] == item["source event"] for other in selected) > 1
                or sum(other["activity id"] == item["activity id"] for other in selected) > 1):
            blocked.add(item["destination account"])
    return [item for item in selected if item["destination account"] not in blocked], blocked


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
        if (set(entry) not in (JOURNAL_FIELDS, JOURNAL_FIELDS | {"authority", "eligibility"})
                or entry.get("authority", "manual") not in ("manual", "conservative", "balanced", "permissive")
                or entry["host"] != config["ghost_host"]
                or entry["status"] not in ("pending", "confirmed")
                or not isinstance(entry["before"], dict) or not isinstance(entry["after"], dict)
                or entry["before"].get("id") != entry["activity id"]
                or entry["after"].get("id") != entry["activity id"]
                or entry["before"].get("accountId") != entry["destination account"]
                or entry["after"].get("accountId") != entry["destination account"]
                or entry["proposal key"] not in (
                    fingerprint([entry["source event"], entry["destination account"], entry["activity id"]]),
                    proposal_key(entry["source event"], entry["destination account"], entry["activity id"]))
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
    from ghostfolio_ibkr_sync.config import timezone_preview_reason
    from ghostfolio_ibkr_sync.outcome import RECONCILIATION_COUNTS

    simulated = bool(config.get("dry_run") or timezone_preview_reason())
    rebuilt_cooling = state["evidence"]["rebuild cooldown"] > 1
    if not simulated and state["evidence"]["rebuild cooldown"]:
        state["evidence"]["rebuild cooldown"] -= 1
    cooling: set[str] = set()
    counts = dict.fromkeys(RECONCILIATION_COUNTS, 0)
    consistent: dict[str, Any] = {}

    def publish(proposals: dict[str, Any]) -> None:
        publish_review(state, {"version": 1, "proposals": proposals, "consistent": consistent,
            "groups": reconciliation_rules.group_diagnosis(events, proposals),
            "summary": {"profile": config.get("activity_reconciliation", "off"),
                        "simulation": simulated, "outcomes": dict(counts),
                        "queue estimate": "Current eligible inventory; later runs revalidate; no completion promise"}})
    # Journal-owned historical proposals may outlive a configured account.
    # This does not permit dispatch without a fresh source and matching target.
    journal_bindings = {(entry["source event"], entry["destination account"], entry["activity id"])
                        for entry in state["journal"]["entries"].values()}

    def refresh(previous: dict[str, Any], current_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], set[str]]:
        from ghostfolio_ibkr_sync.corporate_actions import candidate_held

        corporate_held = {event_id for event_id, event in events.items()
            if (decision := config.get("_corporate_decisions", {}).get(event["source account"])) is not None
            and candidate_held(decision, event["payload"])}
        fresh, current_held = refresh_proposals(previous, events, current_rows, accounts, journal_bindings,
            reconciliation=config.get("activity_reconciliation", "off"), timezone=os.environ.get("TZ", "").strip(),
            held_events=corporate_held)
        cooling.update(key for key, item in fresh.items() if item.get("rejection cooldown"))
        for key, item in fresh.items():
            if key in cooling:
                item["rejection cooldown"] = 1
            if key in cooling or rebuilt_cooling:
                item["automatic eligible"] = False
        return fresh, current_held

    rows = snapshot_rows(config)
    # Validate every file binding before any journal completion or correction.
    refreshed, held = refresh(original, rows)
    blocked: set[str] = set()
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
            counts["manually corrected" if entry.get("authority", "manual") == "manual" else "automatically corrected"] += 1
        else:
            unresolved.add(entry["destination account"])
            unresolved_events.add(entry["source event"])
    blocked |= unresolved
    consumed = {(state["evidence"]["aliases"].get(entry["proposal key"], entry["proposal key"]), entry["review revision"])
                for entry in state["journal"]["entries"].values() if entry["status"] == "confirmed"}
    remaining_previous = {key: item for key, item in original.items()
                          if (key, item["review revision"]) not in consumed}
    refreshed, held = refresh(remaining_previous, snapshot_rows(config))
    apply_corporate_review_holds(config, refreshed, snapshot_rows(config))
    for event_id, event in events.items():
        if event_id in unresolved_events or any(item["source event"] == event_id for item in refreshed.values()):
            continue
        matches = [row for row in rows if marker_of(row) == event_id]
        if len(matches) == 1:
            consistent[event_id] = {"destination activity": matches[0]["id"], "security": event["values"]["symbol"],
                                    "type": event["values"]["type"], "status": "already consistent"}
    counts["already consistent"] = len(consistent)
    approved, refreshed_blocked = selected_proposals(refreshed)
    blocked |= refreshed_blocked
    # Simulation cannot consume a proposal whose pending request now appears applied.
    for key, old in original.items():
        if old["source event"] in unresolved_events:
            refreshed[key] = {**old, "status": "unresolved request; account writes blocked"}
    for position, item in enumerate(sorted(approved, key=lambda item: (item.get("first eligible") or "", item["key"])), 1):
        item["queue position"] = position
        item["remaining eligible runs"] = position
    publish(refreshed)
    executed = 0
    planned = 0
    previews: set[str] = set()
    for item in sorted(approved, key=lambda item: (item.get("first eligible") or "", item["key"])):
        account = item["destination account"]
        if (account in blocked or item["source event"] not in events or not item["actionable"]
                or item["key"] not in refreshed or item.get("execution path") != "normal run"):
            continue
        qualification = QUALIFIED_EXECUTION
        if qualification is None:
            log.warning("Reviewed correction retained: exact-image execution budget not qualified")
            continue
        image, limit, delay = qualification
        if not image or type(limit) is not int or limit < 1 or not 0 <= delay < float("inf"):
            raise RuntimeError("Invalid qualified correction execution budget")
        if executed + planned >= limit:
            continue
        if simulated:
            planned += 1
            counts["would correct"] += 1
            previews.add(item["key"])
            item["status"] = "would correct"
            log.info("DRY RUN would correct activity %s; authority=%s; fields=%s", item["activity id"],
                     "manual" if item["approve"] == "yes" else item["profile"], item["changed fields"])
            continue
        if executed and delay:
            time.sleep(delay)
        assert_unchanged(state)
        fresh_rows = snapshot_rows(config)
        fresh, _ = refresh(refreshed, fresh_rows)
        apply_corporate_review_holds(config, fresh, fresh_rows)
        current = fresh.get(item["key"])
        fresh_selection, fresh_conflicts = selected_proposals(fresh)
        blocked |= fresh_conflicts
        authorized = current is not None and any(candidate["key"] == item["key"] for candidate in fresh_selection)
        if not authorized or current is None or account in blocked or not current["actionable"]:
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
                 "status": "pending", "verified result": None,
                 "authority": "manual" if current["approve"] == "yes" else current["profile"],
                 "eligibility": {"timezone": os.environ.get("TZ", "").strip(),
                                 "dates": current.get("profile date context", {}),
                                 "numeric evidence": current.get("numeric evidence", {})}}
        state["journal"]["version"] = 2
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
        counts["manually corrected" if entry["authority"] == "manual" else "automatically corrected"] += 1
        refreshed = {key: candidate for key, candidate in refreshed.items()
                     if candidate["source event"] != item["source event"]}
        publish(refreshed)
    # Rediscover new context and release reassigned alternatives after confirmed PUTs.
    if not simulated and executed:
        refreshed, _ = refresh(refreshed, snapshot_rows(config))
    apply_corporate_review_holds(config, refreshed, snapshot_rows(config))
    deferred, conflicts = selected_proposals(refreshed)
    blocked |= conflicts
    counts["automatic work deferred"] = len({item["source event"] for item in deferred
        if item["destination account"] not in blocked and item["key"] not in previews})
    counts["rejected association"] = sum(bool(item.get("rejected")) for item in refreshed.values())
    counts["blocked"] = len(unresolved_events | {item["source event"] for item in refreshed.values()
        if not item["actionable"] or item["destination account"] in blocked})
    counts["manual review required"] = len({item["source event"] for item in refreshed.values()
        if item["actionable"] and not item.get("automatic eligible") and item["approve"] != "yes"
        and not item.get("rejected")})
    queue = [item for item in deferred if item["destination account"] not in blocked and item["key"] not in previews]
    for position, item in enumerate(sorted(queue, key=lambda item: (item.get("first eligible") or "", item["key"])), 1):
        item["queue position"] = position
        item["remaining eligible runs"] = position
        if item["destination account"] not in blocked and item["key"] not in previews:
            item["status"] = "automatic work deferred"
    publish(refreshed)
    outcome = config.get("_corporate_outcome")
    if outcome is not None:
        outcome["reconciliation"] = dict(counts)
    held = {item["source event"] for item in refreshed.values() if proposal_holds(item)} | unresolved_events
    config["_review_rejected"] = {}
    for item in refreshed.values():
        if item.get("rejected") and item["source event"] in events:
            config["_review_rejected"].setdefault(item["source event"], set()).add(item["activity id"])
    pending = {entry["source event"] for entry in state["journal"]["entries"].values()
               if entry["status"] != "confirmed"}
    report_review_outcome(state, config, refreshed, held, pending)
    return blocked, held



def report_review_outcome(state: ReviewState, config: dict[str, Any], proposals: dict[str, Any],
                          held: set[str], uncertain: set[str]) -> None:
    """Report decisions without changing approvals, holds or execution state."""
    from ghostfolio_ibkr_sync.outcome import ACTION_INSTRUCTIONS, record_action

    outcome = config.get("_corporate_outcome")
    deferred: set[str] = set()
    for key, item in sorted(proposals.items()):
        event = item["source event"]
        if event in uncertain:
            reason = "review_uncertain"
        elif item.get("execution path") == "historical maintenance":
            reason = "review_maintenance"
        elif item.get("rejected") and not proposal_holds(item):
            continue
        elif item.get("rejected"):
            reason = "review_evidence"
        elif (not item.get("actionable") or item.get("status") in
              ("source unavailable", "target missing or unavailable") or QUALIFIED_EXECUTION is None):
            reason = "review_evidence"
        elif item.get("approve") == "yes" or item.get("automatic eligible"):
            deferred.add(event)
            log.info("Activity review deferred automatic work: %s; container path=%s; section=%s; key=%s; "
                     "approval retained; hold remains; simulation=%s", event, state["path"],
                     item.get("section", "proposals"), key, bool(config.get("dry_run")))
            continue
        else:
            reason = "review_approval"
        log.warning("User action required: %s; ACTIVITY_REVIEW_FILE container path=%s; section=%s; "
                    "key=%s; held event=%s; reason=%s; %s; only lowercase literal yes approves "
                    "an eligible normal-run proposal; simulation=%s", reason, state["path"],
                    item.get("section", "proposals"), key, event, item.get("status"),
                    ACTION_INSTRUCTIONS[reason], bool(config.get("dry_run")))
        record_action(outcome, reason, event)
    for event in uncertain:
        record_action(outcome, "review_uncertain", event)
        log.warning("Review journal needs exact readback; container path=%s; held event=%s; %s",
                    state["journal_path"], event, ACTION_INSTRUCTIONS["review_uncertain"])
    if outcome is not None:
        outcome["review_held"] = set(held)
        outcome["deferred"] = deferred - uncertain
    if held:
        log.warning("Activity review holds %d unique source event(s); %d proposal(s); "
                    "ACTIVITY_REVIEW_FILE container path=%s", len(held), len(proposals), state["path"])


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
