"""Offline bounded recovery: preserve accepted rows and refuse uncertain evidence."""

import copy
import json
import os
import socket
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

import identity_recovery as recovery
from identity_maintenance import canonical_json, digest, exact_json


def source_xml():
    cash = []
    accruals = []
    for action, gross, quantity, tax in (("ordinary", "25", "100", "-3.75"),
                                          ("bonus", "12", "30", "-1.20")):
        keys = f'accountId="U1" conid="1001" currency="USD" actionID="{action}" exDate="20260101"'
        cash.append(f'<CashTransaction {keys} isin="US0000000001" symbol="TEST" '
                    f'type="Dividends" levelOfDetail="DETAIL" amount="{gross}" '
                    'dateTime="20260110;120000 UTC"/>')
        cash.append(f'<CashTransaction {keys} isin="US0000000001" symbol="TEST" '
                    f'type="Withholding Tax" levelOfDetail="DETAIL" amount="{tax}" '
                    'dateTime="20260110;120000 UTC"/>')
        accruals.append(f'<ChangeInDividendAccrual {keys} quantity="{quantity}" code="Re" '
                        'payDate="20260110" date="20260110" reportDate="20260110"/>')
    return ('<FlexQueryResponse><FlexStatements><FlexStatement fromDate="20260101" '
            'toDate="20260131"><AccountInformation accountId="U1"/>'
            '<CashTransactions>' + ''.join(cash) + '</CashTransactions>'
            '<ChangeInDividendAccruals>' + ''.join(accruals) + '</ChangeInDividendAccruals>'
            '</FlexStatement></FlexStatements></FlexQueryResponse>').encode()


def accepted(payload, row_id="accepted-1"):
    return {**payload, "id": row_id, "isDraft": False, "tags": [],
            "assetProfile": {"symbol": payload["symbol"], "dataSource": "YAHOO",
                             "isin": "US0000000001", "currency": "USD"}}


@pytest.fixture
def case(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Network or credentials are forbidden")

    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("GHOST_TOKEN", "must-not-read")
    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(requests.sessions.Session, "request", denied)
    monkeypatch.setattr(os, "getenv", denied)
    source = source_xml()
    groups = recovery.parse_cash_dividends(source.decode())
    payloads, ok = recovery.convert_dividend_actions(groups[0], "destination", {}, {}, groups)
    assert ok and len(payloads) == 2
    snapshot = {"activities": [accepted(payloads[0])], "count": 1}
    evidence = {
        "schema": "ibkr-recovery-evidence-v1", "source_complete": True,
        "destination_complete": True, "unredacted": True,
        "tool_commit": "a" * 40, "destination_version": "qualified-version",
        "destination_image": "sha256:" + "b" * 64, "snapshot_ref": "saved-capture-1",
        "source_account": "U1", "destination_account": "destination",
        "snapshot_captured_at": "2026-01-11T00:00:00Z",
        "window": ["2026-01-01", "2026-01-31"], "symbol_mapping": {},
        "requests": {"import-1": {"status": "completed", "settlement_ref": "request-result-1",
                                  "settled_at": "2026-01-10T15:00:00Z", "payloads": payloads}},
    }
    return {"source": source, "snapshot": snapshot, "evidence": evidence, "root": tmp_path,
            "payloads": payloads}


def save(case):
    root = case["root"]
    source, destination, evidence = [root / name for name in ("source.xml", "snapshot.json", "evidence.json")]
    source.write_bytes(case["source"])
    destination.write_bytes(canonical_json(case["snapshot"]))
    # Snapshot numeric evidence must be original JSON numbers, not manifest decimal strings.
    context = copy.deepcopy(case["evidence"])
    context.update(source_sha256=digest(source.read_bytes()),
                   destination_sha256=digest(destination.read_bytes()))
    evidence.write_bytes(canonical_json(context))
    return source, destination, evidence, digest(evidence.read_bytes())


def run(case, output="preview"):
    return recovery.preview(*save(case), case["root"] / output)


def test_v2_partial_recovery_preview_exact_missing_private_deterministic(case):
    paths = save(case)
    original = [p.read_bytes() for p in paths[:3]]
    first = recovery.preview(*paths, case["root"] / "first")
    second = recovery.preview(*paths, case["root"] / "second")
    assert first == second
    manifest = exact_json((case["root"] / "first/manifest.json").read_bytes())
    assert manifest["missing_payloads"] == case["payloads"][1:]
    assert manifest["preserved"] == [{"id": "accepted-1", "comment": case["payloads"][0]["comment"],
        "fingerprint": digest(canonical_json(exact_json(original[1])["activities"][0]))}]
    assert [p.read_bytes() for p in paths[:3]] == original
    assert (case["root"] / "first").stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in (case["root"] / "first").iterdir())
    assert (case["root"] / "first/manifest.sha256").read_text().strip() == first


