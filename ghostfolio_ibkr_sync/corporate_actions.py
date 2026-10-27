"""Corporate-action evidence and conservative BUY/SELL decisions.

This module never dispatches a financial request. Stored conclusions are reports,
not authority: each run reparses retained source bytes and reads the destination.
"""

import fcntl
import hashlib
import logging
import os
import re
import stat
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, DecimalException
from fractions import Fraction
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from ghostfolio_ibkr_sync.activity_review import (
    atomic_yaml,
    file_bytes,
    fingerprint,
    read_yaml,
    safe_path,
)
from ghostfolio_ibkr_sync.ghostfolio import activity_date_is_current, activity_is_active
from ghostfolio_ibkr_sync.ibkr import (
    IBKR_MAX_XML_BYTES,
    parse_ibkr_datetime,
)
from ghostfolio_ibkr_sync.outcome import RunOutcome, record_action

log = logging.getLogger(__name__)


class Event(TypedDict):
    rows: list[dict[str, str]]
    candidate_ratio: list[int] | None
    reasons: list[str]
    symbols: list[str]
    isins: list[str]
    held: bool
    conclusions: dict[str, str]


class Inventory(TypedDict):
    source: str
    sha256: str
    period: list[str]
    section_present: bool
    account_held: bool
    events: dict[str, Event]
    trades: list[dict[str, str]]
    positions: list[dict[str, str]]
    trades_present: bool
    cash: list[dict[str, str]]


def number(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise RuntimeError("Invalid corporate-action decimal")
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError
        return result
    except DecimalException, ValueError:
        raise RuntimeError("Invalid corporate-action decimal") from None


def inventory(xml: str, source: str) -> Inventory:
    """Recognize events without certifying quantity, timing or treatment."""
    if len(xml.encode()) > IBKR_MAX_XML_BYTES:
        raise RuntimeError("Corporate-action report exceeds the source size limit")
    root = ET.fromstring(xml)
    accounts = {
        node.get("accountId", "").strip() for node in root.iter("AccountInformation")
    }
    if accounts != {source}:
        raise RuntimeError("Corporate-action source account mismatch")
    statements = list(root.iter("FlexStatement"))
    if len(statements) != 1 or statements[0].get("accountId") not in (None, source):
        raise RuntimeError("Corporate-action source account statement mismatch")
    statement = statements[0]
    period = [statement.get(key, "") for key in ("fromDate", "toDate")]
    section = statement.find("CorporateActions")
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for node in statement.iter("CorporateAction"):
        row = dict(node.attrib)
        if row.get("accountId") != source:
            raise RuntimeError("Corporate-action source account row mismatch")
        key = (
            row.get("actionID")
            or "unidentified-"
            + hashlib.sha256(repr(sorted(row.items())).encode()).hexdigest()
        )
        if row not in grouped[key]:
            grouped[key].append(row)
    events: dict[str, Event] = {}
    unbounded = (
        section is None
        or len(statement.findall("CorporateActions")) != 1
        or len(list(statement.iter("CorporateAction")))
        != (len(list(section.iter("CorporateAction"))) if section is not None else 0)
    )
    for key, rows in sorted(grouped.items()):
        events[key] = event_inventory(rows)
        if any(
            not row.get("conid") or not row.get("isin") or not row.get("symbol")
            for row in rows
        ):
            unbounded = True
    return {
        "source": source,
        "sha256": hashlib.sha256(xml.encode()).hexdigest(),
        "period": period,
        "section_present": section is not None,
        "account_held": unbounded,
        "events": events,
        "trades": [dict(row.attrib) for row in statement.iter("Trade")],
        "positions": [dict(row.attrib) for row in statement.iter("OpenPosition")],
        "trades_present": statement.find("Trades") is not None,
        "cash": [dict(row.attrib) for row in statement.iter("CashTransaction")],
    }


def event_inventory(rows: list[dict[str, str]]) -> Event:
    """Recompute conclusions when compatible query columns add evidence."""
    rows.sort(key=lambda row: sorted(row.items()))
    reasons: set[str] = set()
    ratios: set[tuple[int, int]] = set()
    transactions: dict[str, dict[str, str]] = {}
    for row in rows:
        required = (
            "accountId",
            "type",
            "actionID",
            "transactionID",
            "levelOfDetail",
            "conid",
            "isin",
            "symbol",
            "quantity",
            "currency",
            "reportDate",
        )
        if any(not row.get(field, "").strip() for field in required):
            reasons.add("missing_fields")
        if row.get("levelOfDetail") != "DETAIL":
            reasons.add("unsupported_detail")
        try:
            number(row.get("quantity"))
            for field in ("proceeds", "amount", "fifoPnlRealized", "value"):
                if row.get(field):
                    number(row[field])
        except RuntimeError:
            reasons.add("invalid_number")
        if (
            not re.fullmatch(
                r"[0-9]{8};[0-9]{6} [A-Za-z_+:/0-9-]+", row.get("dateTime", "")
            )
            or parse_ibkr_datetime(row.get("dateTime")) is None
        ):
            reasons.add("invalid_processing_time")
        try:
            datetime.strptime(row.get("reportDate", ""), "%Y%m%d")
        except ValueError:
            reasons.add("invalid_report_date")
        descriptions = [
            row[field]
            for field in ("description", "actionDescription")
            if row.get(field)
        ]
        if not descriptions:
            reasons.add("ratio_unproven")
        for description in descriptions:
            matches = re.findall(
                r"\bSPLIT ([1-9][0-9]*) FOR ([1-9][0-9]*)\b", description
            )
            if len(matches) != 1:
                reasons.add("ratio_unproven")
            else:
                ratios.add((int(matches[0][0]), int(matches[0][1])))
        if row.get("securityIDType") == "ISIN" and row.get("securityID") != row.get(
            "isin"
        ):
            reasons.add("conflicting_security_identity")
        if row.get("transactionID") in transactions:
            reasons.add("conflicting_transaction")
        transactions[row.get("transactionID", "")] = row
    if len(ratios) != 1:
        reasons.add("conflicting_ratio")
    ratio = list(next(iter(ratios))) if len(ratios) == 1 else None
    kinds = {row.get("type") for row in rows}
    if kinds == {"FS"}:
        if len(rows) != 1 or not ratio or ratio[0] <= ratio[1]:
            reasons.add("incomplete_forward_shape")
        try:
            if number(rows[0].get("quantity")) <= 0:
                reasons.add("incomplete_forward_shape")
        except RuntimeError:
            reasons.add("incomplete_forward_shape")
        reasons.add("before_quantity_unproven")
    elif kinds == {"RS"}:
        try:
            negative = [row for row in rows if number(row.get("quantity")) < 0]
            positive = [row for row in rows if number(row.get("quantity")) > 0]
            if (
                len(rows) != 2
                or len(negative) != 1
                or len(positive) != 1
                or ratio is None
                or ratio[0] >= ratio[1]
                or number(positive[0]["quantity"]) * ratio[1]
                != -number(negative[0]["quantity"]) * ratio[0]
                or negative[0].get("isin") == positive[0].get("isin")
                or negative[0].get("conid") == positive[0].get("conid")
            ):
                reasons.add("incomplete_reverse_legs")
        except RuntimeError:
            reasons.add("incomplete_reverse_legs")
    else:
        reasons.add("unsupported_type")
    if len({row.get("currency") for row in rows}) != 1:
        reasons.add("conflicting_currency")
    if any(row.get("code", "").strip() for row in rows):
        reasons.add("revision_or_cancellation")
    # The processing/report dates do not establish the market effective date.
    reasons.add("effective_date_unproven")
    symbols = sorted({row["symbol"] for row in rows if row.get("symbol")})
    isins = sorted({row["isin"] for row in rows if row.get("isin")})
    cash_fields = [row.get(field) for row in rows for field in ("amount", "proceeds")]
    cash = "missing_proof"
    if all(value not in (None, "") for value in cash_fields):
        try:
            cash = (
                "no_action_cash_observed"
                if all(number(v) == 0 for v in cash_fields)
                else "explicit_action_cash_requires_linked_evidence"
            )
        except RuntimeError:
            pass
    return {
        "rows": rows,
        "candidate_ratio": ratio,
        "reasons": sorted(reasons),
        "symbols": symbols,
        "isins": isins,
        "held": True,
        "conclusions": {
            "source": "observed_bounded_window",
            "identity": "missing_proof",
            "quantity": "missing_proof",
            "history": "missing_proof",
            "cash": cash,
            "timing": "missing_proof",
        },
    }


class Store(TypedDict):
    path: Path
    evidence: Path
    inputs: list[Path]
    lock: int
    original: bytes | None
    document: dict[str, Any]
    verified: dict[str, tuple[int, int, int, int, int]]
    inventories: dict[str, Inventory]
    bindings: dict[str, tuple[tuple[int, int, int, int, int], dict[str, Any]]]
    references: dict[str, Any] | None
    reference_original: bytes | None
    maintenance_warning: bool


def private_directory(path: Path) -> None:
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise RuntimeError("Corporate-action paths must not contain symlinks")
    info = path.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or info.st_mode & 0o700 != 0o700
    ):
        raise RuntimeError("Corporate-action directory must be private and writable")


