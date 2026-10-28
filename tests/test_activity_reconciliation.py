"""Profile acceptance with synthetic source values and offline destinations."""
from decimal import Decimal as D

import pytest

from ghostfolio_ibkr_sync import config
from ghostfolio_ibkr_sync import activity_reconciliation as reconciliation


@pytest.fixture
def configured(monkeypatch):
    for name, value in {"IBKR_TOKEN": "synthetic", "IBKR_ACCOUNT_IDS": "U1",
                        "IBKR_QUERY_IDS": "Q1", "GHOST_TOKEN": "synthetic",
                        "GHOST_HOST": "http://example.invalid"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("GHOST_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ACTIVITY_RECONCILIATION", raising=False)
    monkeypatch.delenv("ACTIVITY_REVIEW_FILE", raising=False)


@pytest.mark.parametrize("name", ["", "off", "conservative", "balanced", "permissive"])
def test_profile_config_values(configured, monkeypatch, tmp_path, name):
    monkeypatch.setenv("ACTIVITY_RECONCILIATION", name)
    if name not in ("", "off"):
        monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(tmp_path / "review.yaml"))
    assert config.load().activity_reconciliation == (name or "off")
    assert config.load_config()["activity_reconciliation"] == (name or "off")


@pytest.mark.parametrize("name", ["yes", "BALANCED", "invalid"])
def test_profile_config_invalid(configured, monkeypatch, name):
    monkeypatch.setenv("ACTIVITY_RECONCILIATION", name)
    with pytest.raises(RuntimeError, match="ACTIVITY_RECONCILIATION"):
        config.load()


def test_profile_config_requires_review(configured, monkeypatch):
    monkeypatch.setenv("ACTIVITY_RECONCILIATION", "balanced")
    with pytest.raises(RuntimeError, match="ACTIVITY_REVIEW_FILE"):
        config.load()


@pytest.mark.parametrize("name,source,target,currency,accepted", [
    ("off", "100", "100", "USD", False),
    ("conservative", "100", "100.000", "USD", True),
    ("conservative", "100", "100.000001", "USD", False),
    ("balanced", "10", "10.01", "USD", True),
    ("balanced", "9", "9.01", "USD", False),
    ("balanced", "10000", "10000.010001", "USD", False),
    ("balanced", "1000", "1001", "JPY", True),
    ("balanced", "999", "1000", "JPY", False),
    ("permissive", "100", "101", "EUR", True),
    ("permissive", "99", "100", "EUR", False),
    ("permissive", "10000", "10001.00001", "CAD", False),
    ("permissive", "100", "100", "CHF", False),
    ("permissive", "100", "100", "ZAc", False),
    ("balanced", "0", "0", "USD", False),
    ("balanced", "-1", "-1", "USD", False),
    ("balanced", "NaN", "1", "USD", False),
])
def test_financial_limits_both_bounds(name, source, target, currency, accepted):
    assert reconciliation.gross_within_limits(name, D(source), D(target), currency) is accepted


def test_financial_limits_quantity_and_denomination():
    source = dict(type="BUY", quantity="10", unitPrice="10", currency="GBP", fee="1")
    target = dict(source, unitPrice="1000", currency="GBp", fee="999")
    assert reconciliation.financial_eligible("balanced", source, target)
    assert not reconciliation.financial_eligible("permissive", source, dict(target, quantity="10.00001"))
    assert not reconciliation.financial_eligible("permissive", source, dict(target, currency="EUR"))
    dividend = dict(source, type="DIVIDEND")
    assert not reconciliation.financial_eligible("balanced", dividend, dict(dividend, quantity="1", unitPrice="100"))
    assert reconciliation.financial_eligible("balanced", dividend, dict(dividend, quantity="1", unitPrice="100"), dividend_quantity_proven=True)


def test_numeric_residue_reproduces_existing_trade_conversion():
    from _sync_helpers import report, trade_xml
    from ghostfolio_ibkr_sync.activity_review import source_events
    event = next(iter(source_events(report(trade_xml("T1", qty=1000000, symbol="TEST.L",
                     currency="GBP", tradePrice="0.018")), "U1", "acc", {}).values()))
    original = dict(event["values"], unitPrice="1.8")
    evidence = reconciliation.numeric_evidence(event, original)
    assert evidence["calculation residue"] is True
    assert evidence["source gross"] == "18000"
    assert event["values"]["unitPrice"] == "1.7999999999999998"
    assert not reconciliation.numeric_evidence(event, dict(original, unitPrice="1.800000000001"))["calculation residue"]


def test_numeric_residue_dividend_quotient_and_unexplained_difference():
    from _sync_helpers import report, div_xml
    from ghostfolio_ibkr_sync.activity_review import source_events
    xml = report(divs=div_xml(amount="1")).replace('quantity="100"', 'quantity="3"')
    event = next(iter(source_events(xml, "U1", "acc", {}).values()))
    evidence = reconciliation.numeric_evidence(event, dict(event["values"], quantity="1", unitPrice="1"))
    assert evidence["calculation residue"] is True
    assert evidence["source gross"] == "1"
    assert not reconciliation.numeric_evidence(event, dict(event["values"], quantity="1", unitPrice="1.00000001"))["calculation residue"]


