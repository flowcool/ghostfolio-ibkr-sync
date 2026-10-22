"""Bounded dividend-action recovery outside the runtime image.

Preview reads saved evidence only. Explicit submit requires separate operation
approval and a new durable journal; it never resumes or retries a submission.
"""

import argparse
import logging
import os
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path
from typing import Any

from ghostfolio_ibkr_sync.ghostfolio import (
    activity_is_active,
    dividend_context,
    format_versioned_activity_identity,
    parse_versioned_activity_identity,
)
from ghostfolio_ibkr_sync.ibkr import (
    DIVIDEND_CASH_TYPES,
    WITHHOLDING_CASH_TYPE,
    _dividend_decimal,
    dividend_field_prerequisites,
    flex_provenance_failures,
    historical_dividend_report_window,
    parse_cash_dividends,
    parse_source_account_ids,
)
from ghostfolio_ibkr_sync.sync import (
    convert_dividend_actions,
    dividend_action_conflict,
    dividend_dedup_decision,
    dividend_positive_actions,
)
from identity_maintenance import (
    canonical_json,
    digest,
    exact_json,
    instant,
    publish_private,
    read_evidence,
    require,
    safe_path,
)

PAYLOAD_FIELDS = frozenset({"accountId", "comment", "currency", "dataSource", "date",
                            "fee", "quantity", "symbol", "type", "unitPrice"})


def normalized_payload(payload: dict[str, Any]) -> dict[str, Any]:
    require(isinstance(payload, dict), "Invalid submitted payload")
    require(set(payload) == PAYLOAD_FIELDS, "Incomplete or unexpected submitted payload fields")
    result = dict(payload)
    result["date"] = instant(payload["date"])
    for field in ("quantity", "unitPrice", "fee"):
        number = payload[field]
        require(isinstance(number, (Decimal, float, int)) and not isinstance(number, bool),
                "Missing or redacted financial field")
        number = Decimal(str(number))
        require(number.is_finite() and (number >= 0 if field == "fee" else number > 0),
                "Invalid financial field")
        result[field] = number
    return result


def accepted_payload(row: dict[str, Any]) -> dict[str, Any]:
    require(activity_is_active(row), "Accepted identity has inactive context")
    profile = row["assetProfile"] if "assetProfile" in row else row.get("SymbolProfile")
    require(isinstance(profile, dict), "Missing accepted security context")
    require(row.get("account") is None or isinstance(row["account"], dict),
            "Invalid accepted account context")
    account = row.get("accountId") or (row.get("account") or {}).get("id")
    require(not row.get("account") or row["account"].get("id") == account,
            "Conflicting accepted account context")
    require(not profile.get("currency") or profile["currency"] == row.get("currency"),
            "Conflicting accepted currency context")
    return {**{field: row.get(field) for field in PAYLOAD_FIELDS},
            "accountId": account, "symbol": profile.get("symbol"),
            "dataSource": profile.get("dataSource"),
            "unitPrice": row.get("unitPrice")}


