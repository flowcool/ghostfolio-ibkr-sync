"""Corporate-action behavior at the approved source/decision/runtime seams."""

from itertools import permutations
from xml.etree import ElementTree as ET

import pytest

from ghostfolio_ibkr_sync.corporate_actions import inventory


def action(**changes):
    return {
        "accountId": "SOURCE",
        "type": "FS",
        "actionID": "EVENT1",
        "transactionID": "LEG1",
        "levelOfDetail": "DETAIL",
        "conid": "CONTRACT1",
        "isin": "JP0000000001",
        "symbol": "SAMPLE.T",
        "quantity": "400",
        "currency": "JPY",
        "dateTime": "20250327;202500 EDT",
        "reportDate": "20250328",
        "description": "SAMPLE SPLIT 5 FOR 1",
        "proceeds": "0",
        "amount": "0",
        **changes,
    }


def report(
    rows=(), *, section=True, account="SOURCE", start="20250101", end="20251231"
):
    root = ET.Element("FlexQueryResponse")
    statement = ET.SubElement(
        root, "FlexStatement", accountId=account, fromDate=start, toDate=end
    )
    ET.SubElement(statement, "AccountInformation", accountId=account, currency="JPY")
    if section:
        actions = ET.SubElement(statement, "CorporateActions")
        for row in rows:
            ET.SubElement(actions, "CorporateAction", row)
    ET.SubElement(statement, "Trades")
    ET.SubElement(statement, "CashTransactions")
    ET.SubElement(statement, "ChangeInDividendAccruals")
    return ET.tostring(root, encoding="unicode")


def test_inventory_three_observed_shapes_ignore_row_order_and_exact_repeats():
    rows = [
        action(),
        action(actionID="EVENT2", transactionID="LEG2", conid="CONTRACT2"),
        action(
            type="RS",
            actionID="EVENT3",
            transactionID="OUT",
            quantity="-3000",
            conid="OLD",
            isin="CA0000000001",
            description="SAMPLE SPLIT 1 FOR 30",
        ),
        action(
            type="RS",
            actionID="EVENT3",
            transactionID="IN",
            quantity="100",
            conid="NEW",
            isin="CA0000000002",
            description="SAMPLE SPLIT 1 FOR 30",
        ),
    ]
    expected = None
    for order in permutations(rows):
        result = inventory(report([*order, order[0]]), "SOURCE")
        assert len(result["events"]) == 3
        if expected is None:
            expected = result
        assert result["events"] == expected["events"]
        assert all(e["held"] for e in result["events"].values())
    forward = result["events"]["EVENT1"]
    assert forward["candidate_ratio"] == [5, 1]
    assert "before_quantity_unproven" in forward["reasons"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", "NaN"),
        ("quantity", "Infinity"),
        ("quantity", "bad"),
        ("actionID", ""),
        ("conid", ""),
        ("dateTime", "20250327;202500"),
        ("reportDate", "wrong"),
        ("type", "MERGER"),
        ("levelOfDetail", "SUMMARY"),
    ],
)
def test_inventory_malformed_or_unsupported_remains_held(field, value):
    result = inventory(report([action(**{field: value})]), "SOURCE")
    assert result["events"]
    assert all(e["held"] and e["reasons"] for e in result["events"].values())


def test_inventory_conflicting_transaction_and_wrong_source_cannot_release():
    result = inventory(report([action(), action(quantity="401")]), "SOURCE")
    assert "conflicting_transaction" in result["events"]["EVENT1"]["reasons"]
    with pytest.raises(RuntimeError, match="source account"):
        inventory(report([action(accountId="OTHER")]), "SOURCE")


def test_source_sections_absent_empty_and_wrong_statement_are_distinct():
    assert inventory(report(), "SOURCE")["section_present"]
    assert not inventory(report(section=False), "SOURCE")["section_present"]
    assert inventory(report(section=False), "SOURCE")["account_held"]
    assert not inventory(report(), "SOURCE")["account_held"]
    with pytest.raises(RuntimeError, match="source account"):
        inventory(report(account="OTHER"), "SOURCE")