def open_store(filename: str, input_files: list[str], *, simulation: bool) -> Store:
    """Lock financial evidence for the run; live never bootstraps blank state."""
    if not filename:
        raise RuntimeError("Corporate-action state path is required")
    path = Path(filename).absolute()
    private_directory(path.parent)
    inputs = [Path(item).absolute() for item in input_files if item]
    evidence = Path(str(path) + ".evidence")
    lock_path = Path(str(path) + ".lock")
    for target in (path, lock_path, Path(str(path) + ".references.yaml"),
                   Path(str(path) + ".rotation")):
        safe_path(target, inputs)
    # Delivery-state failures alone do not affect financial decisions. Only an
    # actual output/input collision is a configuration failure here.
    for target in (
        Path(str(path) + ".notifications.yaml"),
        Path(str(path) + ".notifications.yaml.lock"),
    ):
        for item in inputs:
            if target.resolve() == item.resolve() or (
                target.exists() and item.exists() and os.path.samefile(target, item)
            ):
                raise RuntimeError("Corporate-action output overlaps an input")
    if any(source.resolve().is_relative_to(evidence.resolve()) for source in inputs):
        raise RuntimeError("Corporate-action evidence overlaps an input")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original = file_bytes(path)
        if original is None and not simulation:
            raise RuntimeError(
                "Corporate-action state missing; initialize in simulation"
            )
        document = (
            read_yaml(original)
            if original is not None
            else {"version": 1, "reports": {}, "findings": {}}
        )
        if (
            set(document) != {"version", "reports", "findings"}
            or type(document["version"]) is not int
            or document["version"] != 1
            or not isinstance(document["reports"], dict)
            or not isinstance(document["findings"], dict)
        ):
            raise RuntimeError("Invalid corporate-action state schema")
        if not evidence.exists():
            evidence.mkdir(mode=0o700)
        private_directory(evidence)
        return {
            "path": path,
            "evidence": evidence,
            "inputs": inputs,
            "lock": fd,
            "original": original,
            "document": document,
            "verified": {},
            "inventories": {},
            "bindings": {},
            "references": None,
            "reference_original": file_bytes(Path(str(path) + ".references.yaml")),
            "maintenance_warning": False,
        }
    except BaseException:
        os.close(fd)
        raise


def close_store(store: Store) -> None:
    os.close(store["lock"])


def check_store(store: Store) -> None:
    private_directory(store["path"].parent)
    private_directory(store["evidence"])
    for target in (store["path"], Path(str(store["path"]) + ".lock")):
        safe_path(target, store["inputs"])
    for target in (
        Path(str(store["path"]) + ".notifications.yaml"),
        Path(str(store["path"]) + ".notifications.yaml.lock"),
    ):
        for source in store["inputs"]:
            if target.resolve() == source.resolve() or (
                target.exists() and source.exists() and os.path.samefile(target, source)
            ):
                raise RuntimeError("Corporate-action output overlaps an input")
    if file_bytes(store["path"]) != store["original"]:
        raise RuntimeError("Corporate-action state changed during this run")


def immutable_object(path: Path, data: bytes, inputs: list[Path]) -> None:
    """Create once and sync; never replace surviving source or acquisition proof."""
    safe_path(path, inputs)
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError("Retained corporate-action object hash changed")
        return
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def object_signature(path: Path) -> tuple[int, int, int, int, int]:
    info = path.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def parse_report(store: Store | None, xml: str, source: str) -> Inventory:
    """Parse identical bytes once per run; cached facts never replace file checks."""
    digest = hashlib.sha256(xml.encode()).hexdigest()
    if store is not None and digest in store["inventories"]:
        result = store["inventories"][digest]
        if result["source"] != source:
            raise RuntimeError("Corporate-action source binding changed")
        return result
    result = inventory(xml, source)
    if store is not None:
        store["inventories"][digest] = result
    return result


def retained_binding(store: Store, path: Path) -> dict[str, Any]:
    safe_path(path, store["inputs"])
    signature = object_signature(path)
    cached = store["bindings"].get(path.stem)
    if cached is not None:
        if cached[0] != signature:
            raise RuntimeError(
                "Retained corporate-action binding changed during this run"
            )
        return cached[1]
    result = read_yaml(path.read_bytes())
    store["bindings"][path.stem] = signature, result
    return result


def utc_now() -> datetime:
    return datetime.now(UTC)


def report_facts(report: Inventory) -> list[str]:
    """Exact decision inputs, excluding XML generation metadata and window overlap."""
    facts = {fingerprint({"event": key, "rows": sorted(fingerprint(row) for row in event["rows"])})
             for key, event in report["events"].items()}
    for kind in ("trades", "cash", "positions"):
        for row in report[kind]:
            # Position observations are dated independent quantity anchors.
            facts.add(fingerprint({"kind": kind, "row": row,
                                   "date": report["period"][1] if kind == "positions" else None}))
    facts.add(fingerprint({"section": report["section_present"],
                           "trades": report["trades_present"],
                           "held": report["account_held"]}))
    return sorted(facts)


def report_dependencies(report: Inventory) -> dict[str, Any]:
    """Bind row facts to source identities so unrelated history can rotate."""
    scopes: dict[str, list[str]] = {}
    for kind in ("trades", "cash", "positions"):
        for row in report[kind]:
            fact = fingerprint({"kind": kind, "row": row,
                                "date": report["period"][1] if kind == "positions" else None})
            scopes[fact] = [field + ":" + row[field] for field in ("conid", "isin", "symbol", "actionID") if row.get(field)]
    identities = {field + ":" + row[field] for event in report["events"].values()
                  for row in event["rows"] for field in ("conid", "isin", "symbol", "actionID") if row.get(field)}
    event_scopes = {key: sorted({field + ":" + row[field] for row in event["rows"]
                                for field in ("conid", "isin", "symbol", "actionID") if row.get(field)})
                    for key, event in report["events"].items()}
    positions = {fingerprint({"kind": "positions", "row": row, "date": report["period"][1]}):
                 report["period"][1] for row in report["positions"]}
    return {"rows": scopes, "identities": sorted(identities), "positions": positions,
            "event_scopes": event_scopes,
            "unbounded": report["account_held"]}


def acquisition_summary(record: dict[str, Any]) -> dict[str, Any]:
    """New bindings own their source summary; only legacy bindings need a companion."""
    summary: dict[str, Any] = record["binding"] if record["binding"]["schema"] == 2 else record["summary"]
    return summary