@pytest.mark.parametrize("status", ["pending", "timeout", "unknown", "failed", None])
def test_v2_partial_recovery_preview_unsettled_request(case, status):
    case["evidence"]["requests"]["import-1"]["status"] = status
    with pytest.raises(RuntimeError, match="Unresolved"):
        run(case)
    assert not (case["root"] / "preview").exists()


@pytest.mark.parametrize("mutation", [
    "source_complete", "destination_complete", "unredacted", "requests", "settlement_ref",
    "late_settlement", "short_window", "missing_action", "quantity", "fee", "currency",
    "duplicate", "inactive", "wrong_account", "changed_action", "no_accepted", "count",
    "missing_accrual", "invalid_cash", "source_account", "extra_action", "legacy",
])
def test_v2_partial_recovery_preview_rejects_incomplete_or_changed_evidence(case, mutation):
    context = case["evidence"]
    row = case["snapshot"]["activities"][0]
    if mutation in ("source_complete", "destination_complete", "unredacted"):
        context[mutation] = False
    elif mutation == "requests":
        context["requests"] = {}
    elif mutation == "settlement_ref":
        context["requests"]["import-1"]["settlement_ref"] = ""
    elif mutation == "late_settlement":
        context["requests"]["import-1"]["settled_at"] = "2026-01-12T00:00:00Z"
    elif mutation == "short_window":
        context["window"][0] = "2026-01-10"
    elif mutation == "missing_action":
        context["requests"]["import-1"]["payloads"] = case["payloads"][:1]
    elif mutation in ("quantity", "fee", "currency"):
        row[mutation] = 123 if mutation != "currency" else "EUR"
    elif mutation == "duplicate":
        case["snapshot"]["activities"].append({**row, "id": "duplicate"})
        case["snapshot"]["count"] += 1
    elif mutation == "inactive":
        row["isDraft"] = True
    elif mutation == "wrong_account":
        row["accountId"] = "another-account"
    elif mutation == "changed_action":
        row["comment"] += "-revised"
    elif mutation == "no_accepted":
        case["snapshot"] = {"activities": [], "count": 0}
    elif mutation == "count":
        case["snapshot"]["count"] = 2
    elif mutation == "missing_accrual":
        case["source"] = case["source"].replace(b'quantity="30"', b'quantity=""')
    elif mutation == "invalid_cash":
        case["source"] = case["source"].replace(b'amount="12"', b'amount="invalid"')
    elif mutation == "source_account":
        case["source"] = case["source"].replace(b'accountId="U1"', b'accountId="U2"')
    elif mutation == "extra_action":
        case["snapshot"]["activities"].append({**row, "id": "extra", "comment": row["comment"] + "-extra"})
        case["snapshot"]["count"] += 1
    elif mutation == "legacy":
        row["comment"] = "dividend#TEST#2026-01-10"
    with pytest.raises(RuntimeError):
        run(case)
    assert not (case["root"] / "preview").exists()


@pytest.mark.parametrize("index", [0, 1, 2])
def test_v2_partial_recovery_preview_changed_input_hash(case, index):
    paths = save(case)
    paths[index].write_bytes(paths[index].read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="hash changed"):
        recovery.preview(*paths, case["root"] / "preview")


