"""Corporate-action behavior at the approved source/decision/runtime seams."""

from itertools import permutations
from xml.etree import ElementTree as ET

import pytest

from ghostfolio_ibkr_sync.corporate_actions import inventory


def test_retention_age_exact_boundary_repeat_restart_and_file_times(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta
    import os
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(ca, "utc_now", lambda: now)
    path = tmp_path / "state.yaml"
    original = report()
    store = ca.open_store(str(path), [], simulation=True)
    ca.retain_report(store, original, "SOURCE", "Q", {})
    obj = store["evidence"] / (inventory(original, "SOURCE")["sha256"] + ".xml")
    ca.close_store(store)
    for hours in (719, 720):
        now = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=hours)
        os.utime(obj, None)
        store = ca.open_store(str(path), [], simulation=True)
        ca.retain_report(store, original, "SOURCE", "Q", {})
        ca.close_store(store)
        assert obj.exists() is (hours == 719)


@pytest.mark.parametrize("timestamp", [None, "missing", "bad", "2099-01-01T00:00:00+00:00"])
def test_retention_age_untrusted_timestamp_receives_one_durable_grace(tmp_path, monkeypatch, timestamp):
    from datetime import UTC, datetime, timedelta
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(ca, "utc_now", lambda: now)
    path = tmp_path / "state.yaml"
    store = ca.open_store(str(path), [], simulation=True)
    ca.retain_report(store, report(), "SOURCE", "Q", {})
    refs = store["references"]
    key = next(iter(refs["records"]))
    if timestamp == "missing":
        del refs["records"][key]["acquired"]
    else:
        refs["records"][key]["acquired"] = timestamp
    ca.atomic_yaml(ca.reference_path(store), refs)
    ca.close_store(store)
    now += timedelta(days=100)
    store = ca.open_store(str(path), [], simulation=True)
    ca.retain_report(store, report(), "SOURCE", "Q", {})
    assert store["references"]["records"][key]["acquired"] == now.isoformat()
    ca.close_store(store)
    now += timedelta(hours=720)
    store = ca.open_store(str(path), [], simulation=True)
    ca.retain_report(store, report(end="20260101"), "SOURCE", "Q", {})
    assert key not in store["references"]["records"]
    ca.close_store(store)