def test_numeric_residue_round_total_once_half_even_and_preserve_payload():
    from _sync_helpers import report, trade_xml
    from ghostfolio_ibkr_sync.activity_review import source_events
    event = next(iter(source_events(report(trade_xml("T1", qty=3, tradePrice="0.335")), "U1", "acc", {}).values()))
    before = dict(event["payload"])
    evidence = reconciliation.numeric_evidence(event, dict(event["values"]))
    assert evidence["source display"] == "1.00"
    assert evidence["source gross"] == "1.005"
    assert event["payload"] == before


def test_numeric_residue_does_not_accept_arbitrary_minor_difference():
    from _sync_helpers import report, trade_xml
    from ghostfolio_ibkr_sync.activity_review import source_events
    event = next(iter(source_events(report(trade_xml("T1", qty=1, currency="JPY", tradePrice="100")), "U1", "acc", {}).values()))
    assert not reconciliation.numeric_evidence(event, dict(event["values"], unitPrice="101"))["calculation residue"]


def matching_events(xml=None):
    from test_activity_review import source_events
    return source_events(xml)


def matching_row(**kwargs):
    from test_activity_review import destination
    return destination(quantity=D("10"), **kwargs)


def test_unique_matching_complete_graph_both_directions():
    from _sync_helpers import report, trade_xml
    from ghostfolio_ibkr_sync.activity_review import refresh_proposals
    events = matching_events(report(trade_xml("T1") + trade_xml("T2")))
    rows = [matching_row(id="one"), matching_row(id="two", fee=D("999"))]
    for ordered in (rows, rows[::-1]):
        proposals, _ = refresh_proposals({}, events, ordered, {"U1": "acc"}, reconciliation="balanced", timezone="UTC")
        assert len(proposals) == 4
        assert not any(p["automatic eligible"] for p in proposals.values())
    unique, _ = refresh_proposals({}, matching_events(), [rows[0]], {"U1": "acc"}, reconciliation="balanced", timezone="UTC")
    assert next(iter(unique.values()))["automatic eligible"]


@pytest.mark.parametrize("name,reference,eligible", [
    ("conservative", None, False), ("conservative", "IBKR#v2#U1:TRADE:T1", True),
    ("balanced", None, True), ("off", None, False),
])
def test_unique_matching_reference_and_profile(name, reference, eligible):
    from ghostfolio_ibkr_sync.activity_review import refresh_proposals
    proposals, _ = refresh_proposals({}, matching_events(), [matching_row(comment=reference, fee=D("100"))],
                                    {"U1": "acc"}, reconciliation=name, timezone="UTC")
    assert next(iter(proposals.values()))["automatic eligible"] is eligible


def test_unique_matching_exact_conflict_prevents_proximity():
    from ghostfolio_ibkr_sync.activity_review import refresh_proposals
    rows = [matching_row(comment="IBKR#v2#U1:TRADE:T1", currency="EUR"), matching_row(id="near")]
    proposals, _ = refresh_proposals({}, matching_events(), rows, {"U1": "acc"}, reconciliation="permissive", timezone="UTC")
    assert len(proposals) == 1
    assert not next(iter(proposals.values()))["automatic eligible"]


@pytest.mark.parametrize("zone,source,target,name,eligible", [
    ("America/New_York", "2026-08-02T00:30:00Z", "2026-08-01T23:30:00Z", "balanced", True),
    ("Europe/Zurich", "2026-03-29T00:30:00Z", "2026-03-29T22:30:00Z", "balanced", False),
    ("Europe/Zurich", "2026-03-29T00:30:00Z", "2026-03-31T00:30:00Z", "permissive", True),
    ("UTC", "2026-08-01T23:59:00Z", "2026-08-04T00:00:00Z", "permissive", False),
    ("bad/zone", "2026-08-01T00:00:00Z", "2026-08-01T00:00:00Z", "balanced", False),
    ("", "2026-08-01T00:00:00Z", "2026-08-01T00:00:00Z", "balanced", False),
])
def test_unique_matching_local_calendar(zone, source, target, name, eligible):
    assert reconciliation.date_eligible(name, source, target, "BUY", zone)[0] is eligible


@pytest.mark.parametrize("zone", ["America/New_York", "Asia/Tokyo"])
def test_unique_matching_dividend_midnight_local_dates(zone):
    allowed, context = reconciliation.date_eligible("balanced", "2026-07-15T00:00:00Z",
                                                  "2026-07-15T01:00:00Z", "DIVIDEND", zone)
    assert allowed
    assert context["source local date"] == context["destination local date"]
    assert reconciliation.date_eligible("permissive", "2026-07-15T00:00:00Z", "2026-07-18T00:00:00Z", "DIVIDEND", zone)[0]
    assert not reconciliation.date_eligible("permissive", "2026-07-15T00:00:00Z", "2026-07-19T00:00:00Z", "DIVIDEND", zone)[0]


@pytest.mark.parametrize("change", [{"assetProfile": {"symbol": "KO", "isin": "OTHER", "dataSource": "YAHOO"}},
                                    {"assetProfile": {"symbol": "KO", "dataSource": "MANUAL"}},
                                    {"comment": "IBKR#v2#U1:TRADE:T2"},
                                    {"date": "2026-08-01T10:00:00.0000001Z"}])