def test_v2_partial_recovery_preview_complete_coverage_has_no_payload(case):
    case["snapshot"]["activities"].append(accepted(case["payloads"][1], "accepted-2"))
    case["snapshot"]["count"] = 2
    run(case)
    manifest = exact_json((case["root"] / "preview/manifest.json").read_bytes())
    assert manifest["missing_payloads"] == []
    assert len(manifest["preserved"]) == 2


@pytest.mark.parametrize("collision", ["existing", "input_parent", "symlink", "input_file"])
def test_v2_partial_recovery_preview_preserves_inputs_and_prior_outputs(case, collision):
    paths = save(case)
    original = [p.read_bytes() for p in paths[:3]]
    target = case["root"] / "output"
    if collision == "existing":
        target.mkdir()
        (target / "manifest.json").write_bytes(b"previous review")
    elif collision == "input_parent":
        target = case["root"]
    elif collision == "input_file":
        target = paths[0]
    else:
        target.symlink_to(case["root"], target_is_directory=True)
    with pytest.raises((RuntimeError, FileExistsError)):
        recovery.preview(*paths, target)
    assert [p.read_bytes() for p in paths[:3]] == original
    if collision == "existing":
        assert (target / "manifest.json").read_bytes() == b"previous review"


def test_v2_partial_recovery_preview_cli_offline_and_private_errors(case, monkeypatch, capsys):
    source, destination, evidence, sha = save(case)
    args = ["identity_recovery.py", "preview", "--source", str(source), "--destination", str(destination),
            "--evidence", str(evidence), "--evidence-sha256", sha, "--output", str(case["root"] / "cli")]
    monkeypatch.setattr("sys.argv", args)
    with patch("logging.disable"):
        assert recovery.main() == 0
    assert capsys.readouterr().out.startswith("Recovery preview SHA256: ")
    source.write_bytes(b"private-invalid-source")
    with patch("logging.disable"), pytest.raises(SystemExit) as error:
        recovery.main()
    assert error.value.code == 1
    text = capsys.readouterr().err
    assert "private-invalid-source" not in text and str(source) not in text


def test_v2_partial_recovery_preview_original_decimal_fields_do_not_round(case):
    # A difference invisible as a float must still refuse an accepted row.
    paths = save(case)
    raw = paths[1].read_bytes().replace(b'"quantity":30.0', b'"quantity":30.000000000000000000001')
    assert raw != paths[1].read_bytes()
    paths[1].write_bytes(raw)
    context = exact_json(paths[2].read_bytes())
    context["destination_sha256"] = digest(raw)
    # canonical_json renders Decimal as evidence strings; use original numeric JSON for the context.
    paths[2].write_text(json.dumps(json.loads(paths[2].read_text()) | {"destination_sha256": digest(raw)}))
    with pytest.raises(RuntimeError, match="context changed"):
        recovery.preview(paths[0], paths[1], paths[2], digest(paths[2].read_bytes()), case["root"] / "preview")


@pytest.mark.parametrize("mutation", ["manual_overlap", "unknown_context", "redacted",
                                     "malformed_tax", "mapping", "wrong_type", "extra_field"])
def test_v2_partial_recovery_preview_unsafe_snapshot_or_projection(case, mutation):
    row = case["snapshot"]["activities"][0]
    if mutation in ("manual_overlap", "unknown_context"):
        manual = {**row, "id": "manual", "comment": None}
        if mutation == "unknown_context":
            manual.pop("assetProfile")
        case["snapshot"]["activities"].append(manual)
        case["snapshot"]["count"] += 1
    elif mutation == "redacted":
        row["fee"] = None
    elif mutation == "malformed_tax":
        case["source"] = case["source"].replace(b'amount="-3.75"', b'amount="invalid"')
    elif mutation == "mapping":
        case["evidence"]["symbol_mapping"] = {"US0000000001": "OTHER"}
    elif mutation == "wrong_type":
        row["type"] = "BUY"
    elif mutation == "extra_field":
        case["payloads"][0]["unexpected"] = "not allowed"
    with pytest.raises(RuntimeError):
        run(case)