def test_retention_age_legacy_adoption_preserves_bytes_and_grace(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta
    import hashlib
    import yaml
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    path = tmp_path / "state.yaml"
    evidence = tmp_path / "state.yaml.evidence"
    evidence.mkdir(mode=0o700)
    xml = report().encode()
    digest = hashlib.sha256(xml).hexdigest()
    binding = {"schema": 1, "source": "SOURCE", "query": "Q", "sha256": digest,
               "period": ["20250101", "20251231"], "mapping": ca.fingerprint({})}
    key = ca.fingerprint(binding)
    for name, data in ((digest + ".xml", xml), (key + ".yaml", yaml.safe_dump(binding).encode())):
        (evidence / name).write_bytes(data)
        (evidence / name).chmod(0o600)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(ca, "utc_now", lambda: now)
    for days in (0, 29, 30):
        now = datetime(2030, 1, 1, tzinfo=UTC) + timedelta(days=days)
        store = ca.open_store(str(path), [], simulation=True)
        ca.retain_report(store, report(end="20260101"), "SOURCE", "Q", {})
        ca.close_store(store)
        assert (evidence / (digest + ".xml")).exists() is (days < 30)


def test_retention_safety_anchor_trades_conflicts_coverage_and_decisions(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(ca, "utc_now", lambda: now)
    path = tmp_path / "state.yaml"
    baseline = ET.fromstring(report(end="20250326"))
    section = ET.SubElement(baseline.find("FlexStatement"), "OpenPositions")
    ET.SubElement(section, "OpenPosition", accountId="SOURCE", conid="CONTRACT1",
                  isin="JP0000000001", levelOfDetail="SUMMARY", position="100")
    originals = [ET.tostring(baseline, encoding="unicode"), report([action()], start="20250327")]
    store = ca.open_store(str(path), [], simulation=True)
    for xml in originals:
        ca.retain_report(store, xml, "SOURCE", "Q", {})
    _, _, snapshot, evidence, proofs = reverse_case()
    mapping = {"JP0000000001": "SAMPLE.T"}
    snapshot["activities"][0]["quantity"] = 500
    snapshot["activities"][0]["assetProfile"]["isin"] = "JP0000000001"
    evidence["SAMPLE.T"]["holding"]["quantity"] = 500
    before = ca.decide([inventory(x, "SOURCE") for x in originals], "SOURCE", "TARGET",
                       mapping, snapshot, evidence, proofs)
    assert not before["findings"]["EVENT1"]["held"]
    now += timedelta(days=40)
    duplicate = originals[1].replace("<FlexQueryResponse>", '<FlexQueryResponse generated="new">')
    retained = ca.retain_report(store, duplicate, "SOURCE", "Q", {})
    after = ca.decide(retained, "SOURCE", "TARGET", mapping, snapshot, evidence, proofs)
    assert after == before
    assert len(store["references"]["safety"]) == 2
    # A later conflicting revision survives an exact repeat and a closed position.
    revised = report([action(quantity="401")], start="20250327")
    ca.retain_report(store, revised, "SOURCE", "Q", {})
    now += timedelta(days=40)
    retained = ca.retain_report(store, report(start="20260101", end="20260131"), "SOURCE", "Q", mapping)
    conflict = ca.decide(retained, "SOURCE", "TARGET", mapping, snapshot, evidence, proofs)
    assert conflict["symbols"]
    assert len(store["references"]["safety"]) == 4
    assert all((store["evidence"] / (inventory(x, "SOURCE")["sha256"] + ".xml")).exists()
               for x in [*originals, revised])
    ca.close_store(store)


def test_retention_safety_closed_trade_chain_cash_unknown_actions_and_unrelated_rows(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from fractions import Fraction
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(ca, "utc_now", lambda: now)
    reports, mapping, _, _, _ = reverse_case()
    event = report(reports[0]["events"]["EVENT1"]["rows"])
    closing = ET.fromstring(report())
    ET.SubElement(closing.find(".//Trades"), "Trade", accountId="SOURCE", conid="NEW",
                  isin="CA0000000002", symbol="SAMPLE.T", tradeID="CLOSE", buySell="SELL",
                  quantity="100", dateTime="20250401;120000 EDT")
    ET.SubElement(closing.find(".//CashTransactions"), "CashTransaction", accountId="SOURCE",
                  actionID="EVENT1", type="Corporate Action", amount="1", currency="JPY")
    closing_xml = ET.tostring(closing, encoding="unicode")
    unrelated = ET.fromstring(event)
    ET.SubElement(unrelated.find(".//Trades"), "Trade", accountId="SOURCE", conid="UNRELATED",
                  isin="XX0000000000", symbol="OTHER", tradeID="IGNORED", buySell="BUY",
                  quantity="10", dateTime="20250401;120000 EDT")
    unrelated_xml = ET.tostring(unrelated, encoding="unicode")
    unknown = report([action(actionID="UNKNOWN", type="MERGER")])
    store = ca.open_store(str(tmp_path / "state.yaml"), [], simulation=True)
    for xml in (event, closing_xml, unrelated_xml, unknown):
        ca.retain_report(store, xml, "SOURCE", "Q", mapping)
    now += timedelta(days=31)
    maintained = ca.retain_report(store, report(start="20260101", end="20260131"), "SOURCE", "Q", mapping)
    originals = [inventory(x, "SOURCE") for x in (event, closing_xml, unrelated_xml, unknown)]
    events = {**reports[0]["events"]}
    assert ca.source_chain(originals, events, "SAMPLE.T", mapping, {"EVENT1": "2025-03-27"})[0] == Fraction(0)
    assert ca.source_chain(maintained, events, "SAMPLE.T", mapping, {"EVENT1": "2025-03-27"})[0] == Fraction(0)
    decision = ca.decide(maintained, "SOURCE", "TARGET", mapping, None, {}, {})
    assert decision["findings"]["EVENT1"]["conclusions"]["cash"] == "explicit_linked_cash_observed_no_treatment"
    assert decision["findings"]["UNKNOWN"]["held"]
    assert not (store["evidence"] / (inventory(unrelated_xml, "SOURCE")["sha256"] + ".xml")).exists()
    ca.close_store(store)


def test_retention_safety_post_event_positions_do_not_create_per_acquisition_history(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(ca, "utc_now", lambda: now)
    store = ca.open_store(str(tmp_path / "state.yaml"), [], simulation=True)
    baseline = ET.fromstring(report(end="20250326"))
    ET.SubElement(ET.SubElement(baseline.find("FlexStatement"), "OpenPositions"), "OpenPosition",
                  accountId="SOURCE", conid="CONTRACT1", isin="JP0000000001",
                  levelOfDetail="SUMMARY", position="100")
    dates = {("SOURCE", "EVENT1"): "2025-03-27"}
    mapping = {"JP0000000001": "SAMPLE.T"}
    ca.retain_report(store, ET.tostring(baseline, encoding="unicode"), "SOURCE", "Q", mapping, dates=dates)
    ca.retain_report(store, report([action()], start="20250327"), "SOURCE", "Q", mapping, dates=dates)
    for day in range(40):
        now += timedelta(days=1)
        end = (datetime(2025, 4, 1) + timedelta(days=day)).strftime("%Y%m%d")
        root = ET.fromstring(report(start="20250327", end=end))
        ET.SubElement(ET.SubElement(root.find("FlexStatement"), "OpenPositions"), "OpenPosition",
                      accountId="SOURCE", conid="CONTRACT1", isin="JP0000000001",
                      levelOfDetail="SUMMARY", position="500")
        ca.retain_report(store, ET.tostring(root, encoding="unicode"), "SOURCE", "Q", mapping, dates=dates)
        assert len(store["references"]["safety"]) == 2
    reports = ca.retained_inventories(store, "SOURCE", "Q", mapping)
    events = next(r["events"] for r in reports if r["events"])
    assert ca.source_chain(reports, events, "SAMPLE.T", mapping, {"EVENT1": "2025-03-27"})[0] == 500
    ca.close_store(store)


def test_retention_reporting_missing_required_proof_remains_a_hold(tmp_path):
    from collections import defaultdict
    from ghostfolio_ibkr_sync import app, corporate_actions as ca
    from ghostfolio_ibkr_sync.outcome import new_run_outcome

    tmp_path.chmod(0o700)
    store = ca.open_store(str(tmp_path / "state.yaml"), [], simulation=True)
    ca.retain_report(store, report([action()]), "SOURCE", "Q", {})
    (store["evidence"] / (inventory(report([action()]), "SOURCE")["sha256"] + ".xml")).unlink()
    outcome = new_run_outcome()
    config = {"account_ids": ["SOURCE"], "query_ids": ["Q"],
              "_source_reports": {("SOURCE", "Q"): report()},
              "_source_accounts": {("SOURCE", "Q"): "TARGET"},
              "_corporate_store": store, "_corporate_outcome": outcome}
    app.refresh_corporate_decisions(config, {}, {"activities": [], "count": 0}, {"qty": defaultdict(float)})
    assert config["_corporate_decisions"]["SOURCE"]["account_held"]
    assert not store["maintenance_warning"]
    ca.close_store(store)


@pytest.mark.parametrize("failure", ["unlink", "publication", "missing_index"])
def test_retention_recovery_committed_references_never_resurrect_retired_bindings(tmp_path, monkeypatch, failure):
    from datetime import UTC, datetime, timedelta
    from pathlib import Path
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(ca, "utc_now", lambda: now)
    path = tmp_path / "state.yaml"
    store = ca.open_store(str(path), [], simulation=True)
    ca.retain_report(store, report(), "SOURCE", "Q", {})
    old_digest = inventory(report(), "SOURCE")["sha256"]
    old_file = store["evidence"] / (old_digest + ".xml")
    now += timedelta(days=31)
    unlink = Path.unlink
    atomic = ca.atomic_yaml

    def denied(file, *args, **kwargs):
        if file.parent == store["evidence"]:
            raise PermissionError("synthetic")
        return unlink(file, *args, **kwargs)

    def fail_publication(file, data):
        if file == ca.reference_path(store):
            # Cut after atomic publication: callers cannot assume it failed before commit.
            atomic(file, data)
            raise OSError("synthetic post-publication interruption")
        return atomic(file, data)

    if failure == "publication":
        monkeypatch.setattr(ca, "atomic_yaml", fail_publication)
        with pytest.raises(OSError):
            ca.retain_report(store, report(end="20260101"), "SOURCE", "Q", {})
    else:
        monkeypatch.setattr(Path, "unlink", denied)
        ca.retain_report(store, report(end="20260101"), "SOURCE", "Q", {})
        assert store["maintenance_warning"]
    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(ca, "atomic_yaml", atomic)
    ca.close_store(store)
    path.unlink()  # Findings loss must not turn stale bindings into active proof.
    if failure == "missing_index":
        ca.reference_path(store).unlink()
    store = ca.open_store(str(path), [], simulation=True)
    try:
        if failure == "missing_index":
            with pytest.raises(RuntimeError, match="Missing committed"):
                ca.retain_report(store, report(), "SOURCE", "Q", {})
            assert old_file.exists()
        else:
            ca.retain_report(store, report(end="20260101"), "SOURCE", "Q", {})
            assert not old_file.exists()
            assert not store["document"]["reports"]
    finally:
        ca.close_store(store)


@pytest.mark.parametrize("damage", ["symlink", "hardlink", "input", "changed"])
def test_retention_recovery_cleanup_protects_inputs_aliases_and_changed_objects(tmp_path, monkeypatch, damage):
    from datetime import UTC, datetime, timedelta
    import os
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(ca, "utc_now", lambda: now)
    store = ca.open_store(str(tmp_path / "state.yaml"), [], simulation=True)
    ca.retain_report(store, report(), "SOURCE", "Q", {})
    obj = store["evidence"] / (inventory(report(), "SOURCE")["sha256"] + ".xml")
    journal = tmp_path / "review.journal.yaml"
    journal.write_bytes(obj.read_bytes())
    journal.chmod(0o600)
    if damage == "symlink":
        obj.unlink()
        obj.symlink_to(journal)
    elif damage == "hardlink":
        obj.unlink()
        os.link(journal, obj)
    elif damage == "input":
        store["inputs"].append(obj)
    else:
        obj.write_bytes(b"changed")
    before = obj.read_bytes()
    now += timedelta(days=31)
    ca.retain_report(store, report(end="20260101"), "SOURCE", "Q", {})
    assert store["maintenance_warning"]
    assert obj.read_bytes() == before
    assert journal.read_bytes() == report().encode()
    ca.close_store(store)


@pytest.mark.parametrize("stage", ["xml", "binding", "active", "cleanup_binding", "cleanup_xml", "cleanup_sync"])
def test_retention_recovery_interruptions_retain_complete_committed_generation(tmp_path, monkeypatch, stage):
    from datetime import UTC, datetime, timedelta
    from pathlib import Path
    import os
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(ca, "utc_now", lambda: now)
    path = tmp_path / "state.yaml"
    store = ca.open_store(str(path), [], simulation=True)
    original = report([action()])
    ca.retain_report(store, original, "SOURCE", "Q", {})
    ordinary = report()
    ca.retain_report(store, ordinary, "SOURCE", "Q", {})
    now += timedelta(days=31)
    new = report(start="20260101", end="20260131")
    immutable, atomic, unlink, fsync = ca.immutable_object, ca.atomic_yaml, Path.unlink, os.fsync
    fired = False

    def interrupt_object(file, data, inputs):
        nonlocal fired
        immutable(file, data, inputs)
        if not fired and ((stage == "xml" and file.suffix == ".xml")
                          or (stage == "binding" and file.suffix == ".yaml")):
            fired = True
            raise KeyboardInterrupt("synthetic acquisition crash")

    def interrupt_active(file, data):
        nonlocal fired
        result = atomic(file, data)
        if stage == "active" and file == ca.reference_path(store) and any(
                r["binding"]["sha256"] == inventory(new, "SOURCE")["sha256"] for r in data["records"].values()):
            fired = True
            raise KeyboardInterrupt("synthetic committed publication crash")
        return result

    def interrupt_unlink(file, *args, **kwargs):
        nonlocal fired
        result = unlink(file, *args, **kwargs)
        if (not fired and file.parent == store["evidence"]
                and stage == "cleanup_" + ("xml" if file.suffix == ".xml" else "binding")):
            fired = True
            raise KeyboardInterrupt("synthetic cleanup crash")
        return result

    def interrupt_sync(fd):
        nonlocal fired
        fsync(fd)
        if stage == "cleanup_sync" and not fired and store["references"]["pending"]:
            # Only interrupt the evidence directory sync after the retired ordinary object vanished.
            old = store["evidence"] / (inventory(ordinary, "SOURCE")["sha256"] + ".xml")
            if not old.exists():
                fired = True
                raise KeyboardInterrupt("synthetic directory-sync crash")

    with monkeypatch.context() as patch:
        patch.setattr(ca, "immutable_object", interrupt_object)
        patch.setattr(ca, "atomic_yaml", interrupt_active)
        patch.setattr(Path, "unlink", interrupt_unlink)
        patch.setattr(os, "fsync", interrupt_sync)
        with pytest.raises(KeyboardInterrupt):
            ca.retain_report(store, new, "SOURCE", "Q", {})
    ca.close_store(store)
    assert fired
    store = ca.open_store(str(path), [], simulation=True)
    recovered = ca.retain_report(store, new, "SOURCE", "Q", {})
    assert any("EVENT1" in r["events"] for r in recovered)
    assert not store["references"]["pending"]
    assert len(list(store["evidence"].glob("*.xml"))) == len(store["references"]["records"])
    ca.close_store(store)


@pytest.mark.parametrize("after_replace", [False, True])
def test_retention_recovery_storage_failure_during_maintenance_is_warning_only(tmp_path, monkeypatch, after_replace):
    from datetime import UTC, datetime, timedelta
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(ca, "utc_now", lambda: now)
    store = ca.open_store(str(tmp_path / "state.yaml"), [], simulation=True)
    ca.retain_report(store, report(), "SOURCE", "Q", {})
    now += timedelta(days=30)
    atomic = ca.atomic_yaml

    def unavailable(file, data):
        if file == ca.reference_path(store):
            if after_replace:
                atomic(file, data)
            raise OSError(28, "synthetic storage failure")
        return atomic(file, data)

    monkeypatch.setattr(ca, "atomic_yaml", unavailable)
    current = ca.retain_report(store, report(), "SOURCE", "Q", {})
    assert store["maintenance_warning"]
    assert not ca.decide(current, "SOURCE", "TARGET", {}, None, {}, {})["account_held"]
    ca.close_store(store)


def test_retention_recovery_concurrent_reference_change_fences_evidence(tmp_path):
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    store = ca.open_store(str(tmp_path / "state.yaml"), [], simulation=True)
    ca.retain_report(store, report([action()]), "SOURCE", "Q", {})
    ca.reference_path(store).write_bytes(store["reference_original"] + b"\n")
    with pytest.raises(RuntimeError, match="references changed"):
        ca.retain_report(store, report(), "SOURCE", "Q", {})
    ca.close_store(store)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("unavailable", ["missing", "malformed", "wrong_account", "target", "section"])
@pytest.mark.parametrize("shared", [False, True])
def test_shared_owner_unavailable_holds_before_dispatch(tmp_path, monkeypatch, reverse, unavailable, shared):
    from collections import defaultdict
    from ghostfolio_ibkr_sync import app, corporate_actions as ca

    tmp_path.chmod(0o700)
    store = ca.open_store(str(tmp_path / "state.yaml"), [], simulation=True)
    pairs = [("SOURCE", "Q"), ("OTHER", "Q2")]
    if reverse:
        pairs.reverse()
    reports = {("SOURCE", "Q"): report(), ("OTHER", "Q2"): report(account="OTHER")}
    targets = {("SOURCE", "Q"): "TARGET", ("OTHER", "Q2"): "TARGET" if shared else "DISTINCT"}
    if unavailable == "missing":
        reports[("OTHER", "Q2")] = None
    elif unavailable == "malformed":
        reports[("OTHER", "Q2")] = "<broken"
    elif unavailable == "wrong_account":
        reports[("OTHER", "Q2")] = report()
    elif unavailable == "section":
        reports[("OTHER", "Q2")] = report(account="OTHER", section=False)
    else:
        targets.pop(("OTHER", "Q2"))
    config = {"account_ids": [p[0] for p in pairs], "query_ids": [p[1] for p in pairs],
              "account_names": ["Shared" if shared else p[0] for p in pairs],
              "_source_reports": reports, "_source_accounts": targets, "_corporate_store": store}
    try:
        app.refresh_corporate_decisions(config, {}, {"activities": [], "count": 0}, {"qty": defaultdict(float)})
        decisions = config["_corporate_decisions"]
        assert decisions["OTHER"]["account_held"]
        assert decisions["SOURCE"]["account_held"] is shared
    finally:
        ca.close_store(store)


def test_shared_owner_unavailable_named_group_keeps_proven_distinct_target_independent(tmp_path):
    from collections import defaultdict
    from ghostfolio_ibkr_sync import app, corporate_actions as ca

    tmp_path.chmod(0o700)
    store = ca.open_store(str(tmp_path / "state.yaml"), [], simulation=True)
    config = {"account_ids": ["SOURCE", "OTHER", "THIRD"], "query_ids": ["Q", "Q2", "Q3"],
              "account_names": ["One", "One", "Two"], "_corporate_store": store,
              "_source_reports": {("SOURCE", "Q"): report(),
                                  ("OTHER", "Q2"): None,
                                  ("THIRD", "Q3"): report(account="THIRD")},
              "_source_accounts": {("SOURCE", "Q"): "TARGET", ("THIRD", "Q3"): "DISTINCT"}}
    app.refresh_corporate_decisions(config, {}, {"activities": [], "count": 0}, {"qty": defaultdict(float)})
    assert config["_corporate_decisions"]["SOURCE"]["account_held"]
    assert config["_corporate_decisions"]["OTHER"]["account_held"]
    assert not config["_corporate_decisions"]["THIRD"]["account_held"]
    ca.close_store(store)


@pytest.mark.parametrize("configured", [False, True])
@pytest.mark.parametrize("simulation", [False, True])
def test_retention_reporting_cleanup_warning_is_not_a_financial_failure(tmp_path, monkeypatch, configured, simulation):
    from datetime import UTC, datetime, timedelta
    from pathlib import Path
    from collections import defaultdict
    from ghostfolio_ibkr_sync import app, corporate_actions as ca
    from ghostfolio_ibkr_sync.outcome import new_run_outcome

    tmp_path.chmod(0o700)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(ca, "utc_now", lambda: now)
    store = ca.open_store(str(tmp_path / "state.yaml"), [], simulation=True)
    ca.retain_report(store, report(), "SOURCE", "Q", {})
    now += timedelta(days=31)
    unlink = Path.unlink

    def denied(file, *args, **kwargs):
        if file.parent == store["evidence"]:
            raise PermissionError("private path must not enter notification")
        return unlink(file, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", denied)
    outcome = new_run_outcome()
    config = {"account_ids": ["SOURCE"], "query_ids": ["Q"],
              "_source_reports": {("SOURCE", "Q"): report(end="20260101")},
              "_source_accounts": {("SOURCE", "Q"): "TARGET"},
              "_corporate_store": store, "_corporate_outcome": outcome}
    sent = []
    monkeypatch.setenv("DRY_RUN", "true" if simulation else "false")
    monkeypatch.setattr(app, "load_notification_delivery", lambda: ({}, "configured") if configured else (None, "disabled"))
    monkeypatch.setattr(app, "send_notification", lambda *args: sent.append(args) or "sent")
    app.refresh_corporate_decisions(config, {}, {"activities": [], "count": 0}, {"qty": defaultdict(float)})
    assert not config["_corporate_decisions"]["SOURCE"]["account_held"]
    assert outcome["failures"] == []
    app.finalize_run(outcome, 0)
    assert len(sent) == int(configured)
    if configured:
        assert "maintenance_incomplete (1)" in sent[0][2]
        assert "SOURCE" not in sent[0][2] and str(tmp_path) not in sent[0][2]
    ca.close_store(store)


@pytest.mark.parametrize("daily", [True, False])
def test_retention_longevity_ten_year_daily_and_high_frequency(tmp_path, monkeypatch, daily):
    from datetime import UTC, datetime, timedelta
    from ghostfolio_ibkr_sync import corporate_actions as ca
    import yaml

    # Only accelerate YAML token parsing/emission in this endurance scenario.
    # Keep custom node validation, every iteration, real files and all fsyncs.
    # The other recovery/serialization tests use the production Python codec.
    monkeypatch.setattr(yaml, "SafeLoader", getattr(yaml, "CSafeLoader", yaml.SafeLoader))
    monkeypatch.setattr(yaml, "SafeDumper", getattr(yaml, "CSafeDumper", yaml.SafeDumper))

    tmp_path.chmod(0o700)
    origin = datetime(2026, 1, 1, tzinfo=UTC)
    now = origin
    monkeypatch.setattr(ca, "utc_now", lambda: now)
    path = tmp_path / "state.yaml"
    parse = ca.inventory
    parses = 0

    def observed(xml, source):
        nonlocal parses
        parses += 1
        return parse(xml, source)

    monkeypatch.setattr(ca, "inventory", observed)
    steps = range(3653) if daily else [*range(72), *range(816, 888)]
    for step in steps:
        now = origin + (timedelta(days=step) if daily else timedelta(hours=step))
        end = now.date()
        start = end - timedelta(days=364)
        rows = []
        # Sparse events and a revision must survive after leaving rolling windows.
        if step < 50 or (daily and 1500 <= step < 1550):
            rows = [action()] if step < 50 else [action(actionID="EVENT2", transactionID="LEG2",
                    dateTime="20300209;120000 EST", reportDate="20300209")]
        if daily and step == 1520:
            rows = [action(actionID="EVENT2", transactionID="LEG2", quantity="401",
                           dateTime="20300209;120000 EST", reportDate="20300301")]
        xml = report(rows, start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"))
        xml = xml.replace("<FlexQueryResponse>", f'<FlexQueryResponse generated="{step}">')
        store = ca.open_store(str(path), [], simulation=True)
        parses = 0
        try:
            reports = ca.retain_report(store, xml, "SOURCE", "Q", {})
            refs = store["references"]
            ordinary = set(refs["records"]) - set(refs["safety"])
            assert len(ordinary) <= (30 if daily else 72)
            # Continuous coverage needs at most one full-window original per year,
            # plus the two events/revision and the current boundary.
            assert len(refs["safety"]) <= (16 if daily else 4)
            assert parses <= 2 * len(refs["safety"]) + 2
            assert len(list(store["evidence"].glob("*.xml"))) == len(refs["records"])
            assert not refs["pending"] and not store["maintenance_warning"]
        finally:
            ca.close_store(store)
    events = ca.decide(reports, "SOURCE", "TARGET", {}, None, {}, {})["findings"]
    assert "EVENT1" in events
    if daily:
        assert "EVENT2" in events
        assert "conflicting_event_revision" in events["EVENT2"]["reasons"]


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
        decision = decide(
            list(order), "SOURCE", "TARGET", mapping, snapshot, evidence, proofs
        )
        event = decision["findings"]["EVENT1"]
        assert event["held"]
        assert "conflicting_event_revision" in event["reasons"]
        assert decision["account_held"]
        assert "SAMPLE.T" in decision["symbols"]


def test_conclusions_query_column_enrichment_is_not_a_revision():
    from copy import deepcopy
    from ghostfolio_ibkr_sync import corporate_actions as ca

    reports, mapping, snapshot, evidence, proofs = reverse_case()
    old = deepcopy(reports[0])
    new = deepcopy(reports[0])
    for row in old["events"]["EVENT1"]["rows"]:
        row.pop("amount")
    for row in new["events"]["EVENT1"]["rows"]:
        row["actionDescription"] = row["description"]
        row["newOptionalColumn"] = "extra source evidence"
    for order in permutations([old, new, old]):
        decision = ca.decide(
            list(order), "SOURCE", "TARGET", mapping, snapshot, evidence, proofs
        )
        event = decision["findings"]["EVENT1"]
        assert "conflicting_event_revision" not in event["reasons"]
        assert not decision["account_held"] and not event["held"]
        assert event["conclusions"]["cash"] == "no_action_cash_observed"


def test_retained_evidence_parsed_and_verified_once_per_object_per_run(
    tmp_path, monkeypatch
):
    from ghostfolio_ibkr_sync import corporate_actions as ca

    tmp_path.chmod(0o700)
    path = tmp_path / "state.yaml"
    store = ca.open_store(str(path), [], simulation=True)
    source = report([action()])
    other = report([action(accountId="OTHER")], account="OTHER")
    ca.retain_report(store, source, "SOURCE", "query1", {})
    ca.retain_report(store, other, "OTHER", "query2", {})
    ca.close_store(store)
    store = ca.open_store(str(path), [], simulation=False)
    parses, reads = [], []
    from pathlib import Path

    original_inventory, original_read = ca.inventory, Path.read_bytes

    def count_inventory(xml, account):
        parses.append(account)
        return original_inventory(xml, account)

    def count_read(file):
        if file.suffix == ".xml":
            reads.append(file.name)
        return original_read(file)

    monkeypatch.setattr(ca, "inventory", count_inventory)
    monkeypatch.setattr(Path, "read_bytes", count_read)
    try:
        for _ in range(4):
            ca.retain_report(store, source, "SOURCE", "query1", {})
            ca.retain_report(store, other, "OTHER", "query2", {})
        assert sorted(parses) == ["OTHER", "SOURCE"]
        assert len(reads) == len(set(reads)) == 2
        # A cache never hides a modified immutable object during this run.
        target = store["evidence"] / reads[0]
        target.write_bytes(original_read(target) + b" ")
        with pytest.raises(RuntimeError, match="changed during this run"):
            ca.retained_inventories(store, "SOURCE", "query1", {})
    finally:
        ca.close_store(store)


@pytest.mark.parametrize("shared_target", [False, True])
def test_holds_distinct_sources_cannot_certify_shared_destination_ownership(
    tmp_path, monkeypatch, shared_target
):
    from copy import deepcopy
    from collections import defaultdict
    import hashlib
    from ghostfolio_ibkr_sync import app, corporate_actions as ca

    tmp_path.chmod(0o700)
    store = ca.open_store(str(tmp_path / "state.yaml"), [], simulation=True)
    reports, mapping, snapshot, evidence, _ = reverse_case()
    original_rows = reports[0]["events"]["EVENT1"]["rows"]
    other_rows = [{**row, "accountId": "OTHER"} for row in original_rows]
    second_target = "TARGET" if shared_target else "OTHER_TARGET"
    if not shared_target:
        second = deepcopy(snapshot["activities"][0])
        second.update(id="ROW2", accountId=second_target)
        snapshot["activities"].append(second)
        snapshot["count"] = 2
        evidence["SAMPLE.T"]["holding"]["quantity"] = 200
    document = tmp_path / "official.txt"
    document.write_bytes(b"official date")
    document.chmod(0o600)
    proof = {
        "effective_date": "2025-03-27",
        "source_url": "https://issuer.example/split",
        "document": str(document),
        "bytes": document.read_bytes(),
        "sha256": hashlib.sha256(document.read_bytes()).hexdigest(),
    }
    monkeypatch.setattr(
        ca,
        "load_date_proofs",
        lambda _: {(source, "EVENT1"): proof for source in ("SOURCE", "OTHER")},
    )
    monkeypatch.setattr(
        app, "ghost_corporate_evidence", lambda *_: evidence["SAMPLE.T"]
    )
    config = {
        "account_ids": ["SOURCE", "OTHER"],
        "query_ids": ["Q1", "Q2"],
        "account_names": ["One", "Two"],
        "_corporate_store": store,
        "_source_reports": {
            ("SOURCE", "Q1"): report(original_rows),
            ("OTHER", "Q2"): report(other_rows, account="OTHER"),
        },
        "_source_accounts": {
            ("SOURCE", "Q1"): "TARGET",
            ("OTHER", "Q2"): second_target,
        },
    }
    positions = {"qty": defaultdict(float)}
    try:
        app.refresh_corporate_decisions(config, mapping, snapshot, positions)
        assert all(
            d["account_held"] is shared_target
            for d in config["_corporate_decisions"].values()
        )
        if shared_target:
            assert not positions["qty"]
        else:
            assert positions["qty"][("TARGET", "SAMPLE.T")] == 100
    finally:
        ca.close_store(store)


@pytest.mark.parametrize("status", ["sent", "failed", "timeout"])
def test_operator_action_corporate_repeats_with_review_and_fingerprint_loss(monkeypatch, tmp_path, status):
    from ghostfolio_ibkr_sync import app, corporate_actions as ca
    from ghostfolio_ibkr_sync.outcome import new_run_outcome, record_action
    tmp_path.chmod(0o700)
    monkeypatch.setenv("APPRISE_URLS", '["json://notify.invalid/hook"]')
    monkeypatch.setenv("DRY_RUN", "true")
    sent = []
    monkeypatch.setattr(app, "send_notification", lambda cfg, title, body: sent.append(body) or status)
    filename = str(tmp_path / "state.yaml")
    decision = notification_decision(False)
    decision["findings"]["EVENT1"]["conclusions"]["history"] = "bounded_cost_dates_differ"
    for _ in range(2):
        out = new_run_outcome()
        ca.prepare_notifications(out, filename, {"PRIVATE": decision})
        record_action(out, "review_approval", "PRIVATE-REVIEW")
        app.finalize_run(out, 0)
        assert len(out["actions"]["corporate_action"]) == 1
    assert len(sent) == 2
    assert all("corporate_action (1)" in body and "review_approval (1)" in body for body in sent)
    assert all("PRIVATE" not in body and "EVENT1" not in body and str(tmp_path) not in body for body in sent)
