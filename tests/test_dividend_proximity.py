"""Offline proximity index: connector-comment rows are excluded, exact identity still dedups."""
import pytest

from ghostfolio_ibkr_sync import diagnostics
from test_dividend_diagnostics import destination, read
from test_orchestration import ACC, ISIN_KO, World, div_xml, report


def payments():
    return (div_xml(amount="25.00", date="20260715")
            + div_xml(amount="100.00", date="20260716").replace('actionID="A1"', 'actionID="A2"'))


def run_against(monkeypatch, rows):
    ids, comments, positions = read(monkeypatch, rows, dry=False)
    world = World(monkeypatch, report(divs=payments()))
    world.run(ids=ids, comments=comments, pos=positions)
    return world, positions


def test_dividend_proximity_canonical_row_is_not_indexed(monkeypatch):
    _, comments, positions = read(monkeypatch, [destination()], dry=False)
    assert (ACC, f"dividend#{ISIN_KO}#2026-07-15") in comments
    assert positions["dividend_dates"][(ACC, "KO")] == []


def test_dividend_proximity_canonical_neighbour_does_not_hide_distinct_payment(monkeypatch, caplog):
    world, _ = run_against(monkeypatch, [destination()])
    assert [a["date"][:10] for a in world.activities] == ["2026-07-16"]
    assert world.activities[0]["unitPrice"] * world.activities[0]["quantity"] == 100
    assert "treated as the same payment" not in caplog.text


def test_dividend_proximity_canonical_rerun_imports_nothing(monkeypatch):
    first, _ = run_against(monkeypatch, [destination()])
    imported = first.activities[0]
    new_row = destination(id="dividend-2", comment=imported["comment"], date=imported["date"],
                          unitPrice=imported["unitPrice"], quantity=imported["quantity"])
    second, _ = run_against(monkeypatch, [destination(), new_row])
    assert second.activities == []


def test_dividend_proximity_canonical_manual_row_still_skips(monkeypatch):
    manual = destination(comment="manual", date="2026-07-17T00:00:00Z")
    world, _ = run_against(monkeypatch, [manual])
    assert world.activities == []


@pytest.mark.parametrize("changes,expected_ok,expected_count", [
    ({}, False, 0),  # replaced action, same security/day
    ({"accountId": "moved-destination"}, False, 0),
    ({"isDraft": True}, False, 0),
    ({"account": {"isExcluded": True}}, False, 0),
    ({"unitPrice": 999}, False, 0),
    ({"date": None}, False, 0),
    ({"date": "not-a-date"}, False, 0),
    ({"date": "2026-07-15"}, False, 0),  # unknown stored instant
    ({"assetProfile": {"symbol": "unknown", "dataSource": "MANUAL"}}, False, 0),
    ({"assetProfile": {"symbol": "OLD", "isin": ISIN_KO, "dataSource": "YAHOO"}}, False, 0),
    ({"date": "2026-07-14T00:00:00Z"}, True, 1),  # never ±3-day proximity
    ({"assetProfile": {"symbol": "PEP", "isin": "US7134481081", "dataSource": "YAHOO"}}, True, 1),
    ({"assetProfile": {"symbol": "PEP", "dataSource": "YAHOO"}}, False, 0),
    ({"comment": "IBKR#v2#U2:DIVIDEND:OLD"}, True, 1),
    ({"comment": "IBKR#v2#U1:DIVIDEND:A1", "unitPrice": 999}, True, 0),
    ({"date": "2026-07-14T00:00:00Z",
      "assetProfile": {"symbol": "unknown", "dataSource": "MANUAL"}}, True, 1),
])
@pytest.mark.parametrize("dry", [False, True])
def test_v2_action_conflict_saved_context_matrix(monkeypatch, caplog, changes, expected_ok, expected_count, dry):
    row = destination(**{"comment": "IBKR#v2#U1:DIVIDEND:OLD", **changes})
    ids, comments, pos = read(monkeypatch, [row], dry=dry)
    assert not pos["dividend_dates"]
    assert not pos.get("dividend_evidence")
    world = World(monkeypatch, report(divs=div_xml()))
    assert world.run(ids=ids, comments=comments, pos=pos)[1] is expected_ok
    assert len(world.activities) == expected_count
    assert world.cash_calls == [(ACC, 100.5)]
    assert ("action-context conflict or unknown overlap" in caplog.text) is (not expected_ok)
    assert "treated as the same payment" not in caplog.text


def test_v2_action_conflict_duplicate_identity_keeps_every_stored_context(monkeypatch):
    rows = [destination(comment="IBKR#v2#U1:DIVIDEND:OLD"),
            destination(id="second", comment="IBKR#v2#U1:DIVIDEND:OLD", date="2026-07-10T00:00:00Z")]
    ids, comments, pos = read(monkeypatch, rows, dry=False)
    assert len(pos["versioned_dividend_context"][("U1", rows[0]["comment"])]) == 2
    world = World(monkeypatch, report(divs=div_xml()))
    assert world.run(ids=ids, comments=comments, pos=pos)[1] is False
    assert world.activities == []