def test_v2_partial_recovery_preview_unrelated_manual_null_comment_is_preserved(case):
    row = {**case["snapshot"]["activities"][0], "id": "unrelated-manual", "comment": None,
           "date": "2025-01-10T00:00:00Z"}
    case["snapshot"]["activities"].append(row)
    case["snapshot"]["count"] += 1
    run(case)
    manifest = exact_json((case["root"] / "preview/manifest.json").read_bytes())
    assert manifest["missing_payloads"] == case["payloads"][1:]


def test_v2_partial_recovery_preview_cancelled_request_needs_independent_settlement(case):
    case["evidence"]["requests"]["import-1"]["status"] = "cancelled"
    case["evidence"]["requests"]["import-1"]["settlement_ref"] = "independent-cancellation-proof"
    run(case)


def test_v2_partial_recovery_preview_input_symlink_is_refused(case):
    source, destination, evidence, sha = save(case)
    link = case["root"] / "source-link.xml"
    link.symlink_to(source)
    with pytest.raises(RuntimeError, match="Symlink"):
        recovery.preview(link, destination, evidence, sha, case["root"] / "preview")


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_v2_partial_recovery_preview_ambiguous_json_refused(raw):
    with pytest.raises(RuntimeError):
        exact_json(raw)


@pytest.mark.parametrize("failure", ["fsync", "rename"])
def test_v2_partial_recovery_preview_publication_failure_leaves_no_partial_output(case, monkeypatch, failure):
    paths = save(case)
    before = {p.name: p.read_bytes() for p in case["root"].iterdir()}

    def fail(*args, **kwargs):
        raise OSError("Synthetic publication failure")

    if failure == "fsync":
        monkeypatch.setattr("identity_maintenance.os.fsync", fail)
    else:
        monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises(OSError, match="Synthetic publication failure"):
        recovery.preview(*paths, case["root"] / "preview")
    assert {p.name: p.read_bytes() for p in case["root"].iterdir()} == before


@pytest.fixture
def submission(case, monkeypatch, request):
    import yaml
    from unittest.mock import Mock

    if getattr(request, "param", None) == "three_actions":
        case["source"] = case["source"].replace(b'</CashTransactions>',
            b'<CashTransaction accountId="U1" conid="1001" currency="USD" actionID="third" '
            b'exDate="20260101" isin="US0000000001" symbol="TEST" type="Dividends" '
            b'amount="10" dateTime="20260110;120000 UTC"/></CashTransactions>')
        case["source"] = case["source"].replace(b'</ChangeInDividendAccruals>',
            b'<ChangeInDividendAccrual accountId="U1" conid="1001" currency="USD" actionID="third" '
            b'exDate="20260101" quantity="20" code="Re" payDate="20260110" date="20260110" '
            b'reportDate="20260110"/></ChangeInDividendAccruals>')
        groups = recovery.parse_cash_dividends(case["source"].decode())
        payloads, ok = recovery.convert_dividend_actions(groups[0], "destination", {}, {}, groups)
        assert ok and len(payloads) == 3
        case["payloads"] = payloads
        case["evidence"]["requests"]["import-1"]["payloads"] = payloads
    paths = save(case)
    output = case["root"] / "review"
    manifest_hash = recovery.preview(*paths, output)
    permit = {
        "schema": "ibkr-recovery-approval-v1", "host": "https://ghostfolio.invalid",
        "manifest_sha256": manifest_hash, "operation_plan_ref": "approved-plan",
        "backup_ref": "verified-backup", "writer_exclusion_ref": "stopped-all-writers",
        "settlement_ref": "independent-settlement", "writers_stopped": True,
        "requests_settled": True, "destination_version": case["evidence"]["destination_version"],
        "destination_image": case["evidence"]["destination_image"],
    }
    approval = case["root"] / "approval.json"
    approval.write_bytes(canonical_json(permit))
    journal = case["root"] / "journal.yaml"
    after = {"activities": case["snapshot"]["activities"] +
             [accepted(case["payloads"][1], "new-1")], "count": 2}

    def response(body, status=200):
        result = requests.Response()
        result.status_code = status
        result._content = canonical_json(body)
        return result

    get = Mock(side_effect=[response(case["snapshot"]), response(after), response(after)])

    def dispatch(*args, **kwargs):
        # The unresolved state and exact payload must be durable BEFORE the POST.
        state = yaml.safe_load(journal.read_text())
        assert state["status"] == "unknown"
        assert state["payloads"] == kwargs["json"]["activities"] == case["payloads"][1:]
        assert journal.stat().st_mode & 0o777 == 0o600
        return response({"activities": after["activities"][1:]}, 201)

    post = Mock(side_effect=dispatch)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)
    return {"paths": paths, "manifest": output / "manifest.json", "hash": manifest_hash,
            "approval": approval, "permit": permit, "journal": journal,
            "after": after, "get": get, "post": post, "response": response}


