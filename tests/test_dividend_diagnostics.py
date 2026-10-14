"""Offline historical dividend comparisons using synthetic broker/API evidence."""
import re
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
    assert "1 to check, 0 informational, 0 noise" in caplog.text


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


def test_historical_diagnostic_actionable_anomaly_block_and_failed_check_counts(monkeypatch, caplog):
    import logging
    profile = {"symbol": "PEP", "isin": ISIN_KO, "dataSource": "YAHOO", "currency": "USD"}
    findings = comparison(monkeypatch, [destination(date="2026-07-16T00:00:00Z", assetProfile=profile)])
    caplog.set_level(logging.INFO)
    m.log_historical_dividend_comparison(findings, ACC)
    text = caplog.text
    assert "Dividend to check: uncertain" in text
    assert f"Security: KO (ISIN {ISIN_KO}), dividend date 2026-07-15" in text
    assert "Identity check symbol fail for activity dividend-1: expected KO, found PEP" in text
    assert "Identity check date fail" in text and "UTC date 2026-07-16" in text and "local date" in text
    assert "Ghostfolio: activity dividend-1 (PEP) on 2026-07-16" in text
    assert "quantity 100, gross 25.00 USD, fee 0 USD" in text and "Nothing was written." in text
    assert "failed_checks={'date': 1, 'symbol': 1}" in text


def test_historical_diagnostic_actionable_outside_window_shows_destination_values(monkeypatch, caplog):
    import logging
    _, _, pos = read(monkeypatch, [destination(date="2025-07-15T00:00:00Z")])
    findings = m.historical_dividend_comparison([], ACC, {}, pos, ("2026-07-01", "2026-07-31"))
    caplog.set_level(logging.INFO)
    m.log_historical_dividend_comparison(findings, ACC)
    assert "Ghostfolio: activity" not in caplog.text  # outside window logs at DEBUG only
    caplog.set_level(logging.DEBUG)
    m.log_historical_dividend_comparison(findings, ACC)
    assert "Dividend outside report window" in caplog.text
    assert "Ghostfolio: activity dividend-1 (KO) on 2025-07-15" in caplog.text
    assert "quantity 100, gross 25.00 USD" in caplog.text
    assert findings[0]["source"] is None


def test_historical_diagnostic_actionable_proximity_skip_is_explained_not_certified(monkeypatch, caplog):
    import logging
    weak = destination(comment="legacy KO dividend", date="2026-07-17T00:00:00Z")
    findings = comparison(monkeypatch, [weak])
    absent = findings[0]
    assert absent["category"] == "absent" and "representations" not in absent
    assert absent["proximity"]["matched_date"] == "2026-07-17"
    assert [item["activity_id"] for item in absent["proximity"]["candidates"]] == ["dividend-1"]
    caplog.set_level(logging.INFO)
    m.log_historical_dividend_comparison(findings, ACC)
    assert "skipped by proximity" in caplog.text
    assert "Weak candidate: activity dividend-1 (comment legacy KO dividend, 2026-07-17)" in caplog.text
    assert "quantity 100, gross 25.00 USD" in caplog.text


def test_historical_diagnostic_actionable_no_proximity_note_beyond_window(monkeypatch):
    far = destination(comment="legacy", date="2026-07-25T00:00:00Z")
    absent = comparison(monkeypatch, [far])[0]
    assert absent["category"] == "absent" and "proximity" not in absent
    assert "skipped by proximity" not in absent["reason"]


def test_historical_diagnostic_actionable_levels_and_privacy(monkeypatch, caplog):
    import logging
    coherent = comparison(monkeypatch, [destination()])
    caplog.set_level(logging.INFO)
    m.log_historical_dividend_comparison(coherent, ACC)
    assert "Dividend coherent" not in caplog.text  # coherent detail is DEBUG only
    assert "failed_checks={}" in caplog.text
    caplog.clear()
    caplog.set_level(logging.DEBUG)
    m.log_historical_dividend_comparison(coherent, ACC)
    assert "Dividend coherent: coherent" in caplog.text
    assert CFG["ghost_host"] not in caplog.text