def test_unique_matching_refuses_conflicting_evidence(change):
    from ghostfolio_ibkr_sync.activity_review import refresh_proposals
    proposals, _ = refresh_proposals({}, matching_events(), [matching_row(**change)],
                                     {"U1": "acc"}, reconciliation="permissive", timezone="UTC")
    assert not any(item["automatic eligible"] for item in proposals.values())


def test_legacy_migration_preserves_all_other_values_and_separates_correction():
    from ghostfolio_ibkr_sync import activity_review as review
    from test_activity_review import destination
    events = matching_events()
    row = destination("IBKR#T1", quantity=D("2"), fee=D("999"), date="2020-01-01T00:00:00Z")
    proposals, _ = review.refresh_proposals({}, events, [row], {"U1": "acc"}, reconciliation="conservative")
    item = next(iter(proposals.values()))
    assert item["changed fields"] == ["comment"]
    assert item["automatic eligible"] and item["actionable"]
    assert {k: v for k, v in item["current values"].items() if k != "comment"} == {k: v for k, v in item["proposed values"].items() if k != "comment"}
    row["comment"] = item["proposed values"]["comment"]
    later, _ = review.refresh_proposals({}, events, [row], {"U1": "acc"}, reconciliation="conservative")
    correction = next(iter(later.values()))
    assert correction["changed fields"] == ["date", "fee", "quantity"]
    assert not correction["automatic eligible"]


def test_legacy_migration_manual_off_and_current_collisions():
    from ghostfolio_ibkr_sync.activity_review import refresh_proposals
    row = matching_row(comment="IBKR#T1", fee=D("99"))
    proposals, _ = refresh_proposals({}, matching_events(), [row], {"U1": "acc"})
    assert next(iter(proposals.values()))["actionable"]
    assert not next(iter(proposals.values()))["automatic eligible"]
    for extra in (dict(row, id="duplicate"), dict(row, id="occupied", comment="IBKR#v2#U1:TRADE:T1")):
        proposals, _ = refresh_proposals({}, matching_events(), [row, extra], {"U1": "acc"}, reconciliation="balanced")
        assert not any(item["actionable"] for item in proposals.values())


def test_legacy_migration_same_ids_independent_destinations():
    from _sync_helpers import report, trade_xml
    from ghostfolio_ibkr_sync.activity_review import source_events, refresh_proposals
    events = matching_events()
    events.update(source_events(report(trade_xml("T1"), source_account="U2"), "U2", "other", {}))
    rows = [matching_row(comment="IBKR#T1"), matching_row(id="second", comment="IBKR#T1", accountId="other")]
    proposals, _ = refresh_proposals({}, events, rows, {"U1": "acc", "U2": "other"}, reconciliation="balanced")
    assert len(proposals) == 2 and all(item["automatic eligible"] for item in proposals.values())
    events[next(key for key in events if "U2" in key)]["destination account"] = "acc"
    proposals, _ = refresh_proposals({}, events, rows[:1], {"U1": "acc", "U2": "acc"}, reconciliation="balanced")
    assert not any(item["actionable"] for item in proposals.values())


def test_legacy_migration_readback_rebuilds_pending_financial_correction(tmp_path, monkeypatch):
    from test_activity_review import run_review, destination
    from ghostfolio_ibkr_sync import activity_review as review
    server, state, config, blocked, held = run_review(tmp_path, monkeypatch, rows=[destination("IBKR#T1")])
    try:
        assert not blocked and len(server.writes) == 1
        assert server.writes[0]["quantity"] == 1
        assert held == {"IBKR#v2#U1:TRADE:T1"}
        item = next(iter(state["document"]["proposals"].values()))
        assert item["changed fields"] == ["quantity"] and item["approve"] is None
    finally:
        review.close_review(state)


def test_conformity_unrelated_missing_isin_and_actual_conflict():
    from _sync_helpers import report, div_xml
    from ghostfolio_ibkr_sync.activity_review import refresh_proposals
    from test_activity_review import destination
    events = matching_events(report(divs=div_xml()))
    consistent = destination("IBKR#v2#U1:DIVIDEND:A1", type="DIVIDEND", date="2026-07-15T00:00:00Z",
                             quantity=D("100"), unitPrice=D("0.25"), fee=D("0"))
    unrelated = dict(consistent, id="unrelated", comment="IBKR#v2#U1:DIVIDEND:OTHER",
                     assetProfile={"id": "p2", "symbol": "PEP", "dataSource": "YAHOO"})
    proposals, held = refresh_proposals({}, events, [consistent, unrelated], {"U1": "acc"})
    assert proposals == {} and not held
    proposals, _ = refresh_proposals({}, events, [dict(consistent, fee=D("1")), unrelated], {"U1": "acc"})
    assert next(iter(proposals.values()))["actionable"]
    related = dict(unrelated, assetProfile=consistent["assetProfile"])
    proposals, held = refresh_proposals({}, events, [consistent, related], {"U1": "acc"})
    item = next(iter(proposals.values()))
    assert not item["actionable"] and "unrelated" in item["status"] and held


