"""Offline historical dividend comparisons using synthetic broker/API evidence."""
import json
from decimal import Decimal

import pytest

import ibkr_to_ghostfolio as m
from test_orchestration import ACC, CFG, ISIN_KO, div_xml, report


def destination(**changes):
    row = {"id": "dividend-1", "type": "DIVIDEND", "accountId": ACC,
           "comment": f"dividend#{ISIN_KO}#2026-07-15", "date": "2026-07-15T00:00:00Z",
           "quantity": 100, "unitPrice": 0.25, "fee": 0, "currency": "USD",
           "assetProfile": {"symbol": "KO", "isin": ISIN_KO, "dataSource": "YAHOO", "currency": "USD"}}
    row.update(changes)
    return row


def read(monkeypatch, rows, wire=None, dry=True):
    response = m.requests.Response()
    response.status_code = 200
    response._content = (wire or json.dumps({"activities": rows, "count": len(rows)})).encode()
    calls = []
    monkeypatch.setattr(m.requests, "get", lambda *args, **kwargs: calls.append((args, kwargs)) or response)
    result = m.ghost_get_existing_orders({**CFG, "dry_run": dry})
    assert len(calls) == 1
    return result


def comparison(monkeypatch, rows, xml=None, wire=None):
    _, _, positions = read(monkeypatch, rows, wire)
    source = m.parse_cash_dividends(xml or report(divs=div_xml()))
    return m.historical_dividend_comparison(source, ACC, {}, positions)


def test_historical_diagnostic_coherent_whole_payment(monkeypatch):
    findings = comparison(monkeypatch, [destination()])
    assert len(findings) == 1
    assert findings[0]["category"] == "coherent_single"
    assert findings[0]["activity_ids"] == ["dividend-1"]
    assert findings[0]["source_quantity"] == Decimal(100)
    assert findings[0]["gross_delta"] == findings[0]["fee_delta"] == 0
    assert findings[0]["currency_provenance"] == "activity"


def test_historical_diagnostic_coherent_source_components_consolidated(monkeypatch):
    xml = report(divs=div_xml(amount="15") + div_xml(amount="10").replace('actionID="A1"', 'actionID="A2"'))
    findings = comparison(monkeypatch, [destination()], xml)
    assert findings[0]["category"] == "coherent_single"
    assert findings[0]["quantity"] == Decimal(100)  # never sum component quantities
    assert findings[0]["source_gross"] == Decimal(25)


def test_historical_diagnostic_coherent_no_amount_based_component_partition(monkeypatch):
    xml = report(divs=div_xml(amount="15") + div_xml(amount="10").replace('actionID="A1"', 'actionID="A2"'))
    findings = comparison(monkeypatch, [destination(unitPrice=0.15), destination(id="dividend-2", unitPrice=0.10)], xml)
    assert len(findings) == 1
    assert findings[0]["category"] == "uncertain"
    assert findings[0]["reason"] == "component partition identity not proven"


def test_historical_diagnostic_coherent_retains_json_before_float_decoding(monkeypatch):
    row = destination()
    wire = json.dumps({"activities": [row], "count": 1}).replace('"unitPrice": 0.25', '"unitPrice": 0.250000000000000000001')
    _, _, positions = read(monkeypatch, [row], wire)
    raw = positions["dividend_evidence"][0]
    assert raw["activity"]["unitPrice"] == Decimal("0.250000000000000000001")
    finding = m.historical_dividend_comparison(m.parse_cash_dividends(report(divs=div_xml())), ACC, {}, positions)[0]
    assert finding["gross_delta"] == Decimal("0.000000000000000000100")
    assert finding["category"] == "differences"


def test_historical_diagnostic_coherent_reader_preserves_tuple_and_indexes(monkeypatch):
    rows = [destination(), destination(id="buy-1", type="BUY", quantity=0.1234567890123456789,
                                      comment="IBKR#buy-1"), destination(id="sell-1", type="SELL", quantity=0.02,
                                                                         comment=None)]
    live = read(monkeypatch, rows, dry=False)
    dry = read(monkeypatch, rows)
    assert len(live) == len(dry) == 3
    assert live[:2] == dry[:2]
    assert all(dry[2][key] == value for key, value in live[2].items())
    assert "dividend_evidence" not in live[2]
    assert isinstance(dry[2]["qty"][(ACC, "KO")], float)
    assert len(dry[2]["dividend_evidence"]) == 1


