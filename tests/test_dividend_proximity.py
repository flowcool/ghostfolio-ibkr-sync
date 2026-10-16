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