def test_retained_evidence_reparse_and_recovery_after_state_loss(tmp_path):
    from ghostfolio_ibkr_sync.corporate_actions import (
        close_store,
        open_store,
        retain_report,
    )

    tmp_path.chmod(0o700)
    path = tmp_path / "actions.yaml"
    store = open_store(str(path), [], simulation=True)
    try:
        retained = retain_report(
            store, report([action()]), "SOURCE", "QUERY", {"JP0000000001": "SAMPLE.T"}
        )
        assert retained[0]["events"]["EVENT1"]["held"]
    finally:
        close_store(store)
    path.rename(tmp_path / "saved-state.yaml")
    # Surviving source bindings must rebuild known events, never blank them.
    store = open_store(str(path), [], simulation=True)
    try:
        retained = retain_report(
            store, report(), "SOURCE", "QUERY", {"JP0000000001": "SAMPLE.T"}
        )
        assert any("EVENT1" in r["events"] for r in retained)
    finally:
        close_store(store)


def test_persistence_live_missing_state_and_unsafe_directory_are_refused(tmp_path):
    from ghostfolio_ibkr_sync.corporate_actions import open_store

    tmp_path.chmod(0o700)
    with pytest.raises(RuntimeError, match="simulation"):
        open_store(str(tmp_path / "actions.yaml"), [], simulation=False)
    assert not (tmp_path / "actions.yaml").exists()
    tmp_path.chmod(0o755)
    with pytest.raises(RuntimeError, match="private"):
        open_store(str(tmp_path / "actions.yaml"), [], simulation=True)


def test_retained_evidence_changed_bytes_refuse_without_replacing_state(tmp_path):
    from ghostfolio_ibkr_sync.corporate_actions import (
        close_store,
        open_store,
        retain_report,
    )

    tmp_path.chmod(0o700)
    path = tmp_path / "actions.yaml"
    store = open_store(str(path), [], simulation=True)
    try:
        retain_report(store, report([action()]), "SOURCE", "QUERY", {})
        original = path.read_bytes()
        obj = next((tmp_path / "actions.yaml.evidence").glob("*.xml"))
        obj.write_text(report())
        with pytest.raises(RuntimeError, match="hash"):
            retain_report(store, report(), "SOURCE", "QUERY", {})
        assert path.read_bytes() == original
    finally:
        close_store(store)


def test_persistence_report_without_required_section_cannot_bootstrap(tmp_path):
    from ghostfolio_ibkr_sync.corporate_actions import (
        close_store,
        open_store,
        retain_report,
    )

    tmp_path.chmod(0o700)
    path = tmp_path / "actions.yaml"
    store = open_store(str(path), [], simulation=True)
    try:
        with pytest.raises(RuntimeError, match="section"):
            retain_report(store, report(section=False), "SOURCE", "QUERY", {})
        assert not path.exists()
    finally:
        close_store(store)


def test_conclusions_official_date_proof_is_bound_to_document(tmp_path):
    import hashlib
    import yaml
    from ghostfolio_ibkr_sync.corporate_actions import load_date_proofs

    tmp_path.chmod(0o700)
    document = tmp_path / "announcement.txt"
    document.write_text("Official split effective date: 2025-03-27")
    document.chmod(0o600)
    path = tmp_path / "proofs.yaml"
    record = {
        "effective_date": "2025-03-27",
        "source_url": "https://issuer.example/announcement",
        "document": "announcement.txt",
        "sha256": hashlib.sha256(document.read_bytes()).hexdigest(),
    }
    path.write_text(
        yaml.safe_dump({"version": 1, "events": {"SOURCE": {"EVENT1": record}}})
    )
    path.chmod(0o600)
    proofs = load_date_proofs(str(path))
    assert proofs[("SOURCE", "EVENT1")]["effective_date"] == "2025-03-27"
    document.write_text("changed")
    with pytest.raises(RuntimeError, match="digest"):
        load_date_proofs(str(path))


