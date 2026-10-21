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
        "replay_order": ["report-1"],
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
    assert manifest["pending"] == []
    assert manifest["selection_proof"]["equal"] is True
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
            config["replay_order"].append(name)
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


def test_v2_migration_selection_complete_payloads_and_holdings(case):
    result = migration_run(case, rows=[migration_row()], trades=[
        migration_trade(), migration_trade(tradeID="new-buy", quantity="3"),
        migration_trade(tradeID="safe-sell", buySell="SELL", quantity="-2"),
        migration_trade(tradeID="unbacked-sell", buySell="SELL", quantity="-4",
                        symbol="EMPTY", isin="US-EMPTY")],
        cash=[migration_cash()], accruals=[migration_accrual()])
    proof = result["selection_proof"]
    assert proof["equal"] is True and result["pending"] == []
    assert proof["before"] == proof["after"]
    query, = proof["before"]["queries"]
    assert [a["comment"] for a in query["selected"]] == [
        "IBKR#v2#U1:TRADE:new-buy", "IBKR#v2#U1:DIVIDEND:A", "IBKR#v2#U1:TRADE:safe-sell"]
    assert len(query["holdings"]["prepared"]) == 3
    assert len(query["holdings"]["kept"]) == 2
    assert query["holdings_after"] == [{"account": "dest", "symbol": "TEST", "quantity": 2.0}]
    assert proof["before_sha256"] == proof["after_sha256"]


def test_v2_migration_selection_legacy_global_release_is_rejected(case):
    # The eligibility guard already excludes this collision. Exercise the
    # independent replay guard with that unsafe replacement deliberately supplied.
    root, config, *_ = case
    config["accounts"]["U2"] = "dest2"
    config["replay_order"] = ["first", "second"]
    reports = {"first": ("U1", migration_xml([migration_trade()])),
               "second": ("U2", migration_xml([migration_trade(accountId="U2")], account="U2"))}
    rows = exact_json(json.dumps([migration_row()]).encode())
    planned = [{"id": "row-1", "new_comment": "IBKR#v2#U1:TRADE:123"}]
    proof = migration.prove_selection(reports, rows, config, planned)
    assert proof["equal"] is False and proof["reason"] == "selection-changed"
    assert proof["before"]["queries"][1]["selected"] == []
    selected, = proof["after"]["queries"][1]["selected"]
    assert selected["comment"] == "IBKR#v2#U2:TRADE:123"
    manifest = {"replacements": planned, "events": [{"status": "eligible-replacement"}],
                "rows": [{"id": "row-1", "status": "eligible-replacement"}]}
    migration.bind_selection(manifest, reports, rows, config)
    assert manifest["replacements"] == []
    assert manifest["pending"] == ["selection-changed"]
    assert manifest["counts"]["historical_rows"] == {"selection-changed": 1}
    assert manifest["ordered_row_fingerprints"][0]["before"] == manifest["ordered_row_fingerprints"][0]["after"]


@pytest.mark.parametrize("start,end", [("20260102", "20260131"), ("20260101", "20260130"),
                                       ("20260110", "20260120")])
def test_v2_migration_selection_short_windows_block_conversion(case, start, end):
    xml = migration_xml(account="U2").replace('fromDate="20260101"', f'fromDate="{start}"').replace(
        'toDate="20260131"', f'toDate="{end}"')
    result = migration_run(case, extra=[("other", "U2", xml)])
    assert not result["replacements"]
    assert result["selection_proof"]["missing_windows"] == ["U2"]
    assert result["pending"] == ["incomplete-window"]
    assert result["events"][0]["status"] == "incomplete-window"
    assert result["rows"][0]["status"] == "incomplete-window"


@pytest.mark.parametrize("second_start,complete", [("20260116", True), ("20260115", True),
                                                    ("20260117", False)])
def test_v2_migration_selection_adjacent_and_gapped_windows(case, second_start, complete):
    first = migration_xml(account="U2").replace('toDate="20260131"', 'toDate="20260115"')
    second = migration_xml(account="U2").replace('fromDate="20260101"', f'fromDate="{second_start}"')
    result = migration_run(case, extra=[("a", "U2", first), ("b", "U2", second)])
    assert result["selection_proof"]["equal"] is complete
    assert bool(result["replacements"]) is complete


def test_v2_migration_selection_empty_report_is_window_evidence(case):
    result = migration_run(case, extra=[("empty", "U2", migration_xml(account="U2"))])
    assert result["selection_proof"]["equal"] is True
    assert len(result["selection_proof"]["before"]["queries"]) == 2
    assert len(result["replacements"]) == 1