def build_preview(source: bytes, snapshot: dict[str, Any], evidence: dict[str, Any],
                  bindings: dict[str, str]) -> dict[str, Any]:
    """Validate all evidence before exposing any missing payload."""
    require(isinstance(evidence, dict) and isinstance(snapshot, dict), "Invalid evidence structure")
    require(evidence.get("schema") == "ibkr-recovery-evidence-v1", "Unsupported evidence schema")
    for key in ("source_complete", "destination_complete", "unredacted"):
        require(evidence.get(key) is True, "Incomplete evidence declaration")
    for key in ("tool_commit", "destination_version", "destination_image", "snapshot_ref"):
        require(isinstance(evidence.get(key), str) and evidence[key].strip(),
                "Missing evidence provenance")
    source_account = evidence["source_account"]
    destination_account = evidence["destination_account"]
    format_versioned_activity_identity(source_account, "DIVIDEND", "validation")
    require(isinstance(destination_account, str) and destination_account.strip(),
            "Missing destination account")
    captured = instant(evidence["snapshot_captured_at"])
    requests = evidence["requests"]
    require(isinstance(requests, dict) and requests, "Missing request settlement evidence")
    attempted: dict[str, dict[str, Any]] = {}
    for request_id, request in requests.items():
        require(isinstance(request_id, str) and request_id.strip(), "Missing request identity")
        require(isinstance(request, dict), "Invalid request evidence")
        require(request.get("status") in ("completed", "cancelled")
                and isinstance(request.get("settlement_ref"), str)
                and request["settlement_ref"].strip(), "Unresolved request")
        require(instant(request["settled_at"]) <= captured, "Snapshot predates request settlement")
        require(isinstance(request.get("payloads"), list) and request["payloads"],
                "Missing original submitted payloads")
        for payload in request["payloads"]:
            normalized_payload(payload)
            comment = payload["comment"]
            identity = parse_versioned_activity_identity(comment, payload["type"])
            require(identity and identity[:2] == (source_account, "DIVIDEND"),
                    "Submitted payload is not a source dividend")
            require(comment not in attempted, "Repeated original action request")
            attempted[comment] = payload

    xml = source.decode("utf-8")
    require("<!DOCTYPE" not in xml, "Document types are not allowed")
    root = ET.fromstring(xml)
    require(len(list(root.iter("FlexStatement"))) == 1, "Expected one complete source statement")
    # The runtime parser skips malformed amounts/dates. Maintenance must refuse
    # that loss, including malformed withholding that could change a missing fee.
    for element in root.iter("CashTransaction"):
        row = element.attrib
        if row.get("type") not in (*DIVIDEND_CASH_TYPES, WITHHOLDING_CASH_TYPE):
            continue
        if row.get("levelOfDetail", "DETAIL").upper() != "DETAIL":
            continue
        require(row.get("accountId") == source_account
                and _dividend_decimal(row.get("amount")) is not None,
                "Invalid cash evidence")
    require(parse_source_account_ids(xml) == {source_account}, "Source account mismatch")
    window = historical_dividend_report_window(xml)
    require(window and list(window) == evidence["window"], "Incomplete source window")
    require(not dividend_field_prerequisites(xml) and not flex_provenance_failures(xml),
            "Incomplete source action evidence")
    groups = parse_cash_dividends(xml)
    require(groups is not None, "Missing cash section")
    mapping = evidence["symbol_mapping"]
    require(isinstance(mapping, dict) and all(isinstance(k, str) and isinstance(v, str) and v
                                            for k, v in mapping.items()), "Invalid symbol mapping")

    rows = snapshot.get("activities")
    require(isinstance(rows, list) and snapshot.get("count") == len(rows),
            "Incomplete destination snapshot")
    by_comment: dict[str, list[dict[str, Any]]] = {}
    row_ids: set[str] = set()
    contexts: dict[Any, Any] = {}
    identities = set()
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"]
                and row["id"] not in row_ids, "Missing or duplicate destination row identity")
        require(row.get("account") is None or isinstance(row["account"], dict),
                "Invalid destination account context")
        for name in ("SymbolProfile", "assetProfile"):
            require(row.get(name) is None or isinstance(row[name], dict),
                    "Invalid destination security context")
        row_ids.add(row["id"])
        require("comment" in row and (row["comment"] is None or isinstance(row["comment"], str)),
                "Incomplete destination comments")
        # Null comments can be legitimate. Null financial fields indicate a
        # restricted or incomplete capture and cannot establish absence.
        for field in ("quantity", "unitPrice", "fee"):
            require(isinstance(row.get(field), Decimal) and row[field].is_finite(),
                    "Redacted or incomplete destination financial evidence")
        identity = parse_versioned_activity_identity(row["comment"], row.get("type"))
        if row["comment"] is not None:
            by_comment.setdefault(row["comment"].split("\n", 1)[0] if identity else row["comment"], []).append(row)
        if identity and identity[1] == "DIVIDEND":
            key = identity[0], row["comment"].split("\n", 1)[0]
            identities.add(key)
            profile = row.get("SymbolProfile") or row.get("assetProfile") or {}
            contexts.setdefault(key, []).append(dividend_context(profile, row.get("date")))
        elif row.get("type") == "DIVIDEND" and (
                row.get("accountId") or (row.get("account") or {}).get("id")) == destination_account:
            # A manual/historical row must not silently stand for a missing
            # action. Reuse the conservative security/day overlap decision.
            key = source_account, f"IBKR#v2#{source_account}:DIVIDEND:unproven-row:{row['id']}"
            identities.add(key)
            profile = row.get("SymbolProfile") or row.get("assetProfile") or {}
            contexts[key] = [dividend_context(profile, row.get("date"))]

    decisions = []
    missing = []
    preserved = []
    seen = set()
    for group in groups:
        actions = dividend_positive_actions(group)
        require(actions is not None, "Invalid source action coverage")
        expected_comments = {format_versioned_activity_identity(account, "DIVIDEND", action)
                             for account, action in actions}
        if not expected_comments.intersection(attempted):
            continue
        require(expected_comments <= attempted.keys(), "Incomplete original group payloads")
        require(all(account == source_account for account, _ in actions), "Cash account mismatch")
        require(window[0] <= group["date"] <= window[1], "Payment outside source window")
        proposed, ok = convert_dividend_actions(group, destination_account, mapping, {}, groups)
        require(ok and {p["comment"] for p in proposed} == expected_comments,
                "Incomplete source action conversion")
        symbol = proposed[0]["symbol"]
        historical = {f"dividend#{key}#{group['date']}"
                      for key in (group["isin"], group["symbol"], symbol) if key}
        require(not any(row["comment"] in historical
                        and (row.get("accountId") or (row.get("account") or {}).get("id"))
                        == destination_account for row in rows),
                "Legacy precedence does not prove action completeness")
        # Exclude expected identities, then use the existing overlap guard.
        other = {key for key in identities if key[1] not in expected_comments}
        require(not dividend_action_conflict(group, symbol, actions, {
            "versioned_identities": other, "versioned_dividend_context": contexts}),
            "Conflicting destination action context")
        accepted = []
        absent = []
        for payload in sorted(proposed, key=lambda p: p["comment"]):
            comment = payload["comment"]
            require(comment not in seen, "Source action appears in several groups")
            seen.add(comment)
            require(normalized_payload(payload) == normalized_payload(attempted[comment]),
                    "Source or submitted financial evidence changed")
            occupied = by_comment.get(comment, [])
            require(len(occupied) <= 1, "Duplicate accepted identity")
            if occupied:
                row = occupied[0]
                require(normalized_payload({**accepted_payload(row), "comment": comment}) == normalized_payload(payload),
                        "Accepted row financial or ownership context changed")
                accepted.append(row["id"])
                preserved.append({"id": row["id"], "comment": comment,
                                  "fingerprint": digest(canonical_json(row))})
            else:
                absent.append(payload)
        require(accepted, "Recovery requires proven partial or complete acceptance")
        missing.extend(absent)
        decisions.append({"security": group["isin"] or group["symbol"], "day": group["date"],
                          "accepted_ids": sorted(accepted),
                          "missing_identities": sorted(p["comment"] for p in absent)})
    require(seen == attempted.keys(), "Submitted actions lack complete source evidence")
    return {"schema": "ibkr-recovery-preview-v1", "bindings": bindings,
            "provenance": {key: evidence[key] for key in (
                "tool_commit", "destination_version", "destination_image", "snapshot_ref",
                "snapshot_captured_at", "source_account", "destination_account", "window")},
            "missing_payloads": sorted(missing, key=lambda p: p["comment"]),
            "preserved": sorted(preserved, key=lambda p: p["id"]),
            "groups": sorted(decisions, key=lambda p: (p["day"], p["security"])),
            "limitations": ["Legacy precedence does not certify event completeness.",
                            "Saved evidence cannot prove future quiescence or freshness.",
                            "Dispatch needs a separate approved operation plan and fresh checks."]}