def test_conformity_distinct_legacy_dividends_are_not_exact_action_identities():
    from _sync_helpers import report, div_xml
    from ghostfolio_ibkr_sync.activity_review import refresh_proposals
    from test_activity_review import destination
    cash = div_xml(amount="25") + div_xml(amount="50").replace('actionID="A1"', 'actionID="A2"')
    events = matching_events(report(divs=cash))
    rows = [destination("dividend#KO#2026-07-15", type="DIVIDEND", date="2026-07-15T00:00:00Z",
                        quantity=D("100"), unitPrice=D(price), fee=D("0"), id=key)
            for price, key in [("0.25", "one"), ("0.50", "two")]]
    proposals, _ = refresh_proposals({}, events, rows, {"U1": "acc"}, reconciliation="balanced")
    eligible = [item for item in proposals.values() if item["automatic eligible"]]
    assert len(eligible) == 2
    assert all(item["match reason"] == "legacy alias" and item["changed fields"] == ["comment"] for item in eligible)


def test_conformity_blocked_differences_remain_visible_and_partial_scope_holds():
    from _sync_helpers import report, div_xml
    from ghostfolio_ibkr_sync.activity_review import refresh_proposals
    from test_activity_review import destination
    cash = div_xml() + div_xml().replace('actionID="A1"', 'actionID="A2"')
    row = destination("IBKR#v2#U1:DIVIDEND:A1", type="DIVIDEND", date="2026-07-15T00:00:00Z")
    proposals, held = refresh_proposals({}, matching_events(report(divs=cash)), [row], {"U1": "acc"})
    item = next(iter(proposals.values()))
    assert not item["actionable"] and "quantity" in item["changed fields"]
    assert held


@pytest.mark.parametrize("tax,refund,fee", [("-3", "1", "2"), ("-1", "3", "0")])
def test_conformity_signed_tax_keeps_validated_source_fee(tax, refund, fee):
    from _sync_helpers import report, div_xml
    from ghostfolio_ibkr_sync.activity_review import refresh_proposals
    from test_activity_review import destination
    taxes = "".join(div_xml(amount=value).replace('type="Dividends"', 'type="Withholding Tax"') for value in (tax, refund))
    events = matching_events(report(divs=div_xml() + taxes))
    row = destination("IBKR#v2#U1:DIVIDEND:A1", type="DIVIDEND", date="2026-07-15T00:00:00Z",
                      quantity=D("100"), unitPrice=D("0.25"), fee=D(fee))
    proposals, held = refresh_proposals({}, events, [row], {"U1": "acc"})
    assert not proposals and not held


def test_compact_review_private_evidence_decision_and_missing_state(tmp_path):
    from ghostfolio_ibkr_sync import activity_review as review
    from test_activity_review import preview
    path = tmp_path / "review.yaml"
    state = review.open_review(str(path), [])
    try:
        review.publish_review(state, {"version": 1, "proposals": preview()})
    finally:
        review.close_review(state)
    public = review.read_yaml(path.read_bytes())
    assert public["version"] == 3
    assert set(public) == {"version", "generation", "summary", "groups", "consistent", *review.SECTIONS}
    item = next(iter(public["activity_corrections"].values()))
    assert "current values" not in item and "binding" not in item
    assert item["proposed"]["comment"] == "IBKR#v2#U1:TRADE:T1"
    item["decision"] = "yes"
    path.write_text(__import__("yaml").safe_dump(public))
    loaded = review.load_review(path)
    assert next(iter(loaded["proposals"].values()))["approve"] == "yes"
    evidence = path.with_name(path.name + ".state.yaml")
    assert evidence.stat().st_mode & 0o777 == 0o600
    evidence.rename(path.with_name("retained-state.yaml"))
    with pytest.raises(RuntimeError, match="state"):
        review.open_review(str(path), [])


def test_compact_review_previous_generation_and_unknown_generation(tmp_path, monkeypatch):
    from ghostfolio_ibkr_sync import activity_review as review
    from test_activity_review import preview
    path = tmp_path / "review.yaml"
    state = review.open_review(str(path), [])
    try:
        review.publish_review(state, {"version": 1, "proposals": preview()})
        public = review.read_yaml(path.read_bytes())
        next(iter(public["activity_corrections"].values()))["decision"] = "yes"
        path.write_text(__import__("yaml").safe_dump(public))
    finally:
        review.close_review(state)
    state = review.open_review(str(path), [])
    real_atomic = review.atomic_yaml
    def crash(target, document):
        if target == path:
            raise OSError("synthetic publication interruption")
        return real_atomic(target, document)
    try:
        monkeypatch.setattr(review, "atomic_yaml", crash)
        changed = __import__("copy").deepcopy(state["document"])
        next(iter(changed["proposals"].values()))["status"] = "new status"
        with pytest.raises(OSError):
            review.publish_review(state, changed)
    finally:
        review.close_review(state)
    monkeypatch.setattr(review, "atomic_yaml", real_atomic)
    state = review.open_review(str(path), [])
    try:
        assert next(iter(state["document"]["proposals"].values()))["approve"] == "yes"
        review.publish_review(state, state["document"])
    finally:
        review.close_review(state)
    public = review.read_yaml(path.read_bytes())
    public["generation"] = "unknown"
    path.write_text(__import__("yaml").safe_dump(public))
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="generation"):
        review.open_review(str(path), [])
    assert path.read_bytes() == before