def test_v2_migration_selection_manual_and_partial_decisions(case):
    result = migration_run(case, rows=[migration_row(),
        migration_row(id="manual", comment=None, quantity=2),
        migration_row(id="partial", comment="IBKR#v2#U1:DIVIDEND:A", type="DIVIDEND")],
        trades=[migration_trade(), migration_trade(tradeID="manual-buy", quantity="2")],
        cash=[migration_cash(), migration_cash("B")],
        accruals=[migration_accrual(), migration_accrual("B")])
    proof = result["selection_proof"]
    assert proof["equal"] is True
    query, = proof["before"]["queries"]
    assert query["selected"] == [] and query["ok"] is False
    assert query["holdings"]["manual_trade_ids"] == [["U1", "manual-buy"]]
    assert query["holdings"]["prepared"] and not query["holdings"]["kept"]


def test_v2_migration_selection_query_order_and_simulated_acceptance(case):
    # Same destination, different source IDs: the second query must see the
    # first query's proposed BUY before its SELL passes the holdings gate.
    case[1]["accounts"]["U2"] = "dest"
    result = migration_run(case, rows=[], trades=[migration_trade(quantity="2")], extra=[(
        "second", "U2", migration_xml([migration_trade(accountId="U2", tradeID="sell",
                                  buySell="SELL", quantity="-2")], account="U2"))])
    queries = result["selection_proof"]["before"]["queries"]
    assert [q["source_account"] for q in queries] == ["U1", "U2"]
    assert [a["type"] for q in queries for a in q["selected"]] == ["BUY", "SELL"]
    assert queries[1]["holdings_before"][0]["quantity"] == 2
    assert queries[1]["holdings_after"][0]["quantity"] == 0
    root, config, save, inputs, *_ = case
    config["replay_order"].reverse()
    save()
    migration.preview(inputs, root / "reverse")
    reverse = json.loads((root / "reverse/manifest.json").read_text())
    first, second = reverse["selection_proof"]["before"]["queries"]
    assert first["selected"] == []
    assert second["selected"][0]["type"] == "BUY"
    assert reverse["bindings"]["inputs"] != result["bindings"]["inputs"]


@pytest.mark.parametrize("order", [None, [], ["unknown"], ["report-1", "report-1"], {"report-1": 1}])
def test_v2_migration_selection_invalid_query_order(case, order):
    root, config, save, inputs, *_ = case
    config["replay_order"] = order
    save()
    with pytest.raises(RuntimeError, match="Replay order"):
        migration.preview(inputs, root / "bad-order")
    assert not (root / "bad-order").exists()


def test_v2_migration_selection_binds_ordered_rows_and_implementation(case):
    result = migration_run(case, rows=[migration_row(id="z"),
        migration_row(id="a", comment=None, type="DIVIDEND")])
    assert [r["id"] for r in result["ordered_row_fingerprints"]] == ["z", "a"]
    replaced, untouched = result["ordered_row_fingerprints"]
    assert replaced["before"] != replaced["after"]
    assert untouched["before"] == untouched["after"]
    assert result["snapshot"]["destination_version"] == "3.86.0"
    assert result["snapshot"]["destination_image"].startswith("sha256:")
    assert result["bindings"]["inventory"] and result["bindings"]["mapping"]
    for path, sha in result["implementation"].items():
        assert digest((Path(migration.__file__).parent / path).read_bytes()) == sha


@pytest.mark.parametrize("field", ["quantity", "fee", "symbol", "holdings"])
def test_v2_migration_selection_rejects_equal_counts_with_changed_values(case, monkeypatch, field):
    config = case[1]
    calls = []

    def replay(*args):
        payload = {"quantity": 1, "fee": 0, "symbol": "TEST", "holdings": 1}
        if calls:
            payload[field] = 2 if field != "symbol" else "OTHER"
        calls.append(True)
        return {"selected": [payload]}

    monkeypatch.setattr(migration, "replay_selection", replay)
    proof = migration.prove_selection({"report-1": ("U1", migration_xml())}, [], config, [])
    assert proof["equal"] is False
    assert len(proof["before"]["selected"]) == len(proof["after"]["selected"])
    assert proof["before_sha256"] != proof["after_sha256"]


def test_v2_migration_selection_clock_is_capture_bound(case):
    result = migration_run(case, trades=[migration_trade(), migration_trade(
        tradeID="after-capture", dateTime="20260120;120000")])
    proof = result["selection_proof"]
    assert proof["equal"] is True
    assert proof["clock"] == "2026-01-11T00:00:00Z"
    query, = proof["before"]["queries"]
    assert query["selected"] == [] and query["ok"] is False