def dispatch_recovery(submission):
    s = submission
    return recovery.submit(*s["paths"], s["manifest"], s["hash"], s["approval"],
                           digest(s["approval"].read_bytes()), s["journal"],
                           "https://ghostfolio.invalid", "synthetic-bearer")


def journal_state(submission):
    import yaml
    return yaml.safe_load(submission["journal"].read_text())


def test_v2_partial_recovery_submit_exact_missing_once_and_simulation(case, submission):
    s = submission
    before = [p.read_bytes() for p in s["paths"][:3]]
    # The normal rule refuses the initial partial state; recovery does not relax it.
    group = recovery.parse_cash_dividends(case["source"].decode())[0]
    comment = case["payloads"][0]["comment"]
    decision, _, _ = recovery.dividend_dedup_decision(group, "destination", {},
        {"versioned_identities": {("U1", comment)}}, set())
    assert decision == "partial"
    dispatch_recovery(s)
    state = journal_state(s)
    assert state["status"] == "complete"
    assert state["accepted_ids"] == ["new-1"]
    assert state["simulation_reinsertions"] == 0 and state["coverage_groups"] == 1
    assert s["post"].call_count == 1 and s["get"].call_count == 3
    assert [p.read_bytes() for p in s["paths"][:3]] == before
    assert "synthetic-bearer" not in s["journal"].read_text()
    assert s["post"].call_args.args == ("https://ghostfolio.invalid/api/v1/import",)
    assert s["post"].call_args.kwargs["allow_redirects"] is False
    assert s["post"].call_args.kwargs["timeout"] == 60
    with pytest.raises(RuntimeError, match="already exists"):
        dispatch_recovery(s)
    assert s["post"].call_count == 1


@pytest.mark.parametrize("field,value", [
    ("writers_stopped", False), ("requests_settled", False),
    ("operation_plan_ref", ""), ("backup_ref", ""), ("writer_exclusion_ref", ""),
    ("settlement_ref", ""), ("host", "https://other.invalid"),
    ("manifest_sha256", "changed"), ("destination_version", "changed"),
    ("destination_image", "changed"), ("schema", "other"),
])
def test_v2_partial_recovery_submit_requires_approved_envelope(submission, field, value):
    s = submission
    s["permit"][field] = value
    s["approval"].write_bytes(canonical_json(s["permit"]))
    with pytest.raises(RuntimeError):
        dispatch_recovery(s)
    assert not s["journal"].exists()
    s["get"].assert_not_called()
    s["post"].assert_not_called()


@pytest.mark.parametrize("which", ["source", "snapshot", "evidence", "manifest", "approval_hash"])
def test_v2_partial_recovery_submit_changed_review_refuses(submission, which):
    s = submission
    if which in ("source", "snapshot", "evidence"):
        s["paths"][("source", "snapshot", "evidence").index(which)].write_bytes(b"changed")
    elif which == "manifest":
        data = exact_json(s["manifest"].read_bytes())
        data["missing_payloads"][0]["quantity"] = 99
        s["manifest"].write_bytes(canonical_json(data))
        s["hash"] = digest(s["manifest"].read_bytes())
    else:
        # Direct call supplies an approval hash reviewed before replacement.
        s["approval"].write_bytes(b"changed")
    with pytest.raises((RuntimeError, ValueError)):
        dispatch_recovery(s)
    s["get"].assert_not_called()
    s["post"].assert_not_called()