def preview(source: Path, destination: Path, evidence: Path, evidence_sha256: str,
            output: Path) -> str:
    evidence_bytes = read_evidence(evidence, evidence_sha256)
    context = exact_json(evidence_bytes)
    require(isinstance(context, dict), "Invalid evidence structure")
    source_bytes = read_evidence(source, context["source_sha256"])
    destination_bytes = read_evidence(destination, context["destination_sha256"])
    bindings = {"source_sha256": digest(source_bytes),
                "destination_sha256": digest(destination_bytes),
                "evidence_sha256": digest(evidence_bytes)}
    manifest = build_preview(source_bytes, exact_json(destination_bytes), context, bindings)
    # Catch evidence replacement during validation before publishing anything.
    for path, expected in ((source, bindings["source_sha256"]),
                           (destination, bindings["destination_sha256"]),
                           (evidence, evidence_sha256)):
        read_evidence(path, expected)
    data = canonical_json(manifest)
    manifest_hash = digest(data)
    publish_private(output, {"manifest.json": data, "manifest.sha256": (manifest_hash + "\n").encode()},
                    [source, destination, evidence])
    return manifest_hash


def recovery_response(response: Any) -> dict[str, Any]:
    require(200 <= response.status_code < 300, "Recovery HTTP outcome unresolved")
    body = exact_json(response.content)
    require(isinstance(body, dict), "Invalid recovery response")
    return body