@pytest.mark.parametrize("change", ["mapping", "inventory", "timezone", "tool", "image", "version", "clock"])
def test_v2_migration_selection_configuration_invalidates_manifest(case, change):
    migration_run(case)
    root, config, save, inputs, *_ = case
    previous = (root / "preview/manifest.sha256").read_text().strip()
    if change == "mapping":
        config["symbol_mapping"]["US-TEST"] = "OTHER"
    elif change == "inventory":
        config["accounts"]["U1"] = "other-destination"
    elif change == "timezone":
        config["timezone"] = "UTC"
    elif change == "tool":
        config["tool_commit"] = "c" * 40
    elif change == "image":
        config["snapshot"]["destination_image"] = "sha256:" + "c" * 64
    elif change == "version":
        config["snapshot"]["destination_version"] = "3.87.0"
    else:
        config["snapshot"]["captured_at"] = "2026-01-12T00:00:00Z"
    save()
    assert migration.preview(inputs, root / "changed-selection") != previous


@pytest.fixture
def apply_case(case, monkeypatch):
    """A complete synthetic review, approval and stateful HTTP double."""
    from copy import deepcopy
    from types import SimpleNamespace

    root, config, save, inputs, source, snapshot = case
    rows = [migration_row(userId="owner", tags=[{"id": "tag-1", "name": "Keep"}]),
            migration_row(id="row-2", comment="IBKR#456", userId="owner")]
    migration_run(case, rows=rows, trades=[migration_trade(), migration_trade(tradeID="456")])
    manifest = root / "preview/manifest.json"
    manifest_hash = digest(manifest.read_bytes())
    permit = {
        "schema": "ibkr-migration-approval-v1", "host": "https://ghostfolio.example.test",
        "manifest_sha256": manifest_hash, "destination_version": "3.86.0",
        "destination_image": config["snapshot"]["destination_image"],
        "operation_plan_ref": "synthetic-approved-plan", "backup_ref": "synthetic-backup",
        "writer_exclusion_ref": "synthetic-exclusion", "settlement_ref": "synthetic-settlement",
        "preservation_qualification_ref": "synthetic-G5-not-image-proof",
        "pacing_qualification_ref": "synthetic-measurement-not-live-proof",
        "owner_id": "owner", "writers_stopped": True, "requests_settled": True,
        "write_count": 2, "batch_size": 1, "pause_seconds": 0.25,
    }
    approval = root / "approval.json"
    journal = root / "apply.yaml"
    state = SimpleNamespace(rows=deepcopy(rows), calls=[], puts=[], delays=[], gets=0,
                            before_get=None, put_effect=None, status=200)

    def get(url, **kwargs):
        assert url == permit["host"] + "/api/v1/activities"
        assert kwargs == {"headers": {"Authorization": "Bearer synthetic-token",
                                     "Content-Type": "application/json"},
                          "timeout": 60, "allow_redirects": False}
        state.gets += 1
        state.calls.append("get")
        if state.before_get:
            state.before_get()
        return SimpleNamespace(status_code=200, content=json.dumps(
            {"activities": state.rows, "count": len(state.rows)}).encode())

    def put(url, **kwargs):
        payload = kwargs["json"]
        assert url == permit["host"] + "/api/v1/activities/" + payload["id"]
        assert kwargs["timeout"] == 60 and kwargs["allow_redirects"] is False
        durable = yaml.safe_load(journal.read_bytes())
        if durable["status"] == "rollback_in_progress":
            assert durable["rows"][payload["id"]]["rollback_status"] == "pending"
        else:
            assert durable["rows"][payload["id"]]["status"] == "pending"
            assert durable["status"] == "in_progress"
        state.calls.append("put")
        state.puts.append(deepcopy(payload))
        if state.put_effect:
            state.put_effect(payload)
        else:
            next(r for r in state.rows if r["id"] == payload["id"])["comment"] = payload["comment"]
        return SimpleNamespace(status_code=state.status)

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "put", put)
    monkeypatch.setattr(migration.time, "sleep", state.delays.append)

    def run(**overrides):
        approval.write_text(json.dumps(permit))
        arguments = dict(inputs=inputs, manifest=manifest, manifest_sha256=manifest_hash,
                         approval=approval, approval_sha256=digest(approval.read_bytes()),
                         journal=journal, host=permit["host"], token="synthetic-token")
        arguments.update(overrides)
        migration.apply(**arguments)

    return state, permit, run, journal, rows, case


