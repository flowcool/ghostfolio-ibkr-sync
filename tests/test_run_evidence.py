"""Synthetic native lab evidence; all HTTP is mocked."""
import io
import json
import logging
from unittest.mock import Mock

import pytest

import ibkr_to_ghostfolio as m


CFG = {"ghost_host": "http://ghost.invalid", "ghost_token": "SECRET_SENTINEL"}
SEND = ('<R><Status>Success</Status><ReferenceCode>synthetic-ref</ReferenceCode>'
        '<Url>https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement</Url></R>')
XML = '<R><FlexStatements><FlexStatement fromDate="20251016" toDate="20261015"/></FlexStatements></R>'


def candidate(kind="BUY", **changes):
    row = dict(accountId="lab-account", comment="IBKR#synthetic", currency="EUR", type=kind,
               symbol="TEST", dataSource="YAHOO", date="2026-10-14T00:00:00+02:00",
               quantity=3.125, unitPrice=10.01, fee=0.001)
    row.update(changes)
    return row


@pytest.fixture
def http(monkeypatch):
    get, post, put = Mock(), Mock(), Mock()
    monkeypatch.setattr(m.requests, "get", get)
    monkeypatch.setattr(m.requests, "post", post)
    monkeypatch.setattr(m.requests, "put", put)
    monkeypatch.setattr(m.time, "sleep", Mock())
    return get, post, put


def response(body=None, text="", status=200):
    return Mock(text=text, content=text.encode(), status_code=status, json=Mock(return_value=body))


def fetch(http, xml=XML, retry=False):
    get, _, _ = http
    responses = [response(text=SEND)]
    if retry:
        responses.append(response(text='<R><Status>Warn</Status><ErrorCode>1019</ErrorCode></R>'))
    responses.append(response(text=xml))
    get.side_effect = responses
    return m.fetch_flex_report("SECRET_SENTINEL", "synthetic-query")


def cash_response(http, currency="EUR", status=200):
    get, _, put = http
    get.side_effect = None
    get.return_value = response(dict(currency=currency, name="Synthetic", platformId=None))
    put.return_value = response(status=status, text="synthetic failure" if status >= 400 else "")


def evidence(caplog):
    return [json.loads(r.getMessage().removeprefix("LAB_EVIDENCE "))
            for r in caplog.records if r.getMessage().startswith("LAB_EVIDENCE ")]


