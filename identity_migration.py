"""Offline identity migration evidence preview, outside the runtime image.

This first stage validates and binds saved inputs. It cannot authorize conversion.
No runtime configuration, credential loader or network client is used.
"""

import argparse
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from ghostfolio_ibkr_sync.ghostfolio import format_versioned_activity_identity
from ghostfolio_ibkr_sync.ibkr import (
    historical_dividend_report_window,
    parse_source_account_ids,
)
from identity_maintenance import (
    canonical_json,
    digest,
    exact_json,
    instant,
    publish_private,
    require,
    safe_path,
)


def keyed_yaml(data: bytes) -> dict[str, Any]:
    """Accept JSON-compatible keyed YAML without duplicate keys or aliases."""
    root = yaml.compose(data, Loader=yaml.SafeLoader)
    seen: set[int] = set()

    def check(node: Any) -> None:
        require(id(node) not in seen, "YAML aliases are not allowed")
        seen.add(id(node))
        if isinstance(node, yaml.MappingNode):
            keys: set[str] = set()
            for key, value in node.value:
                require(isinstance(key, yaml.ScalarNode) and key.tag == 'tag:yaml.org,2002:str'
                        and key.value and key.value not in keys, "Invalid or duplicate YAML key")
                keys.add(key.value)
                check(value)
        elif isinstance(node, yaml.SequenceNode):
            for child in node.value:
                check(child)
        else:
            require(isinstance(node, yaml.ScalarNode) and node.tag in {
                'tag:yaml.org,2002:str', 'tag:yaml.org,2002:int',
                'tag:yaml.org,2002:bool', 'tag:yaml.org,2002:null'}, "Unsupported YAML value")

    check(root)
    result = yaml.safe_load(data)
    require(isinstance(result, dict), "Inputs must be keyed YAML")
    return result


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_snapshot(snapshot: Any, metadata: Any) -> None:
    require(isinstance(metadata, dict), "Missing snapshot metadata")
    require(metadata.get("complete") is True and metadata.get("unredacted") is True,
            "Incomplete or redacted snapshot")
    for key in ("capture_ref", "destination_version", "destination_image"):
        require(text(metadata.get(key)), "Missing snapshot provenance")
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", metadata["destination_image"]),
            "Invalid destination image digest")
    instant(metadata.get("captured_at"))
    require(isinstance(snapshot, dict) and isinstance(snapshot.get("activities"), list),
            "Invalid snapshot")
    rows = snapshot["activities"]
    require(type(metadata.get("count")) is int and metadata["count"] == len(rows)
            and isinstance(snapshot.get("count"), Decimal) and snapshot["count"] == len(rows),
            "Incomplete snapshot count")
    ids: set[str] = set()
    for row in rows:
        require(isinstance(row, dict) and text(row.get("id")) and row["id"] not in ids,
                "Missing or duplicate activity ID")
        ids.add(row["id"])
        require("comment" in row and (row["comment"] is None or isinstance(row["comment"], str)),
                "Missing or redacted comment")
        for key in ("quantity", "unitPrice", "fee"):
            require(isinstance(row.get(key), Decimal) and row[key].is_finite(),
                    "Missing or redacted financial number")
        require(text(row.get("type")) and type(row.get("isDraft")) is bool
                and isinstance(row.get("tags"), list), "Incomplete activity context")
        # Null assignment/currency can be legitimate. Preserve it for exclusion
        # by the exact eligibility stage; never invent account or asset evidence.
        for key in ("accountId", "currency"):
            require(key in row and (row[key] is None or text(row[key])), "Missing activity context")
        instant(row.get("date"))
        require(any(key in row for key in ("assetProfile", "SymbolProfile")),
                "Missing security context")
        for key in ("assetProfile", "SymbolProfile"):
            if key in row:
                require(row[key] is None or isinstance(row[key], dict), "Invalid security context")