@pytest.mark.parametrize("key", [ISIN_KO, "KO", "MAPPED"])
@pytest.mark.parametrize("inactive", [False, True])
def test_v2_generation_dedup_mixed_history_legacy_wins_before_conflict(monkeypatch, key, inactive):
    rows = [destination(comment=f"dividend#{key}#2026-07-15", isDraft=inactive),
            destination(id="v2", comment="IBKR#v2#U1:DIVIDEND:OLD")]
    ids, comments, pos = read(monkeypatch, rows, dry=False)
    world = World(monkeypatch, report(divs=div_xml()))
    assert world.run(ids=ids, comments=comments, pos=pos, mapping={ISIN_KO: "MAPPED"})[1] is True
    assert world.activities == []


@pytest.mark.parametrize("inactive", [False, True])
def test_v2_generation_dedup_complete_actions_remain_global_and_inactive(monkeypatch, inactive):
    rows = [destination(comment=f"IBKR#v2#U1:DIVIDEND:{action}", id=action,
                        accountId="moved-destination", isDraft=inactive) for action in ("A1", "A2")]
    ids, comments, pos = read(monkeypatch, rows, dry=False)
    world = World(monkeypatch, report(divs=div_xml(amount="15") +
                                    div_xml(amount="10").replace('actionID="A1"', 'actionID="A2"')))
    assert world.run(ids=ids, comments=comments, pos=pos)[1] is True
    assert world.activities == []


def amount_run(monkeypatch, caplog, rows, xml=None):
    caplog.set_level("INFO")
    ids, comments, positions = read(monkeypatch, rows, dry=False)
    world = World(monkeypatch, xml or report(divs=div_xml(amount="25.00", date="20260715")))
    result = world.run(ids=ids, comments=comments, pos=positions)
    return world, result, [r for r in caplog.records if "Ghostfolio has a dividend" in r.message]


def manual(**changes):
    return destination(comment="manual", date="2026-07-17T00:00:00Z", **changes)


def test_dividend_proximity_amount_equal_gross_logs_info(monkeypatch, caplog):
    world, result, records = amount_run(monkeypatch, caplog, [manual(fee=1)])
    assert world.activities == [] and result[1] is True
    assert [r.levelname for r in records] == ["INFO"]
    assert "amounts agree" in records[0].message
    assert "source fee 0" in records[0].message and "existing fee 1" in records[0].message


def test_dividend_proximity_amount_different_gross_warns_once(monkeypatch, caplog):
    world, result, records = amount_run(monkeypatch, caplog, [manual(unitPrice=1)])
    assert world.activities == [] and result[1] is True
    assert [r.levelname for r in records] == ["WARNING"]
    message = records[0].message
    assert "2026-07-17" in message and "2026-07-15" in message
    assert "source 25.00 USD" in message and "existing 100 USD" in message
    assert "source fee" in message and "add it by hand" in message


def test_dividend_proximity_amount_minor_unit_row_matches_major_source(monkeypatch, caplog):
    row = manual(unitPrice=25, quantity=100, currency="GBp")      # 2500 pence = 25 GBP
    xml = report(divs=div_xml(amount="25.00", date="20260715").replace('currency="USD"', 'currency="GBP"'))
    _, _, records = amount_run(monkeypatch, caplog, [row], xml)
    assert [r.levelname for r in records] == ["INFO"]


def test_dividend_proximity_amount_unsupported_currency_is_not_comparable(monkeypatch, caplog):
    xml = report(divs=div_xml(amount="25.00", date="20260715").replace('currency="USD"', 'currency="XXX"'))
    world, _, records = amount_run(monkeypatch, caplog, [manual(currency="XXX")], xml)
    assert world.activities == []
    assert [r.levelname for r in records] == ["WARNING"]
    assert "source 25.00 XXX" in records[0].message and "amounts agree" not in records[0].message


def test_dividend_proximity_amount_equal_numbers_in_different_currencies_warn(monkeypatch, caplog):
    world, _, records = amount_run(monkeypatch, caplog, [manual(currency="EUR")])
    assert world.activities == []
    assert [r.levelname for r in records] == ["WARNING"]


def test_dividend_proximity_amount_manual_ordinary_next_to_pil_is_skipped_with_warning(monkeypatch, caplog):
    xml = report(divs=div_xml(amount="100.00", date="20260716").replace('actionID="A1"', 'actionID="A2"'))
    manual_row = destination(comment="manual", date="2026-07-15T00:00:00Z")      # ordinary 25
    world, result, records = amount_run(monkeypatch, caplog, [manual_row], xml)
    assert world.activities == [] and result[1] is True
    assert [r.levelname for r in records] == ["WARNING"]


def test_dividend_proximity_amount_readable_report_shows_no_raw_tuple(monkeypatch, caplog):
    from test_dividend_diagnostics import comparison
    findings = comparison(monkeypatch, [manual()])
    absent = findings[0]
    assert absent["proximity"]["matched_date"] == "2026-07-17"
    text = diagnostics.format_historical_dividend_finding(absent, ACC)
    assert "within 3 days of 2026-07-17" in text and "Decimal(" not in text and "('2026" not in text