def test_native_evidence_reads_preserve_exact_json_and_never_follow_redirects(
    monkeypatch,
):
    from ghostfolio_ibkr_sync.ghostfolio import ghost_read_exact
    from unittest.mock import Mock
    import requests

    response = Mock(status_code=200, content=b'{"quantity":100.00000000000001}')
    response.is_redirect = False
    response.headers = {}
    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)
    data = ghost_read_exact(
        {"ghost_host": "https://ghost.example", "ghost_token": "secret"},
        "/api/v1/portfolio/holding/YAHOO/SAMPLE",
    )
    assert str(data["quantity"]) == "100.00000000000001"
    assert get.call_args.kwargs["allow_redirects"] is False
    response.status_code = 302
    with pytest.raises(RuntimeError):
        ghost_read_exact(
            {"ghost_host": "https://ghost.example", "ghost_token": "secret"},
            "/api/v1/export",
        )


def reverse_case():
    from ghostfolio_ibkr_sync.corporate_actions import inventory

    rows = [
        action(
            type="RS",
            quantity="-3000",
            isin="CA0000000001",
            conid="OLD",
            transactionID="OUT",
            description="SAMPLE SPLIT 1 FOR 30",
        ),
        action(
            type="RS",
            quantity="100",
            isin="CA0000000002",
            conid="NEW",
            transactionID="IN",
            description="SAMPLE SPLIT 1 FOR 30",
        ),
    ]
    reports = [inventory(report(rows), "SOURCE")]
    mapping = {"CA0000000001": "SAMPLE.T", "CA0000000002": "SAMPLE.T"}
    row = {
        "id": "ROW",
        "accountId": "TARGET",
        "type": "BUY",
        "quantity": 100,
        "unitPrice": 12,
        "fee": 1,
        "currency": "JPY",
        "date": "2025-03-28T00:00:00Z",
        "assetProfile": {
            "symbol": "SAMPLE.T",
            "dataSource": "YAHOO",
            "isin": "CA0000000002",
        },
    }
    snapshot = {"count": 1, "activities": [row]}
    evidence = {
        "SAMPLE.T": {
            "profile": {"assetProfile": row["assetProfile"], "splits": []},
            "holding": {"quantity": 100},
            "version": None,
        }
    }
    proofs = {("SOURCE", "EVENT1"): {"effective_date": "2025-03-27"}}
    return reports, mapping, snapshot, evidence, proofs


def test_conclusions_reverse_identity_and_effective_holdings_release_without_history_claim():
    from ghostfolio_ibkr_sync.corporate_actions import decide

    reports, mapping, snapshot, evidence, proofs = reverse_case()
    result = decide(reports, "SOURCE", "TARGET", mapping, snapshot, evidence, proofs)
    event = result["findings"]["EVENT1"]
    assert not result["account_held"] and not event["held"]
    assert event["conclusions"]["quantity"] == "observed_agreement"
    assert event["conclusions"]["history"] == "missing_proof"
    assert event["conclusions"]["cash"] == "no_action_cash_observed"
    assert result["effective"]["SAMPLE.T"] == 100


@pytest.mark.parametrize(
    "variant",
    [
        "missing_date",
        "missing_mapping",
        "null_isin",
        "conflicting_isin",
        "quantity_mismatch",
        "wrong_holding_scope",
        "unqualified_native",
        "missing_splits",
        "competing_alias",
    ],
)
def test_conclusions_missing_financial_proof_holds(variant):
    from ghostfolio_ibkr_sync.corporate_actions import decide

    reports, mapping, snapshot, evidence, proofs = reverse_case()
    if variant == "missing_date":
        proofs = {}
    if variant == "missing_mapping":
        mapping.pop("CA0000000001")
    if variant == "null_isin":
        evidence["SAMPLE.T"]["profile"]["assetProfile"]["isin"] = None
    if variant == "conflicting_isin":
        evidence["SAMPLE.T"]["profile"]["assetProfile"]["isin"] = "OTHER"
    if variant == "quantity_mismatch":
        snapshot["activities"][0]["quantity"] = 101
    if variant == "wrong_holding_scope":
        evidence["SAMPLE.T"]["holding"]["quantity"] = 200
    if variant == "missing_splits":
        evidence["SAMPLE.T"]["profile"].pop("splits")
    if variant == "unqualified_native":
        evidence["SAMPLE.T"]["profile"]["splits"] = [
            {"date": "2025-03-27", "numerator": 1, "denominator": 30}
        ]
        evidence["SAMPLE.T"]["version"] = "3.92.0"
    if variant == "competing_alias":
        snapshot["activities"].append(
            {
                **snapshot["activities"][0],
                "id": "OTHER",
                "assetProfile": {
                    "dataSource": "YAHOO",
                    "symbol": "OLD.T",
                    "isin": "CA0000000001",
                },
            }
        )
        snapshot["count"] = 2
    result = decide(reports, "SOURCE", "TARGET", mapping, snapshot, evidence, proofs)
    assert result["account_held"] or "SAMPLE.T" in result["symbols"]