def preview(inputs: Path, output: Path) -> str:
    config_path = safe_path(inputs)
    config_bytes = config_path.read_bytes()
    config = keyed_yaml(config_bytes)
    require(config.get("schema") == "ibkr-migration-inputs-v1", "Unsupported inputs schema")
    require(re.fullmatch(r"[0-9a-f]{40}", str(config.get("tool_commit", ""))),
            "Missing exact tool commit")
    require(text(config.get("timezone")), "Missing IANA timezone")
    ZoneInfo(config["timezone"])
    window = config.get("window")
    require(isinstance(window, list) and len(window) == 2 and all(text(v) for v in window),
            "Missing report window")
    require(date.fromisoformat(window[0]) <= date.fromisoformat(window[1]), "Invalid report window")
    accounts = config.get("accounts")
    require(config.get("inventory_complete") is True and isinstance(accounts, dict) and accounts,
            "Missing complete configured source inventory")
    for account, destination in accounts.items():
        format_versioned_activity_identity(account, "TRADE", "validation")
        require(text(destination), "Missing destination account mapping")
    mapping = config.get("symbol_mapping")
    require(isinstance(mapping, dict) and all(text(k) and text(v) for k, v in mapping.items()),
            "Invalid symbol mapping")
    records = config.get("reports")
    require(isinstance(records, dict) and records, "Missing keyed reports")
    bindings = {"inputs": digest(config_bytes)}
    captured: dict[Path, bytes] = {config_path: config_bytes}

    def read(ref: Any) -> bytes:
        require(isinstance(ref, dict) and text(ref.get("path")), "Missing saved input path")
        path = safe_path(config_path.parent / ref["path"])
        data = path.read_bytes()
        require(re.fullmatch(r"[0-9a-f]{64}", str(ref.get("sha256", "")))
                and digest(data) == ref["sha256"], "Saved input hash changed")
        require(path not in captured, "Duplicate input path")
        captured[path] = data
        return data

    reports: dict[str, Any] = {}
    covered: set[str] = set()
    for name, ref in sorted(records.items()):
        require(isinstance(ref, dict) and ref.get("source_account") in accounts,
                "Report account missing from inventory")
        account = ref["source_account"]
        xml = read(ref).decode("utf-8-sig")
        require(parse_source_account_ids(xml) == {account}, "Report source account mismatch")
        bounds = historical_dividend_report_window(xml)
        require(bounds is not None, "Missing report window evidence")
        # Bounds are evidence of scope, not proof of full event completeness.
        reports[name] = {"source_account": account, "window": bounds, "sha256": ref["sha256"]}
        covered.add(account)
    require(covered == accounts.keys(), "Inventory accounts lack saved reports")
    snapshot_ref = config.get("snapshot")
    snapshot = exact_json(read(snapshot_ref))
    validate_snapshot(snapshot, snapshot_ref)
    bindings.update({"snapshot": snapshot_ref["sha256"],
                     "mapping": digest(canonical_json(mapping)),
                     "inventory": digest(canonical_json(accounts))})
    manifest = {
        "schema": "ibkr-migration-preview-v1", "stage": "validated-inputs",
        "actionable": False, "replacements": [],
        "pending": ["exact-historical-eligibility", "complete-import-selection-proof"],
        "bindings": bindings, "tool_commit": config["tool_commit"],
        "timezone": config["timezone"], "window": window, "accounts": accounts,
        "symbol_mapping": mapping, "reports": reports,
        "snapshot": {k: v for k, v in snapshot_ref.items() if k != "path"},
        "rows": [{"id": row["id"], "fields": row,
                  "fingerprint": digest(canonical_json(row))}
                 for row in sorted(snapshot["activities"], key=lambda row: row["id"])],
        "limitations": ["Declared inventory and report bounds do not prove event completeness.",
                        "This evidence preview cannot authorize apply or rollback."],
    }
    for path, data in captured.items():
        require(safe_path(path).read_bytes() == data, "Input changed during preview")
    data = canonical_json(manifest)
    manifest_hash = digest(data)
    publish_private(output, {"manifest.json": data,
                            "manifest.sha256": (manifest_hash + "\n").encode()}, list(captured))
    return manifest_hash


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("preview", help="Validate saved migration evidence offline")
    command.add_argument("--inputs", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(preview(args.inputs, args.output))
    except (RuntimeError, ValueError, OSError, KeyError, TypeError, SyntaxError, yaml.YAMLError) as error:
        parser.exit(1, f"Preview refused ({type(error).__name__}); check saved input evidence.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
