"""Synthetic migration boundary checks; no service or credential access."""

import json
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
    assert len(manifest["pending"]) == 2
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