def test_candidate_units_normalized_history_and_boundary_day_stay_held():
    from ghostfolio_ibkr_sync.corporate_actions import candidate_held, decide

    reports, mapping, snapshot, evidence, proofs = reverse_case()
    decision = decide(reports, "SOURCE", "TARGET", mapping, snapshot, evidence, proofs)
    base = {"type": "BUY", "symbol": "SAMPLE.T"}
    assert candidate_held(decision, {**base, "date": "2025-03-26"})
    assert candidate_held(decision, {**base, "date": "2025-03-27"})
    assert not candidate_held(decision, {**base, "date": "2025-03-28"})
    assert not candidate_held(decision, {"type": "DIVIDEND", "symbol": "SAMPLE.T"})
    assert not candidate_held(
        decision, {**base, "symbol": "UNRELATED", "date": "2025-03-26"}
    )


def test_effective_holdings_source_forward_delta_requires_independent_before_position():
    from ghostfolio_ibkr_sync.corporate_actions import decide

    reports, mapping, snapshot, evidence, proofs = reverse_case()
    baseline = ET.fromstring(report([], end="20250326"))
    section = ET.SubElement(baseline.find("FlexStatement"), "OpenPositions")
    ET.SubElement(
        section,
        "OpenPosition",
        accountId="SOURCE",
        conid="CONTRACT1",
        isin="JP0000000001",
        levelOfDetail="SUMMARY",
        position="100",
    )
    reports = [
        inventory(ET.tostring(baseline, encoding="unicode"), "SOURCE"),
        inventory(report([action()], start="20250327"), "SOURCE"),
    ]
    mapping = {"JP0000000001": "SAMPLE.T"}
    snapshot["activities"][0]["quantity"] = 500
    snapshot["activities"][0]["assetProfile"]["isin"] = "JP0000000001"
    evidence["SAMPLE.T"]["holding"]["quantity"] = 500
    result = decide(reports, "SOURCE", "TARGET", mapping, snapshot, evidence, proofs)
    assert not result["findings"]["EVENT1"]["held"]
    baseline.find(".//OpenPosition").set("position", "101")
    reports[0] = inventory(ET.tostring(baseline, encoding="unicode"), "SOURCE")
    assert decide(reports, "SOURCE", "TARGET", mapping, snapshot, evidence, proofs)[
        "symbols"
    ]


@pytest.mark.parametrize(
    "version,expected",
    [
        ("3.90.9", False),
        ("3.91.0", True),
        ("3.92.0", True),
        ("3.92.0-rc.1", False),
        (None, False),
        ("v3.92.0", False),
    ],
)
def test_native_evidence_version_is_a_necessary_gate(version, expected):
    from ghostfolio_ibkr_sync.corporate_actions import native_version_supported

    assert native_version_supported(version) is expected


def test_native_evidence_effective_holdings_exact_residue_stays_unresolved(monkeypatch):
    from decimal import Decimal
    from ghostfolio_ibkr_sync import corporate_actions as ca

    reports, mapping, snapshot, evidence, proofs = reverse_case()
    row = snapshot["activities"][0]
    row["quantity"] = 3000
    row["date"] = "2025-03-20T00:00:00Z"
    evidence["SAMPLE.T"]["profile"]["splits"] = [
        {"date": "2025-03-27", "numerator": 1, "denominator": 30}
    ]
    evidence["SAMPLE.T"]["version"] = "3.92.0"
    monkeypatch.setattr(
        ca, "NATIVE_READ_QUALIFIED", True
    )  # offline calculation, no runtime qualification
    assert not ca.decide(
        reports, "SOURCE", "TARGET", mapping, snapshot, evidence, proofs
    )["symbols"]
    evidence["SAMPLE.T"]["holding"]["quantity"] = Decimal("100.00000000000001")
    result = ca.decide(reports, "SOURCE", "TARGET", mapping, snapshot, evidence, proofs)
    assert "SAMPLE.T" in result["symbols"]


