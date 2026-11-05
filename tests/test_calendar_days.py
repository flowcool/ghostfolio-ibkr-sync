"""Execution instants and ledger calendar days must remain separate."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import logging
import time
import xml.etree.ElementTree as ET

import pytest

from _sync_helpers import div_xml, report, trade_xml, positions
from ghostfolio_ibkr_sync import activity_review as review, app, ibkr, sync
from test_activity_review import destination


ZONES = ["Europe/Paris", "Asia/Bangkok", "America/Los_Angeles", "Asia/Kolkata"]


@pytest.fixture
def configured_timezone(request, monkeypatch):
    with monkeypatch.context() as scoped:
        scoped.setenv("TZ", request.param)
        time.tzset()
        try:
            yield request.param
        finally:
            scoped.undo()
            time.tzset()


@pytest.mark.parametrize("day,token", [
    ("20260307", "EST"), ("20260308", "EST"), ("20260308", "EDT"),
    ("20261031", "EDT"), ("20261101", "EDT"), ("20261101", "EST"),
])
@pytest.mark.parametrize("clock", ["190000", "200000", "202000", "210000", "220000", "235959"])
def test_ledger_clock_calendar_day_across_dst_and_midnight(day, token, clock):
    raw = f"{day};{clock} {token}"
    expected_day = datetime.strptime(day, "%Y%m%d").date().isoformat()
    xml = report(divs=div_xml(date=raw))
    root = ET.fromstring(xml)
    payment = next(root.iter("CashTransaction"))
    # Both payment kinds and their withholding must group on the written day.
    payment.set("type", "Payment In Lieu Of Dividends")
    payment.set("reportDate", "20261231")
    tax = dict(payment.attrib, type="Withholding Tax", amount="-2")
    next(root.iter("CashTransactions")).append(ET.Element("CashTransaction", tax))
    group, = ibkr.parse_cash_dividends(ET.tostring(root, encoding="unicode"))
    assert group["date"] == expected_day
    assert group["tax"] == -2
    # Qualified accruals retain their calendar day, just like date-only accruals.
    for field in ("payDate", "date", "reportDate"):
        group["accruals"][0][field] = raw
    assert sync.dividend_structured_quantity(group) == Decimal(100)
    payloads, ok = sync.convert_dividend_actions(group, "acc", {}, {}, [group])
    assert ok and len(payloads) == 1
    assert payloads[0]["date"] == expected_day + "T00:00:00+00:00"
    assert payloads[0]["fee"] == 2
    # The same raw clock has a different meaning for a trade.
    instant = datetime.fromisoformat(ibkr.parse_ibkr_datetime(raw))
    wall = datetime.strptime(day + clock, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    assert instant == wall + timedelta(hours=5 if token == "EST" else 4)


@pytest.mark.parametrize("raw", [
    "20260811;202000 JST", "20260811;202000 EDT garbage",
    "20260230;202000 EDT", "20260811;256000 EDT", "", None,
])
def test_calendar_day_rejects_invalid_complete_evidence(raw):
    assert ibkr.parse_ibkr_calendar_day(raw) is None
    assert sync._dividend_day(raw) is None


@pytest.mark.parametrize("venue,raw,business_day", [
    ("KRX", "20260810;202000 EDT", "20260811"),
    ("TSEJ", "20260118;190000 EST", "20260119"),
    ("LSE", "20260713;203000 EDT", "20260714"),
    ("NASDAQ", "20260308;030000 EDT", "20260308"),
    ("NYSE", "20261101;013000 EST", "20261101"),
    ("ARCA", "20261101;013000 EDT", "20261101"),
    ("BYX", "20260811;235959 EDT", "20260811"),
    ("TSE", "20260811;235959 EDT", "20260811"),
])
def test_trade_business_day_check_uses_known_execution_venue(venue, raw, business_day, caplog):
    row, = ibkr.parse_trades(report(trade_xml("T1", date=raw, exchange=venue, tradeDate=business_day)))
    assert ibkr.trade_business_day_failure(row) is None
    assert sync.convert_trade_to_activity(row, "acc", {}, {})["date"] == ibkr.parse_ibkr_datetime(raw)
    row["tradeDate"] = "20200101"
    with caplog.at_level(logging.ERROR):
        assert sync.convert_trade_to_activity(row, "acc", {}, {}) is None
    assert "held" in caplog.text and "differs from tradeDate" in caplog.text
    xml = report(trade_xml("T1", date=raw, exchange=venue, tradeDate="20200101"))
    assert not review.source_events(xml, "U1", "acc", {})


@pytest.mark.parametrize("day", ["", "invalid", "20260230"])
def test_known_exchange_missing_business_day_is_held(day):
    assert ibkr.trade_business_day_failure({"exchange": "NYSE", "tradeDate": day,
                                          "dateTime": "20260811;100000 EDT"})


@pytest.mark.parametrize("venue", ["", "UNKNOWN", "SMART", "DARK", "EUDARK"])
def test_unknown_exchange_zone_is_not_inferred_from_currency(venue):
    row, = ibkr.parse_trades(report(trade_xml("T1", exchange=venue, currency="JPY", tradeDate="19990101")))
    assert ibkr.trade_business_day_failure(row) is None
    assert sync.convert_trade_to_activity(row, "acc", {}, {}) is not None


@pytest.mark.parametrize("category", ["CASH", "OPT"])
def test_fx_value_date_and_excluded_categories_are_not_execution_days(category):
    row = {"assetCategory": category, "exchange": "NYSE", "tradeDate": "20200101",
           "dateTime": "20260811;202000 EDT"}
    assert ibkr.trade_business_day_failure(row) is None
    assert sync.convert_trade_to_activity(row, "acc", {}, {}) is None


@pytest.mark.parametrize("configured_timezone", ZONES, indirect=True)
def test_canonical_values_review_and_migration_keep_payment_day(configured_timezone):
    zone = configured_timezone
    xml = report(trade_xml("T1", date="20260811;235959 EDT", exchange="NYSE", tradeDate="20260811"),
                 div_xml(date="20260811;202000 EDT"))
    events = review.source_events(xml, "U1", "acc", {})
    trade = events["IBKR#v2#U1:TRADE:T1"]
    dividend = events["IBKR#v2#U1:DIVIDEND:A1"]
    assert trade["values"]["date"] == "2026-08-12T03:59:59+00:00"
    assert dividend["values"]["date"] == "2026-08-11T00:00:00+00:00"
    row = destination(trade["event"], date="2026-08-01T03:59:59Z",
                      quantity=Decimal(10))
    proposals, _ = review.refresh_proposals({}, events, [row], {"U1": "acc"}, timezone=zone)
    proposal, = proposals.values()
    assert proposal["changed fields"] == ["date"]
    assert proposal["proposed values"]["date"] == "2026-08-12T03:59:59+00:00"
    # Correct stored 00:00Z day: no date proposal, including reference migration.
    for marker in (dividend["event"], "dividend#US1912161007#2026-08-11"):
        row = destination(marker, type="DIVIDEND", date="2026-08-11T00:00:00Z",
                          quantity=Decimal(100), unitPrice=Decimal("0.25"), fee=Decimal(0))
        proposals, _ = review.refresh_proposals({}, events, [row], {"U1": "acc"}, timezone=zone)
        for proposal in proposals.values():
            assert "date" not in proposal["changed fields"]
            assert proposal["proposed values"]["date"] == "2026-08-11T00:00:00+00:00"
        if marker.startswith("dividend#"):
            proposal, = proposals.values()
            assert proposal["changed fields"] == ["comment"]
    # A genuinely wrong day gets the same canonical proposal in all four zones.
    row = destination(dividend["event"], type="DIVIDEND", date="2026-08-14T00:00:00Z",
                      quantity=Decimal(100), unitPrice=Decimal("0.25"), fee=Decimal(0))
    proposals, _ = review.refresh_proposals({}, events, [row], {"U1": "acc"}, timezone=zone)
    proposal, = proposals.values()
    assert proposal["changed fields"] == ["date"]
    assert proposal["proposed values"]["date"] == "2026-08-11T00:00:00+00:00"
    assert proposal["date context"]["source calendar day"] == "2026-08-11"
    # Legacy dedup must also use the written payment-day alias.
    group, = ibkr.parse_cash_dividends(xml)
    old = {("acc", "dividend#US1912161007#2026-08-11")}
    assert sync.dividend_dedup_decision(group, "acc", {}, positions(), old)[0] == "existing"


def test_startup_logs_validated_comparison_timezone(monkeypatch, caplog):
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    monkeypatch.setattr(app, "load_mapping", lambda path: (_ for _ in ()).throw(RuntimeError("stop offline")))
    with caplog.at_level(logging.INFO):
        app._run_configured_sync({"dry_run": True, "mapping_file": "synthetic"}, app.new_run_outcome())
    assert "Activity comparison TZ=Asia/Kolkata; must match the Ghostfolio server TZ" in caplog.text
