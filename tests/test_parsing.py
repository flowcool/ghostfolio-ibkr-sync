"""Offline tests: Flex XML parsing, date parsing, mapping and secret redaction."""
from decimal import Decimal
from itertools import permutations
import xml.etree.ElementTree as ET

import pytest

import ibkr_to_ghostfolio as m


def flex(cash_rows="", trades=""):
    section = f"<CashTransactions>{cash_rows}</CashTransactions>" if cash_rows is not None else ""
    return (f"<FlexQueryResponse><FlexStatements><FlexStatement>"
            f"<Trades>{trades}</Trades>{section}"
            f"</FlexStatement></FlexStatements></FlexQueryResponse>")


def cash(type_, amount, date="20260715", isin="US1912161007", symbol="KO", ccy="USD",
         desc="KO CASH DIVIDEND USD 0.25 PER SHARE", level=None):
    lvl = f' levelOfDetail="{level}"' if level else ""
    return (f'<CashTransaction type="{type_}" amount="{amount}" dateTime="{date}" isin="{isin}" '
            f'symbol="{symbol}" currency="{ccy}" description="{desc}"{lvl}/>')


# --- parse_cash_dividends -------------------------------------------------

def test_dividend_and_withholding_are_summed_per_isin_and_day():
    rows = cash("Dividends", "25.00") + cash("Withholding Tax", "-3.75")
    [d] = m.parse_cash_dividends(flex(rows))
    assert (d["isin"], d["date"], d["currency"]) == ("US1912161007", "2026-07-15", "USD")
    assert d["amount"] == pytest.approx(25.0)
    assert d["tax"] == pytest.approx(-3.75)


def test_reversal_and_repayment_net_to_the_final_payment():
    rows = (cash("Dividends", "25.00", desc="OLD USD 0.25 PER SHARE")
            + cash("Dividends", "-25.00", desc="OLD USD 0.25 PER SHARE")
            + cash("Dividends", "30.00", desc="NEW USD 0.30 PER SHARE"))
    [d] = m.parse_cash_dividends(flex(rows))
    assert d["amount"] == pytest.approx(30.0)
    assert "NEW" in d["description"]


def test_full_reversal_nets_to_zero():
    rows = cash("Dividends", "25.00") + cash("Dividends", "-25.00")
    [d] = m.parse_cash_dividends(flex(rows))
    assert d["amount"] == pytest.approx(0.0)


def test_summary_rows_are_ignored_when_detail_rows_exist():
    rows = cash("Dividends", "25.00", level="DETAIL") + cash("Dividends", "25.00", level="SUMMARY")
    [d] = m.parse_cash_dividends(flex(rows))
    assert d["amount"] == pytest.approx(25.0)


def test_other_cash_types_are_ignored():
    assert m.parse_cash_dividends(flex(cash("Broker Interest Received", "1.00"))) == []


def test_payment_in_lieu_counts_as_dividend():
    [d] = m.parse_cash_dividends(flex(cash("Payment In Lieu Of Dividends", "7.00")))
    assert d["amount"] == pytest.approx(7.0)


def test_invalid_amount_or_date_is_skipped():
    rows = cash("Dividends", "abc") + cash("Dividends", "5.00", date="garbage")
    assert m.parse_cash_dividends(flex(rows)) == []


def test_missing_cash_transactions_section_returns_none():
    assert m.parse_cash_dividends(flex(cash_rows=None)) is None


def test_symbol_is_grouping_key_when_isin_is_missing():
    rows = cash("Dividends", "5.00", isin="") + cash("Dividends", "5.00", isin="")
    [d] = m.parse_cash_dividends(flex(rows))
    assert d["amount"] == pytest.approx(10.0)


# --- parse_trades / parse_cash_report ------------------------------------

def test_parse_trades_keeps_only_trade_elements():
    xml = flex(trades='<Trade tradeID="1" symbol="A"/><AssetSummary symbol="A"/><Trade tradeID="2"/>',
               cash_rows="")
    assert [t["tradeID"] for t in m.parse_trades(xml)] == ["1", "2"]


def test_parse_cash_report_reads_base_summary_only():
    xml = ('<R><CashReport><CashReportCurrency currency="EUR" endingCash="1"/>'
           '<CashReportCurrency currency="BASE_SUMMARY" endingCash="1234.5"/></CashReport></R>')
    assert m.parse_cash_report(xml) == pytest.approx(1234.5)