def notification_decision(held=False, reason="observed"):
    return {
        "account_held": False,
        "symbols": {"SAMPLE.T"} if held else set(),
        "effective": {},
        "dates": {},
        "normalized": set(),
        "findings": {
            "EVENT1": {
                "rows": [],
                "candidate_ratio": [5, 1],
                "reasons": [reason],
                "symbols": ["SAMPLE.T"],
                "isins": ["JP0000000001"],
                "held": held,
                "conclusions": {"quantity": reason},
            }
        },
    }


def test_notifications_first_changed_repeated_holds_and_resumption(tmp_path):
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    filename = str(tmp_path / "state.yaml")
    plan = ca.plan_notifications(filename, {"SOURCE": notification_decision()})
    assert plan["counts"] == {
        "active_holds": 0,
        "changed_findings": 1,
        "resumptions": 0,
    }
    assert ca.confirm_notification(plan)
    assert not ca.plan_notifications(filename, {"SOURCE": notification_decision()})[
        "sent"
    ]
    changed = ca.plan_notifications(
        filename, {"SOURCE": notification_decision(reason="changed")}
    )
    assert changed["counts"]["changed_findings"] == 1
    assert ca.confirm_notification(changed)
    for _ in range(2):
        active = ca.plan_notifications(
            filename, {"SOURCE": notification_decision(True)}
        )
        assert active["counts"]["active_holds"] == 1
        assert ca.confirm_notification(active)
    resumed = ca.plan_notifications(filename, {"SOURCE": notification_decision()})
    assert resumed["counts"]["resumptions"] == 1


def test_notification_persistence_generation_drift_never_overwrites(tmp_path):
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    filename = str(tmp_path / "state.yaml")
    one = ca.plan_notifications(filename, {"SOURCE": notification_decision()})
    concurrent = ca.plan_notifications(filename, {"OTHER": notification_decision()})
    assert ca.confirm_notification(concurrent)
    path = tmp_path / "state.yaml.notifications.yaml"
    protected = path.read_bytes()
    assert not ca.confirm_notification(one)
    assert path.read_bytes() == protected
    assert ca.plan_notifications(filename, {"SOURCE": notification_decision()})["sent"]


@pytest.mark.parametrize("status", ["sent", "timeout", "failed"])
def test_notifications_finalize_single_redacted_dispatch_in_simulation(
    monkeypatch, tmp_path, status
):
    import json
    from ghostfolio_ibkr_sync import app, corporate_actions as ca
    from ghostfolio_ibkr_sync.outcome import new_run_outcome, record_failure

    tmp_path.chmod(0o700)
    filename = str(tmp_path / "state.yaml")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv(
        "APPRISE_URLS", json.dumps(["json://canary:secret@notify.invalid/hook"])
    )
    result = new_run_outcome()
    ca.prepare_notifications(
        result, filename, {"PRIVATE-SOURCE": notification_decision(True)}
    )
    record_failure(result, "corporate_actions", "trade_hold")
    calls = []
    monkeypatch.setattr(
        app,
        "send_notification",
        lambda settings, title, body: calls.append((title, body)) or status,
    )
    app.finalize_run(result, 1)
    assert len(calls) == 1
    assert "active_holds (1)" in calls[0][1]
    for private in (
        "PRIVATE-SOURCE",
        "SAMPLE.T",
        "JP0000000001",
        "EVENT1",
        "secret",
        str(tmp_path),
    ):
        assert private not in calls[0][1]
    assert (tmp_path / "state.yaml.notifications.yaml").exists() is (status == "sent")