def recovery_snapshot(host: str, headers: dict[str, str]) -> dict[str, Any]:
    return recovery_response(recovery_request("get", f"{host}/api/v1/activities", headers=headers))


def recovery_request(method: str, url: str, **kwargs: Any) -> Any:
    import requests

    try:
        return getattr(requests, method)(url, timeout=60, allow_redirects=False, **kwargs)
    except requests.RequestException:
        raise RuntimeError("Recovery request unresolved; inspect durable journal") from None


def submit(source: Path, destination: Path, evidence: Path, evidence_sha256: str,
           manifest: Path, manifest_sha256: str, approval: Path, approval_sha256: str,
           journal: Path, host: str, token: str) -> None:
    """Explicit one-shot maintenance. An existing journal is never resumed or retried."""
    from cleanup_recovery import journal_host, lock_journal, write_journal
    from ghostfolio_ibkr_sync.ghostfolio import ghost_get_existing_orders, ghost_headers

    host = journal_host({"ghost_host": host})
    require(isinstance(token, str) and token.strip(), "Missing recovery credential")
    context = exact_json(read_evidence(evidence, evidence_sha256))
    source_bytes = read_evidence(source, context["source_sha256"])
    snapshot_bytes = read_evidence(destination, context["destination_sha256"])
    snapshot = exact_json(snapshot_bytes)
    bindings = {"source_sha256": digest(source_bytes),
                "destination_sha256": digest(snapshot_bytes), "evidence_sha256": evidence_sha256}
    proposed = build_preview(source_bytes, snapshot, context, bindings)
    reviewed = exact_json(read_evidence(manifest, manifest_sha256))
    require(reviewed == exact_json(canonical_json(proposed)), "Reviewed manifest changed")
    permit = exact_json(read_evidence(approval, approval_sha256))
    require(isinstance(permit, dict) and permit.get("schema") == "ibkr-recovery-approval-v1",
            "Invalid recovery approval")
    for key in ("operation_plan_ref", "backup_ref", "writer_exclusion_ref", "settlement_ref"):
        require(isinstance(permit.get(key), str) and permit[key].strip(),
                "Missing operation prerequisite")
    require(permit.get("writers_stopped") is True and permit.get("requests_settled") is True,
            "Writers or requests are not settled")
    require(all(permit.get(key) == value for key, value in {
        "host": host, "manifest_sha256": manifest_sha256,
        "destination_version": context["destination_version"],
        "destination_image": context["destination_image"],
    }.items()), "Approval target or manifest changed")
    payloads = proposed["missing_payloads"]
    require(payloads, "No missing actions; submission refused")
    # Validate destinations before opening even the companion lock. Exclusive
    # creation prevents replacing an existing journal, including a hard-link alias.
    path = safe_path(journal)
    inputs = [source, destination, evidence, manifest, approval]
    lock_path = Path(str(path) + ".lock")
    safe_path(lock_path)
    for target in (path, lock_path):
        for item in inputs:
            item = safe_path(item)
            require(not item.is_relative_to(target) and not target.is_relative_to(item),
                    "Journal overlaps evidence")
            require(not target.exists() or not target.samefile(item), "Journal aliases evidence")
    lock = lock_journal(path)
    try:
        require(not path.exists(), "Recovery journal already exists; automatic retry refused")
        record = {"schema": "ibkr-recovery-journal-v1", "host": host,
                  "manifest_sha256": manifest_sha256, "approval_sha256": approval_sha256,
                  "bindings": bindings, "payloads": payloads, "status": "prepared"}
        write_journal(path, record, create=True)
        headers = ghost_headers(token)
        fresh = recovery_snapshot(host, headers)
        require(canonical_json(fresh) == canonical_json(snapshot), "Destination changed since review")
        # Repeat all evidence validation after the fresh read, before dispatch.
        build_preview(source_bytes, fresh, context, bindings)
        for item, expected in ((source, bindings["source_sha256"]),
                               (destination, bindings["destination_sha256"]),
                               (evidence, evidence_sha256), (manifest, manifest_sha256),
                               (approval, approval_sha256)):
            read_evidence(item, expected)
        record["status"] = "unknown"
        write_journal(path, record)
        # No runtime import helper: it can retry unresolved symbols. Maintenance
        # sends exactly this reviewed batch once, including on HTTP 400/timeout.
        response = recovery_request("post", f"{host}/api/v1/import", headers=headers,
                                    json={"activities": payloads})
        body = recovery_response(response)
        rows = body.get("activities")
        require(isinstance(rows, list), "Missing accepted response")
        expected = {p["comment"]: normalized_payload(p) for p in payloads}
        seen: set[str] = set()
        ids: set[str] = {row["id"] for row in snapshot["activities"]}
        for row in rows:
            require(isinstance(row, dict) and not row.get("error"), "Invalid accepted response")
            comment = row.get("comment")
            row_id = row.get("id")
            require(isinstance(row_id, str) and row_id.strip() and row_id not in ids
                    and isinstance(comment, str) and comment in expected and comment not in seen,
                    "Unmatched accepted identity")
            require(normalized_payload({**accepted_payload(row), "comment": comment}) == expected[comment],
                    "Accepted response changed financial evidence")
            seen.add(comment)
            ids.add(row_id)
        record["accepted_ids"] = sorted(ids - {r["id"] for r in snapshot["activities"]})
        if seen != expected.keys():
            record["status"] = "partial"
            write_journal(path, record)
            raise RuntimeError("Partial recovery; inspect settlement before a new approved preview")
        record["status"] = "accepted_unverified"
        write_journal(path, record)
        after = recovery_snapshot(host, headers)
        completed = build_preview(source_bytes, after, context, bindings)
        require(not completed["missing_payloads"], "Recovery coverage incomplete")
        # Preserve every existing row, not just accepted dividend fingerprints.
        before_rows = {r["id"]: r for r in snapshot["activities"]}
        after_rows = {r["id"]: r for r in after["activities"]}
        require(all(key in after_rows and canonical_json(row) == canonical_json(after_rows[key])
                    for key, row in before_rows.items()), "Existing destination row changed")
        require(after_rows.keys() == ids, "Unexpected readback row identities")
        require({p["id"] for p in completed["preserved"]} ==
                {p["id"] for p in proposed["preserved"]} | set(record["accepted_ids"]),
                "Readback does not prove accepted response identities")
        # Run the normal reader and selection rule, with dry_run forced locally.
        import requests

        try:
            _, historical, positions = ghost_get_existing_orders(
                {"ghost_host": host, "ghost_token": token, "dry_run": True})
        except requests.RequestException:
            raise RuntimeError("Normal simulation read unresolved; inspect durable journal") from None
        groups = parse_cash_dividends(source_bytes.decode())
        relevant = {p["comment"] for request in context["requests"].values()
                    for p in request["payloads"]}
        require({(context["source_account"], comment) for comment in relevant}
                <= positions["versioned_identities"], "Normal simulation lost action coverage")
        checked = 0
        for group in groups or []:
            actions = dividend_positive_actions(group)
            if not actions or not any(format_versioned_activity_identity(a, "DIVIDEND", b)
                                      in relevant for a, b in actions):
                continue
            decision, _, _ = dividend_dedup_decision(group, context["destination_account"],
                                                    context["symbol_mapping"], positions, historical)
            require(decision == "existing", "Normal simulation would reinsert or reject recovery")
            checked += 1
        require(checked == len(proposed["groups"]), "Incomplete normal simulation")
        record.update(status="complete", simulation_reinsertions=0, coverage_groups=checked,
                      readback_sha256=digest(canonical_json(after)))
        write_journal(path, record)
    finally:
        os.close(lock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["preview", "submit"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--evidence-sha256", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--approval-sha256")
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--host")
    args = parser.parse_args()
    submission = (args.manifest, args.manifest_sha256, args.approval, args.approval_sha256,
                  args.journal, args.host)
    if args.command == "preview" and (args.output is None or any(submission)):
        parser.error("preview requires --output and refuses submission options")
    if args.command == "submit" and (args.output is not None or not all(submission)):
        parser.error("submit requires manifest/approval hashes, journal and host; refuses --output")
    # Pure runtime helpers can log source values; keep private evidence out of stdout/stderr.
    logging.disable(logging.CRITICAL)
    try:
        if args.command == "submit":
            submit(args.source, args.destination, args.evidence, args.evidence_sha256,
                   *submission[:4], args.journal, args.host, os.environ.get("GHOST_TOKEN", ""))
            print("Recovery complete: full coverage; normal simulation reinsertions: 0")
            return 0
        result = preview(args.source, args.destination, args.evidence, args.evidence_sha256, args.output)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ET.ParseError):
        parser.exit(1, f"Recovery {args.command} refused: invalid, incomplete or changed evidence; "
                    "inspect journal.\n")
    print(f"Recovery preview SHA256: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