def safety_facts(record: dict[str, Any], identities: set[str], unbounded: bool,
                 anchor_dates: dict[str, str | None]) -> set[str]:
    scopes = acquisition_summary(record)["dependencies"]["rows"]
    facts = {fact for fact in acquisition_summary(record)["facts"]
             if unbounded or fact not in scopes or identities.intersection(scopes[fact])}
    if not unbounded:
        for fact, day in acquisition_summary(record)["dependencies"]["positions"].items():
            dates = [anchor_dates[identity] for identity in scopes[fact] if identity in anchor_dates]
            if dates and all(value is not None for value in dates):
                first = min(value for value in dates if value is not None)
                if day >= first.replace("-", ""):
                    # source_chain uses only independent positions before the first event.
                    facts.discard(fact)
    return facts


def source_anchor_dates(records: dict[str, Any], mapping: dict[str, str],
                        dates: dict[tuple[str, str], str]) -> dict[str, dict[str, str | None]]:
    result: dict[str, dict[str, str | None]] = {}
    for record in records.values():
        source = record["binding"]["source"]
        limits = result.setdefault(source, {})
        for key, values in acquisition_summary(record)["dependencies"]["event_scopes"].items():
            scope = set(values)
            symbols = {mapping[value[5:]] for value in scope
                       if value.startswith("isin:") and value[5:] in mapping}
            scope.update("isin:" + isin for isin, symbol in mapping.items() if symbol in symbols)
            day = dates.get((source, key))
            for identity in scope:
                if identity not in limits:
                    limits[identity] = day
                elif day is None or limits[identity] is None:
                    limits[identity] = None
                else:
                    limits[identity] = min(str(limits[identity]), day)
    return result


def read_report(store: Store, key: str, binding: dict[str, Any]) -> Inventory:
    fields = {"schema", "source", "query", "sha256", "period", "mapping"}
    if binding.get("schema") == 2:
        fields |= {"acquired", "facts", "events", "dependencies"}
    if (not re.fullmatch(r"[0-9a-f]{64}", key)
            or set(binding) != fields
            or type(binding["schema"]) is not int or binding["schema"] not in (1, 2)
            or fingerprint(binding) != key
            or not isinstance(binding["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", binding["sha256"])):
        raise RuntimeError("Invalid retained corporate-action binding")
    binding_path = store["evidence"] / (key + ".yaml")
    if not binding_path.is_file() or retained_binding(store, binding_path) != binding:
        raise RuntimeError("Missing retained corporate-action binding")
    obj = store["evidence"] / (binding["sha256"] + ".xml")
    safe_path(obj, store["inputs"])
    if not obj.is_file():
        raise RuntimeError("Missing retained corporate-action source")
    signature = object_signature(obj)
    digest = binding["sha256"]
    if digest in store["verified"]:
        if store["verified"][digest] != signature:
            raise RuntimeError("Retained corporate-action source hash changed during this run")
        result = store["inventories"][digest]
    else:
        data = obj.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError("Retained corporate-action source hash changed")
        result = parse_report(store, data.decode(), binding["source"])
        store["verified"][digest] = signature
    if result["source"] != binding["source"]:
        raise RuntimeError("Retained corporate-action source binding changed")
    if result["period"] != binding["period"] or not result["section_present"]:
        raise RuntimeError("Retained corporate-action scope changed")
    if binding["schema"] == 2 and (binding["facts"] != report_facts(result)
            or binding["events"] != bool(result["events"])
            or binding["dependencies"] != report_dependencies(result)):
        raise RuntimeError("Retained corporate-action acquisition facts changed")
    return result


def reference_path(store: Store) -> Path:
    return Path(str(store["path"]) + ".references.yaml")


def publish_references(store: Store, references: dict[str, Any]) -> None:
    """A committed generation is authoritative even if mutable findings are lost."""
    check_store(store)
    path = reference_path(store)
    safe_path(path, store["inputs"])
    if file_bytes(path) != store["reference_original"]:
        raise RuntimeError("Corporate-action references changed during this run")
    references = {**references, "generation": references["generation"] + 1}
    try:
        data = atomic_yaml(path, references)
    except OSError:
        # A directory-sync error can occur after replacement. Keep the complete
        # published generation in memory, but do not proceed with deletion.
        observed = file_bytes(path)
        if observed is not None and read_yaml(observed) == references:
            store["reference_original"] = observed
            store["references"] = references
        raise
    if file_bytes(path) != data:
        raise RuntimeError("Corporate-action reference publication failed")
    store["reference_original"] = data
    store["references"] = references
    # If the index is subsequently lost, old orphan bindings cannot resurrect.
    immutable_object(Path(str(store["path"]) + ".rotation"), b"version: 1\n", store["inputs"])


def load_references(store: Store) -> dict[str, Any]:
    if store["references"] is not None:
        return store["references"]
    raw = store["reference_original"]
    if raw is not None:
        references = read_yaml(raw)
        if (set(references) != {"version", "generation", "records", "safety", "pending", "last"}
                or type(references["version"]) is not int or references["version"] != 1
                or type(references["generation"]) is not int or references["generation"] < 0
                or not isinstance(references["records"], dict)
                or not isinstance(references["safety"], list)
                or not isinstance(references["pending"], list)
                or not isinstance(references["last"], dict)
                or any(not isinstance(key, str) or key not in references["records"]
                       for key in references["safety"])):
            raise RuntimeError("Invalid corporate-action reference generation")
        for key, record in references["records"].items():
            if (not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key)
                    or not isinstance(record, dict)
                    or set(record) - {"binding", "acquired", "summary"}
                    or not isinstance(record.get("binding"), dict)
                    or fingerprint(record["binding"]) != key):
                raise RuntimeError("Invalid corporate-action reference record")
            binding = record["binding"]
            if (not {"source", "query", "mapping", "sha256", "period", "schema"} <= binding.keys()
                    or any(not isinstance(binding[field], str)
                           for field in ("source", "query", "mapping", "sha256"))
                    or type(binding["schema"]) is not int or binding["schema"] not in (1, 2)
                    or not isinstance(binding["period"], list) or len(binding["period"]) != 2
                    or any(not isinstance(day, str) for day in binding["period"])):
                raise RuntimeError("Invalid corporate-action reference binding")
            try:
                start, end = (datetime.strptime(day, "%Y%m%d") for day in binding["period"])
                if start > end:
                    raise ValueError
            except ValueError:
                raise RuntimeError("Invalid corporate-action reference period") from None
            if binding["schema"] == 1 and not isinstance(record.get("summary"), dict):
                raise RuntimeError("Invalid legacy corporate-action summary")
            summary = acquisition_summary(record)
            if (not {"facts", "events", "dependencies"} <= summary.keys()
                    or not isinstance(summary["facts"], list)
                    or any(not isinstance(fact, str) for fact in summary["facts"])
                    or type(summary["events"]) is not bool
                    or not isinstance(summary["dependencies"], dict)
                    or set(summary["dependencies"]) != {"rows", "identities", "unbounded", "positions", "event_scopes"}
                    or any(not isinstance(summary["dependencies"][field], dict)
                           for field in ("rows", "positions", "event_scopes"))
                    or not isinstance(summary["dependencies"]["identities"], list)
                    or type(summary["dependencies"]["unbounded"]) is not bool
                    or any(not isinstance(item, str) for item in summary["dependencies"]["identities"])):
                raise RuntimeError("Invalid corporate-action acquisition summary")
            for field in ("rows", "event_scopes"):
                for identity, values in acquisition_summary(record)["dependencies"][field].items():
                    if (not isinstance(identity, str) or not isinstance(values, list)
                            or any(not isinstance(item, str) for item in values)):
                        raise RuntimeError("Invalid corporate-action reference identities")
            for fact, day in acquisition_summary(record)["dependencies"]["positions"].items():
                if (not isinstance(fact, str) or fact not in acquisition_summary(record)["dependencies"]["rows"]
                        or not isinstance(day, str) or not re.fullmatch(r"[0-9]{8}", day)):
                    raise RuntimeError("Invalid corporate-action reference position")
        if any(not isinstance(last, dict) or not {"key", "identity"} <= last.keys()
               for last in references["last"].values()):
            raise RuntimeError("Invalid corporate-action acquisition history")
        store["references"] = references
        return references
    if Path(str(store["path"]) + ".rotation").exists():
        raise RuntimeError("Missing committed corporate-action reference generation")
    records = dict(store["document"]["reports"])
    for path in sorted(store["evidence"].glob("*.yaml")):
        binding = retained_binding(store, path)
        if path.stem in records and records[path.stem] != binding:
            raise RuntimeError("Retained corporate-action binding changed")
        records[path.stem] = binding
    adopted = {}
    last = {}
    for key, binding in records.items():
        if binding.get("schema") == 2:
            raise RuntimeError("Missing committed corporate-action reference generation")
        result = read_report(store, key, binding)
        adopted[key] = {"binding": binding, "acquired": utc_now().isoformat(),
                        "summary": {"facts": report_facts(result), "events": bool(result["events"]),
                                    "dependencies": report_dependencies(result)}}
        acquisition = fingerprint({"source": binding["source"], "query": binding["query"],
                                   "mapping": binding["mapping"]})
        identity = fingerprint({field: binding[field] for field in
                                ("source", "query", "sha256", "period", "mapping")})
        last[acquisition] = {"key": key, "identity": identity, "acquired": adopted[key]["acquired"]}
    references = {"version": 1, "generation": 0, "records": adopted,
                  "safety": list(adopted), "pending": [], "last": last}
    publish_references(store, references)
    return load_references(store)


