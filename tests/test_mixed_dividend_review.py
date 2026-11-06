"""Synthetic regressions for three mixed-history dividend group shapes."""

from copy import deepcopy
from decimal import Decimal
import xml.etree.ElementTree as ET

import pytest

from _sync_helpers import div_xml, report
from test_activity_review import destination, source_events, ReviewServer, write_review
from ghostfolio_ibkr_sync import activity_review as review
from ghostfolio_ibkr_sync.app import select_account_activities
from ghostfolio_ibkr_sync.ghostfolio import index_existing_activities


def mixed_shape(shape=0):
    # Observed structures: Re only; repeated Po/Re revisions; one Po/Re pair.
    # All identifiers, days and monetary values here are synthetic.
    quantities = (80, 120, 160)
    missing = ("A1", "A2", "A2")[shape]
    cash = ""
    for action, factor in (("A1", 1), ("A2", 2)):
        payment = div_xml(amount=str(quantities[shape] // 4 * factor))
        payment = payment.replace('actionID="A1"', f'actionID="{action}"')
        cash += payment + payment.replace(
            'type="Dividends"', 'type="Withholding Tax"'
        ).replace(f'amount="{quantities[shape] // 4 * factor}"', 'amount="-2"')
    root = ET.fromstring(report(divs=cash.replace('currency="USD"', 'currency="JPY"')))
    accruals = root.find(".//ChangeInDividendAccruals")
    originals = list(accruals)
    accruals.clear()
    for row in originals:
        row.set("quantity", str(quantities[shape]))
        codes = (
            ("Re",)
            if shape == 0
            else (
                ("Po", "Po", "Po", "Re", "Re", "Re")
                if shape == 1 and row.get("actionID") != missing
                else ("Po", "Re")
            )
        )
        for ordinal, code in enumerate(codes):
            revision = deepcopy(row)
            revision.set("code", code)
            if len(codes) == 6 and ordinal < 5:
                revision.set("payDate", "")
                revision.set("date", "20260701")
                revision.set("reportDate", f"202607{2 + ordinal:02}")
            accruals.append(revision)
    xml = ET.tostring(root, encoding="unicode")
    events = source_events(xml)
    rows = []
    for marker, event in events.items():
        values = event["values"]
        is_missing = marker.endswith(":" + missing)
        rows.append(
            destination(
                "dividend#KO#2026-07-15" if is_missing else marker,
                id="legacy" if is_missing else "covered",
                type="DIVIDEND",
                date=values["date"],
                currency=None,
                quantity=Decimal(values["quantity"]),
                unitPrice=Decimal(values["unitPrice"]),
                fee=Decimal("0"),
                assetProfile={
                    "id": "profile1",
                    "symbol": "KO",
                    "dataSource": "YAHOO",
                    "isin": event["isin"],
                    "currency": "JPY",
                },
            )
        )
    return xml, events, rows, "IBKR#v2#U1:DIVIDEND:" + missing


def refresh(events, rows, previous=None, profile="off"):
    return review.refresh_proposals(
        previous or {},
        events,
        rows,
        {"U1": "acc"},
        reconciliation=profile,
        timezone="Europe/Zurich",
    )


def assert_no_import(xml, rows, held):
    ids, comments, positions = index_existing_activities(
        {"activities": rows, "count": len(rows)}
    )
    activities, _, _, ok = select_account_activities(
        xml, "U1", "acc", {}, ids, comments, positions, review_holds=held
    )
    assert ok and activities == []


@pytest.mark.parametrize("shape", range(3))
@pytest.mark.parametrize("profile", ["off", "conservative", "balanced", "permissive"])
def test_mixed_shapes_unique_proposal_and_no_import(shape, profile):
    xml, events, rows, missing = mixed_shape(shape)
    proposals, held = refresh(events, rows, profile=profile)
    selected = [item for item in proposals.values() if item["actionable"]]
    assert len(selected) == 1
    item = selected[0]
    assert item["source event"] == missing and item["activity id"] == "legacy"
    assert item["changed fields"] == ["comment", "fee"]
    assert item["automatic eligible"] is (profile in ("balanced", "permissive"))
    assert item["proposed values"]["comment"] == missing
    for field in ("id", "quantity", "unitPrice", "date", "tags", "userId", "accountId"):
        assert item["proposed values"][field] == item["current values"][field]
    assert len(held) == 2
    assert_no_import(xml, rows, held)


@pytest.mark.parametrize(
    "fault",
    [
        "two_legacy",
        "manual_overlap",
        "duplicate_v2",
        "quantity",
        "gross",
        "gross_small",
        "equal_gross_wrong_quantity",
        "day",
        "currency",
        "account",
        "isin",
        "symbol",
        "inactive",
        "data_source",
        "tax",
        "accruals",
        "sibling_tax",
        "covered_account",
        "covered_currency",
        "extra_v2",
        "three_actions",
    ],
)
def test_mixed_blocked_ambiguity(fault):
    xml, events, rows, missing = mixed_shape()
    legacy = next(row for row in rows if row["id"] == "legacy")
    covered = next(row for row in rows if row["id"] == "covered")
    if fault in ("two_legacy", "manual_overlap", "duplicate_v2", "extra_v2"):
        extra = deepcopy(covered if fault == "duplicate_v2" else legacy)
        extra["id"] = "extra"
        if fault == "manual_overlap":
            extra["comment"] = None
        if fault == "extra_v2":
            extra["comment"] = "IBKR#v2#U1:DIVIDEND:OTHER"
        rows.append(extra)
    elif fault in ("quantity", "gross"):
        legacy["quantity" if fault == "quantity" else "unitPrice"] += Decimal("1")
    elif fault == "gross_small":
        legacy["unitPrice"] += Decimal("0.0001")
    elif fault == "equal_gross_wrong_quantity":
        legacy["quantity"] *= 2
        legacy["unitPrice"] /= 2
    elif fault == "day":
        legacy["date"] = "2026-07-16T00:00:00Z"
    elif fault == "currency":
        legacy["currency"] = "EUR"
    elif fault == "account":
        legacy["accountId"] = "other"
    elif fault == "isin":
        legacy["assetProfile"]["isin"] = "US0000000001"
    elif fault == "symbol":
        legacy["assetProfile"]["symbol"] = "OTHER"
    elif fault == "inactive":
        legacy["isDraft"] = True
    elif fault == "data_source":
        legacy["assetProfile"]["dataSource"] = "MANUAL"
    elif fault in ("tax", "sibling_tax"):
        event = (
            events[missing]
            if fault == "tax"
            else next(e for k, e in events.items() if k != missing)
        )
        event["source evidence"]["cash_rows"] = event["source evidence"]["payments"]
    elif fault == "accruals":
        events[missing]["source evidence"]["accruals"] = []
    elif fault == "covered_account":
        covered["accountId"] = "other"
    elif fault == "covered_currency":
        covered["currency"] = "EUR"
    elif fault == "three_actions":
        third = deepcopy(events[missing])
        third_id = "IBKR#v2#U1:DIVIDEND:A3"
        third["event"] = third_id
        third["values"]["comment"] = third_id
        third["payload"]["comment"] = third_id
        events[third_id] = third
        for event in events.values():
            event["dividend scope"]["events"] = sorted(events)
    proposals, held = refresh(events, rows, profile="permissive")
    assert proposals and not any(item["actionable"] for item in proposals.values())
    for item in proposals.values():
        item["approve"] = "yes"
    proposals, held = refresh(events, rows, proposals, profile="permissive")
    assert not any(
        item["actionable"] or item.get("automatic eligible")
        for item in proposals.values()
    )
    assert_no_import(xml, rows, held)


@pytest.mark.parametrize("change", ["sibling_fee", "sibling_source", "extra_candidate"])
def test_mixed_dispatch_group_drift_clears_approval(change):
    _, events, rows, missing = mixed_shape()
    proposals, _ = refresh(events, rows)
    item = next(item for item in proposals.values() if item["actionable"])
    item["approve"] = "yes"
    if change == "sibling_fee":
        next(row for row in rows if row["id"] == "covered")["fee"] += Decimal("1")
    elif change == "sibling_source":
        next(e for k, e in events.items() if k != missing)["source evidence"][
            "accruals"
        ][0]["code"] = "Po"
    else:
        rows.append(
            destination(id="extra", type="DIVIDEND", date="2026-07-15T00:00:00Z")
        )
    fresh, _ = refresh(events, rows, proposals)
    assert fresh[item["key"]]["approve"] is None
    assert fresh[item["key"]]["review revision"] != item["review revision"]


@pytest.mark.parametrize("shape", range(3))
@pytest.mark.parametrize("outcome", ["success", "unchanged"])
def test_mixed_dispatch_confirm_restart_or_stop(tmp_path, monkeypatch, shape, outcome):
    monkeypatch.setenv("TZ", "Europe/Zurich")
    xml, events, rows, missing = mixed_shape(shape)
    server = ReviewServer(monkeypatch, rows, outcome=outcome)
    proposals, _ = refresh(events, rows)
    item = next(item for item in proposals.values() if item["actionable"])
    item["approve"] = "yes"
    path = tmp_path / "review.yaml"
    write_review(path, {"version": 1, "proposals": proposals})
    config = {
        "ghost_host": "http://ghost",
        "ghost_token": "synthetic",
        "activity_review_file": str(path),
    }
    for attempt in range(2):
        state = review.open_review(str(path), [])
        try:
            blocked, held = review.process_review(state, config, events, {"U1": "acc"})
            assert len(server.writes) == 1
            assert server.writes[0]["id"] == "legacy"
            entry = next(iter(state["journal"]["entries"].values()))
            assert entry["status"] == (
                "confirmed" if outcome == "success" else "pending"
            )
            assert bool(blocked) is (outcome != "success")
            if outcome == "success":
                sibling = next(
                    p
                    for p in state["document"]["proposals"].values()
                    if p["activity id"] == "covered"
                )
                assert sibling["actionable"] and sibling["changed fields"] == ["fee"]
                assert {r["id"] for r in server.rows} == {"legacy", "covered"}
                assert (
                    next(r for r in server.rows if r["id"] == "legacy")["comment"]
                    == missing
                )
            assert_no_import(xml, server.rows, held)
        finally:
            review.close_review(state)


def test_mixed_dispatch_volatile_values_preserve_consent():
    _, events, rows, _ = mixed_shape()
    proposals, _ = refresh(events, rows)
    item = next(item for item in proposals.values() if item["actionable"])
    item["approve"] = "yes"
    for row in rows:
        row["updatedAt"] = "2026-08-03T00:00:00Z"
        row["valueInBaseCurrency"] = Decimal("999")
        row["account"]["balance"] = Decimal("999")
    fresh, _ = refresh(events, rows, proposals)
    assert fresh[item["key"]]["approve"] == "yes"
    assert fresh[item["key"]]["review revision"] == item["review revision"]


def test_mixed_dispatch_simulation_preserves_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Zurich")
    _, events, rows, _ = mixed_shape()
    server = ReviewServer(monkeypatch, rows)
    proposals, _ = refresh(events, rows)
    item = next(item for item in proposals.values() if item["actionable"])
    item["approve"] = "yes"
    path = tmp_path / "review.yaml"
    write_review(path, {"version": 1, "proposals": proposals})
    state = review.open_review(str(path), [])
    try:
        review.process_review(
            state,
            {
                "ghost_host": "http://ghost",
                "ghost_token": "synthetic",
                "dry_run": True,
                "activity_review_file": str(path),
            },
            events,
            {"U1": "acc"},
        )
        assert not server.writes and not state["journal"]["entries"]
        assert state["document"]["proposals"][item["key"]]["approve"] == "yes"
    finally:
        review.close_review(state)
