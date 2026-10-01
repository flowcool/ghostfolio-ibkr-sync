"""Offline tests: Flex XML parsing, date parsing, mapping and secret redaction."""
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
])
def test_parse_ibkr_datetime_formats(raw, iso):
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
    monkeypatch.setattr(m, "_ibkr_get", lambda *a, **k: Resp())
    with pytest.raises(RuntimeError, match="Unexpected IBKR statement URL"):
        m.fetch_flex_report("tok", "q")


def test_deliberate_failure_ci_demo():
    assert False, "throwaway: proves a failing test blocks CI"