def retained_inventories(
    store: Store, source: str, query: str, mapping: dict[str, str]
) -> list[Inventory]:
    """Only active safety originals enter financial reconstruction."""
    references = load_references(store)
    safe_path(reference_path(store), store["inputs"])
    if file_bytes(reference_path(store)) != store["reference_original"]:
        raise RuntimeError("Corporate-action references changed during this run")
    inventories = []
    for key in references["safety"]:
        record = references["records"][key]
        result = read_report(store, key, record["binding"])
        if (report_facts(result) != acquisition_summary(record)["facts"] or bool(result["events"]) != acquisition_summary(record)["events"]
                or report_dependencies(result) != acquisition_summary(record)["dependencies"]):
            raise RuntimeError("Retained corporate-action facts changed")
        if result["source"] == source:
            inventories.append(result)
    store["document"]["reports"] = {
        key: references["records"][key]["binding"] for key in references["safety"]}
    return inventories


def acquisition_time(value: object, now: datetime) -> datetime | None:
    try:
        stamp = datetime.fromisoformat(str(value))
        if stamp.utcoffset() != timedelta(0) or stamp > now:
            return None
        return stamp
    except (ValueError, TypeError):
        return None


def maintain_reports(store: Store, mapping: dict[str, str], dates: dict[tuple[str, str], str]) -> None:
    """Commit retirement before deleting only explicitly retired owned objects."""
    from copy import deepcopy

    references = deepcopy(load_references(store))
    now = utc_now()
    for record in references["records"].values():
        if acquisition_time(record.get("acquired"), now) is None:
            record["acquired"] = now.isoformat()
    for last in references["last"].values():
        if acquisition_time(last.get("acquired"), now) is None:
            last["acquired"] = now.isoformat()
    sources = {record["binding"]["source"] for record in references["records"].values()
               if acquisition_summary(record)["events"]}
    candidates = {key: record for key, record in references["records"].items()
                  if record["binding"]["source"] in sources}
    anchor_dates = source_anchor_dates(candidates, mapping, dates)
    identities = {source: {identity for record in candidates.values()
                           if record["binding"]["source"] == source
                           for identity in acquisition_summary(record)["dependencies"]["identities"]}
                  for source in sources}
    for scope in identities.values():
        symbols = {value.removeprefix("symbol:") for value in scope if value.startswith("symbol:")}
        symbols.update(mapping[value.removeprefix("isin:")] for value in scope
                       if value.startswith("isin:") and value.removeprefix("isin:") in mapping)
        scope.update("isin:" + isin for isin, symbol in mapping.items() if symbol in symbols)
    unbounded = {source: any(acquisition_summary(record)["dependencies"]["unbounded"] for record in candidates.values()
                            if record["binding"]["source"] == source) for source in sources}
    safety = set(candidates)
    # Prefer older originals. Retire a later copy only if all exact inputs and
    # its entire declared interval survive in the same source/query/mapping scope.
    for key in reversed(list(candidates)):
        record = candidates[key]
        binding = record["binding"]
        peers = [candidates[other] for other in safety - {key}
                 if all(candidates[other]["binding"][field] == binding[field]
                        for field in ("source", "query", "mapping"))]
        source = binding["source"]
        facts = {fact for peer in peers for fact in safety_facts(
            peer, identities[source], unbounded[source], anchor_dates[source])}
        covered = datetime.strptime(binding["period"][0], "%Y%m%d").date()
        end = datetime.strptime(binding["period"][1], "%Y%m%d").date()
        for start_text, end_text in sorted(peer["binding"]["period"] for peer in peers):
            start, stop = (datetime.strptime(text, "%Y%m%d").date()
                           for text in (start_text, end_text))
            if start <= covered:
                covered = max(covered, stop + timedelta(days=1))
        if safety_facts(record, identities[source], unbounded[source], anchor_dates[source]) <= facts and covered > end:
            safety.remove(key)
    # Recheck every surviving original before publishing a reduced generation.
    for key in safety:
        record = candidates[key]
        result = read_report(store, key, record["binding"])
        if (report_facts(result) != acquisition_summary(record)["facts"]
                or report_dependencies(result) != acquisition_summary(record)["dependencies"]):
            raise RuntimeError("Retained corporate-action facts changed")
    references["safety"] = sorted(safety)
    if any(acquisition_summary(candidates[key])["dependencies"]["positions"]
           and any(day is None for day in anchor_dates[candidates[key]["binding"]["source"]].values())
           and now - datetime.fromisoformat(candidates[key]["acquired"]) >= timedelta(hours=720)
           for key in safety):
        if not store["maintenance_warning"]:
            log.warning("Corporate-action dated anchors retained; redundancy unproven")
        store["maintenance_warning"] = True
    for key, record in list(references["records"].items()):
        acquired = acquisition_time(record["acquired"], now)
        if key not in safety and acquired is not None and now - acquired >= timedelta(hours=720):
            references["pending"].extend([key + ".yaml", record["binding"]["sha256"] + ".xml"])
            del references["records"][key]
    active_files = {name for key, record in references["records"].items()
                    for name in (key + ".yaml", record["binding"]["sha256"] + ".xml")}
    references["pending"] = sorted(set(references["pending"]) - active_files)
    publish_references(store, references)
    for name in references["pending"]:
        if not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{64}\.(xml|yaml)", name):
            raise RuntimeError("Invalid corporate-action retirement path")
        path = store["evidence"] / name
        safe_path(path, store["inputs"])
        if path.exists():
            # Refuse changed originals, hard links, symlinks and input aliases.
            signature = object_signature(path)
            if path.suffix == ".xml":
                if hashlib.sha256(path.read_bytes()).hexdigest() != path.stem:
                    raise RuntimeError("Retired corporate-action source changed")
            elif fingerprint(read_yaml(path.read_bytes())) != path.stem:
                raise RuntimeError("Retired corporate-action binding changed")
            safe_path(path, store["inputs"])
            if object_signature(path) != signature:
                raise RuntimeError("Retired corporate-action object changed during cleanup")
            path.unlink()
            if path.suffix == ".xml":
                store["verified"].pop(path.stem, None)
            else:
                store["bindings"].pop(path.stem, None)
    directory = os.open(store["evidence"], os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    if references["pending"]:
        publish_references(store, {**references, "pending": []})


def retain_report(
    store: Store, xml: str, source: str, query: str, mapping: dict[str, str], *,
    dates: dict[tuple[str, str], str] | None = None,
) -> list[Inventory]:
    """Durably acquire evidence, then attempt independent local maintenance."""
    from copy import deepcopy

    import yaml

    check_store(store)
    retained_inventories(store, source, query, mapping)
    current = parse_report(store, xml, source)
    if not current["section_present"]:
        raise RuntimeError("Required CorporateActions section is missing")
    try:
        start, end = (datetime.strptime(value, "%Y%m%d") for value in current["period"])
        if start > end:
            raise ValueError
    except ValueError:
        raise RuntimeError("Corporate-action report period is unavailable") from None
    binding = {"schema": 1, "source": source, "query": query,
               "sha256": current["sha256"], "period": current["period"], "mapping": fingerprint(mapping)}
    references = deepcopy(load_references(store))
    identity = fingerprint({field: value for field, value in binding.items() if field != "schema"})
    acquisition = fingerprint({"source": source, "query": query, "mapping": binding["mapping"]})
    last = references["last"].get(acquisition, {})
    acquired = last.get("acquired") if last.get("identity") == identity else utc_now().isoformat()
    binding.update(schema=2, acquired=acquired, facts=report_facts(current),
                   events=bool(current["events"]), dependencies=report_dependencies(current))
    key = fingerprint(binding)
    # Re-reading any surviving acquisition never changes its original binding or age.
    for old_key, record in references["records"].items():
        old = record["binding"]
        if identity == fingerprint({field: old[field] for field in
                                    ("source", "query", "sha256", "period", "mapping")}):
            key, binding, acquired = old_key, old, record.get("acquired")
            break
    if key not in references["records"]:
        # Record uncommitted object names first. A crash can then leave only
        # active references or explicit, retryable garbage, never hidden orphans.
        names = {key + ".yaml", current["sha256"] + ".xml"}
        active = {name for old_key, record in references["records"].items()
                  for name in (old_key + ".yaml", record["binding"]["sha256"] + ".xml")}
        references["pending"] = sorted(set(references["pending"]) | (names - active))
        publish_references(store, references)
        references = deepcopy(load_references(store))
        immutable_object(store["evidence"] / (current["sha256"] + ".xml"), xml.encode(), store["inputs"])
        immutable_object(store["evidence"] / (key + ".yaml"),
                         yaml.safe_dump(binding, sort_keys=True).encode(), store["inputs"])
        store["verified"][current["sha256"]] = object_signature(
            store["evidence"] / (current["sha256"] + ".xml"))
        references["records"][key] = {"binding": binding, "acquired": acquired}
        references["pending"] = sorted(set(references["pending"]) - names)
        references["last"][acquisition] = {"key": key, "identity": identity, "acquired": acquired}
        # A new report must be durable before any dependent financial decision.
        if current["events"] or any(r["binding"]["source"] == source and acquisition_summary(r)["events"]
                                    for r in references["records"].values()):
            references["safety"] = list(set(references["safety"]) | {key})
        publish_references(store, references)
    try:
        maintain_reports(store, mapping, dates or {})
    except (RuntimeError, OSError, ValueError):
        if not store["maintenance_warning"]:
            log.warning("Corporate-action report maintenance incomplete; retry next run")
        store["maintenance_warning"] = True
    reports = retained_inventories(store, source, query, mapping)
    store["original"] = atomic_yaml(store["path"], store["document"])
    # Current ordinary input participates only in this run; expired archives do not.
    return reports if any(r["sha256"] == current["sha256"] for r in reports) else [*reports, current]


class DateProof(TypedDict):
    effective_date: str
    source_url: str
    sha256: str
    document: str
    bytes: bytes


def load_date_proofs(filename: str | None) -> dict[tuple[str, str], DateProof]:
    """Read operator-verified facts, never acknowledgments or approval flags."""
    if not filename:
        return {}
    path = Path(filename).absolute()
    private_directory(path.parent)
    safe_path(path, [])
    document = read_yaml(path.read_bytes())
    if (
        set(document) != {"version", "events"}
        or type(document["version"]) is not int
        or document["version"] != 1
        or not isinstance(document["events"], dict)
    ):
        raise RuntimeError("Invalid corporate-action date evidence")
    result: dict[tuple[str, str], DateProof] = {}
    for source, events in document["events"].items():
        if not isinstance(source, str) or not source or not isinstance(events, dict):
            raise RuntimeError("Invalid corporate-action date binding")
        for action, proof in events.items():
            if (
                not isinstance(action, str)
                or not action
                or not isinstance(proof, dict)
                or set(proof) != {"effective_date", "source_url", "document", "sha256"}
                or not all(isinstance(v, str) and v for v in proof.values())
            ):
                raise RuntimeError("Invalid corporate-action date record")
            try:
                parsed = date.fromisoformat(proof["effective_date"])
                if parsed.isoformat() != proof["effective_date"]:
                    raise ValueError
                url = urlsplit(proof["source_url"])
                if (
                    url.scheme != "https"
                    or not url.hostname
                    or url.username
                    or url.password
                    or url.fragment
                    or url.query
                ):
                    raise ValueError
            except ValueError:
                raise RuntimeError(
                    "Invalid official corporate-action date/source"
                ) from None
            original = path.parent / proof["document"]
            private_directory(original.parent)
            safe_path(original, [path])
            data = original.read_bytes()
            if not data or hashlib.sha256(data).hexdigest() != proof["sha256"]:
                raise RuntimeError("Corporate-action official document digest changed")
            result[(source, action)] = {
                "effective_date": proof["effective_date"],
                "source_url": proof["source_url"],
                "sha256": proof["sha256"],
                "document": str(original.absolute()),
                "bytes": data,
            }
    return result


# Native reads remain unavailable as financial proof until the separate
# image-backed, non-admin qualification required by OpenSpec is retained.
NATIVE_READ_QUALIFIED = False


def native_version_supported(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        return False
    return tuple(map(int, value.split("."))) >= (3, 91, 0)


def row_profile(row: dict[str, Any]) -> dict[str, Any]:
    profile = (
        row.get("assetProfile") if "assetProfile" in row else row.get("SymbolProfile")
    )
    return profile if isinstance(profile, dict) else {}


def source_chain(
    reports: list[Inventory],
    events: dict[str, Event],
    symbol: str,
    mapping: dict[str, str],
    dates: dict[str, str],
) -> tuple[Fraction, dict[str, Fraction]]:
    """Reconstruct a bounded ledger from an independent opening position or RS legs."""
    related = {
        key: event
        for key, event in events.items()
        if any(mapping.get(isin) == symbol for isin in event["isins"])
    }
    if not related or any(key not in dates for key in related):
        raise RuntimeError("effective_date_unproven")
    ordered = sorted(related, key=lambda key: (dates[key], key))
    if len({dates[key] for key in ordered}) != len(ordered):
        raise RuntimeError("event_order_unproven")
    first = date.fromisoformat(dates[ordered[0]])
    security_isins = {isin for event in related.values() for isin in event["isins"]}
    contracts = {
        row["conid"]
        for event in related.values()
        for row in event["rows"]
        if row.get("conid")
    }
    # A reverse withdrawal is independent pre-event quantity evidence.
    first_rows = related[ordered[0]]["rows"]
    negatives = [row for row in first_rows if number(row.get("quantity")) < 0]
    baselines: list[tuple[date, Fraction]] = []
    if {row.get("type") for row in first_rows} == {"RS"} and len(negatives) == 1:
        baselines.append(
            (first - timedelta(days=1), Fraction(-number(negatives[0]["quantity"])))
        )
    for report in reports:
        end = datetime.strptime(report["period"][1], "%Y%m%d").date()
        positions = [
            row for row in report["positions"] if row.get("conid") in contracts
        ]
        if end < first and len(positions) == 1:
            row = positions[0]
            if (
                row.get("accountId") == report["source"]
                and row.get("levelOfDetail") == "SUMMARY"
                and row.get("isin") in security_isins
            ):
                baselines.append((end, Fraction(number(row.get("position")))))
    if not baselines:
        raise RuntimeError("before_quantity_unproven")
    baseline_day, quantity = max(baselines, key=lambda pair: pair[0])
    if any(q != quantity for day, q in baselines if day == baseline_day):
        raise RuntimeError("conflicting_before_quantity")
    if quantity < 0:
        raise RuntimeError("unsupported_short_position")
    windows = sorted(
        (
            datetime.strptime(r["period"][0], "%Y%m%d").date(),
            datetime.strptime(r["period"][1], "%Y%m%d").date(),
        )
        for r in reports
    )
    covered = baseline_day
    for start, end in windows:
        if end <= covered:
            continue
        if start > covered + timedelta(days=1):
            raise RuntimeError("source_coverage_unproven")
        covered = end
    if covered < max(date.fromisoformat(day) for day in dates.values()):
        raise RuntimeError("source_coverage_unproven")
    trades: dict[str, dict[str, str]] = {}
    for report in reports:
        if not report["trades_present"]:
            raise RuntimeError("source_trades_unavailable")
        for row in report["trades"]:
            if (
                row.get("conid") not in contracts
                and row.get("isin") not in security_isins
            ):
                continue
            if (
                row.get("accountId") != report["source"]
                or not row.get("tradeID")
                or row.get("isin") not in security_isins
                or row.get("conid") not in contracts
                or row.get("buySell") not in ("BUY", "SELL")
            ):
                raise RuntimeError("source_trade_identity_unproven")
            key = row["tradeID"]
            if key in trades and trades[key] != row:
                raise RuntimeError("conflicting_source_trade")
            trades[key] = row
    timeline: list[tuple[str, str, str]] = [
        (dates[key], "event", key) for key in ordered
    ]
    for key, row in trades.items():
        stamp = parse_ibkr_datetime(row.get("dateTime"))
        if stamp is None:
            raise RuntimeError("source_trade_date_unproven")
        day = stamp[:10]
        if day in {dates[key] for key in ordered}:
            raise RuntimeError("ambiguous_boundary_trade")
        if date.fromisoformat(day) > baseline_day:
            if date.fromisoformat(day) > covered:
                raise RuntimeError("source_trade_outside_coverage")
            timeline.append((day, "trade", key))
    before: dict[str, Fraction] = {}
    for _, kind, key in sorted(timeline):
        if kind == "trade":
            row = trades[key]
            amount = abs(Fraction(number(row.get("quantity"))))
            if amount <= 0:
                raise RuntimeError("invalid_source_quantity")
            quantity += amount if row["buySell"] == "BUY" else -amount
        else:
            event = related[key]
            ratio = event["candidate_ratio"]
            if ratio is None:
                raise RuntimeError("ratio_unproven")
            before[key] = quantity
            after = quantity * Fraction(*ratio)
            if quantity <= 0 or after.denominator != 1:
                raise RuntimeError("fractional_entitlement_unproven")
            if {row.get("type") for row in event["rows"]} == {"FS"}:
                if len(event["rows"]) != 1 or after - quantity != number(
                    event["rows"][0]["quantity"]
                ):
                    raise RuntimeError("forward_quantity_mismatch")
            else:
                negative = [row for row in event["rows"] if number(row["quantity"]) < 0]
                positive = [row for row in event["rows"] if number(row["quantity"]) > 0]
                if (
                    len(negative) != 1
                    or len(positive) != 1
                    or quantity != -number(negative[0]["quantity"])
                    or after != number(positive[0]["quantity"])
                ):
                    raise RuntimeError("reverse_quantity_mismatch")
            quantity = after
        if quantity < 0:
            raise RuntimeError("negative_source_position")
    return quantity, before


def destination_quantities(
    snapshot: dict[str, Any], evidence: dict[str, Any], symbol: str, target: str
) -> tuple[Fraction, Fraction, bool]:
    """Keep raw identity rows separate from exactly calculated effective units."""
    rows = snapshot.get("activities")
    if not isinstance(rows, list) or snapshot.get("count") != len(rows):
        raise RuntimeError("destination_listing_incomplete")
    profile_response = evidence.get("profile")
    if not isinstance(profile_response, dict) or not isinstance(
        profile_response.get("splits"), list
    ):
        raise RuntimeError("destination_splits_unavailable")
    splits = profile_response["splits"]
    native = bool(splits)
    if native and (
        not NATIVE_READ_QUALIFIED
        or not native_version_supported(evidence.get("version"))
    ):
        raise RuntimeError("native_read_unqualified")
    total = Fraction(0)
    account = Fraction(0)
    seen_ids: set[str] = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("id"), str)
            or not row["id"]
            or row["id"] in seen_ids
        ):
            raise RuntimeError("destination_identity_ambiguous")
        seen_ids.add(row["id"])
        if not isinstance(row, dict):
            raise RuntimeError("destination_listing_invalid")
        profile = row_profile(row)
        if profile.get("symbol") != symbol or profile.get("dataSource") != "YAHOO":
            continue
        if row.get("type") not in ("BUY", "SELL"):
            continue
        if not activity_is_active(row) or not activity_date_is_current(row):
            raise RuntimeError("shared_profile_scope_unproven")
        amount = Fraction(number(row.get("quantity")))
        if amount < 0:
            raise RuntimeError("destination_quantity_invalid")
        instant = row.get("date")
        if not isinstance(instant, str) or len(instant) < 10:
            raise RuntimeError("destination_date_unproven")
        day = date.fromisoformat(instant[:10])
        for split in splits:
            if not isinstance(split, dict) or not isinstance(split.get("date"), str):
                raise RuntimeError("destination_split_invalid")
            effective = date.fromisoformat(split["date"][:10])
            numerator, denominator = (
                number(split.get("numerator")),
                number(split.get("denominator")),
            )
            if numerator <= 0 or denominator <= 0:
                raise RuntimeError("destination_split_invalid")
            if day < effective:
                amount *= Fraction(numerator) / Fraction(denominator)
        amount *= -1 if row["type"] == "SELL" else 1
        total += amount
        if row.get("accountId") == target:
            account += amount
    holding = evidence.get("holding")
    if not isinstance(holding, dict) or number(holding.get("quantity")) != total:
        raise RuntimeError("destination_holding_mismatch")
    if account < 0:
        raise RuntimeError("destination_quantity_invalid")
    return account, total, native