def test_v2_migration_apply_rollback_exact_preservation(apply_case):
    state, permit, run, journal, original, case = apply_case
    run()
    assert state.calls == ["get", "get", "put", "get", "get", "put", "get"]
    assert state.delays == [0.25]
    assert state.rows == [{**r, "comment": "IBKR#v2#U1:TRADE:" +
                           ("123" if r["id"] == "row-1" else "456")} for r in original]
    for payload, row in zip(state.puts, original):
        assert set(payload) == {"id", "accountId", "comment", "currency", "date", "fee", "quantity",
                                "symbol", "type", "unitPrice", "dataSource", "tags"}
        assert payload == {**{k: row[k] for k in ("id", "accountId", "currency", "date", "fee",
                                                 "quantity", "type", "unitPrice")},
                           "comment": "IBKR#v2#U1:TRADE:" +
                           ("123" if row["id"] == "row-1" else "456"),
                           "symbol": "TEST", "dataSource": "YAHOO",
                           "tags": [tag["id"] for tag in row["tags"]]}
    record = yaml.safe_load(journal.read_bytes())
    assert record["status"] == "complete"
    assert all(r["status"] == "verified" for r in record["rows"].values())
    assert record["rows"]["row-1"]["preimage"]["fee"] == "0.01"
    assert journal.stat().st_mode & 0o777 == 0o600
    assert Path(str(journal) + ".lock").stat().st_mode & 0o777 == 0o600
    with pytest.raises(RuntimeError, match="Existing migration journal"):
        run()
    assert len(state.puts) == 2


@pytest.mark.parametrize("key,value", [
    ("backup_ref", ""), ("operation_plan_ref", ""), ("writer_exclusion_ref", None),
    ("settlement_ref", ""), ("preservation_qualification_ref", ""),
    ("pacing_qualification_ref", ""), ("writers_stopped", False), ("requests_settled", False),
    ("owner_id", "other-owner"), ("manifest_sha256", "0" * 64),
    ("destination_version", "other"), ("destination_image", "sha256:" + "c" * 64),
    ("write_count", 1), ("batch_size", None), ("batch_size", 0), ("batch_size", 1.5),
    ("pause_seconds", None), ("pause_seconds", -1),
])
def test_v2_migration_apply_rollback_prerequisites(apply_case, key, value):
    state, permit, run, journal, original, case = apply_case
    permit[key] = value
    with pytest.raises(RuntimeError):
        run()
    assert not state.calls and not journal.exists()


@pytest.mark.parametrize("field,value", [
    ("comment", "manual"), ("quantity", 2), ("unitPrice", 3), ("fee", 1),
    ("date", "2026-01-10T13:00:00Z"), ("accountId", "other"), ("userId", "other"),
    ("currency", "EUR"), ("type", "SELL"), ("tags", []), ("isDraft", True),
    ("assetProfile", {"symbol": "OTHER", "dataSource": "YAHOO", "currency": "USD"}),
])
def test_v2_migration_apply_rollback_stale_context(apply_case, field, value):
    state, permit, run, journal, original, case = apply_case
    state.rows[0][field] = value
    with pytest.raises(RuntimeError):
        run()
    assert not state.puts
    assert yaml.safe_load(journal.read_bytes())["status"] == "prepared"


@pytest.mark.parametrize("change", ["occupied", "absent", "duplicate", "incomplete", "late-writer"])
def test_v2_migration_apply_rollback_occupancy(apply_case, change):
    state, permit, run, journal, original, case = apply_case
    if change == "occupied":
        state.rows.append(migration_row(id="occupied", comment="IBKR#v2#U1:TRADE:123"))
    elif change == "absent":
        state.rows.pop()
    elif change == "duplicate":
        state.rows[1]["id"] = "row-1"
    elif change == "incomplete":
        state.rows[0]["fee"] = None
    else:
        def drift():
            if state.gets == 2:
                state.rows[1]["comment"] = "concurrent edit"
        state.before_get = drift
    with pytest.raises(RuntimeError):
        run()
    assert not state.puts


@pytest.mark.parametrize("outcome", ["timeout", "redirect", "server-error", "old-comment",
                                     "profile", "tags", "quantity", "unrelated", "failed-get"])
def test_v2_migration_apply_rollback_pending_on_uncertainty(apply_case, outcome):
    state, permit, run, journal, original, case = apply_case

    def effect(payload):
        if outcome == "timeout":
            raise requests.Timeout("synthetic delayed response")
        if outcome in ("redirect", "server-error"):
            state.status = 302 if outcome == "redirect" else 500
        elif outcome != "old-comment":
            state.rows[0]["comment"] = payload["comment"]
            if outcome == "profile":
                state.rows[0]["assetProfile"]["currency"] = "EUR"
            elif outcome == "tags":
                state.rows[0]["tags"] = []
            elif outcome == "quantity":
                state.rows[0]["quantity"] = 1.0001
            elif outcome == "unrelated":
                state.rows[1]["fee"] = 2
            elif outcome == "failed-get":
                def fail():
                    raise requests.Timeout("readback timeout")
                state.before_get = fail
    state.put_effect = effect
    with pytest.raises(RuntimeError):
        run()
    record = yaml.safe_load(journal.read_bytes())
    assert record["rows"]["row-1"]["status"] == "pending"
    assert record["rows"]["row-2"]["status"] == "prepared"
    assert len(state.puts) == 1
    with pytest.raises(RuntimeError, match="Existing migration journal"):
        run()
    assert len(state.puts) == 1