@pytest.mark.parametrize("version", [1, 2])
def test_compact_review_legacy_journal_keys_preserved_and_never_resent(tmp_path, monkeypatch, version):
    from ghostfolio_ibkr_sync import activity_review as review
    from test_activity_review import run_review
    server, state, config, blocked, _ = run_review(tmp_path, monkeypatch, outcome="unchanged")
    assert blocked
    proposal = __import__("copy").deepcopy(next(iter(state["document"]["proposals"].values())))
    entry = __import__("copy").deepcopy(next(iter(state["journal"]["entries"].values())))
    path, journal_path, state_path = state["path"], state["journal_path"], state["state_path"]
    review.close_review(state)
    legacy_key = review.fingerprint([proposal["source event"], proposal["destination account"], proposal["activity id"]])
    proposal.update(key=legacy_key, approve="yes")
    entry["proposal key"] = legacy_key
    entry.pop("authority"); entry.pop("eligibility")
    journal = {"version": 1, "entries": {review.fingerprint([legacy_key, entry["review revision"]]): entry}}
    legacy = {"version": 1, "proposals": {legacy_key: proposal}} if version == 1 else {
        "version": 2, "reference_updates": {}, "activity_corrections": {legacy_key: proposal}}
    review.atomic_yaml(path, legacy)
    review.atomic_yaml(journal_path, journal)
    state_path.rename(tmp_path / "saved-state.yaml")
    journal_before = journal_path.read_bytes()
    state = review.open_review(str(path), [])
    try:
        item = next(iter(state["document"]["proposals"].values()))
        assert item["approve"] is None and item["review revision"] == proposal["review revision"]
        assert state["evidence"]["aliases"][legacy_key] == item["key"]
        blocked, held = review.process_review(state, config, matching_events(), {"U1": "acc"})
        assert blocked and held and len(server.writes) == 1
        assert journal_path.read_bytes() == journal_before
    finally:
        review.close_review(state)


@pytest.mark.parametrize("companion", [".state.yaml", ".journal.yaml", ".lock"])
def test_compact_review_preserves_input_at_every_companion_boundary(tmp_path, companion):
    from ghostfolio_ibkr_sync import activity_review as review
    path = tmp_path / "review.yaml"
    source = tmp_path / ("review.yaml" + companion)
    source.write_text("protected input")
    source.chmod(0o600)
    with pytest.raises(RuntimeError, match="overlaps"):
        review.open_review(str(path), [str(source)])
    assert source.read_text() == "protected input" and not path.exists()


def test_pair_rejection_survives_fee_tags_notes_profile_changes_and_releases_hold():
    from ghostfolio_ibkr_sync import activity_review as review
    events = matching_events()
    row = matching_row()
    previous, _ = review.refresh_proposals({}, events, [row], {"U1": "acc"})
    key = next(iter(previous)); previous[key]["approve"] = "reject"
    rejected, held = review.refresh_proposals(previous, events, [row], {"U1": "acc"}, reconciliation="balanced")
    assert not held and rejected[key]["rejected"]
    changed = dict(row, fee=D("99"), comment="new notes", tags=[{"id": "new-tag"}])
    refreshed, held = review.refresh_proposals(rejected, events, [changed], {"U1": "acc"}, reconciliation="permissive", timezone="Asia/Tokyo")
    assert not held and refreshed[key]["rejected"] and refreshed[key]["approve"] == "reject"
    changed["unitPrice"] = D("60.001")
    stale, held = review.refresh_proposals(refreshed, events, [changed], {"U1": "acc"}, reconciliation="permissive")
    assert held and stale[key]["approve"] is None and not stale[key]["automatic eligible"]


def test_pair_rejection_new_candidates_and_recognized_claim_still_hold():
    from ghostfolio_ibkr_sync import activity_review as review
    row = matching_row()
    previous, _ = review.refresh_proposals({}, matching_events(), [row], {"U1": "acc"})
    key = next(iter(previous)); previous[key]["approve"] = "reject"
    refreshed, held = review.refresh_proposals(previous, matching_events(), [row, dict(row, id="new")], {"U1": "acc"})
    assert held and refreshed[key]["rejected"]
    exact = dict(row, comment="IBKR#v2#U1:TRADE:T1", fee=D("99"))
    previous, _ = review.refresh_proposals({}, matching_events(), [exact], {"U1": "acc"})
    key = next(iter(previous)); previous[key]["approve"] = "reject"
    refreshed, held = review.refresh_proposals(previous, matching_events(), [exact], {"U1": "acc"})
    assert held and refreshed[key]["rejected"]


def test_pair_rejection_missing_target_and_source_suspend_without_authority():
    from ghostfolio_ibkr_sync import activity_review as review
    previous, _ = review.refresh_proposals({}, matching_events(), [matching_row()], {"U1": "acc"})
    key = next(iter(previous)); previous[key]["approve"] = "reject"
    rejected, _ = review.refresh_proposals(previous, matching_events(), [matching_row()], {"U1": "acc"})
    absent, held = review.refresh_proposals(rejected, matching_events(), [], {"U1": "acc"})
    assert not held and absent[key]["rejected"]
    absent, held = review.refresh_proposals(rejected, {}, [matching_row()], {"U1": "acc"})
    assert held and absent[key]["rejected"]