@pytest.mark.parametrize("fault", ["timeout", "redirect", "http400", "http500", "malformed",
                                    "partial", "duplicate", "financial", "wrong_account", "id"])
def test_v2_partial_recovery_submit_uncertain_or_partial_never_retries(submission, fault):
    s = submission
    row = copy.deepcopy(s["after"]["activities"][1])
    if fault == "timeout":
        s["post"].side_effect = requests.Timeout("secret response must not be logged")
    else:
        status = {"redirect": 307, "http400": 400, "http500": 500}.get(fault, 201)
        if fault == "financial":
            row["fee"] += 1
        if fault == "wrong_account":
            row["accountId"] = "other"
        if fault == "id":
            row["id"] = "accepted-1"
        rows = [] if fault == "partial" else [row, row] if fault == "duplicate" else [row]
        body = {} if fault == "malformed" else {"activities": rows}
        s["post"].side_effect = None
        s["post"].return_value = s["response"](body, status)
    with pytest.raises(RuntimeError):
        dispatch_recovery(s)
    assert s["post"].call_count == 1 and s["get"].call_count == 1
    assert journal_state(s)["status"] == ("partial" if fault == "partial" else "unknown")
    with pytest.raises(RuntimeError, match="already exists"):
        dispatch_recovery(s)
    assert s["post"].call_count == 1


@pytest.mark.parametrize("fault", ["pre_drift", "pre_partial", "readback_missing", "readback_money",
    "readback_preserved", "readback_duplicate", "readback_id", "readback_extra", "readback_timeout",
    "simulation_partial", "simulation_timeout"])
def test_v2_partial_recovery_submit_readback_and_simulation_gates(case, submission, fault):
    s = submission
    fresh, after, simulation = [copy.deepcopy(x) for x in (case["snapshot"], s["after"], s["after"])]
    if fault == "pre_drift":
        fresh["activities"][0]["tags"] = ["changed"]
    if fault == "pre_partial":
        fresh["count"] = 5
    if fault == "readback_missing":
        after = case["snapshot"]
    if fault == "readback_money":
        after["activities"][1]["quantity"] += 1
    if fault == "readback_preserved":
        after["activities"][0]["tags"] = ["changed"]
    if fault == "readback_duplicate":
        after["activities"].append({**after["activities"][1], "id": "duplicate"})
        after["count"] += 1
    if fault == "readback_id":
        after["activities"][1]["id"] = "different-id"
    if fault == "readback_extra":
        after["activities"].append({**after["activities"][0], "id": "extra", "comment": None})
        after["count"] += 1
    if fault == "simulation_partial":
        simulation = case["snapshot"]
    sequence = [s["response"](fresh), s["response"](after), s["response"](simulation)]
    if fault == "readback_timeout":
        sequence[1] = requests.Timeout("private")
    if fault == "simulation_timeout":
        sequence[2] = requests.Timeout("private")
    s["get"].side_effect = sequence
    with pytest.raises(RuntimeError):
        dispatch_recovery(s)
    assert s["post"].call_count == (0 if fault.startswith("pre_") else 1)
    assert journal_state(s)["status"] == ("prepared" if fault.startswith("pre_")
                                         else "accepted_unverified")


@pytest.mark.parametrize("fault", ["lock", "journal", "symlink", "evidence_alias", "lock_alias",
                                    "write_failure", "pending_failure", "evidence_race"])