@pytest.mark.parametrize("currency,profile_currency,provenance", [
    ("USD", "EUR", "activity"), (None, "USD", "assetProfile"),
])
def test_historical_diagnostic_coherent_currency_provenance(monkeypatch, currency, profile_currency, provenance):
    row = destination(currency=currency)
    row["assetProfile"]["currency"] = profile_currency
    finding = comparison(monkeypatch, [row])[0]
    assert finding["category"] == "coherent_single"
    assert finding["denomination"] == "USD"
    assert finding["currency_provenance"] == provenance


def test_historical_diagnostic_coherent_legacy_profile_precedence(monkeypatch):
    row = destination(currency=None)
    row["SymbolProfile"] = row.pop("assetProfile")
    finding = comparison(monkeypatch, [row])[0]
    assert finding["category"] == "coherent_single"
    assert finding["currency_provenance"] == "SymbolProfile"
    row["assetProfile"] = {**row["SymbolProfile"], "currency": "EUR"}
    assert comparison(monkeypatch, [row])[0]["category"] == "uncertain"


@pytest.mark.parametrize("currency", ["", "AAA", False])
def test_historical_diagnostic_coherent_invalid_currency_never_falls_back(monkeypatch, currency):
    finding = comparison(monkeypatch, [destination(currency=currency)])[0]
    assert finding["category"] == "uncertain"
    assert finding["reason"] == "missing or unsupported currency context"


def test_historical_diagnostic_coherent_unavailable_wire_is_uncertain(monkeypatch):
    from types import SimpleNamespace
    row = destination()
    monkeypatch.setattr(m.requests, "get", lambda *args, **kwargs: SimpleNamespace(
        status_code=200, raise_for_status=lambda: None, json=lambda: {"activities": [row], "count": 1}))
    _, _, positions = m.ghost_get_existing_orders({**CFG, "dry_run": True})
    finding = m.historical_dividend_comparison(m.parse_cash_dividends(report(divs=div_xml())), ACC, {}, positions)[0]
    assert finding["category"] == "uncertain"
    assert finding["reason"] == "original JSON numeric evidence unavailable"


@pytest.mark.parametrize("currency,price", [("GBP", 0.25), ("GBp", 25)])
def test_historical_diagnostic_coherent_activity_denomination_over_profile(monkeypatch, currency, price):
    xml = report(divs=div_xml(symbol="KO.L").replace('currency="USD"', 'currency="GBP"'))
    row = destination(currency=currency, unitPrice=price)
    row["assetProfile"].update(symbol="KO.L", currency="GBp")
    finding = comparison(monkeypatch, [row], xml)[0]
    assert finding["category"] == "coherent_single"
    assert finding["denomination"] == currency
    assert finding["currency"] == "GBP"
    assert finding["currency_provenance"] == "activity"


def test_historical_diagnostic_coherent_decimal_decode_does_not_add_failures(monkeypatch):
    wire = json.dumps({"activities": [destination()], "count": 1}).replace(
        '"unitPrice": 0.25', '"unitPrice": 1e999999999999999999999999')
    _, comments, pos = read(monkeypatch, [], wire)
    assert comments == {(ACC, f"dividend#{ISIN_KO}#2026-07-15")}
    assert pos["dividend_evidence"][0]["exact_json"] is False


@pytest.mark.parametrize("mutation,error", [("count", "incomplete list"), ("quantity", "redacted"),
                                         ("profile", "invalid asset profile")])
def test_historical_diagnostic_coherent_reader_failures_unchanged(monkeypatch, mutation, error):
    row = destination()
    if mutation == "quantity":
        row["quantity"] = None
    if mutation == "profile":
        row["assetProfile"] = None
    wire = json.dumps({"activities": [row], "count": 2 if mutation == "count" else 1})
    with pytest.raises(RuntimeError, match=error):
        read(monkeypatch, [row], wire)


def test_historical_diagnostic_coherent_account_scoped(monkeypatch):
    assert comparison(monkeypatch, [destination(accountId="other")])[0]["category"] == "absent"


@pytest.mark.parametrize("changes", [{"isDraft": True}, {"date": "2026-07-16T00:00:00Z"},
                                     {"comment": "dividend#KO#2026-07-15"}])
def test_historical_diagnostic_coherent_weak_identity_never_certifies(monkeypatch, changes):
    assert all(finding["category"] != "coherent_single"
               for finding in comparison(monkeypatch, [destination(**changes)]))