def test_v2_migration_apply_rollback_partial_subset(apply_case):
    state, permit, run, journal, original, case = apply_case

    def effect(payload):
        if len(state.puts) == 2:
            raise requests.Timeout()
        state.rows[0]["comment"] = payload["comment"]
    state.put_effect = effect
    with pytest.raises(RuntimeError):
        run()
    record = yaml.safe_load(journal.read_bytes())
    assert record["rows"]["row-1"]["status"] == "verified"
    assert record["rows"]["row-2"]["status"] == "pending"
    assert state.rows[1] == original[1]


@pytest.mark.parametrize("target", ["manifest", "approval", "source", "inputs"])
def test_v2_migration_apply_rollback_changed_input(apply_case, target):
    state, permit, run, journal, original, case = apply_case
    root, config, save, inputs, source, snapshot = case
    path = {"manifest": root / "preview/manifest.json", "approval": root / "approval.json",
            "source": source, "inputs": inputs}[target]

    def drift():
        if state.gets == 2:
            path.write_bytes(path.read_bytes() + b" ")
    state.before_get = drift
    with pytest.raises(RuntimeError, match="Reviewed input changed"):
        run()
    assert not state.puts


@pytest.mark.parametrize("target", ["source", "snapshot", "inputs", "manifest", "approval", "lock-alias"])
def test_v2_migration_apply_rollback_journal_input_collision(apply_case, target):
    state, permit, run, journal, original, case = apply_case
    root, config, save, inputs, source, snapshot = case
    paths = {"source": source, "snapshot": snapshot, "inputs": inputs,
             "manifest": root / "preview/manifest.json", "approval": root / "approval.json"}
    if target == "lock-alias":
        Path(str(journal) + ".lock").hardlink_to(source)
        destination = journal
    else:
        destination = paths[target]
    before = {p: p.read_bytes() for p in (inputs, source, snapshot, root / "preview/manifest.json")}
    with pytest.raises(RuntimeError, match="Journal overlaps evidence"):
        run(journal=destination)
    assert not state.calls
    assert all(p.read_bytes() == data for p, data in before.items())


def test_v2_migration_apply_rollback_cli_replay(apply_case, monkeypatch, capsys):
    state, permit, run, journal, original, case = apply_case
    root, config, save, inputs, source, snapshot = case
    approval = root / "approval.json"
    approval.write_text(json.dumps(permit))
    monkeypatch.setenv("GHOST_TOKEN", "synthetic-token")
    monkeypatch.setattr(sys, "argv", ["identity_migration.py", "apply", "--inputs", str(inputs),
        "--manifest", str(root / "preview/manifest.json"), "--manifest-sha256", permit["manifest_sha256"],
        "--approval", str(approval), "--approval-sha256", digest(approval.read_bytes()),
        "--journal", str(journal), "--host", permit["host"]])
    assert migration.main() == 0
    assert "Migration complete: reviewed comments verified" in capsys.readouterr().out
    assert yaml.safe_load(journal.read_bytes())["status"] == "complete"


def test_v2_migration_apply_rollback_pending_persistence_failure(apply_case, monkeypatch):
    import cleanup_recovery
    state, permit, run, journal, original, case = apply_case
    write = cleanup_recovery.write_journal

    def fail(path, record, create=False):
        if record["rows"]["row-1"]["status"] == "pending":
            raise OSError("synthetic fsync failure")
        write(path, record, create=create)
    monkeypatch.setattr(cleanup_recovery, "write_journal", fail)
    with pytest.raises(OSError):
        run()
    assert not state.puts
    assert yaml.safe_load(journal.read_bytes())["rows"]["row-1"]["status"] == "prepared"


def test_v2_migration_apply_rollback_numeric_representation_drift(apply_case):
    state, permit, run, journal, original, case = apply_case

    def normalized(payload):
        state.rows[0]["comment"] = payload["comment"]
        state.rows[0]["quantity"] = 1.0
    state.put_effect = normalized
    with pytest.raises(RuntimeError, match="context changed"):
        run()
    assert len(state.puts) == 1
    assert yaml.safe_load(journal.read_bytes())["rows"]["row-1"]["status"] == "pending"


def test_v2_migration_apply_rollback_lock_excludes_writer(apply_case):
    from cleanup_recovery import lock_journal
    state, permit, run, journal, original, case = apply_case
    lock = lock_journal(journal)
    try:
        with pytest.raises(RuntimeError, match="already in use"):
            run()
    finally:
        os.close(lock)
    assert not state.calls and not journal.exists()


@pytest.mark.parametrize("field,value", [("quantity", Decimal("1.0000000000000000001")),
                                         ("fee", Decimal("1e1000"))])