def test_notification_persistence_loss_does_not_change_financial_decision(tmp_path):
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    filename = str(tmp_path / "state.yaml")
    decision = notification_decision()
    plan = ca.plan_notifications(filename, {"SOURCE": decision})
    assert ca.confirm_notification(plan)
    (tmp_path / "state.yaml.notifications.yaml").write_text("broken: [")
    repeated = ca.plan_notifications(filename, {"SOURCE": decision})
    assert repeated["sent"]
    assert not decision["account_held"] and not decision["symbols"]


def offline_runtime(monkeypatch, tmp_path, xml, *, mode="true", state=True, rows=()):
    import json
    import requests
    from ghostfolio_ibkr_sync import app
    from ghostfolio_ibkr_sync.outcome import new_run_outcome

    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = directory / "state.yaml"
    if state:
        path.write_text("version: 1\nreports: {}\nfindings: {}\n")
        path.chmod(0o600)
    config = {
        "ibkr_token": "synthetic",
        "account_ids": ["SOURCE"],
        "query_ids": ["QUERY"],
        "account_names": ["TARGET"],
        "ghost_host": "http://ghost.invalid",
        "ghost_token": "synthetic",
        "ghost_access_token": None,
        "ghost_platform_id": "",
        "mapping_file": "",
        "dry_run": mode == "true",
        "corporate_action_state_file": str(path),
        "corporate_action_evidence_file": None,
    }
    monkeypatch.setenv("DRY_RUN", mode)
    fetched = []
    monkeypatch.setattr(
        app, "fetch_flex_report", lambda token, query: fetched.append(query) or xml
    )
    reads = []
    writes = []

    def response(value, status=200):
        result = requests.Response()
        result.status_code = status
        result._content = json.dumps(value).encode()
        return result

    def get(url, **kwargs):
        reads.append(url)
        assert kwargs["allow_redirects"] is False
        if url.endswith("/api/v1/account"):
            return response({"accounts": [{"name": "TARGET", "id": "TARGET"}]})
        if url.endswith("/api/v1/account/TARGET"):
            return response(
                {"id": "TARGET", "name": "TARGET", "currency": "JPY", "balance": 1}
            )
        if url.endswith("/api/v1/activities"):
            return response({"count": len(rows), "activities": list(rows)})
        raise AssertionError("Unexpected read " + url)

    def post(url, **kwargs):
        writes.append(("POST", url, kwargs["json"]))
        accepted = [
            {
                **row,
                "id": "NEW" + str(i),
                "assetProfile": {"symbol": row["symbol"], "dataSource": "YAHOO"},
            }
            for i, row in enumerate(kwargs["json"]["activities"])
        ]
        return response({"activities": accepted}, 201)

    def put(url, **kwargs):
        writes.append(("PUT", url, kwargs["json"]))
        return response({})

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "put", put)
    result = new_run_outcome()
    code = app.run_configured_sync(config, result)
    return code, result, fetched, reads, writes, path


def trade_report(*, section=True, action_rows=(), cash=False):
    root = ET.fromstring(report(action_rows, section=section))
    trades = root.find(".//Trades")
    ET.SubElement(
        trades,
        "Trade",
        accountId="SOURCE",
        tradeID="NEWTRADE",
        symbol="UNRELATED",
        isin="US0000000001",
        assetCategory="STK",
        buySell="BUY",
        quantity="5",
        tradePrice="10",
        ibCommission="-1",
        currency="JPY",
        dateTime="20250402;120000 EDT",
    )
    if cash:
        section = ET.SubElement(root.find("FlexStatement"), "CashReport")
        ET.SubElement(
            section, "CashReportCurrency", currency="BASE_SUMMARY", endingCash="20"
        )
    return ET.tostring(root, encoding="unicode")


def test_runtime_contract_clean_simulation_bootstraps_after_one_acquisition(
    monkeypatch, tmp_path
):
    code, result, fetched, reads, writes, path = offline_runtime(
        monkeypatch, tmp_path, trade_report(), state=False
    )
    assert code == 0 and path.exists()
    assert fetched == ["QUERY"] and writes == []
    assert reads.index("http://ghost.invalid/api/v1/account") < reads.index(
        "http://ghost.invalid/api/v1/activities"
    )