@pytest.mark.parametrize("dry", [True, False])
def test_info_byte_identical(http, dry):
    """These exact formatted bytes also pass before the evidence implementation."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    formatter.formatTime = lambda *args: "2026-10-15 12:00:00"
    handler.setFormatter(formatter)
    old_level = m.log.level
    m.log.setLevel(logging.INFO)
    m.log.addHandler(handler)
    try:
        assert fetch(http) == XML
        cfg = dict(CFG, dry_run=dry)
        rows = [candidate()]
        http[1].return_value = response({"activities": [dict(row, id=f"created-{i}", assetProfile={"symbol": row["symbol"], "dataSource": row["dataSource"]}) for i, row in enumerate(rows)]})
        assert m.ghost_import_activities(cfg, rows) == (rows, True)
        assert m.ghost_import_activities(cfg, []) == ([], True)
        cash_response(http)
        assert m.ghost_update_cash_balance(cfg, "lab-account", 25.900000000000002, "EUR")
        assert not m.ghost_update_cash_balance(cfg, "lab-account", 1, None)
    finally:
        m.log.removeHandler(handler)
        m.log.setLevel(old_level)
    messages = [("INFO", "Got reference code synthetic-ref, fetching statement...")]
    if dry:
        messages += [("INFO", "[DRY RUN] would import 1 activities (no POST sent):"),
                     ("INFO", "[DRY RUN]   BUY      TEST           qty=3.125 price=10.01 EUR fee=0.001  IBKR#synthetic")]
    else:
        messages += [("INFO", "Ghostfolio created 1 of 1 submitted activities")]
    messages += [("INFO", "No new activities to import"),
                 ("INFO", "[DRY RUN] would set cash balance for account lab-account to 25.90 (no PUT sent)"
                  if dry else "Updated cash balance for account lab-account to 25.90"),
                 ("ERROR", "Cash balance not updated for account lab-account: the report has no base currency "
                  "(Account Information CurrencyPrimary missing from the Flex Query)")]
    expected = "".join(f"2026-10-15 12:00:00 [{level}] {message}\n" for level, message in messages)
    assert stream.getvalue().encode() == expected.encode()


@pytest.mark.parametrize("statements,expected", [
    ('<FlexStatement fromDate="20251016" toDate="20261015"/>', ["2025-10-16", "2026-10-15"]),
    ('<FlexStatement fromDate="20251016" toDate="20261015"/>' * 2, ["2025-10-16", "2026-10-15"]),
    ('<FlexStatement/>', None),
    ('<FlexStatement fromDate="20260230" toDate="20261015"/>', None),
    ('<FlexStatement fromDate="20261016" toDate="20261015"/>', None),
    ('<FlexStatement fromDate="20251016" toDate="20261015"/>'
     '<FlexStatement fromDate="20251017" toDate="20261015"/>', None),
])
def test_window(http, caplog, statements, expected):
    caplog.set_level(logging.DEBUG, logger=m.__name__)
    xml = f"<R><FlexStatements>{statements}</FlexStatements></R>"
    assert fetch(http, xml, retry=True) == xml
    assert evidence(caplog) == [dict(kind="window", value=expected)]
    assert http[0].call_count == 3


@pytest.mark.parametrize("dry", [True, False])
@pytest.mark.parametrize("empty", [True, False])
def test_preview(http, caplog, dry, empty):
    caplog.set_level(logging.DEBUG, logger=m.__name__)
    rows = [] if empty else [candidate(kind, comment=f'{kind} quote" newline\nbackslash\\')
                            for kind in ("BUY", "SELL", "DIVIDEND")]
    http[1].return_value = response({"activities": [dict(row, id=f"created-{i}", assetProfile={"symbol": row["symbol"], "dataSource": row["dataSource"]}) for i, row in enumerate(rows)]})
    assert m.ghost_import_activities(dict(CFG, dry_run=dry), rows) == (rows, True)
    assert evidence(caplog) == ([dict(kind="preview", value=rows)] if dry else [])
    assert http[1].call_count == int(not dry and not empty)
    if not dry and not empty:
        assert http[1].call_args.kwargs["json"] == {"activities": rows}


@pytest.mark.parametrize("dry", [True, False])
@pytest.mark.parametrize("balance", [0, -12.34567, 25.900000000000002, 0.000001])
def test_cash(http, caplog, dry, balance):
    caplog.set_level(logging.DEBUG, logger=m.__name__)
    cash_response(http)
    assert m.ghost_update_cash_balance(dict(CFG, dry_run=dry), "lab-account", balance, "EUR")
    assert evidence(caplog) == [dict(kind="cash", value=dict(accountId="lab-account", balance=balance, currency="EUR"))]
    assert http[0].call_count == 1
    assert http[2].call_count == int(not dry)
    if not dry:
        assert http[2].call_args.kwargs["json"]["balance"] == balance


@pytest.mark.parametrize("currency", [None, "USD"])
def test_cash_guards(http, caplog, currency):
    caplog.set_level(logging.DEBUG, logger=m.__name__)
    cash_response(http)
    assert not m.ghost_update_cash_balance(CFG, "lab-account", 1, currency)
    assert evidence(caplog) == []
    http[2].assert_not_called()


def test_cash_failed_put_still_describes_target(http, caplog):
    caplog.set_level(logging.DEBUG, logger=m.__name__)
    cash_response(http, status=400)
    assert not m.ghost_update_cash_balance(CFG, "lab-account", 1.001, "EUR")
    assert evidence(caplog) == [dict(kind="cash", value=dict(accountId="lab-account", balance=1.001, currency="EUR"))]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_keeps_existing_results_without_invalid_json(http, caplog, value):
    caplog.set_level(logging.DEBUG, logger=m.__name__)
    rows = [candidate(unitPrice=value)]
    assert m.ghost_import_activities(dict(CFG, dry_run=True), rows) == (rows, True)
    cash_response(http)
    assert m.ghost_update_cash_balance(dict(CFG, dry_run=True), "lab-account", value, "EUR")
    assert evidence(caplog) == []
    http[1].assert_not_called()
    http[2].assert_not_called()


def test_format_single_physical_line_and_no_secrets(http, caplog):
    caplog.set_level(logging.DEBUG, logger=m.__name__)
    row = candidate(comment='quote"\nslash\\')
    m.ghost_import_activities(dict(CFG, dry_run=True, xml="PRIVATE_XML", env="PRIVATE_ENV"), [row])
    records = [r for r in caplog.records if r.getMessage().startswith("LAB_EVIDENCE ")]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.DEBUG
    message = record.getMessage()
    assert len(message.splitlines()) == 1
    assert message == 'LAB_EVIDENCE ' + json.dumps(dict(kind="preview", value=[row]), separators=(",", ":"), allow_nan=False)
    formatted = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S").format(record)
    assert " [DEBUG] LAB_EVIDENCE " in formatted
    assert all(secret not in message for secret in ("SECRET_SENTINEL", "PRIVATE_XML", "PRIVATE_ENV", CFG["ghost_host"]))
    assert evidence(caplog) == [dict(kind="preview", value=[row])]
