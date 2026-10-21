"""Synthetic migration boundary checks; no service or credential access."""

import json
import logging
import os
import socket
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
import requests
import yaml

import identity_migration as migration
from identity_maintenance import digest, exact_json


@pytest.fixture
def case(tmp_path, monkeypatch):
    source = tmp_path / "report.xml"
    source.write_text('<FlexQueryResponse><FlexStatements><FlexStatement fromDate="20260101" '
                      'toDate="20260131"><AccountInformation accountId="U1"/>'
                      '<Trades/><CashTransactions/><ChangeInDividendAccruals/>'
                      '</FlexStatement></FlexStatements></FlexQueryResponse>')
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text('{"count":1,"activities":[{"id":"row-1","comment":"IBKR#123",'
                        '"quantity":1.0000000000000000001,"unitPrice":2.3,"fee":0.01,'
                        '"date":"2026-01-10T12:00:00Z","type":"BUY","accountId":"dest",'
                        '"currency":"USD","isDraft":false,"tags":[],"assetProfile":'
                        '{"symbol":"TEST","dataSource":"YAHOO","currency":"USD"}}]}')
    config = {
        "schema": "ibkr-migration-inputs-v1", "tool_commit": "a" * 40,
        "timezone": "Europe/Zurich", "window": ["2026-01-01", "2026-01-31"],
        "inventory_complete": True, "accounts": {"U1": "dest"}, "symbol_mapping": {},
        "reports": {"report-1": {"path": source.name, "sha256": digest(source.read_bytes()),
                                   "source_account": "U1"}},
        "snapshot": {"path": snapshot.name, "sha256": digest(snapshot.read_bytes()),
                     "count": 1, "complete": True, "unredacted": True,
                     "captured_at": "2026-01-11T00:00:00Z", "capture_ref": "synthetic-capture",
                     "destination_version": "3.86.0", "destination_image": "sha256:" + "b" * 64}}
    inputs = tmp_path / "inputs.yaml"

    def save():
        inputs.write_text(yaml.safe_dump(config))
        return inputs

    save()
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("GHOST_TOKEN", "synthetic-do-not-read")

    def denied(*args, **kwargs):
        raise AssertionError("Network or credential loading attempted")

    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(requests.sessions.Session, "request", denied)
    monkeypatch.setattr(os, "getenv", denied)
    import ghostfolio_ibkr_sync.config as runtime_config
    monkeypatch.setattr(runtime_config, "load_config", denied)
    return tmp_path, config, save, inputs, source, snapshot


def test_v2_migration_offline_private_exact_deterministic(case):
    root, config, save, inputs, source, snapshot = case
    before = {p: p.read_bytes() for p in (inputs, source, snapshot)}
    first = migration.preview(inputs, root / "first")
    second = migration.preview(inputs, root / "second")
    assert first == second
    assert (root / "first/manifest.json").read_bytes() == (root / "second/manifest.json").read_bytes()
    manifest = exact_json((root / "first/manifest.json").read_bytes())
    assert manifest["rows"][0]["fields"]["quantity"] == "1.0000000000000000001"
    assert manifest["actionable"] is False and manifest["replacements"] == []
    assert manifest["pending"] == ["complete-import-selection-proof"]
    assert all(p.read_bytes() == data for p, data in before.items())
    assert (root / "first").stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in (root / "first").iterdir())
    config["symbol_mapping"] = {"TEST": "TEST.US"}
    save()
    assert migration.preview(inputs, root / "changed") != first


@pytest.mark.parametrize("mutation", [
    "count", "complete", "unredacted", "captured_at", "destination_version", "destination_image",
    "capture_ref", "inventory_complete", "accounts", "missing_account", "symbol_mapping",
    "timezone", "window", "tool_commit", "reports", "hash", "source_account",
])
def test_v2_migration_offline_invalid_inputs(case, mutation):
    root, config, save, inputs, source, snapshot = case
    if mutation in config["snapshot"]:
        config["snapshot"][mutation] = None
    elif mutation == "missing_account":
        config["accounts"]["U2"] = "dest2"
    elif mutation in ("hash", "source_account"):
        config["reports"]["report-1"]["sha256" if mutation == "hash" else mutation] = "bad"
    else:
        config[mutation] = None
    save()
    with pytest.raises((RuntimeError, ValueError, KeyError, TypeError)):
        migration.preview(inputs, root / "out")
    assert not (root / "out").exists()