class Decision(TypedDict):
    account_held: bool
    symbols: set[str]
    effective: dict[str, Fraction]
    findings: dict[str, Event]
    dates: dict[str, str]
    normalized: set[str]


def merge_event_rows(
    previous: list[dict[str, str]], current: list[dict[str, str]]
) -> list[dict[str, str]] | None:
    """Additional columns enrich facts; changed shared facts remain revisions."""
    old = {row.get("transactionID", ""): row for row in previous}
    new = {row.get("transactionID", ""): row for row in current}
    if (
        "" in old
        or "" in new
        or len(old) != len(previous)
        or len(new) != len(current)
        or old.keys() != new.keys()
    ):
        return None
    merged = []
    for key in sorted(old):
        left, right = old[key], new[key]
        if left.get("code", "") != right.get("code", "") or any(
            left[field] and right[field] and left[field] != right[field]
            for field in left.keys() & right.keys()
        ):
            return None
        merged.append(
            {**left, **{field: value for field, value in right.items() if value}}
        )
    return merged


def decide(
    reports: list[Inventory],
    source: str,
    target: str,
    mapping: dict[str, str],
    snapshot: dict[str, Any] | None,
    evidence: dict[str, dict[str, Any]],
    proofs: dict[tuple[str, str], DateProof],
) -> Decision:
    """Prove a bounded release. Unsupported/incomplete effects keep their holds."""
    from copy import deepcopy

    events: dict[str, Event] = {}
    account_held = any(report["account_held"] for report in reports)
    for report in reports:
        for key, event in report["events"].items():
            if key not in events:
                events[key] = deepcopy(event)
            elif events[key]["rows"] != event["rows"]:
                merged = merge_event_rows(events[key]["rows"], event["rows"])
                if merged is None:
                    events[key]["reasons"].append("conflicting_event_revision")
                    account_held = True
                else:
                    conflict = "conflicting_event_revision" in events[key]["reasons"]
                    events[key] = event_inventory(merged)
                    if conflict:
                        events[key]["reasons"].append("conflicting_event_revision")
    dates = {
        key: proofs[(source, key)]["effective_date"]
        for key in events
        if (source, key) in proofs
    }
    held: set[str] = set()
    effective: dict[str, Fraction] = {}
    normalized: set[str] = set()
    transaction_events: dict[str, str] = {}
    for key, event in events.items():
        for row in event["rows"]:
            transaction = row.get("transactionID", "")
            if (
                transaction in transaction_events
                and transaction_events[transaction] != key
            ):
                event["reasons"].append("changed_event_identity")
                events[transaction_events[transaction]]["reasons"].append(
                    "changed_event_identity"
                )
            transaction_events[transaction] = key
    for key, event in events.items():
        symbols = {mapping[isin] for isin in event["isins"] if isin in mapping}
        transition = len(event["isins"]) > 1 or any(
            row.get("type") == "RS" for row in event["rows"]
        )
        if not event["isins"] or (
            transition and any(isin not in mapping for isin in event["isins"])
        ):
            event["reasons"].append("explicit_mapping_missing")
            account_held = True
        elif not symbols and len(event["isins"]) == 1 and len(event["symbols"]) == 1:
            # Existing resolver fallback is usable only when fresh profile ISIN
            # proves the single unchanged identity. Transitions require mappings.
            symbols = set(event["symbols"])
        qualified_mapping = dict(mapping)
        if len(symbols) == 1:
            for isin in event["isins"]:
                qualified_mapping.setdefault(isin, next(iter(symbols)))
        event["symbols"] = sorted(set(event["symbols"]) | symbols)
        reasons = set(event["reasons"]) - {"effective_date_unproven"}
        if len(symbols) != 1:
            reasons.add("identity_continuity_unproven")
        if key not in dates:
            reasons.add("effective_date_unproven")
        else:
            event["conclusions"]["timing"] = "official_document_bound_date"
        symbol = next(iter(symbols)) if len(symbols) == 1 else None
        if symbol and not (reasons - {"before_quantity_unproven"}):
            try:
                if snapshot is None or symbol not in evidence:
                    raise RuntimeError("destination_evidence_unavailable")
                response = evidence[symbol]["profile"]
                profile = response.get("assetProfile")
                if (
                    not isinstance(profile, dict)
                    or profile.get("symbol") != symbol
                    or profile.get("dataSource") != "YAHOO"
                    or profile.get("isActive") is False
                    or profile.get("isin") not in event["isins"]
                ):
                    raise RuntimeError("destination_identity_conflict")
                for row in snapshot.get("activities", []):
                    candidate = row_profile(row)
                    if (
                        candidate.get("symbol") == symbol
                        and candidate.get("dataSource") == "YAHOO"
                        and candidate.get("isin") is not None
                        and candidate.get("isin") not in event["isins"]
                    ):
                        raise RuntimeError("destination_identity_conflict")
                    if (
                        row.get("accountId") == target
                        and candidate.get("isin") in event["isins"]
                        and (
                            candidate.get("symbol") != symbol
                            or candidate.get("dataSource") != "YAHOO"
                        )
                    ):
                        raise RuntimeError("competing_destination_alias")
                event["conclusions"]["identity"] = "observed_agreement"
                event["conclusions"]["history"] = history_conclusion(
                    reports, snapshot, symbol, target, qualified_mapping
                )
                expected, before = source_chain(
                    reports, events, symbol, qualified_mapping, dates
                )
                reasons.discard("before_quantity_unproven")
                event["conclusions"]["source"] = "bounded_chain_proven"
                actual, _, native = destination_quantities(
                    snapshot, evidence[symbol], symbol, target
                )
                if expected != actual:
                    # A new post-event trade can explain why the destination is
                    # behind the broker. It must still pass normal candidate,
                    # deduplication and accepted-buy checks before any dispatch.
                    latest = max(dates[other] for other in before)
                    identities = {
                        str(row.get("comment") or "").split("\n", 1)[0]
                        for row in snapshot["activities"]
                        if row.get("accountId") == target
                    }
                    pending: dict[str, dict[str, str]] = {}
                    for report in reports:
                        for trade in report["trades"]:
                            if qualified_mapping.get(trade.get("isin", "")) != symbol:
                                continue
                            tid = trade.get("tradeID", "")
                            stamp = parse_ibkr_datetime(trade.get("dateTime"))
                            if (
                                stamp is not None
                                and stamp[:10] > latest
                                and f"IBKR#v2#{source}:TRADE:{tid}" not in identities
                                and f"IBKR#{tid}" not in identities
                            ):
                                pending[tid] = trade
                    delta = sum(
                        (
                            abs(Fraction(number(row["quantity"])))
                            * (1 if row["buySell"] == "BUY" else -1)
                            for row in pending.values()
                        ),
                        Fraction(0),
                    )
                    if expected - delta != actual:
                        event["conclusions"]["quantity"] = "observed_discrepancy"
                        raise RuntimeError("effective_quantity_mismatch")
                # Every native ratio must match a known dated source event.
                if native:
                    for split in response["splits"]:
                        if not any(
                            dates.get(other) == split["date"][:10]
                            and (known_ratio := events[other]["candidate_ratio"])
                            is not None
                            and Fraction(*known_ratio)
                            == Fraction(number(split["numerator"]))
                            / Fraction(number(split["denominator"]))
                            for other in before
                        ):
                            raise RuntimeError("profile_wide_ratio_unproven")
                event["conclusions"]["identity"] = "observed_agreement"
                event["conclusions"]["quantity"] = "observed_agreement"
                # Full lot cost/date matching is independent from unit safety.
                event["conclusions"]["history"] = history_conclusion(
                    reports, snapshot, symbol, target, qualified_mapping
                )
                effective[symbol] = actual
                if not native:
                    normalized.add(symbol)
            except (
                RuntimeError,
                ValueError,
                KeyError,
                TypeError,
                DecimalException,
            ) as exc:
                reason = (
                    str(exc) if isinstance(exc, RuntimeError) else "invalid_evidence"
                )
                reasons.add(reason)
        linked = [
            row
            for report in reports
            for row in report["cash"]
            if row.get("accountId") == source
            and row.get("actionID") == key
            and row.get("type")
            not in ("Dividends", "Payment In Lieu Of Dividends", "Withholding Tax")
        ]
        if linked:
            event["conclusions"]["cash"] = "explicit_linked_cash_observed_no_treatment"
        event["reasons"] = sorted(reasons)
        event["held"] = bool(reasons)
        if event["held"]:
            held.update(event["symbols"])
    # A held event dominates any other event sharing that profile.
    for symbol in held:
        effective.pop(symbol, None)
    return {
        "account_held": account_held,
        "symbols": held,
        "effective": effective,
        "findings": events,
        "dates": dates,
        "normalized": normalized,
    }


