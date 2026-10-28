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
