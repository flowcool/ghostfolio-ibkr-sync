"""Offline proximity index: connector-comment rows are excluded, exact identity still dedups."""
import ibkr_to_ghostfolio as m
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
    text = m.format_historical_dividend_finding(absent, ACC)
    assert "within 3 days of 2026-07-17" in text and "Decimal(" not in text and "('2026" not in text