def candidate_held(decision: Decision, activity: dict[str, Any]) -> bool:
    if activity.get("type") not in ("BUY", "SELL"):
        return False
    symbol = activity.get("symbol")
    if decision["account_held"] or symbol in decision["symbols"]:
        return True
    # Any boundary-day candidate is ambiguous. Already-normalized histories
    # cannot accept unmatched earlier raw units, even with current agreement.
    day = str(activity.get("date", ""))[:10]
    for key, event in decision["findings"].items():
        if symbol not in event["symbols"]:
            continue
        effective = decision["dates"].get(key)
        if effective is None or day == effective:
            return True
        if symbol in decision["normalized"] and day < effective:
            return True
    return False


def publish_findings(
    store: Store,
    source: str,
    decision: Decision,
    proofs: dict[tuple[str, str], DateProof],
) -> None:
    """Persist inspection output after proof objects; never use it to release."""
    check_store(store)
    findings: dict[str, Any] = {}
    for key, event in decision["findings"].items():
        proof = proofs.get((source, key))
        provenance: dict[str, Any] | None = None
        if proof is not None:
            immutable_object(
                store["evidence"] / (proof["sha256"] + ".official"),
                proof["bytes"],
                store["inputs"],
            )
            provenance = {
                name: proof[name] for name in ("effective_date", "source_url", "sha256")
            }
        findings[key] = {**event, "date_evidence": provenance}
    store["document"]["findings"][source] = {
        "account_held": decision["account_held"],
        "events": findings,
    }
    check_store(store)
    store["original"] = atomic_yaml(store["path"], store["document"])