def test_v2_migration_apply_rollback_transport_precision(field, value):
    row = exact_json(json.dumps(migration_row()).encode())
    row[field] = value
    with pytest.raises(RuntimeError, match="number cannot be preserved"):
        migration.comment_payload(row, "IBKR#v2#U1:TRADE:123")


@pytest.mark.parametrize("argument", ["manifest_sha256", "approval_sha256"])
def test_v2_migration_apply_rollback_unreviewed_hash(apply_case, argument):
    state, permit, run, journal, original, case = apply_case
    with pytest.raises(RuntimeError, match="Evidence hash changed"):
        run(**{argument: "0" * 64})
    assert not state.calls and not journal.exists()


@pytest.fixture
def rollback_case(apply_case, monkeypatch):
    state, permit, run, journal, original, case = apply_case
    root = case[0]

    def reverse(*, cli=False, **overrides):
        approval = root / "rollback-approval.json"
        approved = {**permit, "schema": "ibkr-migration-rollback-approval-v1",
                    "journal_sha256": digest(journal.read_bytes()), "settlements": {}}
        approved.update(overrides)
        approval.write_text(json.dumps(approved))
        if cli:
            monkeypatch.setenv("GHOST_TOKEN", "synthetic-token")
            monkeypatch.setattr(sys, "argv", ["identity_migration.py", "rollback", "--journal", str(journal),
                "--manifest", str(root / "preview/manifest.json"),
                "--manifest-sha256", permit["manifest_sha256"], "--approval", str(approval),
                "--approval-sha256", digest(approval.read_bytes()), "--host", permit["host"]])
            return migration.main()
        migration.rollback(journal, root / "preview/manifest.json", permit["manifest_sha256"],
                           approval, digest(approval.read_bytes()), permit["host"], "synthetic-token")

    def inspect_saved():
        snapshot = root / "resume.json"
        snapshot.write_text(json.dumps({"count": len(state.rows), "activities": state.rows}))
        return migration.inspect(journal, root / "preview/manifest.json", permit["manifest_sha256"],
                                 snapshot, digest(snapshot.read_bytes()))

    return state, run, reverse, inspect_saved, journal, original


def test_v2_migration_apply_rollback_only_preserves_new_imports(rollback_case):
    state, run, reverse, inspect_saved, journal, original = rollback_case
    run()
    new = migration_row(id="new", comment="IBKR#v2#U1:TRADE:new", userId="owner")
    state.rows.append(new)
    assert set(inspect_saved().values()) == {"converted"}
    reverse()
    assert state.rows == original + [new]
    assert [p["comment"] for p in state.puts[2:]] == ["IBKR#123", "IBKR#456"]
    for forward, backward in zip(state.puts[:2], state.puts[2:]):
        assert {k: v for k, v in forward.items() if k != "comment"} == {
            k: v for k, v in backward.items() if k != "comment"}
    assert yaml.safe_load(journal.read_bytes())["status"] == "rolled_back"
    assert set(inspect_saved().values()) == {"original"}
    reverse(write_count=0)
    assert len(state.puts) == 4


@pytest.mark.parametrize("field,value", [
    ("comment", "edited"), ("quantity", 1.0), ("unitPrice", 8), ("fee", 2),
    ("date", "2026-01-11T12:00:00Z"), ("accountId", "other"), ("userId", "other"),
    ("currency", "EUR"), ("type", "SELL"), ("tags", []), ("isDraft", True),
    ("assetProfile", {"symbol": "CHANGED", "dataSource": "YAHOO"}),
])
def test_v2_migration_apply_rollback_only_drift_blocks_all(rollback_case, field, value):
    state, run, reverse, inspect_saved, journal, original = rollback_case
    run()
    state.rows[0][field] = value
    assert inspect_saved()["row-1"] == "drift"
    with pytest.raises(RuntimeError):
        reverse()
    assert len(state.puts) == 2


@pytest.mark.parametrize("readback", ["original", "absent", "converted"])
def test_v2_migration_apply_rollback_only_delayed_request(rollback_case, readback):
    state, run, reverse, inspect_saved, journal, original = rollback_case
    def timeout(payload):
        raise requests.Timeout()
    state.put_effect = timeout
    with pytest.raises(RuntimeError):
        run()
    if readback == "absent":
        state.rows.pop(0)
    elif readback == "converted":
        state.rows[0]["comment"] = "IBKR#v2#U1:TRADE:123"
    before = journal.read_bytes()
    assert inspect_saved()["row-1"] == "uncertain:" + readback
    assert journal.read_bytes() == before
    with pytest.raises(RuntimeError, match="independent settlement"):
        reverse(write_count=1)
    assert len(state.puts) == 1
    # A delayed server completion after negative readback still remains uncertain.
    if readback == "original":
        state.rows[0]["comment"] = "IBKR#v2#U1:TRADE:123"
        assert inspect_saved()["row-1"] == "uncertain:converted"


