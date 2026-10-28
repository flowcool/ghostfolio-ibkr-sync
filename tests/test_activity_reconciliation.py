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