@pytest.mark.parametrize(
    "variant", ["missing_section", "missing_state", "unsupported_event"]
)
def test_holds_runtime_contract_live_keeps_independent_cash(
    monkeypatch, tmp_path, variant
):
    xml = trade_report(
        section=variant != "missing_section",
        cash=True,
        action_rows=[action(type="MERGER", isin="US0000000001", symbol="UNRELATED")]
        if variant == "unsupported_event"
        else [],
    )
    code, result, fetched, reads, writes, path = offline_runtime(
        monkeypatch, tmp_path, xml, mode="false", state=variant != "missing_state"
    )
    assert code == 1 and fetched == ["QUERY"]
    assert [verb for verb, _, _ in writes] == ["PUT"]
    assert writes[0][1].endswith("/api/v1/account/TARGET")
    if variant == "missing_state":
        assert not path.exists()


def test_holds_review_yes_is_visible_but_non_actionable():
    from ghostfolio_ibkr_sync.activity_review import apply_corporate_review_holds

    proposals = {
        "P": {
            "source account": "SOURCE",
            "approve": "yes",
            "actionable": True,
            "proposed values": {
                "type": "BUY",
                "symbol": "SAMPLE.T",
                "date": "2025-04-01",
            },
        }
    }
    config = {
        "_corporate_decisions": {"SOURCE": notification_decision(True)},
        "_corporate_reconcile": lambda rows: None,
    }
    apply_corporate_review_holds(config, proposals, [])
    assert proposals["P"]["approve"] == "yes" and not proposals["P"]["actionable"]


def test_effective_holdings_post_event_candidate_can_explain_destination_lag():
    from ghostfolio_ibkr_sync.corporate_actions import decide

    reports, mapping, snapshot, evidence, proofs = reverse_case()
    reports[0]["trades"].append(
        {
            "accountId": "SOURCE",
            "tradeID": "LATER",
            "conid": "NEW",
            "isin": "CA0000000002",
            "symbol": "SAMPLE.T",
            "assetCategory": "STK",
            "buySell": "BUY",
            "quantity": "5",
            "tradePrice": "10",
            "ibCommission": "-1",
            "currency": "JPY",
            "dateTime": "20250402;120000 EDT",
        }
    )
    result = decide(reports, "SOURCE", "TARGET", mapping, snapshot, evidence, proofs)
    assert not result["symbols"] and result["effective"]["SAMPLE.T"] == 100


def test_effective_holdings_shared_profile_composition_does_not_require_other_broker():
    from ghostfolio_ibkr_sync.corporate_actions import decide

    reports, mapping, snapshot, evidence, proofs = reverse_case()
    other = {
        **snapshot["activities"][0],
        "id": "OTHER-ROW",
        "accountId": "OTHER-BROKER",
        "quantity": 7,
    }
    snapshot["activities"].append(other)
    snapshot["count"] = 2
    evidence["SAMPLE.T"]["holding"]["quantity"] = 107
    decision = decide(reports, "SOURCE", "TARGET", mapping, snapshot, evidence, proofs)
    assert not decision["symbols"] and decision["effective"]["SAMPLE.T"] == 100
    other["isExcluded"] = True
    assert decide(reports, "SOURCE", "TARGET", mapping, snapshot, evidence, proofs)[
        "symbols"
    ]


def test_persistence_exclusive_lock_and_failed_replace_preserve_state(
    tmp_path, monkeypatch
):
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    path = tmp_path / "state.yaml"
    store = ca.open_store(str(path), [], simulation=True)
    try:
        ca.retain_report(store, report(), "SOURCE", "QUERY", {})
        original = path.read_bytes()
        with pytest.raises(OSError):
            ca.open_store(str(path), [], simulation=True)

        def fail(*args):
            raise OSError("injected disk failure")

        monkeypatch.setattr(ca, "atomic_yaml", fail)
        with pytest.raises(OSError):
            ca.retain_report(store, report([action()]), "SOURCE", "QUERY", {})
        assert path.read_bytes() == original
    finally:
        ca.close_store(store)