@pytest.mark.parametrize("outcome", ["completed", "cancelled"])
def test_v2_migration_apply_rollback_only_partial_settlement(rollback_case, outcome):
    state, run, reverse, inspect_saved, journal, original = rollback_case
    def partial(payload):
        if len(state.puts) == 2:
            raise requests.Timeout()
        state.rows[0]["comment"] = payload["comment"]
    state.put_effect = partial
    with pytest.raises(RuntimeError):
        run()
    if outcome == "completed":
        state.rows[1]["comment"] = "IBKR#v2#U1:TRADE:456"
    state.put_effect = None
    reverse(write_count=2 if outcome == "completed" else 1, settlements={
        "row-2": {"direction": "apply", "outcome": outcome, "independent": True,
                  "evidence_ref": "synthetic-request-completion-or-cancellation"}})
    assert state.rows == original
    assert inspect_saved()["row-1"] == "original"


@pytest.mark.parametrize("effect", ["timeout", "normalization", "profile"])
def test_v2_migration_apply_rollback_only_reverse_uncertainty(rollback_case, effect):
    state, run, reverse, inspect_saved, journal, original = rollback_case
    run()
    def fail(payload):
        if effect == "timeout":
            raise requests.Timeout()
        state.rows[0]["comment"] = payload["comment"]
        if effect == "normalization":
            state.rows[0]["quantity"] = 1.0
        else:
            state.rows[0]["assetProfile"]["currency"] = "EUR"
    state.put_effect = fail
    with pytest.raises(RuntimeError):
        reverse()
    assert yaml.safe_load(journal.read_bytes())["rows"]["row-1"]["rollback_status"] == "pending"
    assert inspect_saved()["row-1"].startswith("uncertain:")
    with pytest.raises(RuntimeError, match="independent settlement"):
        reverse()
    assert len(state.puts) == 3


@pytest.mark.parametrize("key,value", [("writers_stopped", False), ("requests_settled", False),
    ("backup_ref", ""), ("owner_id", "other"), ("write_count", 1), ("batch_size", 0),
    ("pause_seconds", -1), ("journal_sha256", "0" * 64), ("manifest_sha256", "0" * 64),
    ("destination_version", "other"), ("destination_image", "other")])
def test_v2_migration_apply_rollback_only_approval(rollback_case, key, value):
    state, run, reverse, inspect_saved, journal, original = rollback_case
    run()
    with pytest.raises(RuntimeError):
        reverse(**{key: value})
    assert len(state.puts) == 2


def test_v2_migration_apply_rollback_only_actual_cli(rollback_case, monkeypatch, capsys):
    state, run, reverse, inspect_saved, journal, original = rollback_case
    run()
    root = journal.parent
    record = yaml.safe_load(journal.read_bytes())
    manifest = root / "preview/manifest.json"
    inspect_saved()
    snapshot = root / "resume.json"
    before = len(state.calls)
    monkeypatch.setattr(sys, "argv", ["identity_migration.py", "inspect", "--journal", str(journal),
        "--manifest", str(manifest), "--manifest-sha256", record["manifest_sha256"],
        "--snapshot", str(snapshot), "--snapshot-sha256", digest(snapshot.read_bytes())])
    assert migration.main() == 0
    assert json.loads(capsys.readouterr().out) == {"row-1": "converted", "row-2": "converted"}
    assert len(state.calls) == before
    # Replay the public rollback CLI against synthetic HTTP and isolated journal.
    assert reverse(cli=True) == 0
    assert "Rollback complete: journal-owned comments restored" in capsys.readouterr().out
    approval = root / "rollback-approval.json"
    monkeypatch.setenv("GHOST_TOKEN", "synthetic-token")
    # The already-consumed approval must fail before HTTP and cannot replay writes.
    monkeypatch.setattr(sys, "argv", ["identity_migration.py", "rollback", "--journal", str(journal),
        "--manifest", str(manifest), "--manifest-sha256", record["manifest_sha256"],
        "--approval", str(approval), "--approval-sha256", digest(approval.read_bytes()),
        "--host", "https://ghostfolio.example.test"])
    with pytest.raises(SystemExit) as error:
        migration.main()
    assert error.value.code == 1
    assert "Rollback refused" in capsys.readouterr().err