def test_pair_rejection_trade_selection_keeps_target_for_other_event():
    from _sync_helpers import report, trade_xml
    from ghostfolio_ibkr_sync.ghostfolio import index_existing_activities
    from ghostfolio_ibkr_sync.app import select_account_activities
    row = matching_row()
    ids, comments, positions = index_existing_activities({"activities": [row], "count": 1})
    activities, _, _, ok = select_account_activities(report(trade_xml("T1") + trade_xml("T2")),
        "U1", "acc", {}, ids, comments, positions,
        review_rejections={"IBKR#v2#U1:TRADE:T1": {"row1"}})
    assert ok and [item["comment"] for item in activities] == ["IBKR#v2#U1:TRADE:T1"]


def test_pair_rejection_dividend_selection_does_not_globally_remove_target():
    from _sync_helpers import report, div_xml
    from ghostfolio_ibkr_sync.ghostfolio import index_existing_activities
    from ghostfolio_ibkr_sync.ibkr import parse_cash_dividends
    from ghostfolio_ibkr_sync.sync import dividend_dedup_decision
    from test_activity_review import destination
    row = destination(type="DIVIDEND", date="2026-07-15T00:00:00Z", quantity=D("100"), unitPrice=D("0.25"))
    ids, comments, positions = index_existing_activities({"activities": [row], "count": 1})
    one = parse_cash_dividends(report(divs=div_xml()))[0]
    two = parse_cash_dividends(report(divs=div_xml().replace('actionID="A1"', 'actionID="A2"')))[0]
    rejected = {"IBKR#v2#U1:DIVIDEND:A1": {"row1"}}
    assert dividend_dedup_decision(one, "acc", {}, positions, comments, rejected)[0] == "new"
    assert dividend_dedup_decision(two, "acc", {}, positions, comments, rejected)[0] == "proximity"


def test_pair_rejection_dividend_group_keeps_target_available_to_other_action():
    from _sync_helpers import report, div_xml
    from ghostfolio_ibkr_sync.ghostfolio import index_existing_activities
    from ghostfolio_ibkr_sync.app import select_account_activities
    from test_activity_review import destination
    row = destination(type="DIVIDEND", date="2026-07-15T00:00:00Z", quantity=D("100"), unitPrice=D("0.25"))
    ids, comments, positions = index_existing_activities({"activities": [row], "count": 1})
    xml = report(divs=div_xml() + div_xml().replace('actionID="A1"', 'actionID="A2"'))
    activities, _, _, ok = select_account_activities(xml, "U1", "acc", {}, ids, comments, positions,
        review_rejections={"IBKR#v2#U1:DIVIDEND:A1": {"row1"}})
    assert ok and [item["comment"] for item in activities] == ["IBKR#v2#U1:DIVIDEND:A1"]


def test_pair_rejection_summed_fill_does_not_reuse_rejected_target():
    from _sync_helpers import report, trade_xml
    from ghostfolio_ibkr_sync.ghostfolio import index_existing_activities
    from ghostfolio_ibkr_sync.app import select_account_activities
    row = matching_row()
    ids, comments, positions = index_existing_activities({"activities": [row], "count": 1})
    activities, _, _, _ = select_account_activities(report(trade_xml("T1", qty=4) + trade_xml("T2", qty=6)),
        "U1", "acc", {}, ids, comments, positions, review_rejections={"IBKR#v2#U1:TRADE:T1": {"row1"}})
    assert [item["comment"] for item in activities] == ["IBKR#v2#U1:TRADE:T1"]
    assert ("U1", "T2") not in positions.get("manual_trade_ids", set())


@pytest.mark.parametrize("name,dry,writes", [("off", False, 0), ("conservative", False, 1),
    ("balanced", False, 1), ("permissive", True, 0)])
def test_profile_execution_fresh_authority_and_exact_journal(tmp_path, monkeypatch, name, dry, writes):
    from test_activity_review import ReviewServer
    from ghostfolio_ibkr_sync import activity_review as review
    row = matching_row(comment="IBKR#v2#U1:TRADE:T1", fee=D("99"))
    server = ReviewServer(monkeypatch, [row])
    state = review.open_review(str(tmp_path / "review.yaml"), [])
    config = {"ghost_host": "http://ghost", "ghost_token": "synthetic", "dry_run": dry, "activity_reconciliation": name, "activity_review_file": str(state["path"])}
    try:
        blocked, held = review.process_review(state, config, matching_events(), {"U1": "acc"})
        assert len(server.writes) == writes and not blocked
        if writes:
            entry = next(iter(state["journal"]["entries"].values()))
            assert entry["authority"] == name and entry["status"] == "confirmed"
            assert entry["eligibility"]["timezone"] == "UTC"
            assert entry["request"]["fee"] == "1"
            assert not held
        else:
            assert not state["journal"]["entries"] and held
            assert next(iter(state["document"]["proposals"].values()))["approve"] is None
    finally:
        review.close_review(state)


