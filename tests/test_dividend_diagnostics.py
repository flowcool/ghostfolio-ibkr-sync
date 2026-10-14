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


def representations(monkeypatch, rows, xml=None, identities=None, wire=None, reverse=False):
    """Supply independently known synthetic identities in internal evidence.

    These annotations are not API activity fields or a new public comment format.
    A real reader does not claim component/partition identity from amounts.
    """
    _, _, positions = read(monkeypatch, rows, wire)
    source = m.parse_cash_dividends(xml or report(divs=div_xml()))
    for item, identity in zip(positions["dividend_evidence"], identities or []):
        item.update(identity)
    return m.historical_dividend_comparison(list(reversed(source)) if reverse else source,
                                          ACC, {}, positions)


def component(action):
    return ("broker-account", "1", "USD", action, "20260701")


def ordinary_bonus():
    return report(divs=div_xml(amount="15") + div_xml(amount="10").replace('actionID="A1"', 'actionID="A2"'))


def test_representations_ordinary_bonus_complete_components(monkeypatch):
    finding = representations(monkeypatch,
        [destination(unitPrice=0.15), destination(id="bonus", unitPrice=0.1)], ordinary_bonus(),
        [{"representation": "components", "component": component("A1")},
         {"representation": "components", "component": component("A2")}])[0]
    assert finding["category"] == "coherent_components"
    assert finding["source_quantity"] == 100
    representation = finding["representations"][0]
    assert representation["quantity_deltas"] == [0, 0]  # not summed to 200
    assert representation["gross_delta"] == representation["fee_delta"] == 0
    assert len(representation["component_deltas"]) == 2


def test_representations_split_pil_is_one_component(monkeypatch):
    pil = div_xml(amount="10").replace('type="Dividends"', 'type="Payment In Lieu Of Dividends"')
    finding = representations(monkeypatch, [destination()], report(divs=div_xml(amount="15") + pil),
                             [{"representation": "payment", "component": component("A1")}])[0]
    assert finding["category"] == "coherent_components"
    assert finding["source_gross"] == 25
    assert finding["representations"][0]["component_deltas"][0]["gross_delta"] == 0


def test_representations_competing_complete_sets_with_discrepancies(monkeypatch):
    rows = [destination(id="whole", unitPrice=0.26), destination(id="ordinary", unitPrice=0.15),
            destination(id="bonus", unitPrice=0.1), destination(id="whole-2", quantity=99)]
    identities = [{"representation": "whole"},
                  {"representation": "split", "component": component("A1")},
                  {"representation": "split", "component": component("A2")},
                  {"representation": "other-whole"}]
    finding = representations(monkeypatch, rows, ordinary_bonus(), identities)[0]
    assert finding["category"] == "probable_repetition"
    first, second, third = finding["representations"]
    assert first["gross_delta"] == 1 and first["coherent"] is False
    assert second["coherent"] is True
    assert third["quantity_deltas"] == [-1] and third["gross_delta"] == Decimal("-0.25")
    assert third["coherent"] is False


def test_representations_component_vector_cannot_hide_offsetting_deltas(monkeypatch):
    finding = representations(monkeypatch,
        [destination(unitPrice=0.16), destination(id="bonus", unitPrice=0.09)], ordinary_bonus(),
        [{"representation": "split", "component": component("A1")},
         {"representation": "split", "component": component("A2")}])[0]
    assert finding["category"] == "differences"
    assert finding["gross_delta"] == 0
    assert [part["gross_delta"] for part in finding["representations"][0]["component_deltas"]] == [1, -1]


@pytest.mark.parametrize("identities", [
    [{"representation": "split", "component": component("A1")}],
    [{"representation": "split", "component": component("A1")},
     {"representation": "split", "component": component("A1")}],
    [{"representation": "split", "component": component("A1")},
     {"representation": "split", "component": component("unknown")}],
])
def test_representations_incomplete_or_duplicate_components_stay_uncertain(monkeypatch, identities):
    rows = [destination(id=f"row-{index}", unitPrice=0.125) for index in range(len(identities))]
    finding = representations(monkeypatch, rows, ordinary_bonus(), identities)[0]
    assert finding["category"] == "uncertain"
    assert finding["reason"] == "incomplete or conflicting component coverage"
    assert "representations" not in finding