@pytest.mark.parametrize("xml", [
    "<R/>",
    '<R><CashReportCurrency currency="BASE_SUMMARY" endingCash="oops"/></R>',
    '<R><CashReportCurrency currency="BASE_SUMMARY" endingCash=""/></R>',
])
def test_parse_cash_report_missing_or_invalid_is_none(xml):
    assert m.parse_cash_report(xml) is None


# --- parse_ibkr_datetime --------------------------------------------------

@pytest.mark.parametrize("raw,iso", [
    ("20260801;143000", "2026-08-01T14:30:00+00:00"),
    ("2026-08-01, 14:30:00", "2026-08-01T14:30:00+00:00"),
    ("2026-08-01;14:30:00", "2026-08-01T14:30:00+00:00"),
    ("20260801", "2026-08-01T00:00:00+00:00"),
    ("2026-08-01", "2026-08-01T00:00:00+00:00"),
    (" 20260801 ", "2026-08-01T00:00:00+00:00"),
    ("20260115;093000 EST", "2026-01-15T09:30:00+00:00"),
    ("20260715;093000 EDT", "2026-07-15T09:30:00+00:00"),
])
def test_parse_ibkr_datetime_formats(raw, iso):
    assert m.parse_ibkr_datetime(raw) == iso


@pytest.mark.parametrize("raw,iso", [
    ("20260801;143000", "2026-08-01T14:30:00+00:00"),
    ("20260115;093000 EST", "2026-01-15T09:30:00+00:00"),
    ("20260715;093000 EDT", "2026-07-15T09:30:00+00:00"),
])
def test_historical_diagnostic_parser(raw, iso):
    assert m.parse_ibkr_datetime(raw) == iso


@pytest.mark.parametrize("raw", ["", None, "garbage", "01/08/2026"])
def test_parse_ibkr_datetime_invalid(raw):
    assert m.parse_ibkr_datetime(raw) is None


# --- symbol mapping -------------------------------------------------------

def test_resolve_symbol_prefers_mapping_then_ibkr_symbol():
    assert m.resolve_symbol("ISIN1", "TAL", {"ISIN1": "TAL.TO"}) == "TAL.TO"
    assert m.resolve_symbol("ISIN2", "TAL", {"ISIN1": "TAL.TO"}) == "TAL"
    assert m.resolve_symbol("", "", {}) is None


def test_load_mapping_ok(tmp_path):
    f = tmp_path / "mapping.yaml"
    f.write_text('symbol_mapping:\n  JP3421100003: "1662.T"\n')
    assert m.load_mapping(str(f)) == {"JP3421100003": "1662.T"}


def test_load_mapping_empty_path_is_explicit_opt_out():
    assert m.load_mapping("") == {}


def test_load_mapping_missing_file_is_fatal(tmp_path):
    with pytest.raises(RuntimeError, match="not found"):
        m.load_mapping(str(tmp_path / "nope.yaml"))


@pytest.mark.parametrize("content", [
    "symbol_mapping:\n  US1: 123\n",          # unquoted numeric ticker
    "symbol_mapping: [a, b]\n",               # wrong type
    "- just\n- a list\n",                     # wrong top level
    "symbol_mapping: {unclosed\n",            # invalid YAML
])
def test_load_mapping_invalid_is_fatal(tmp_path, content):
    f = tmp_path / "mapping.yaml"
    f.write_text(content)
    with pytest.raises(RuntimeError):
        m.load_mapping(str(f))


def test_load_mapping_non_utf8_is_fatal(tmp_path):
    f = tmp_path / "mapping.yaml"
    f.write_bytes(b"symbol_mapping:\n  A: \xff\xfe\n")
    with pytest.raises(RuntimeError):
        m.load_mapping(str(f))


# --- secret redaction -----------------------------------------------------

def test_redact_masks_raw_and_url_encoded_forms():
    secret = "a b/c+d"
    text = f"GET https://x/?t={m.quote_plus(secret)} also {secret} and {m.quote(secret, safe='')}"
    out = m._redact(text, secret)
    assert "a+b" not in out and "a%20b" not in out and secret not in out
    assert out.count("***") == 3


def test_redact_without_secret_is_noop():
    assert m._redact("abc", "") == "abc"