def test_historical_diagnostic_actionable_proximity_lists_every_weak_candidate_with_local_date(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Paris")
    rows = [destination(id="near-1", comment="legacy", date="2026-07-16T22:00:00Z"),
            destination(id="near-2", comment="legacy", date="2026-07-18T00:00:00Z"),
            destination(id="far", comment="legacy", date="2026-07-25T00:00:00Z")]
    proximity = comparison(monkeypatch, rows)[0]["proximity"]
    assert [item["activity_id"] for item in proximity["candidates"]] == ["near-1", "near-2"]
    assert proximity["candidates"][0]["utc_date"] == "2026-07-16"
    assert proximity["candidates"][0]["local_date"] == "2026-07-17"


def test_historical_diagnostic_actionable_source_values_survive_failed_identity(monkeypatch):
    profile = {"symbol": "PEP", "isin": ISIN_KO, "dataSource": "YAHOO", "currency": "USD"}
    finding = comparison(monkeypatch, [destination(assetProfile=profile)])[0]
    assert finding["category"] == "uncertain"
    assert (finding["source_quantity"], finding["source_gross"], finding["source_fee"],
            finding["source_currency"]) == (Decimal(100), Decimal("25.00"), Decimal(0), "USD")
    text = m.format_historical_dividend_finding(finding, ACC)
    assert "IBKR: quantity 100, gross 25.00 USD, fee 0 USD" in text


def test_historical_diagnostic_actionable_destination_before_duplicate_identity_early_return(monkeypatch):
    finding = comparison(monkeypatch, [destination(id="dup"), destination(id="dup")])[0]
    assert finding["reason"] == "duplicate destination activity identity"
    assert [item["activity_id"] for item in finding["destination"]] == ["dup", "dup"]
    assert all(item["utc_date"] == "2026-07-15" for item in finding["destination"])


def skip_cause(monkeypatch, rows, xml=None):
    _, comments, positions = read(monkeypatch, rows)
    source = m.parse_cash_dividends(xml or report(divs=div_xml()))
    return m.historical_dividend_comparison(source, ACC, {}, positions, None, comments)[0]


def test_historical_diagnostic_skip_cause_old_symbol_comment_beats_proximity(monkeypatch, caplog):
    import logging
    carrier = destination(id="old", comment="dividend#KO#2026-07-15", date="2026-07-17T00:00:00Z")
    finding = skip_cause(monkeypatch, [carrier])
    assert finding["category"] == "absent" and "proximity" not in finding
    assert "skipped by historical comment" in finding["reason"]
    assert [(item["activity_id"], item["active"]) for item in finding["historical_comment"]] == [("old", True)]
    caplog.set_level(logging.INFO)
    m.log_historical_dividend_comparison([finding], ACC)
    assert "Skipped by historical comment: activity old" in caplog.text
    assert "Skipped by proximity" not in caplog.text
    assert "quantity 100, gross 25.00 USD" in caplog.text


def test_historical_diagnostic_skip_cause_inactive_carrier(monkeypatch):
    carrier = destination(id="old", comment="dividend#KO#2026-07-15", date="2026-07-17T00:00:00Z",
                          isDraft=True)
    finding = skip_cause(monkeypatch, [carrier])
    assert finding["category"] == "absent"
    assert "skipped by historical comment" in finding["reason"]
    assert [(item["activity_id"], item["active"]) for item in finding["historical_comment"]] == [("old", False)]


def test_historical_diagnostic_skip_cause_proximity_only(monkeypatch):
    finding = skip_cause(monkeypatch, [destination(comment="legacy", date="2026-07-17T00:00:00Z")])
    assert finding["category"] == "absent" and "historical_comment" not in finding
    assert "skipped by proximity" in finding["reason"]


def test_historical_diagnostic_skip_cause_other_account_comment_ignored(monkeypatch):
    carrier = destination(comment="dividend#KO#2026-07-15", accountId="other-account",
                          date="2026-07-25T00:00:00Z")
    finding = skip_cause(monkeypatch, [carrier])
    assert "historical_comment" not in finding and "proximity" not in finding


def currency_finding(monkeypatch, rows, xml=None):
    return comparison(monkeypatch, rows, xml)[0]


def test_historical_diagnostic_skip_cause_unsupported_destination_currency(monkeypatch):
    finding = currency_finding(monkeypatch, [destination(currency="KRW")])
    assert finding["category"] == "uncertain"
    assert finding["reason"] == "missing or unsupported currency context"
    assert finding["currency_context"] == {"source": "USD", "destination": ["KRW"], "provenance": ["activity"]}
    assert "Currency: IBKR USD, Ghostfolio KRW (from activity)" in \
        m.format_historical_dividend_finding(finding, ACC)


def test_historical_diagnostic_skip_cause_missing_destination_currency(monkeypatch):
    row = destination()
    del row["currency"]
    del row["assetProfile"]["currency"]
    finding = currency_finding(monkeypatch, [row])
    assert finding["reason"] == "missing or unsupported currency context"
    assert finding["currency_context"]["destination"] == [None]


def test_historical_diagnostic_skip_cause_conflicting_currency(monkeypatch):
    finding = currency_finding(monkeypatch, [destination(currency="EUR")])
    assert finding["reason"] == "missing, conflicting or unsupported source money evidence"
    assert finding["currency_context"] == {"source": "USD", "destination": ["EUR"], "provenance": ["activity"]}


def test_historical_diagnostic_skip_cause_unsupported_source_currency(monkeypatch):
    finding = currency_finding(monkeypatch, [destination(currency="KRW")],
                               xml=report(divs=div_xml().replace('currency="USD"', 'currency="KRW"')))
    assert finding["category"] == "uncertain"
    assert finding["currency_context"]["source"] == "KRW"
    assert "Currency: IBKR KRW, Ghostfolio KRW" in m.format_historical_dividend_finding(finding, ACC)


def delta_wire(row, price):
    return json.dumps({"activities": [row], "count": 1}).replace(
        '"unitPrice": 0.25', f'"unitPrice": {price}')


@pytest.mark.parametrize("currency,amount,price,fee,quantity,expected", [
    ("USD", "25.00", "0.25", 0, 100, "none"),
    ("USD", "25.00", "0.250001", 0, 100, "noise"),
    ("USD", "25.00", "0.2549", 0, 100, "other"),
    ("USD", "25.00", "0.2501", 0, 100, "minimal"),
    ("EUR", "25.00", "0.2501", 0, 100, "minimal"),
    ("EUR", "25.00", "0.2499", 0, 100, "minimal"),
    ("USD", "25.00", "0.25", 0.004, 100, "noise"),
    ("USD", "25.00", "0.25", 0.01, 100, "minimal"),
    ("USD", "25.00", "0.25", 0.02, 100, "other"),
    ("USD", "25.00", "0.2501", 0, 101, "quantity"),
    ("USD", "25.00", "0.25", 0, 100.000000000001, "quantity"),
    ("JPY", "2500", "25.004", 0, 100, "noise"),
    ("JPY", "2500", "25.005", 0, 100, "other"),
    ("JPY", "2500", "25.01", 0, 100, "minimal"),
    ("JPY", "2500", "25.02", 0, 100, "other"),
])
def test_dividend_readable_classes_deltas(monkeypatch, currency, amount, price, fee, quantity, expected):
    xml = report(divs=div_xml(amount=amount).replace('currency="USD"', f'currency="{currency}"'))
    row = destination(currency=currency, fee=fee, quantity=quantity, unitPrice=25 if currency == "JPY" else 0.25)
    row["assetProfile"]["currency"] = currency
    wire = json.dumps({"activities": [row], "count": 1}).replace(
        f'"unitPrice": {row["unitPrice"]}', f'"unitPrice": {price}', 1)
    _, _, positions = read(monkeypatch, [row], wire)
    source = m.parse_cash_dividends(xml)
    finding = m.historical_dividend_comparison(source, ACC, {}, positions)[0]
    assert finding["delta_class"] == expected


def test_dividend_readable_classes_noise_stays_counted_and_visible(monkeypatch):
    row = destination(unitPrice=0.25)
    finding = comparison(monkeypatch, [row], wire=delta_wire(row, "0.250001"))[0]
    assert finding["delta_class"] == "noise"
    assert finding["category"] == "differences"
    assert finding["gross_delta"] == Decimal("0.0001")


def test_dividend_readable_classes_strongest_class_wins():
    classify = m.classify_dividend_deltas
    zero = Decimal(0)
    assert classify("USD", [zero], [Decimal("0.001")], [Decimal("0.01")]) == "minimal"
    assert classify("USD", [zero], [Decimal("0.01")], [Decimal("0.5")]) == "other"
    assert classify("USD", [Decimal("1")], [Decimal("0.001")], [zero]) == "quantity"
    assert classify("JPY", [zero], [Decimal("0.4")], [zero]) == "noise"


def readable(monkeypatch, rows, comments=(), xml=None):
    _, _, positions = read(monkeypatch, rows)
    source = m.parse_cash_dividends(xml or report(divs=div_xml()))
    return m.historical_dividend_comparison(source, ACC, {}, positions, existing_dividend_comments=set(comments))


def test_dividend_readable_pairs_probable_duplicate(monkeypatch):
    group = destination(unitPrice=0.2501)
    twin = destination(id="dividend-2", comment="legacy KO dividend", quantity=50, unitPrice=0.25)
    findings = readable(monkeypatch, [group, twin])
    by_source = {f["source"] is None: f for f in findings}
    assert by_source[False]["readable"]["label"] == "minimal difference, cause unknown"
    assert by_source[False]["readable"]["related"] == ["dividend-2"]
    legacy = by_source[True]
    assert legacy["category"] == "uncertain"
    assert legacy["readable"]["class"] == "to_check" and legacy["readable"]["label"] == "probable duplicate"


def test_dividend_readable_pairs_legacy_row_of_another_day_is_not_duplicate(monkeypatch):
    twin = destination(id="dividend-2", comment="legacy KO dividend", date="2026-07-16T00:00:00Z")
    findings = readable(monkeypatch, [destination(), twin])
    legacy = [f for f in findings if f["source"] is None][0]
    assert legacy["readable"]["label"] == "uncertain" and legacy["readable"]["class"] == "to_check"


@pytest.mark.parametrize("prices,klass", [((0.125, 0.125), "information"), ((0.125, 0.126), "to_check")])
def test_dividend_readable_pairs_equal_total_split(monkeypatch, prices, klass):
    rows = [destination(id=f"dividend-{i}", quantity=100, unitPrice=price)
            for i, price in enumerate(prices, 1)]
    finding = readable(monkeypatch, rows)[0]
    assert finding["category"] == "uncertain"
    assert finding["readable"]["class"] == klass
    if klass == "information":
        assert finding["readable"]["label"] == "total equal to IBKR, split over 2 rows"
        assert "proven" not in finding["readable"]["label"]


def test_dividend_readable_pairs_absent_with_outside_coverage_twin(monkeypatch):
    carrier = destination(id="dividend-9", comment="dividend#KO#2026-07-15")
    findings = readable(monkeypatch, [carrier], comments=[(ACC, "dividend#KO#2026-07-15")])
    absent, outside = findings[0], findings[1]
    assert absent["category"] == "absent" and outside["category"] == "uncertain"
    assert absent["readable"]["class"] == outside["readable"]["class"] == "information"
    assert absent["readable"]["related"] == ["dividend-9"]
    assert outside["readable"]["related"] == [absent["source"]]


def test_dividend_readable_pairs_twin_with_other_amount_is_not_paired(monkeypatch):
    carrier = destination(id="dividend-9", comment="dividend#KO#2026-07-15", unitPrice=0.26)
    findings = readable(monkeypatch, [carrier], comments=[(ACC, "dividend#KO#2026-07-15")])
    assert findings[0]["readable"]["class"] == "to_check"
    assert findings[1]["readable"]["class"] == "to_check"


def test_dividend_readable_pairs_unpaired_absent_is_to_check(monkeypatch):
    finding = readable(monkeypatch, [])[0]
    assert finding["category"] == "absent"
    assert finding["readable"]["class"] == "to_check"
    assert finding["readable"]["label"] == "possibly missing in Ghostfolio"


def test_dividend_readable_pairs_other_classes_and_catch_all(monkeypatch):
    coherent = readable(monkeypatch, [destination()])[0]
    assert coherent["readable"]["class"] == "coherent"
    old = destination(date="2025-07-15T00:00:00Z")
    _, _, positions = read(monkeypatch, [old])
    window = m.historical_dividend_comparison([], ACC, {}, positions, ("2026-07-01", "2026-07-31"))[0]
    assert window["readable"]["class"] == "outside_window"
    krw = readable(monkeypatch, [destination(currency="KRW")],
                   xml=report(divs=div_xml().replace('currency="USD"', 'currency="KRW"')))[0]
    assert krw["readable"]["class"] == "information" and krw["readable"]["label"] == "unsupported currency"
    missing = readable(monkeypatch, [destination(currency=None, assetProfile={
        "symbol": "KO", "isin": ISIN_KO, "dataSource": "YAHOO"})])[0]
    assert missing["readable"]["class"] == "to_check" and missing["readable"]["reason"]
    far = readable(monkeypatch, [destination(quantity=101)])[0]
    assert far["readable"]["label"] == "quantity difference"
    noise = readable(monkeypatch, [destination(unitPrice=0.250001)])[0]
    assert noise["readable"]["class"] == "noise"


def test_dividend_readable_pairs_equal_total_needs_accepted_identity(monkeypatch):
    rows = [destination(id=f"dividend-{i}", unitPrice=0.125, isDraft=True) for i in (1, 2)]
    finding = readable(monkeypatch, rows)[0]
    assert finding["category"] == "uncertain"
    assert finding["readable"]["class"] == "to_check" and finding["readable"]["label"] == "uncertain"


def report_text(findings, caplog, level="INFO"):
    import logging
    caplog.clear()
    caplog.set_level(getattr(logging, level))
    m.log_historical_dividend_comparison(findings, ACC)
    return caplog.text


def assert_plain(text):
    assert "Decimal(" not in text and "[" not in text.replace("[DRY RUN]", "")
    assert not re.search(r"\d[eE][-+]?\d", text)


def test_dividend_readable_report_quantity_difference_with_two_legacy_twins(monkeypatch, caplog):
    rows = [destination(quantity=101),
            destination(id="dividend-2", comment="legacy KO dividend"),
            destination(id="dividend-3", comment="legacy KO dividend 2")]
    findings = readable(monkeypatch, rows)
    group = [f for f in findings if f["source"] is not None][0]
    twin = [f for f in findings if f["source"] is None][0]
    block = m.format_historical_dividend_finding(group, ACC)
    assert "Dividend to check: quantity difference" in block
    assert "IBKR: quantity 100, gross 25.00 USD, fee 0 USD" in block
    assert "Ghostfolio: activity dividend-1 (KO) on 2026-07-15, quantity 101, gross 25.25 USD" in block
    assert "Difference (Ghostfolio minus IBKR): quantity +1" in block
    assert "Probable duplicates" in block and "dividend-2, dividend-3" in block
    assert "Action:" in block and block.endswith("Nothing was written.")
    twin_block = m.format_historical_dividend_finding(twin, ACC)
    assert "This row looks like a duplicate" in twin_block and "Nothing was written." in twin_block
    assert_plain(block + twin_block)
    text = report_text(findings, caplog)
    assert "3 to check, 0 informational, 0 noise" in text
    assert text.index("to check, 0 informational") < text.index("Dividend to check: quantity difference")


def test_dividend_readable_report_plain_decimals_without_exponent(monkeypatch, caplog):
    row = destination(unitPrice=0.25, quantity=100.0000001)
    findings = readable(monkeypatch, [row])
    block = m.format_historical_dividend_finding(findings[0], ACC)
    assert "quantity +0.0000001" in block
    assert_plain(block)
    assert m._plain(Decimal("1E-7")) == "0.0000001" and m._plain(Decimal("1E+3")) == "1000"
    assert m._plain(0.0000001) == "0.0000001"


def test_dividend_readable_report_levels_and_summary_order(monkeypatch, caplog):
    info = [destination(id=f"dividend-{i}", unitPrice=0.125) for i in (1, 2)]
    text = report_text(readable(monkeypatch, info), caplog)
    assert "0 to check, 1 informational, 0 noise" in text
    assert "total equal to IBKR, split over 2 rows" in text
    assert text.index("Dividend information") < text.index("0 to check, 1 informational")
    noise = readable(monkeypatch, [destination(unitPrice=0.250001)])
    assert "0 to check, 0 informational, 1 noise" in report_text(noise, caplog)
    assert "Dividend noise" not in caplog.text
    assert "Dividend noise: rounding noise" in report_text(noise, caplog, "DEBUG")
    coherent = readable(monkeypatch, [destination()])
    assert "Dividend coherent" not in report_text(coherent, caplog)
    assert "Dividend coherent" in report_text(coherent, caplog, "DEBUG")