def test_representations_without_identity_never_search_amount_subsets(monkeypatch):
    rows = [destination(id="ordinary", unitPrice=0.15), destination(id="bonus", unitPrice=0.1),
            destination(id="whole", unitPrice=0.25)]
    finding = representations(monkeypatch, rows, ordinary_bonus())[0]
    assert finding["category"] == "uncertain"
    assert finding["reason"] == "component partition identity not proven"


@pytest.mark.parametrize("reverse", [False, True])
def test_representations_contested_ownership_in_either_order(monkeypatch, reverse):
    # Same canonical reference, different source securities: neither group owns
    # the destination exclusively, even though the first security could match.
    other = div_xml().replace('conid="1"', 'conid="2"').replace('currency="USD"', 'currency="EUR"')
    # Supply separate synthetic source groups with the same canonical reference
    # to exercise globally contested ownership.
    source = [m.parse_cash_dividends(report(divs=part))[0] for part in (div_xml(), other)]
    _, _, positions = read(monkeypatch, [destination()])
    findings = m.historical_dividend_comparison(source[::-1] if reverse else source, ACC, {}, positions)
    assert len(findings) == 2
    assert all(finding["category"] == "uncertain" for finding in findings)
    assert all(finding["reason"] == "contested destination ownership" for finding in findings)


def test_representations_globally_unique_distinct_groups(monkeypatch):
    xml = report(divs=div_xml() + div_xml(date="20260716"))
    rows = [destination(), destination(id="next-day", comment=f"dividend#{ISIN_KO}#2026-07-16",
                                      date="2026-07-16T00:00:00Z")]
    findings = representations(monkeypatch, rows, xml)
    assert [finding["category"] for finding in findings] == ["coherent_single", "coherent_single"]
    assert [finding["activity_ids"] for finding in findings] == [["dividend-1"], ["next-day"]]


def test_representations_fractional_quantity_and_sub_float_signed_deltas(monkeypatch):
    xml = report(divs=div_xml(amount="0.625")).replace('quantity="100"', 'quantity="2.5"')
    row = destination(quantity=2.5)
    wire = json.dumps({"activities": [row], "count": 1}).replace(
        '"unitPrice": 0.25', '"unitPrice": 0.249999999999999999999')
    finding = representations(monkeypatch, [row], xml, wire=wire)[0]
    assert finding["category"] == "differences"
    assert finding["quantity_delta"] == 0
    assert finding["gross_delta"] == Decimal("-0.0000000000000000000025")
    row["quantity"] = 2.75
    finding = representations(monkeypatch, [row], xml)[0]
    assert finding["quantity_delta"] == Decimal("0.25")
    assert finding["gross_delta"] == Decimal("0.0625")


@pytest.mark.parametrize("tax,refund,fee,expected_fee,delta", [
    ("-4", "1", 2, 3, -1), ("-1", "4", 1, 0, 1),
])
def test_representations_fee_convention_and_signed_tax_refunds(monkeypatch, tax, refund, fee, expected_fee, delta):
    taxes = "".join(div_xml(amount=amount).replace('type="Dividends"', 'type="Withholding Tax"')
                    for amount in (tax, refund))
    finding = representations(monkeypatch, [destination(fee=fee)], report(divs=div_xml() + taxes))[0]
    assert finding["source_fee"] == expected_fee
    assert finding["fee_delta"] == delta
    assert finding["signed_tax_total"] == Decimal(tax) + Decimal(refund)
    assert [row["amount"] for row in finding["signed_tax_rows"]] == [tax, refund]


@pytest.mark.parametrize("currency,profile_currency,price,provenance", [
    (None, "USD", 0.25, "assetProfile"), ("GBP", "GBp", 0.25, "activity"),
    ("GBp", "GBP", 25, "activity"),
])
def test_representations_currency_provenance_and_denomination(monkeypatch, currency, profile_currency, price, provenance):
    broker_currency = "USD" if currency is None else "GBP"
    xml = report(divs=div_xml().replace('currency="USD"', f'currency="{broker_currency}"'))
    row = destination(currency=currency, unitPrice=price)
    row["assetProfile"]["currency"] = profile_currency
    finding = representations(monkeypatch, [row], xml)[0]
    assert finding["category"] == "coherent_single"
    assert finding["currency_provenance"] == provenance
    assert finding["denomination"] == (currency or profile_currency)
    assert finding["gross_delta"] == 0