# --- IBKR statement URL allow-list ---------------------------------------

def test_fetch_flex_report_rejects_foreign_statement_url(monkeypatch):
    class Resp:
        text = ("<FlexStatementResponse><Status>Success</Status><ReferenceCode>1</ReferenceCode>"
                "<Url>https://ndcdyn.interactivebrokers.com.evil.example/x</Url></FlexStatementResponse>")
        content = text.encode("utf-8")
    monkeypatch.setattr(m, "_ibkr_get", lambda *a, **k: Resp())
    with pytest.raises(RuntimeError, match="Unexpected IBKR statement URL"):
        m.fetch_flex_report("tok", "q")


# --- Flex HTTP response size boundary -----------------------------------

@pytest.mark.parametrize("stage", ["send", "statement"])
@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_flex_response_byte_limit_before_parsing(monkeypatch, stage, delta):
    send = ('<R><Status>Success</Status><ReferenceCode>1</ReferenceCode>'
            '<Url>https://ndcdyn.interactivebrokers.com/statement</Url></R>')
    statement = '<FlexQueryResponse><FlexStatements/></FlexQueryResponse>'
    target = send if stage == "send" else statement
    target += ' ' * (m.IBKR_MAX_XML_BYTES + delta - len(target.encode("utf-8")))
    bodies = [target, statement] if stage == "send" else [send, target]
    responses = []
    for body in bodies:
        response = m.requests.Response()
        response._content = body.encode("utf-8")
        response.encoding = "utf-8"
        responses.append(response)
    replies = iter(responses)
    monkeypatch.setattr(m, "_ibkr_get", lambda *a, **k: next(replies))
    original = m.ET.fromstring
    parsed = []

    def parse(text):
        parsed.append(text)
        return original(text)

    monkeypatch.setattr(m.ET, "fromstring", parse)
    if delta > 0:
        with pytest.raises(RuntimeError) as error:
            m.fetch_flex_report("synthetic", "synthetic")
        assert str(error.value) == "IBKR Flex response exceeds XML size limit"
        assert target not in parsed
        assert len(parsed) == (0 if stage == "send" else 1)
    else:
        assert m.fetch_flex_report("synthetic", "synthetic") == bodies[1]
        assert len(parsed) == 2