def test_conclusions_cost_disagreement_does_not_hold_proven_units():
    from ghostfolio_ibkr_sync.corporate_actions import decide

    reports, mapping, snapshot, evidence, proofs = reverse_case()
    reports[0]["trades"].append(
        {
            "accountId": "SOURCE",
            "tradeID": "ORIGINAL",
            "conid": "OLD",
            "isin": "CA0000000001",
            "symbol": "SAMPLE.T",
            "assetCategory": "STK",
            "buySell": "BUY",
            "quantity": "3000",
            "tradePrice": "1",
            "ibCommission": "-1",
            "currency": "JPY",
            "dateTime": "20250320;120000 EDT",
        }
    )
    result = decide(reports, "SOURCE", "TARGET", mapping, snapshot, evidence, proofs)
    assert not result["symbols"]
    assert (
        result["findings"]["EVENT1"]["conclusions"]["history"]
        == "bounded_cost_dates_differ"
    )


def test_native_evidence_profile_reads_use_filtered_version_and_no_financial_calls(
    monkeypatch,
):
    import json
    import requests
    from ghostfolio_ibkr_sync.ghostfolio import ghost_corporate_evidence

    seen = []

    def get(url, **kwargs):
        seen.append((url, kwargs))
        response = requests.Response()
        response.status_code = 200
        if "/asset-profiles/" in url:
            data = {
                "assetProfile": {"symbol": "A/B", "dataSource": "YAHOO"},
                "splits": [{"date": "2025-03-27", "numerator": 1, "denominator": 30}],
            }
        elif "/portfolio/holding/" in url:
            data = {"quantity": 100}
        else:
            assert kwargs["params"] == {
                "activityIds": "00000000-0000-0000-0000-000000000000"
            }
            data = {"meta": {"version": "3.92.0"}, "activities": []}
        response._content = json.dumps(data).encode()
        return response

    monkeypatch.setattr(requests, "get", get)
    result = ghost_corporate_evidence(
        {"ghost_host": "https://ghost.example", "ghost_token": "canary"}, "A/B"
    )
    assert result["version"] == "3.92.0"
    assert "/YAHOO/A%2FB" in seen[0][0]
    assert all(
        kwargs["allow_redirects"] is False
        and kwargs["headers"]["Authorization"] == "Bearer canary"
        for _, kwargs in seen
    )


@pytest.mark.parametrize("variant", ["future", "excluded_account", "duplicate_id"])
def test_effective_holdings_unusable_shared_profile_records_keep_hold(variant):
    from ghostfolio_ibkr_sync.corporate_actions import decide

    reports, mapping, snapshot, evidence, proofs = reverse_case()
    if variant == "future":
        snapshot["activities"][0]["date"] = "2099-01-01T00:00:00Z"
    if variant == "excluded_account":
        snapshot["activities"][0]["account"] = {"isExcluded": True}
    if variant == "duplicate_id":
        snapshot["activities"].append({**snapshot["activities"][0], "quantity": 0})
        snapshot["count"] = 2
    assert decide(reports, "SOURCE", "TARGET", mapping, snapshot, evidence, proofs)[
        "symbols"
    ]


def test_inventory_conflicting_description_ratios_and_security_identifiers_stay_unresolved():
    result = inventory(
        report([action(actionDescription="SAMPLE SPLIT 1 FOR 30")]), "SOURCE"
    )
    assert "conflicting_ratio" in result["events"]["EVENT1"]["reasons"]
    result = inventory(
        report([action(securityIDType="ISIN", securityID="OTHER-IDENTITY")]), "SOURCE"
    )
    assert "conflicting_security_identity" in result["events"]["EVENT1"]["reasons"]


def test_retained_evidence_conflicting_revision_survives_later_exact_repeat():
    from copy import deepcopy
    from ghostfolio_ibkr_sync.corporate_actions import decide

    reports, mapping, snapshot, evidence, proofs = reverse_case()
    original = reports[0]
    revision = deepcopy(original)
    revision["events"]["EVENT1"]["rows"][0]["proceeds"] = "1"
    for order in permutations([original, revision, original]):
        decision = decide(list(order), "SOURCE", "TARGET", mapping, snapshot, evidence, proofs)
        event = decision["findings"]["EVENT1"]
        assert event["held"]
        assert "conflicting_event_revision" in event["reasons"]
        assert decision["account_held"]
        assert "SAMPLE.T" in decision["symbols"]