@pytest.mark.parametrize("field,value", [
    ("quantity", None), ("quantity", "1"), ("unitPrice", None), ("fee", None),
    ("comment", 1), ("id", ""), ("date", "2026-01-01"), ("isDraft", None),
    ("tags", None), ("assetProfile", "redacted"), ("currency", 42),
])
def test_v2_migration_offline_redacted_snapshot(case, field, value):
    root, config, save, inputs, source, snapshot = case
    data = json.loads(snapshot.read_text())
    data["activities"][0][field] = value
    snapshot.write_text(json.dumps(data))
    config["snapshot"]["sha256"] = digest(snapshot.read_bytes())
    save()
    with pytest.raises((RuntimeError, ValueError)):
        migration.preview(inputs, root / "out")
    assert not (root / "out").exists()


@pytest.mark.parametrize("data", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'])
def test_v2_migration_offline_invalid_json(data):
    with pytest.raises(RuntimeError):
        exact_json(data)


@pytest.mark.parametrize("data", [b'x: 1\nx: 2', b'x: &x {a: 1}\ny: *x',
                                   b'x: !!python/object:os.system {}', b'x: 1.2', b'[]', b''])
def test_v2_migration_offline_invalid_yaml(data):
    with pytest.raises((RuntimeError, yaml.YAMLError)):
        migration.keyed_yaml(data)


@pytest.mark.parametrize("target", ["inputs", "source", "snapshot", "parent", "existing", "symlink"])
def test_v2_migration_offline_output_collision(case, target):
    root, config, save, inputs, source, snapshot = case
    before = {p: p.read_bytes() for p in (inputs, source, snapshot)}
    output = {"inputs": inputs, "source": source, "snapshot": snapshot, "parent": root}.get(target)
    if target == "existing":
        output = root / "out"
        output.mkdir()
        (output / "keep").write_text("keep")
    if target == "symlink":
        output = root / "link"
        output.symlink_to(root / "new", target_is_directory=True)
    with pytest.raises(RuntimeError):
        migration.preview(inputs, output)
    assert all(p.read_bytes() == data for p, data in before.items())
    if target == "existing":
        assert (output / "keep").read_text() == "keep"


@pytest.mark.parametrize("target", ["config", "report", "snapshot", "ancestor"])
def test_v2_migration_offline_input_symlink(case, target):
    root, config, save, inputs, source, snapshot = case
    if target == "ancestor":
        link = root / "alias"
        link.symlink_to(root, target_is_directory=True)
        inputs = link / inputs.name
    elif target == "config":
        link = root / "alias.yaml"
        link.symlink_to(inputs)
        inputs = link
    else:
        original = source if target == "report" else snapshot
        link = root / "alias"
        link.symlink_to(original)
        ref = config["reports"]["report-1"] if target == "report" else config["snapshot"]
        ref["path"] = link.name
        save()
    with pytest.raises(RuntimeError, match="Symlink"):
        migration.preview(inputs, root / "out")
    assert not (root / "out").exists()


def test_v2_migration_offline_actual_cli(case):
    root, config, save, inputs, source, snapshot = case
    # sitecustomize applies before imports in the fresh CLI process. It denies
    # sockets and direct environment access to any credential/config names.
    guard = root / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text('''
import os, sys
def audit(event, args):
    if event.startswith("socket."):
        raise AssertionError("Network denied")
sys.addaudithook(audit)
original = os._Environ.__getitem__
def checked(self, key):
    if key.startswith(("IBKR_", "GHOST", "APPRISE", "DRY_RUN")):
        raise AssertionError("Credential/config environment read")
    return original(self, key)
os._Environ.__getitem__ = checked
''')
    env = dict(os.environ)
    env["PYTHONPATH"] = str(guard) + os.pathsep + str(Path.cwd())
    result = subprocess.run([sys.executable, "identity_migration.py", "preview", "--inputs",
                             str(inputs), "--output", str(root / "cli")],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == migration.preview(inputs, root / "direct")


def test_v2_migration_offline_cli_malformed_xml(case, monkeypatch, capsys):
    root, config, save, inputs, source, snapshot = case
    source.write_bytes(b"<FlexQueryResponse><unclosed>")
    config["reports"]["report-1"]["sha256"] = digest(source.read_bytes())
    save()
    monkeypatch.setattr(sys, "argv", ["identity_migration.py", "preview", "--inputs",
                                    str(inputs), "--output", str(root / "out")])
    previous_logging_level = logging.root.manager.disable
    with pytest.raises(SystemExit) as result:
        migration.main()
    assert logging.root.manager.disable == previous_logging_level
    assert result.value.code == 1
    assert "Preview refused (ParseError)" in capsys.readouterr().err
    assert not (root / "out").exists()


# Source strings and original JSON numbers stay separate throughout the tests.
def migration_trade(**changes):
    return {"accountId": "U1", "tradeID": "123", "assetCategory": "STK",
            "isin": "US-TEST", "symbol": "TEST", "currency": "USD", "buySell": "BUY",
            "quantity": "1", "tradePrice": "2.3", "ibCommission": "-0.01",
            "dateTime": "20260110;120000", **changes}


def migration_cash(action="A", amount="2.3", kind="Dividends", **changes):
    return {"accountId": "U1", "actionID": action, "conid": "100", "currency": "USD",
            "isin": "US-TEST", "symbol": "TEST", "type": kind, "amount": amount,
            "levelOfDetail": "DETAIL", "exDate": "20260105", "dateTime": "20260110;120000 EST",
            **changes}


def migration_accrual(action="A", **changes):
    return {"accountId": "U1", "actionID": action, "conid": "100", "currency": "USD",
            "exDate": "20260105", "quantity": "1", "code": "Re", "payDate": "20260110",
            "date": "20260110", "reportDate": "20260110", **changes}


def migration_xml(trades=(), cash=(), accruals=(), account="U1"):
    from xml.etree.ElementTree import Element, SubElement, tostring
    root = Element("FlexQueryResponse")
    statement = SubElement(SubElement(root, "FlexStatements"), "FlexStatement",
                           fromDate="20260101", toDate="20260131")
    SubElement(statement, "AccountInformation", accountId=account)
    for section, name, rows in (("Trades", "Trade", trades),
                                ("CashTransactions", "CashTransaction", cash),
                                ("ChangeInDividendAccruals", "ChangeInDividendAccrual", accruals)):
        parent = SubElement(statement, section)
        for row in rows:
            SubElement(parent, name, row)
    return tostring(root, encoding="unicode")


def migration_row(**changes):
    return {"id": "row-1", "comment": "IBKR#123", "quantity": 1, "unitPrice": 2.3,
            "fee": 0.01, "date": "2026-01-10T12:00:00Z", "type": "BUY", "accountId": "dest",
            "currency": "USD", "isDraft": False, "tags": [],
            "assetProfile": {"symbol": "TEST", "dataSource": "YAHOO", "currency": "USD"},
            **changes}


def migration_run(case, rows=None, trades=None, cash=(), accruals=(), extra=None):
    root, config, save, inputs, source, snapshot = case
    source.write_text(migration_xml(trades if trades is not None else [migration_trade()], cash, accruals))
    config["reports"]["report-1"]["sha256"] = digest(source.read_bytes())
    if extra:
        for name, account, xml in extra:
            path = root / (name + ".xml")
            path.write_text(xml)
            config["accounts"].setdefault(account, "dest2")
            config["reports"][name] = {"path": path.name, "sha256": digest(path.read_bytes()),
                                      "source_account": account}
    rows = rows if rows is not None else [migration_row()]
    snapshot.write_text(json.dumps({"count": len(rows), "activities": rows}))
    config["snapshot"].update(count=len(rows), sha256=digest(snapshot.read_bytes()))
    save()
    originals = {p: p.read_bytes() for p in (inputs, source, snapshot)}
    migration.preview(inputs, root / "preview")
    assert all(p.read_bytes() == content for p, content in originals.items())
    result = json.loads((root / "preview/manifest.json").read_text())
    assert len(result["rows"]) == len(rows)
    assert sum(result["counts"]["source_events"].values()) == len(result["events"])
    assert sum(result["counts"]["historical_rows"].values()) == len(rows)
    assert result["actionable"] is False
    return result


def test_v2_migration_preview_exact_trade(case):
    row = migration_row(date="2026-01-09T23:30:00Z")
    result = migration_run(case, rows=[row])
    event, = result["events"]
    assert event["status"] == "eligible-replacement"
    assert event["association_cardinality"] == {"source_events": 1, "historical_rows": 1}
    assert event["differences"] == []
    assert event["expected"]["gross"] == "23/10"
    replacement, = result["replacements"]
    assert replacement["old_comment"] == "IBKR#123"
    assert replacement["new_comment"] == "IBKR#v2#U1:TRADE:123"
    assert replacement["before_fingerprint"] != replacement["after_fingerprint"]
    assert result["rows"][0]["fields"]["date"] == row["date"]


@pytest.mark.parametrize("field,value,difference", [
    ("quantity", 1.000000001, "quantity"), ("unitPrice", 2.300000001, "gross"),
    ("fee", 0.010000001, "fee"), ("type", "SELL", "type"),
    ("accountId", "other", "accountId"), ("currency", "EUR", "currency"),
    ("date", "2026-01-11T12:00:00Z", "day"),
    ("assetProfile", {"symbol": "OTHER", "dataSource": "YAHOO"}, "symbol"),
    ("assetProfile", {"symbol": "TEST", "dataSource": "MANUAL"}, "dataSource"),
    ("assetProfile", {"symbol": "TEST", "dataSource": "YAHOO", "isin": "OTHER"}, "isin"),
    ("assetProfile", {"symbol": "TEST", "dataSource": "YAHOO", "currency": "EUR"}, "profile_currency"),
    ("account", {"id": "other"}, "account_context"),
    ("SymbolProfile", {"symbol": "OTHER"}, "profile_context"),
])
def test_v2_migration_preview_exact_differences(case, field, value, difference):
    result = migration_run(case, rows=[migration_row(**{field: value})])
    assert not result["replacements"]
    event, = result["events"]
    assert event["status"] == "conflicting"
    assert difference in {d["field"] for d in event["differences"]}


@pytest.mark.parametrize("context", [
    {"isDraft": True}, {"isExcluded": True}, {"account": {"id": "dest", "isExcluded": True}},
    {"tags": [{"id": "0c077abd-eca2-4cbb-818c-6cefbf2d169a"}]},
    {"tags": [{"id": "f2e868af-8333-459f-b161-cbc6544c24bd"}]},
    {"tags": ["malformed"]}, {"account": "malformed"},
])
def test_v2_migration_preview_inactive(case, context):
    result = migration_run(case, rows=[migration_row(**context)])
    assert not result["replacements"]
    assert result["events"][0]["status"] == "unsupported"


@pytest.mark.parametrize("trade", [
    migration_trade(assetCategory="CASH"), migration_trade(assetCategory="OPT"),
    migration_trade(buySell="sell"), migration_trade(accountId="U2"),
    migration_trade(tradeID="bad:ID"), migration_trade(quantity="NaN"),
    migration_trade(ibCommission=""), migration_trade(currency="UNKNOWN"),
    migration_trade(quantity="0"), migration_trade(tradePrice="1e400"),
])
def test_v2_migration_preview_unsupported_source(case, trade):
    result = migration_run(case, trades=[trade])
    assert not result["replacements"]
    assert result["events"][0]["status"] == "unsupported"


def test_v2_migration_preview_duplicate_destination(case):
    result = migration_run(case, rows=[migration_row(), migration_row(id="copy")])
    assert not result["replacements"]
    assert result["events"][0]["status"] == "ambiguous"
    assert {row["status"] for row in result["rows"]} == {"ambiguous"}


def test_v2_migration_preview_legacy_global_ownership(case):
    other = migration_xml([migration_trade(accountId="U2")], account="U2")
    result = migration_run(case, extra=[("other", "U2", other)])
    assert not result["replacements"]
    assert len(result["events"]) == 2
    assert {e["status"] for e in result["events"]} == {"ambiguous"}


def test_v2_migration_preview_overlapping_report(case):
    result = migration_run(case, extra=[("overlap", "U1", migration_xml([migration_trade()]))])
    assert len(result["replacements"]) == 1
    assert len(result["events"]) == 1
    assert len(result["events"][0]["source_refs"]) == 2


def test_v2_migration_preview_conflicting_report(case):
    result = migration_run(case, extra=[("overlap", "U1", migration_xml([
        migration_trade(tradePrice="2.31")]))])
    assert not result["replacements"]
    assert result["events"][0]["status"] == "conflicting"
    assert len(result["events"][0]["variants"]) == 2


def test_v2_migration_preview_duplicate_source(case):
    result = migration_run(case, trades=[migration_trade(), migration_trade()])
    assert not result["replacements"]
    assert result["events"][0]["status"] == "ambiguous"


@pytest.mark.parametrize("occupied_account", ["dest", "other"])
def test_v2_migration_preview_occupied_identity(case, occupied_account):
    result = migration_run(case, rows=[migration_row(), migration_row(
        id="occupied", comment="IBKR#v2#U1:TRADE:123", accountId=occupied_account)])
    assert not result["replacements"]
    assert result["events"][0]["occupied_ids"] == ["occupied"]
    assert result["events"][0]["status"] == "conflicting"
    assert next(r for r in result["rows"] if r["id"] == "occupied")["status"] == "already-v2"


def test_v2_migration_preview_absent_manual_outside(case):
    result = migration_run(case, rows=[migration_row(comment=None),
        migration_row(id="absent", comment="IBKR#999"),
        migration_row(id="outside", comment="IBKR#777", date="2025-12-01T12:00:00Z")])
    assert not result["replacements"]
    assert result["events"][0]["status"] == "absent-new-candidate"
    by_id = {r["id"]: r for r in result["rows"]}
    assert by_id["row-1"]["reason"] == "manual"
    assert by_id["absent"]["reason"] == "absent-source"
    assert by_id["outside"]["status"] == "outside-window"


@pytest.mark.parametrize("old_key", ["US-TEST", "TEST", "MAPPED"])
def test_v2_migration_preview_one_action_split_pil(case, old_key):
    case[1]["symbol_mapping"] = {"US-TEST": "MAPPED"}
    row = migration_row(comment=f"dividend#{old_key}#2026-01-10", type="DIVIDEND",
                        assetProfile={"symbol": "MAPPED", "dataSource": "YAHOO", "currency": "USD"})
    result = migration_run(case, rows=[row], trades=[], cash=[
        migration_cash(amount="1.3"), migration_cash(amount="1", kind="Payment In Lieu Of Dividends"),
        migration_cash(amount="-0.01", kind="Withholding Tax")], accruals=[migration_accrual()])
    assert len(result["replacements"]) == 1
    event, = result["events"]
    assert event["new_comment"] == "IBKR#v2#U1:DIVIDEND:A"
    assert event["expected"]["quantity"] == "1"
    assert event["expected"]["gross"] == "23/10"
    assert event["expected"]["signed_tax"] == "-1/100"
    assert len(event["variants"][0]["cash_rows"]) == 3


@pytest.mark.parametrize("partial", [False, True])
def test_v2_migration_preview_aggregate_and_partial(case, partial):
    rows = [migration_row(comment="dividend#US-TEST#2026-01-10", type="DIVIDEND")]
    if partial:
        rows.append(migration_row(id="v2", type="DIVIDEND", comment="IBKR#v2#U1:DIVIDEND:A"))
    result = migration_run(case, rows=rows, trades=[], cash=[migration_cash(), migration_cash("B")],
                           accruals=[migration_accrual(), migration_accrual("B", quantity="2")])
    assert not result["replacements"]
    assert len(result["events"]) == 2
    assert {e["status"] for e in result["events"]} == {"partial-coverage" if partial else "aggregate"}


def test_v2_migration_preview_both_fee_clamps(case):
    result = migration_run(case, rows=[migration_row(type="DIVIDEND",
        comment="dividend#US-TEST#2026-01-10", fee=0)], trades=[], cash=[
        migration_cash(), migration_cash(amount="-0.01", kind="Withholding Tax"),
        migration_cash("Z", amount="0"), migration_cash("Z", amount="0.01", kind="Withholding Tax")],
        accruals=[migration_accrual()])
    assert not result["replacements"]
    event = next(e for e in result["events"] if e["new_comment"].endswith(":A"))
    assert event["expected"]["historical_fee"] == "0"
    assert event["expected"]["fee"] == "1/100"
    assert event["status"] in {"aggregate", "conflicting"}


@pytest.mark.parametrize("currency,symbol", [("GBP", "TEST.L"), ("ZAR", "TEST.JO"), ("ILS", "TEST.TA")])
def test_v2_migration_preview_minor_units(case, currency, symbol):
    denomination, factor = migration.minor_unit_conversion(symbol, currency)
    result = migration_run(case, trades=[migration_trade(currency=currency, symbol=symbol)],
        rows=[migration_row(unitPrice=230, fee=1, currency=denomination,
            assetProfile={"symbol": symbol, "dataSource": "YAHOO", "currency": denomination})])
    assert len(result["replacements"]) == 1


def test_v2_migration_preview_decimal_rounding_is_not_eligibility(case):
    result = migration_run(case, trades=[migration_trade(quantity="1.0000000000000000001")])
    assert not result["replacements"]
    assert "quantity" in {d["field"] for d in result["events"][0]["differences"]}


def test_v2_migration_preview_dividend_inexact_unit_price(case):
    result = migration_run(case, trades=[], rows=[migration_row(type="DIVIDEND", quantity=3,
        unitPrice=0.7666666666666667, comment="dividend#US-TEST#2026-01-10")],
        cash=[migration_cash(), migration_cash(amount="-0.01", kind="Withholding Tax")],
        accruals=[migration_accrual(quantity="3")])
    assert not result["replacements"]
    assert "gross" in {d["field"] for d in result["events"][0]["differences"]}



@pytest.mark.parametrize("cash,accruals", [
    ([migration_cash()], []),
    ([migration_cash()], [migration_accrual(), migration_accrual()]),
    ([migration_cash()], [migration_accrual(quantity="0")]),
    ([migration_cash()], [migration_accrual(quantity="1e-400")]),
    ([migration_cash()], [migration_accrual(conid="wrong")]),
    ([migration_cash()], [migration_accrual(payDate="20260111")]),
    ([migration_cash(), migration_cash(amount="-0.01", kind="Withholding Tax", actionID="wrong")],
     [migration_accrual()]),
    ([migration_cash(), migration_cash(amount="-0.01", kind="Withholding Tax", exDate="20260106")],
     [migration_accrual()]),
    ([migration_cash(), migration_cash(currency="EUR")], [migration_accrual()]),
    ([migration_cash(accountId="U2")], [migration_accrual(accountId="U2")]),
    ([migration_cash(action="bad:ID")], [migration_accrual(action="bad:ID")]),
    ([migration_cash(amount="-2.3")], [migration_accrual()]),
    ([migration_cash(amount="0")], []),
    ([migration_cash(amount="-0.01", kind="Withholding Tax")], []),
])
def test_v2_migration_preview_invalid_dividend_group(case, cash, accruals):
    result = migration_run(case, trades=[], rows=[migration_row(type="DIVIDEND",
        comment="dividend#US-TEST#2026-01-10")], cash=cash, accruals=accruals)
    assert not result["replacements"]
    assert result["events"]
    assert all(e["status"] in {"unsupported", "conflicting"} for e in result["events"])


@pytest.mark.parametrize("bad", [migration_cash(amount="bad"),
                                 migration_cash(dateTime="bad"),
                                 migration_cash(action="B", amount="bad")])
def test_v2_migration_preview_omitted_cash_is_visible_and_blocks_subset(case, bad):
    result = migration_run(case, trades=[], cash=[migration_cash(), bad],
        accruals=[migration_accrual()], rows=[migration_row(type="DIVIDEND", fee=0,
        comment="dividend#US-TEST#2026-01-10")])
    assert not result["replacements"]
    assert any("omitted_cash" in v for e in result["events"] for v in e["variants"])
    assert all(e["status"] in {"unsupported", "conflicting"} for e in result["events"])


@pytest.mark.parametrize("fee", [0, 0.01])
def test_v2_migration_preview_opposite_signed_clamps_both_must_match(case, fee):
    result = migration_run(case, trades=[], cash=[migration_cash(),
        migration_cash(amount="-0.01", kind="Withholding Tax"),
        migration_cash("Z", amount="0"), migration_cash("Z", amount="0.01", kind="Withholding Tax")],
        accruals=[migration_accrual()], rows=[migration_row(type="DIVIDEND", fee=fee,
        comment="dividend#US-TEST#2026-01-10")])
    assert not result["replacements"]
    event = next(e for e in result["events"] if e["new_comment"].endswith(":A"))
    assert event["status"] == "conflicting"
    assert {d["field"] for d in event["differences"]} & {"fee", "historical_fee"}


def test_v2_migration_preview_zero_action_claims_no_payment(case):
    result = migration_run(case, trades=[], cash=[migration_cash(), migration_cash("Z", amount="0")],
        accruals=[migration_accrual()], rows=[migration_row(type="DIVIDEND", fee=0,
        comment="dividend#US-TEST#2026-01-10")])
    assert len(result["replacements"]) == 1
    assert len(result["events"]) == 2


def test_v2_migration_preview_reserved_legacy_is_not_owned(case):
    result = migration_run(case, trades=[migration_trade(tradeID="v123")],
        rows=[migration_row(comment="IBKR#v123")])
    assert not result["replacements"]
    assert result["events"][0]["status"] == "unsupported"


def test_v2_migration_preview_already_v2(case):
    result = migration_run(case, rows=[migration_row(comment="IBKR#v2#U1:TRADE:123")])
    assert not result["replacements"]
    assert result["events"][0]["status"] == "already-v2"


def test_v2_migration_preview_duplicate_dividend_aliases(case):
    result = migration_run(case, trades=[], cash=[migration_cash()], accruals=[migration_accrual()],
        rows=[migration_row(type="DIVIDEND", comment="dividend#US-TEST#2026-01-10"),
              migration_row(id="alias", type="DIVIDEND", comment="dividend#TEST#2026-01-10")])
    assert not result["replacements"]
    assert result["events"][0]["status"] == "ambiguous"


def test_v2_migration_preview_outside_source_window(case):
    case[1]["window"] = ["2026-01-20", "2026-01-31"]
    result = migration_run(case)
    assert not result["replacements"]
    assert result["events"][0]["status"] == "outside-window"


def test_v2_migration_preview_exact_cli_replay(case):
    root, config, save, inputs, source, snapshot = case
    result = migration_run(case, trades=[migration_trade(), migration_trade(tradeID="124"),
        migration_trade(tradeID="125", buySell="PRIVATE-INVALID-SIDE")],
        cash=[migration_cash()], accruals=[migration_accrual()], rows=[migration_row(),
        migration_row(id="dividend", type="DIVIDEND", fee=0, comment="dividend#TEST#2026-01-10")])
    assert len(result["replacements"]) == 2
    assert {e["status"] for e in result["events"]} == {"eligible-replacement", "absent-new-candidate", "unsupported"}
    # Reuse the fresh-process socket and credential guard with populated inputs.
    test_v2_migration_offline_actual_cli(case)