def test_flex_limit_counts_response_bytes_not_characters(monkeypatch):
    body = '<R>' + '\u00e9' * (m.IBKR_MAX_XML_BYTES // 2) + '</R>'
    assert len(body) < m.IBKR_MAX_XML_BYTES
    response = m.requests.Response()
    response._content = body.encode("utf-8")
    response.encoding = "utf-8"
    monkeypatch.setattr(m, "_ibkr_get", lambda *a, **k: response)
    monkeypatch.setattr(m.ET, "fromstring", lambda text: pytest.fail("must not parse"))
    with pytest.raises(RuntimeError, match="^IBKR Flex response exceeds XML size limit$"):
        m.fetch_flex_report("synthetic", "synthetic")


# --- structured dividend quantity evidence ---------------------------------

def structured_cash(amount="25", action="A1", type_="Dividends", **overrides):
    attrs = {"type": type_, "amount": amount, "dateTime": "20260715", "isin": "US1912161007",
             "symbol": "KO", "currency": "USD", "accountId": "broker-account", "conid": "1",
             "actionID": action, "exDate": "20260701", "levelOfDetail": "DETAIL"}
    attrs.update(overrides)
    return ET.tostring(ET.Element("CashTransaction", attrs), encoding="unicode")


def structured_accrual(quantity="100", action="A1", **overrides):
    attrs = {"accountId": "broker-account", "conid": "1", "currency": "USD", "actionID": action,
             "exDate": "20260701", "quantity": quantity, "code": "Re", "date": "20260715",
             "payDate": "20260715", "reportDate": "20260715"}
    attrs.update(overrides)
    return ET.tostring(ET.Element("ChangeInDividendAccrual", attrs), encoding="unicode")


def structured_dividend(payments, accruals):
    xml = flex("".join(payments)).replace("</FlexStatement>",
          "<ChangeInDividendAccruals>" + "".join(accruals) + "</ChangeInDividendAccruals></FlexStatement>")
    return m.parse_cash_dividends(xml)


@pytest.mark.parametrize("quantity,amount,type_", [
    ("3", "1.5", "Payment In Lieu Of Dividends"), ("450", "45.1", "Dividends"),
    ("1", "0.25", "Dividends"), ("0.125", "0.5", "Dividends"),
    ("1.0000000000000000000000000001", "1", "Dividends"),
])
def test_dividend_structured_quantity_association_preserves_exact_evidence(quantity, amount, type_):
    [dividend] = structured_dividend([structured_cash(amount, type_=type_)], [structured_accrual(quantity)])
    assert m.dividend_structured_quantity(dividend) == Decimal(quantity)
    activity = m.convert_dividend_to_activity(dividend, "ghost-account", {}, {})
    assert activity["quantity"] == float(quantity)
    assert activity["quantity"] * activity["unitPrice"] == pytest.approx(float(amount))
    assert activity["accountId"] == "ghost-account"
    assert activity["comment"] == "dividend#US1912161007#2026-07-15"
    assert activity["date"] == "2026-07-15T00:00:00+00:00"


@pytest.mark.parametrize("dates", [
    {"date": "20260701", "reportDate": "20260715"},
    {"date": "20260715", "reportDate": "20260720"},
])
def test_dividend_structured_quantity_matches_date_or_report_date(dates):
    [dividend] = structured_dividend([structured_cash()], [structured_accrual(**dates)])
    assert m.dividend_structured_quantity(dividend) == Decimal(100)


@pytest.mark.parametrize("overrides", [
    {"accountId": "other"}, {"conid": "other"}, {"currency": "EUR"}, {"actionID": "other"},
    {"exDate": "20260702"}, {"payDate": "20260716"}, {"date": "20260701", "reportDate": "20260720"},
    {"code": "Po"}, {"quantity": ""}, {"quantity": "invalid"}, {"quantity": "0"},
    {"quantity": "-1"}, {"quantity": "NaN"}, {"quantity": "Infinity"},
])
def test_dividend_structured_quantity_rejects_wrong_or_invalid_evidence(overrides, caplog):
    [dividend] = structured_dividend([structured_cash()], [structured_accrual(**overrides)])
    assert m.convert_dividend_to_activity(dividend, "ghost-account", {}, {}) is None
    assert any("not imported" in record.message for record in caplog.records)


@pytest.mark.parametrize("field", ["accountId", "conid", "currency", "actionID", "exDate"])
def test_dividend_structured_quantity_requires_nonempty_association_keys(field):
    for source in ("cash", "accrual"):
        payment = structured_cash(**{field: ""}) if source == "cash" else structured_cash()
        accrual = structured_accrual(**{field: ""}) if source == "accrual" else structured_accrual()
        [dividend] = structured_dividend([payment], [accrual])
        assert m.dividend_structured_quantity(dividend) is None


@pytest.mark.parametrize("extra", [
    structured_accrual(), structured_accrual("101", code="Po", date="20260701"),
    structured_accrual("", code="Po", date="20260701"),
])
def test_dividend_structured_quantity_rejects_multiple_re_or_conflicting_revisions(extra):
    [dividend] = structured_dividend([structured_cash()], [structured_accrual(), extra])
    assert m.dividend_structured_quantity(dividend) is None


def test_dividend_structured_quantity_agrees_across_revisions_and_ignores_unrelated_keys():
    evidence = [structured_accrual("100.00", code="Po", date="20260701"), structured_accrual("1e2"),
                structured_accrual("invalid", action="unrelated")]
    [dividend] = structured_dividend([structured_cash()], evidence)
    assert m.dividend_structured_quantity(dividend) == Decimal(100)


def test_dividend_structured_quantity_re_without_cash_creates_no_payment():
    assert structured_dividend([], [structured_accrual()]) == []
    [dividend] = structured_dividend([structured_cash()], [])
    assert m.dividend_structured_quantity(dividend) is None


@pytest.mark.parametrize("bonus_rate", ["0.25", "0.1"])
def test_dividend_structured_components_split_pil_and_bonus_use_common_quantity_and_cash(bonus_rate):
    payments = [structured_cash("20", description="USD 0.25 PER SHARE"),
                structured_cash("5", type_="Payment In Lieu Of Dividends"),
                structured_cash("10", action="bonus", description=f"USD {bonus_rate} PER SHARE"),
                structured_cash("-4", type_="Withholding Tax", action="")]
    evidence = [structured_accrual(grossAmount="999", tax="-999", rate="999"),
                structured_accrual(action="bonus", grossAmount="0.01", tax="0", rate=bonus_rate)]
    expected = None
    for ordered_cash in permutations(payments):
        for ordered_accruals in permutations(evidence):
            [dividend] = structured_dividend(ordered_cash, ordered_accruals)
            activity = m.convert_dividend_to_activity(dividend, "ghost-account", {}, {})
            assert (dividend["amount"], dividend["tax"]) == (35, -4)
            assert (activity["quantity"], activity["unitPrice"], activity["fee"]) == (100, 0.35, 4)
            assert activity["quantity"] * activity["unitPrice"] - activity["fee"] == pytest.approx(31)
            if expected is None:
                expected = activity
            assert activity == expected


@pytest.mark.parametrize("extra_cash,extra_evidence", [
    ([structured_cash("1", action="bonus")], [structured_accrual("101", action="bonus")]),
    ([structured_cash("-1", action="correction")], []),
    ([structured_cash("1", currency="EUR")], [structured_accrual(currency="EUR")]),
    ([structured_cash("-1", type_="Withholding Tax", currency="EUR")], []),
])
def test_dividend_structured_components_reject_unequal_negative_or_mixed_actions(extra_cash, extra_evidence):
    [dividend] = structured_dividend([structured_cash(), *extra_cash], [structured_accrual(), *extra_evidence])
    assert m.convert_dividend_to_activity(dividend, "ghost-account", {}, {}) is None


def test_dividend_structured_components_zero_net_action_provides_no_quantity():
    payments = [structured_cash(), structured_cash("5", action="cancelled"),
                structured_cash("-5", action="cancelled")]
    evidence = [structured_accrual(), structured_accrual("invalid", action="cancelled")]
    [dividend] = structured_dividend(payments, evidence)
    assert m.dividend_structured_quantity(dividend) == Decimal(100)
    [cancelled] = structured_dividend(payments[1:], evidence[1:])
    assert m.convert_dividend_to_activity(cancelled, "ghost-account", {}, {}) is None


def test_dividend_structured_components_signed_cash_is_exact_and_order_independent():
    payments = [structured_cash("10000000000000000"), structured_cash("1"),
                structured_cash("-10000000000000000")]
    for ordered in permutations(payments):
        [dividend] = structured_dividend(ordered, [structured_accrual("3")])
        assert dividend["amount"] == 1
        activity = m.convert_dividend_to_activity(dividend, "ghost-account", {}, {})
        assert activity["quantity"] == 3
        assert activity["quantity"] * activity["unitPrice"] == pytest.approx(1)


@pytest.mark.parametrize("other", ["1.0000000000000000000000000001", "100.000000000000000000000001"])
def test_dividend_structured_numeric_decimal_conflict_precedes_float_conversion(other):
    first = "1" if other.startswith("1.") else "100"
    assert float(first) == float(other)
    [dividend] = structured_dividend([structured_cash()],
                                    [structured_accrual(first), structured_accrual(other, code="Po")])
    assert m.dividend_structured_quantity(dividend) is None



def test_dividend_structured_quantity_enriched_selection_preserves_baseline():
    payments = [structured_cash(), structured_cash("99", levelOfDetail="SUMMARY"),
                structured_cash("99", type_="Other Fees"), structured_cash("-3.75", type_="Withholding Tax")]
    xml = flex("".join(payments), '<Trade tradeID="T1"/><AssetSummary symbol="KO"/>').replace(
        "</FlexStatement>", "<ChangeInDividendAccruals>" + structured_accrual() +
        "</ChangeInDividendAccruals></FlexStatement>")
    assert m.parse_trades(xml) == [{"tradeID": "T1"}]
    [dividend] = m.parse_cash_dividends(xml)
    activity = m.convert_dividend_to_activity(dividend, "ghost-account", {}, {})
    assert (activity["quantity"], activity["unitPrice"], activity["fee"]) == (100, 0.25, 3.75)


def test_dividend_structured_numeric_decimal_conflict_between_components():
    [dividend] = structured_dividend([structured_cash(), structured_cash("10", action="bonus")],
                                    [structured_accrual("100"),
                                     structured_accrual("100.000000000000000000000001", action="bonus")])
    assert m.dividend_structured_quantity(dividend) is None