def test_representations_unsupported_currency_context_stays_uncertain(monkeypatch):
    finding = representations(monkeypatch, [destination(currency="AAA")])[0]
    assert finding["category"] == "uncertain"
    assert finding["reason"] == "missing or unsupported currency context"


@pytest.mark.parametrize("changes", [
    {"comment": "legacy KO dividend"}, {"comment": "dividend#KO#2026-07-15"},
    {"date": "2026-07-14T22:00:00Z"}, {"date": "2026-07-15T00:00:00+02:00"},
    {"isDraft": True}, {"isExcluded": True},
    {"assetProfile": {"symbol": "KO", "isin": ISIN_KO, "dataSource": "MANUAL"}},
    {"assetProfile": {"symbol": "PEP", "isin": ISIN_KO, "dataSource": "YAHOO"}},
])
def test_evidence_weak_history_is_accounted_without_certification(monkeypatch, changes):
    findings = comparison(monkeypatch, [destination(**changes)])
    assert sum(finding["source"] is not None for finding in findings) == 1
    assert any("dividend-1" in finding["activity_ids"] for finding in findings)
    assert all(finding["category"] in ("absent", "uncertain") for finding in findings)
    assert all("representations" not in finding for finding in findings)


@pytest.mark.parametrize("mode", ["old", "missing", "empty", "conflict", "short"])
def test_evidence_incomplete_source_quantity_is_uncertain(monkeypatch, mode):
    from test_orchestration import structured_input_xml
    finding = comparison(monkeypatch, [destination()], structured_input_xml(mode))[0]
    assert finding["category"] == "uncertain"
    assert "source quantity" in finding["reason"]


@pytest.mark.parametrize("bounds,expected", [
    ('fromDate="20260701" toDate="20260731"', ("2026-07-01", "2026-07-31")),
    ("", None), ('fromDate="bad" toDate="20260731"', None),
    ('fromDate="2026071" toDate="20260731"', None),
    ('fromDate="20260701" toDate="2026073"', None),
    ('fromDate="２０２６０７０１" toDate="20260731"', None),
    ('fromDate="20260801" toDate="20260731"', None),
])
def test_evidence_window_requires_explicit_valid_bounds(bounds, expected):
    xml = report().replace("<FlexStatement>", f"<FlexStatement {bounds}>")
    assert m.historical_dividend_report_window(xml) == expected


def test_evidence_conflicting_statement_windows_are_not_inferred():
    xml = ('<R><FlexStatement fromDate="20260701" toDate="20260731"/>'
           '<FlexStatement fromDate="20260801" toDate="20260831"/></R>')
    assert m.historical_dividend_report_window(xml) is None


@pytest.mark.parametrize("window,category", [(None, "uncertain"),
    (("2026-07-01", "2026-07-31"), "outside_window")])
def test_evidence_unmatched_older_history_and_empty_report(monkeypatch, window, category):
    _, _, pos = read(monkeypatch, [destination(date="2025-07-15T00:00:00Z")])
    findings = m.historical_dividend_comparison([], ACC, {}, pos, window)
    assert len(findings) == 1
    assert findings[0]["category"] == category
    assert findings[0]["source"] is None and findings[0]["activity_ids"] == ["dividend-1"]


def test_evidence_absent_destination_and_info_coverage(monkeypatch, caplog):
    import logging
    findings = comparison(monkeypatch, [])
    assert len(findings) == 1 and findings[0]["category"] == "absent"
    caplog.set_level(logging.INFO)
    m.log_historical_dividend_comparison(findings, ACC)
    assert "source_groups=1 unmatched_destination=0" in caplog.text
    assert findings[0]["source"] in caplog.text and "no canonical destination identity" in caplog.text


def identity(findings):
    return {check["check"]: check for check in findings[0]["identity_checks"]}


def test_historical_diagnostic_identity_six_checks_expose_expected_observed(monkeypatch):
    finding = comparison(monkeypatch, [destination()])[0]
    checks = identity([finding])
    assert list(checks) == ["active", "id", "data_source", "symbol", "date", "isin"]
    assert all(check["status"] == "pass" for check in checks.values())
    assert checks["date"]["expected"] == "2026-07-15"
    assert checks["date"]["observed"] == {"utc": "2026-07-15", "local": "2026-07-15"}
    assert checks["isin"]["expected"] == checks["isin"]["observed"] == ISIN_KO
    assert finding["category"] == "coherent_single"