def test_v2_partial_recovery_submit_local_safety(case, submission, monkeypatch, fault):
    import cleanup_recovery
    s = submission
    original = s["paths"][0].read_bytes()
    lock = None
    if fault == "lock":
        lock = cleanup_recovery.lock_journal(s["journal"])
    elif fault == "journal":
        s["journal"].write_text("existing")
    elif fault == "symlink":
        s["journal"].symlink_to(s["paths"][0])
    elif fault == "evidence_alias":
        s["journal"] = s["paths"][0]
    elif fault == "lock_alias":
        Path(str(s["journal"]) + ".lock").hardlink_to(s["paths"][0])
    elif fault in ("write_failure", "pending_failure"):
        write = cleanup_recovery.write_journal
        def failing(path, record, create=False):
            if fault == "write_failure" or record["status"] == "unknown":
                raise OSError("synthetic disk fault")
            write(path, record, create)
        monkeypatch.setattr(cleanup_recovery, "write_journal", failing)
    else:
        def changed(*args, **kwargs):
            s["paths"][0].write_bytes(b"changed during GET")
            return s["response"](case["snapshot"])
        s["get"].side_effect = changed
    try:
        with pytest.raises((RuntimeError, OSError)):
            dispatch_recovery(s)
    finally:
        if lock is not None:
            os.close(lock)
    s["post"].assert_not_called()
    if fault != "evidence_race":
        assert s["paths"][0].read_bytes() == original


def test_v2_partial_recovery_submit_cli(case, submission, monkeypatch, capsys):
    s = submission
    source, destination, evidence, sha = s["paths"]
    monkeypatch.setenv("GHOST_TOKEN", "synthetic-bearer")
    monkeypatch.setattr("sys.argv", ["identity_recovery.py", "submit", "--source", str(source),
        "--destination", str(destination), "--evidence", str(evidence), "--evidence-sha256", sha,
        "--manifest", str(s["manifest"]), "--manifest-sha256", s["hash"],
        "--approval", str(s["approval"]), "--approval-sha256", digest(s["approval"].read_bytes()),
        "--journal", str(s["journal"]), "--host", "https://ghostfolio.invalid"])
    with patch("logging.disable"):
        assert recovery.main() == 0
    assert "reinsertions: 0" in capsys.readouterr().out
    with patch("logging.disable"), pytest.raises(SystemExit) as error:
        recovery.main()
    assert error.value.code == 1
    assert "synthetic-bearer" not in capsys.readouterr().err


@pytest.mark.parametrize("submission", ["three_actions"], indirect=True)
def test_v2_partial_recovery_submit_preserves_nonempty_partial_subset(case, submission):
    s = submission
    s["post"].side_effect = None
    s["post"].return_value = s["response"]({"activities": s["after"]["activities"][1:]}, 201)
    with pytest.raises(RuntimeError, match="Partial recovery"):
        dispatch_recovery(s)
    state = journal_state(s)
    assert state["status"] == "partial" and state["accepted_ids"] == ["new-1"]
    assert len(state["payloads"]) == 2
    assert s["post"].call_count == 1 and s["get"].call_count == 1


@pytest.mark.parametrize("fault", ["account_shape", "profile_precedence", "null_fee", "inactive",
    "date", "currency", "symbol", "precision", "invalid_json", "response_timeout"])
def test_v2_partial_recovery_submit_response_evidence_is_exact(submission, fault):
    s = submission
    row = copy.deepcopy(s["after"]["activities"][1])
    if fault == "account_shape":
        row["account"] = "invalid"
    elif fault == "profile_precedence":
        row["SymbolProfile"] = row["assetProfile"]
        row["assetProfile"] = None
    elif fault == "null_fee":
        row["fee"] = None
    elif fault == "inactive":
        row["isDraft"] = True
    elif fault == "date":
        row["date"] = "2026-01-09T00:00:00Z"
    elif fault == "currency":
        row["currency"] = "EUR"
    elif fault == "symbol":
        row["assetProfile"]["symbol"] = "OTHER"
    result = s["response"]({"activities": [row]}, 201)
    if fault == "precision":
        result._content = result.content.replace(b'"quantity":100.0',
                                                b'"quantity":100.00000000000000001')
    if fault == "invalid_json":
        result._content = b'not-json'
    if fault == "response_timeout":
        result.status_code = 504
    s["post"].side_effect = None
    s["post"].return_value = result
    with pytest.raises((RuntimeError, ValueError)):
        dispatch_recovery(s)
    assert journal_state(s)["status"] == "unknown"
    assert s["post"].call_count == 1 and s["get"].call_count == 1