class NotificationPlan(TypedDict):
    path: str | None
    original: bytes | None
    records: dict[str, Any]
    sent: dict[str, Any]
    counts: dict[str, int]


def notification_document(data: bytes | None) -> dict[str, Any]:
    doc = read_yaml(data) if data is not None else {"version": 1, "deliveries": {}}
    if (
        set(doc) != {"version", "deliveries"}
        or type(doc["version"]) is not int
        or doc["version"] != 1
        or not isinstance(doc["deliveries"], dict)
    ):
        raise RuntimeError("Invalid corporate-action delivery state")
    for key, record in doc["deliveries"].items():
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"[0-9a-f]{64}", key)
            or not isinstance(record, dict)
            or set(record) != {"fingerprint", "held"}
            or not isinstance(record["fingerprint"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", record["fingerprint"])
            or type(record["held"]) is not bool
        ):
            raise RuntimeError("Invalid corporate-action delivery record")
    return doc


def plan_notifications(
    filename: str | None, decisions: dict[str, Decision]
) -> NotificationPlan:
    path = Path(filename + ".notifications.yaml").absolute() if filename else None
    original: bytes | None = None
    previous: dict[str, Any] = {}
    if path is not None:
        try:
            private_directory(path.parent)
            safe_path(path, [])
            original = file_bytes(path)
            previous = notification_document(original)["deliveries"]
        except RuntimeError, OSError:
            # Losing only delivery state repeats eligible findings, never holds.
            log.warning(
                "Corporate-action delivery state unavailable; eligible notices may repeat"
            )
    records: dict[str, Any] = {}
    for source, decision in decisions.items():
        if decision["account_held"]:
            key = fingerprint([source, "account_hold"])
            records[key] = {"fingerprint": fingerprint(["account_hold"]), "held": True}
        elif fingerprint([source, "account_hold"]) in previous:
            records[fingerprint([source, "account_hold"])] = {
                "fingerprint": fingerprint(["account_resumed"]),
                "held": False,
            }
        for event_key, event in decision["findings"].items():
            key = fingerprint([source, event_key])
            records[key] = {"fingerprint": fingerprint(event), "held": event["held"]}
    counts = {"active_holds": 0, "changed_findings": 0, "resumptions": 0}
    sent: dict[str, Any] = {}
    for key, record in records.items():
        old = previous.get(key)
        if record["held"]:
            counts["active_holds"] += 1
        elif isinstance(old, dict) and old.get("held"):
            counts["resumptions"] += 1
        elif old != record:
            counts["changed_findings"] += 1
        else:
            continue
        sent[key] = record
    return {
        "path": str(path) if path else None,
        "original": original,
        "records": previous,
        "sent": sent,
        "counts": counts,
    }


def prepare_notifications(
    outcome: RunOutcome, filename: str | None, decisions: dict[str, Decision]
) -> None:
    for source, decision in decisions.items():
        if decision["account_held"]:
            record_action(outcome, "corporate_action", f"{source}:account_hold")
        for event_key, event in decision["findings"].items():
            if event["held"] or event["conclusions"].get("history") == "bounded_cost_dates_differ":
                record_action(outcome, "corporate_action", f"{source}:{event_key}")
                log.warning("Corporate-action user action: source=%s event=%s; reasons=%s; "
                            "conclusions=%s; state container path=%s; inspect source/destination proof; "
                            "acknowledgment and state reset do not release holds", source, event_key,
                            event["reasons"], event["conclusions"], filename or "unavailable")
    plan = plan_notifications(filename, decisions)
    if plan["sent"]:
        outcome["corporate_notification"] = plan
    else:
        outcome.pop("corporate_notification", None)


def confirm_notification(plan: NotificationPlan) -> bool:
    """Reacquire a separate lock after send; generation drift never gets replaced."""
    if not plan["path"] or not plan["sent"]:
        return False
    path = Path(plan["path"])
    lock = Path(str(path) + ".lock")
    fd: int | None = None
    try:
        private_directory(path.parent)
        safe_path(path, [])
        safe_path(lock, [])
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if file_bytes(path) != plan["original"]:
            raise RuntimeError("Corporate-action delivery generation changed")
        doc = notification_document(plan["original"])
        doc["deliveries"].update(plan["sent"])
        atomic_yaml(path, doc)
        return True
    except RuntimeError, OSError:
        log.warning(
            "Corporate-action delivery was not recorded; notices remain eligible"
        )
        return False
    finally:
        if fd is not None:
            os.close(fd)


def history_conclusion(
    reports: list[Inventory],
    snapshot: dict[str, Any],
    symbol: str,
    target: str,
    mapping: dict[str, str],
) -> str:
    """Bounded observations only; cost/date disagreement cannot create a hold."""
    trades: dict[str, dict[str, str]] = {}
    for report in reports:
        for row in report["trades"]:
            if (
                mapping.get(row.get("isin", "")) == symbol
                and row.get("buySell") == "BUY"
            ):
                trades[row.get("tradeID", "")] = row
    stored = [
        row
        for row in snapshot["activities"]
        if row.get("accountId") == target
        and row.get("type") == "BUY"
        and row_profile(row).get("symbol") == symbol
    ]
    if not trades or not stored:
        return "missing_proof"
    try:
        source_cost = sum(
            (
                abs(number(row["quantity"])) * number(row["tradePrice"])
                + max(-number(row.get("ibCommission", "0")), Decimal(0))
                for row in trades.values()
            ),
            Decimal(0),
        )
        destination_cost = sum(
            (
                number(row["quantity"]) * number(row["unitPrice"]) + number(row["fee"])
                for row in stored
            ),
            Decimal(0),
        )
        currencies = {row.get("currency") for row in [*trades.values(), *stored]}
        source_days = {
            str(parse_ibkr_datetime(row.get("dateTime")))[:10]
            for row in trades.values()
        }
        stored_days = {str(row.get("date"))[:10] for row in stored}
        if len(currencies) != 1:
            return "missing_proof"
        return (
            "bounded_cost_dates_agree"
            if source_cost == destination_cost and source_days == stored_days
            else "bounded_cost_dates_differ"
        )
    except RuntimeError, KeyError, DecimalException:
        return "missing_proof"