@pytest.mark.parametrize("changes,failed,observed", [
    ({"isDraft": True}, "active", False),
    ({"id": ""}, "id", ""),
    ({"assetProfile": {"symbol": "KO", "isin": ISIN_KO, "dataSource": "MANUAL"}}, "data_source", "MANUAL"),
    ({"assetProfile": {"symbol": "PEP", "isin": ISIN_KO, "dataSource": "YAHOO"}}, "symbol", "PEP"),
    ({"date": "2026-07-16T00:00:00Z"}, "date", {"utc": "2026-07-16", "local": "2026-07-16"}),
    ({"assetProfile": {"symbol": "KO", "isin": "US0000000002", "dataSource": "YAHOO"}}, "isin", "US0000000002"),
])
def test_historical_diagnostic_identity_each_check_fails_alone(monkeypatch, changes, failed, observed):
    finding = comparison(monkeypatch, [destination(**changes)])[0]
    checks = identity([finding])
    assert [name for name, check in checks.items() if check["status"] == "fail"] == [failed]
    assert checks[failed]["observed"] == observed
    assert finding["category"] == "uncertain" and "representations" not in finding


@pytest.mark.parametrize("tz,stored,expected_local", [
    ("Europe/Paris", "2026-01-14T23:00:00.000Z", "2026-01-15"),  # winter, UTC+1
    ("Europe/Paris", "2026-07-14T22:00:00.000Z", "2026-07-15"),  # summer, UTC+2
])
def test_historical_diagnostic_identity_paris_local_date(monkeypatch, tz, stored, expected_local):
    monkeypatch.setenv("TZ", tz)
    comment = f"dividend#{ISIN_KO}#{expected_local}"
    xml = report(divs=div_xml().replace("20260715", expected_local.replace("-", "")))
    finding = comparison(monkeypatch, [destination(date=stored, comment=comment)], xml)[0]
    date = identity([finding])["date"]
    assert date["status"] == "pass" and date["observed"]["local"] == expected_local
    assert date["observed"]["utc"] != expected_local
    assert finding["category"] == "coherent_single"


def test_historical_diagnostic_identity_utc_instant_crossing_paris_midnight(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Paris")
    date = identity(comparison(monkeypatch, [destination(date="2026-07-15T00:00:00Z")]))["date"]
    assert date["status"] == "pass"  # 02:00 Paris, same calendar day
    date = identity(comparison(monkeypatch, [destination(date="2026-07-15T23:00:00Z")]))["date"]
    assert date["status"] == "fail" and date["observed"] == {"utc": "2026-07-15", "local": "2026-07-16"}


@pytest.mark.parametrize("profile_isin", [None, ""])
def test_historical_diagnostic_identity_absent_isin_permits_amount_comparison(monkeypatch, profile_isin):
    profile = {"symbol": "KO", "dataSource": "YAHOO", "currency": "USD"}
    if profile_isin is not None:
        profile["isin"] = profile_isin
    finding = comparison(monkeypatch, [destination(assetProfile=profile)])[0]
    isin = identity([finding])["isin"]
    assert isin["status"] == "unavailable" and isin["expected"] == ISIN_KO and isin["observed"] is None
    assert finding["category"] == "coherent_single"
    assert finding["gross_delta"] == finding["fee_delta"] == 0


def test_historical_diagnostic_identity_conflicting_isin_blocks_amount_comparison(monkeypatch):
    profile = {"symbol": "KO", "isin": "US0000000002", "dataSource": "YAHOO", "currency": "USD"}
    finding = comparison(monkeypatch, [destination(assetProfile=profile)])[0]
    assert identity([finding])["isin"]["status"] == "fail"
    assert finding["category"] == "uncertain" and "gross_delta" not in finding


@pytest.mark.parametrize("tz,reason", [("", "TZ is missing"), ("Not/AZone", "TZ is not a valid IANA timezone")])
def test_historical_diagnostic_identity_invalid_tz_makes_date_unavailable(monkeypatch, tz, reason):
    monkeypatch.setenv("TZ", tz)
    finding = comparison(monkeypatch, [destination()])[0]
    date = identity([finding])["date"]
    assert date["status"] == "unavailable" and date["reason"] == f"{reason}; forced preview"
    assert date["observed"] == {"utc": "2026-07-15", "local": None}
    assert not any(check["status"] == "fail" for check in finding["identity_checks"])