def test_profile_execution_single_budget_and_oldest_manual_work_first(tmp_path, monkeypatch):
    from _sync_helpers import report, trade_xml
    from test_activity_review import ReviewServer, write_review
    from ghostfolio_ibkr_sync import activity_review as review
    row = matching_row(comment="IBKR#v2#U1:TRADE:T1", fee=D("99"))
    first, _ = review.refresh_proposals({}, matching_events(), [row], {"U1": "acc"})
    item = next(iter(first.values())); item["approve"] = "yes"; item["first eligible"] = "2020-01-01T00:00:00+00:00"
    second = dict(row, id="second", comment="IBKR#v2#U1:TRADE:T2")
    server = ReviewServer(monkeypatch, [row, second])
    path = tmp_path / "review.yaml"; write_review(path, {"version": 1, "proposals": first})
    state = review.open_review(str(path), [])
    config = {"ghost_host": "http://ghost", "ghost_token": "synthetic", "dry_run": False, "activity_reconciliation": "balanced", "activity_review_file": str(state["path"])}
    try:
        events = matching_events(report(trade_xml("T1") + trade_xml("T2")))
        blocked, held = review.process_review(state, config, events, {"U1": "acc"})
        assert not blocked and len(server.writes) == 1 and server.writes[0]["id"] == "row1"
        assert held == {"IBKR#v2#U1:TRADE:T2"}
        assert next(iter(state["journal"]["entries"].values()))["authority"] == "manual"
    finally:
        review.close_review(state)


def test_profile_execution_timeout_restart_off_does_not_resend(tmp_path, monkeypatch):
    from test_activity_review import ReviewServer
    from ghostfolio_ibkr_sync import activity_review as review
    row = matching_row(comment="IBKR#v2#U1:TRADE:T1", fee=D("99"))
    server = ReviewServer(monkeypatch, [row], "unchanged")
    path = tmp_path / "review.yaml"; state = review.open_review(str(path), [])
    config = {"ghost_host": "http://ghost", "ghost_token": "synthetic", "dry_run": False, "activity_reconciliation": "balanced", "activity_review_file": str(state["path"])}
    try:
        blocked, held = review.process_review(state, config, matching_events(), {"U1": "acc"})
        assert blocked == {"acc"} and held and len(server.writes) == 1
    finally:
        review.close_review(state)

    config["activity_reconciliation"] = "off"
    state = review.open_review(str(path), [])
    try:
        blocked, held = review.process_review(state, config, matching_events(), {"U1": "acc"})
        assert blocked == {"acc"} and held and len(server.writes) == 1
    finally:
        review.close_review(state)


@pytest.mark.parametrize("cooldown", ["rebuild", "rejection"])
def test_profile_execution_cooldown_requires_prior_blank_publication(tmp_path, monkeypatch, cooldown):
    from test_activity_review import ReviewServer, write_review
    from ghostfolio_ibkr_sync import activity_review as review
    row = matching_row(fee=D("99"))
    previous, _ = review.refresh_proposals({}, matching_events(), [row], {"U1": "acc"})
    key = next(iter(previous))
    if cooldown == "rejection":
        previous[key]["approve"] = "reject"
        previous, _ = review.refresh_proposals(previous, matching_events(), [row], {"U1": "acc"})
        row["unitPrice"] = D("60.0001")
    server = ReviewServer(monkeypatch, [row])
    path = tmp_path / "review.yaml"; write_review(path, {"version": 1, "proposals": previous})
    state = review.open_review(str(path), [])
    if cooldown == "rebuild":
        state["evidence"]["rebuild cooldown"] = 2
    config = {"ghost_host": "http://ghost", "ghost_token": "synthetic", "dry_run": False,
              "activity_reconciliation": "balanced", "activity_review_file": str(path)}
    try:
        review.process_review(state, config, matching_events(), {"U1": "acc"})
        assert not server.writes
        assert next(iter(state["document"]["proposals"].values()))["approve"] is None
    finally:
        review.close_review(state)
    state = review.open_review(str(path), [])
    try:
        blocked, _ = review.process_review(state, config, matching_events(), {"U1": "acc"})
        assert not blocked and len(server.writes) == 1
    finally:
        review.close_review(state)


@pytest.mark.parametrize("timezone", ["", "bad/timezone"])
def test_profile_execution_invalid_timezone_never_writes(tmp_path, monkeypatch, timezone):
    from test_activity_review import ReviewServer
    from ghostfolio_ibkr_sync import activity_review as review
    monkeypatch.setenv("TZ", timezone)
    server = ReviewServer(monkeypatch, [matching_row(comment="IBKR#v2#U1:TRADE:T1", fee=D("99"))])
    state = review.open_review(str(tmp_path / "review.yaml"), [])
    try:
        config = {"ghost_host": "http://ghost", "ghost_token": "synthetic", "dry_run": False,
                  "activity_reconciliation": "permissive", "activity_review_file": str(state["path"])}
        review.process_review(state, config, matching_events(), {"U1": "acc"})
        assert not server.writes and not state["journal"]["entries"]
    finally:
        review.close_review(state)


def test_profile_execution_revalidates_profile_before_dispatch(tmp_path, monkeypatch):
    import requests
    from test_activity_review import ReviewServer
    from ghostfolio_ibkr_sync import activity_review as review
    server = ReviewServer(monkeypatch, [matching_row(fee=D("99"))])
    state = review.open_review(str(tmp_path / "review.yaml"), [])
    config = {"ghost_host": "http://ghost", "ghost_token": "synthetic", "dry_run": False,
              "activity_reconciliation": "balanced", "activity_review_file": str(state["path"])}
    def get(*args, **kwargs):
        response = server.get(*args, **kwargs)
        if server.reads == 4:
            config["activity_reconciliation"] = "off"
        return response
    monkeypatch.setattr(requests, "get", get)
    try:
        blocked, _ = review.process_review(state, config, matching_events(), {"U1": "acc"})
        assert not server.writes and blocked == {"acc"}
    finally:
        review.close_review(state)