@pytest.mark.parametrize("outcome", ["completed", "cancelled"])
def test_v2_migration_apply_rollback_only_resume_reverse(rollback_case, outcome):
    state, run, reverse, inspect_saved, journal, original = rollback_case
    run()
    def timeout(payload):
        raise requests.Timeout()
    state.put_effect = timeout
    with pytest.raises(RuntimeError):
        reverse()
    if outcome == "completed":
        state.rows[0]["comment"] = original[0]["comment"]
    state.put_effect = None
    reverse(write_count=1 if outcome == "completed" else 2, settlements={
        "row-1": {"direction": "rollback", "outcome": outcome, "independent": True,
                  "evidence_ref": "synthetic-independent-reverse-request-proof"}})
    assert state.rows == original
    assert set(inspect_saved().values()) == {"original"}
    assert yaml.safe_load(journal.read_bytes())["status"] == "rolled_back"


@pytest.mark.parametrize("mutation", ["preimage", "replacement", "rows", "status"])
def test_v2_migration_apply_rollback_only_journal_binding(rollback_case, mutation):
    state, run, reverse, inspect_saved, journal, original = rollback_case
    run()
    record = yaml.safe_load(journal.read_bytes())
    if mutation == "preimage":
        record["rows"]["row-1"]["preimage"]["fee"] = "2"
    elif mutation == "replacement":
        record["rows"]["row-1"]["new_comment"] = "IBKR#v2#U1:TRADE:other"
    elif mutation == "rows":
        record["rows"].pop("row-2")
    else:
        record["rows"]["row-1"]["status"] = "unknown"
    journal.write_text(yaml.safe_dump(record))
    with pytest.raises(RuntimeError):
        reverse()
    assert len(state.puts) == 2


def test_v2_migration_apply_rollback_only_concurrent_and_persistence(rollback_case, monkeypatch):
    import cleanup_recovery
    state, run, reverse, inspect_saved, journal, original = rollback_case
    run()
    write = cleanup_recovery.write_journal
    def fail(path, record, create=False):
        if record["status"] == "rollback_in_progress":
            raise OSError("synthetic rollback persistence failure")
        write(path, record, create=create)
    monkeypatch.setattr(cleanup_recovery, "write_journal", fail)
    with pytest.raises(OSError):
        reverse()
    assert len(state.puts) == 2
    lock = cleanup_recovery.lock_journal(journal)
    try:
        with pytest.raises(RuntimeError, match="already in use"):
            reverse()
    finally:
        os.close(lock)


@pytest.mark.parametrize("proof", [
    {"direction": "rollback", "outcome": "completed", "independent": True, "evidence_ref": "proof"},
    {"direction": "apply", "outcome": "completed", "independent": False, "evidence_ref": "GET"},
    {"direction": "apply", "outcome": "completed", "independent": True, "evidence_ref": ""},
    {"direction": "apply", "outcome": "completed", "independent": True, "evidence_ref": "proof"},
])
def test_v2_migration_apply_rollback_only_rejects_weak_or_contradictory_proof(rollback_case, proof):
    state, run, reverse, inspect_saved, journal, original = rollback_case
    def timeout(payload):
        raise requests.Timeout()
    state.put_effect = timeout
    with pytest.raises(RuntimeError):
        run()
    before = journal.read_bytes()
    with pytest.raises(RuntimeError):
        reverse(write_count=0, settlements={"row-1": proof})
    assert journal.read_bytes() == before
    assert len(state.puts) == 1


def test_v2_migration_apply_rollback_only_late_drift(rollback_case):
    state, run, reverse, inspect_saved, journal, original = rollback_case
    run()
    new = migration_row(id="new", comment="IBKR#v2#U1:TRADE:new", userId="owner")
    state.rows.append(new)
    start_gets = state.gets
    def drift():
        if state.gets == start_gets + 3:
            new["fee"] = 8
    state.before_get = drift
    with pytest.raises(RuntimeError, match="context changed"):
        reverse()
    assert len(state.puts) == 2


@pytest.mark.parametrize("value", [None, [], "invalid", 42, True])
def test_v2_migration_apply_rollback_only_invalid_approval_root(rollback_case, value, monkeypatch, capsys):
    state, run, reverse, inspect_saved, journal, original = rollback_case
    run()
    approval = journal.parent / "malformed-approval.json"
    approval.write_text(json.dumps(value))
    manifest = journal.parent / "preview/manifest.json"
    before = journal.read_bytes()
    monkeypatch.setenv("GHOST_TOKEN", "synthetic-token")
    monkeypatch.setattr(sys, "argv", ["identity_migration.py", "rollback", "--journal", str(journal),
        "--manifest", str(manifest), "--manifest-sha256", digest(manifest.read_bytes()),
        "--approval", str(approval), "--approval-sha256", digest(approval.read_bytes()),
        "--host", "https://ghostfolio.example.test"])
    with pytest.raises(SystemExit) as error:
        migration.main()
    assert error.value.code == 1
    assert "Rollback refused (RuntimeError)" in capsys.readouterr().err
    assert journal.read_bytes() == before
    assert len(state.puts) == 2