def test_group_diagnosis_counts_distinct_fills_and_targets_once():
    from _sync_helpers import report, trade_xml
    from ghostfolio_ibkr_sync import activity_review as review
    from test_activity_review import destination
    events = matching_events(report("".join(trade_xml(f"T{i}", qty="2.5", ibCommission="-0.25") for i in range(4))))
    rows = [destination(quantity=D("5"), fee=D("0.505"), id=str(i)) for i in range(2)]
    proposals, _ = review.refresh_proposals({}, events, rows, {"U1": "acc"}, reconciliation="permissive")
    groups = reconciliation.group_diagnosis(events, proposals)
    group = next(iter(groups.values()))
    assert group["source count"] == 4 and group["destination count"] == 2
    assert len(group["members"]) == 8
    assert group["source totals"]["USD"] == {"quantity": "10", "gross": "600", "fee": "1"}
    assert group["destination totals"]["USD"] == {"quantity": "10", "gross": "600", "fee": "1.01"}
    assert group["differences"]["USD"]["fee"] == "0.01"
    assert group["status"] == "manual allocation required"
    assert not any(item["automatic eligible"] for item in proposals.values())


def test_profile_execution_outcomes_are_truthful_and_external_text_is_redacted(tmp_path, monkeypatch):
    from test_activity_review import ReviewServer
    from ghostfolio_ibkr_sync import activity_review as review
    from ghostfolio_ibkr_sync.outcome import new_run_outcome, action_summary
    from ghostfolio_ibkr_sync.notify import reconciliation_summary
    server = ReviewServer(monkeypatch, [matching_row(fee=D("99"))])
    path = tmp_path / "private-review.yaml"; state = review.open_review(str(path), [])
    outcome = new_run_outcome()
    config = {"ghost_host": "http://ghost", "ghost_token": "synthetic", "dry_run": True,
        "activity_reconciliation": "balanced", "activity_review_file": str(path), "_corporate_outcome": outcome}
    try:
        review.process_review(state, config, matching_events(), {"U1": "acc"})
        assert outcome["reconciliation"]["would correct"] == 1
        assert outcome["reconciliation"]["automatically corrected"] == 0 and not server.writes
        public = review.read_yaml(path.read_bytes())
        assert public["summary"]["simulation"] is True and public["summary"]["profile"] == "balanced"
        external = reconciliation_summary(outcome) + action_summary(outcome)
        assert str(path) not in external and "row1" not in external and "IBKR#" not in external and "99" not in external
    finally:
        review.close_review(state)


def test_profile_execution_uncertain_result_is_not_reported_as_corrected(tmp_path, monkeypatch):
    from test_activity_review import ReviewServer
    from ghostfolio_ibkr_sync import activity_review as review
    from ghostfolio_ibkr_sync.outcome import new_run_outcome
    ReviewServer(monkeypatch, [matching_row(fee=D("99"))], "unchanged")
    state = review.open_review(str(tmp_path / "review.yaml"), [])
    outcome = new_run_outcome()
    config = {"ghost_host": "http://ghost", "ghost_token": "synthetic", "dry_run": False,
        "activity_reconciliation": "balanced", "activity_review_file": str(state["path"]), "_corporate_outcome": outcome}
    try:
        blocked, _ = review.process_review(state, config, matching_events(), {"U1": "acc"})
        assert blocked and outcome["reconciliation"]["automatically corrected"] == 0
        assert outcome["reconciliation"]["blocked"] == 1
    finally:
        review.close_review(state)


def test_group_diagnosis_distinct_dividends_keep_independent_pairs():
    from _sync_helpers import report, div_xml
    from ghostfolio_ibkr_sync.activity_review import refresh_proposals
    from test_activity_review import destination
    cash = div_xml(amount="25") + div_xml(amount="50").replace('actionID="A1"', 'actionID="A2"')
    events = matching_events(report(divs=cash))
    rows = [destination("dividend#KO#2026-07-15", type="DIVIDEND", date="2026-07-15T00:00:00Z",
                        quantity=D("100"), unitPrice=D(price), fee=D("0"), id=key)
            for price, key in [("0.25", "one"), ("0.50", "two")]]
    proposals, _ = refresh_proposals({}, events, rows, {"U1": "acc"}, reconciliation="balanced")
    group = next(iter(reconciliation.group_diagnosis(events, proposals).values()))
    assert group["status"] == "independent unique pairs"
    assert group["source totals"]["USD"]["gross"] == "75"
    assert group["destination totals"]["USD"]["gross"] == "75"


def test_financial_limits_preserve_tiny_excess_and_large_display():
    source = {"quantity": "1", "unitPrice": "100", "currency": "USD", "type": "BUY"}
    target = {**source, "unitPrice": "100.01" + "0" * 110 + "1"}
    assert not reconciliation.financial_eligible("balanced", source, target)
    assert reconciliation.gross_within_limits("conservative", D("1e300"), D("1e300"), "USD")
    events = matching_events()
    event = next(iter(events.values()))
    event["values"].update(quantity="1", unitPrice="1e300")
    event["source evidence"].update(quantity="1", tradePrice="1e300")
    evidence = reconciliation.numeric_evidence(event, event["values"])
    assert evidence["source display"] == "1" + "0" * 300 + ".00"
