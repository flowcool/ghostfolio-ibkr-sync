"""Synthetic cleanup regressions; all unmocked HTTP is forbidden."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

import cleanup_dividends
import cleanup_duplicates


@pytest.fixture(params=[cleanup_duplicates, cleanup_dividends], ids=["trades", "dividends"])
def tool(request, monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected HTTP call in cleanup test")
    monkeypatch.setattr(request.param.requests.sessions.Session, "request", forbidden)
    monkeypatch.chdir(tmp_path)
    return request.param


def activity(tool, ident="synced", symbol="AAPL", profile_key="assetProfile"):
    dividend = tool is cleanup_dividends
    return {
        "id": ident, "accountId": "synthetic-account", "currency": "USD",
        "type": "DIVIDEND" if dividend else "BUY", "quantity": 1,
        "unitPrice": 10, "fee": 0, "date": "2026-10-01T00:00:00Z",
        "comment": ("dividend#US0378331005#2026-10-01" if dividend else "IBKR#synthetic")
                   if ident == "synced" else None,
        profile_key: {"symbol": symbol, "dataSource": "YAHOO"},
    }


def run_cleanup(tool, monkeypatch, activities, apply=False):
    monkeypatch.setattr(tool, "load_config", lambda: {"ghost_host": "http://synthetic", "ghost_token": "fake"})
    monkeypatch.setattr(tool, "verify_endpoints", lambda cfg: None)
    monkeypatch.setattr(tool, "fetch_all_activities", lambda cfg: deepcopy(activities))
    monkeypatch.setattr(tool.sys, "argv", ["cleanup"] + (["--apply"] if apply else []))
    tool.main()


@pytest.mark.parametrize("profile_key", ["assetProfile", "SymbolProfile"])
def test_genuine_duplicates_remain_detectable(tool, monkeypatch, caplog, profile_key):
    caplog.set_level("INFO")
    run_cleanup(tool, monkeypatch, [activity(tool, profile_key=profile_key),
                                   activity(tool, "manual", profile_key=profile_key)])
    assert any("Matched pairs" in r.message and r.message.endswith(": 1") for r in caplog.records)


def test_current_profiles_do_not_collapse_distinct_assets(tool, monkeypatch, caplog):
    caplog.set_level("INFO")
    run_cleanup(tool, monkeypatch, [activity(tool), activity(tool, "manual", "MSFT")])
    assert any("Matched pairs" in r.message and r.message.endswith(": 0") for r in caplog.records)


def test_current_profile_takes_precedence_over_legacy(tool):
    a = activity(tool)
    a["SymbolProfile"] = {"symbol": "MSFT", "dataSource": "MANUAL"}
    assert tool.symbol_of(a) == "AAPL"


def test_out_of_scope_cash_activity_without_profile_does_not_block_cleanup(tool, monkeypatch, caplog):
    caplog.set_level("INFO")
    run_cleanup(tool, monkeypatch, [activity(tool), {"id": "cash", "type": "ITEM"},
                                   activity(tool, "manual")])
    assert any("Matched pairs" in r.message and r.message.endswith(": 1") for r in caplog.records)


@pytest.mark.parametrize("invalid", [None, {}, [], {"symbol": ""}, {"symbol": " "}, {"symbol": 123}])
@pytest.mark.parametrize("apply", [False, True])
def test_invalid_profile_aborts_before_planning_or_writes(tool, monkeypatch, caplog, invalid, apply):
    caplog.set_level("INFO")
    a = activity(tool, "manual")
    a["assetProfile"] = invalid
    a["SymbolProfile"] = {"symbol": "AAPL", "dataSource": "YAHOO"}
    with pytest.raises(RuntimeError, match="profile"):
        run_cleanup(tool, monkeypatch, [activity(tool), a], apply=apply)
    assert not any("Matched pairs" in r.message for r in caplog.records)


def test_missing_profile_aborts_before_planning(tool, monkeypatch):
    a = activity(tool)
    del a["assetProfile"]
    with pytest.raises(RuntimeError, match="profile"):
        run_cleanup(tool, monkeypatch, [a, activity(tool, "manual")])


@pytest.mark.parametrize("profile_key", ["assetProfile", "SymbolProfile"])
def test_comment_payload_uses_resolved_profile(tool, monkeypatch, profile_key):
    captured = []
    monkeypatch.setattr(tool.requests, "put", lambda *args, **kwargs:
                        captured.append(kwargs["json"]) or SimpleNamespace(status_code=200))
    a = activity(tool, "manual", profile_key=profile_key)
    if profile_key == "assetProfile":
        a["SymbolProfile"] = {"symbol": "MSFT", "dataSource": "MANUAL"}
    assert tool.put_comment({"ghost_host": "http://synthetic", "ghost_token": "fake"}, a, "tag", False)
    assert captured[0]["symbol"] == "AAPL"
    assert captured[0]["dataSource"] == "YAHOO"


def test_comment_update_rejects_missing_source_without_http(tool):
    a = activity(tool, "manual")
    del a["assetProfile"]["dataSource"]
    with pytest.raises(RuntimeError, match="data source"):
        tool.put_comment({"ghost_host": "http://synthetic", "ghost_token": "fake"}, a, "tag", False)


def test_excluded_financial_type_with_invalid_profile_does_not_block(tool, monkeypatch, caplog):
    caplog.set_level("INFO")
    excluded = {"id": "excluded", "type": "BUY" if tool is cleanup_dividends else "DIVIDEND",
                "assetProfile": None}
    run_cleanup(tool, monkeypatch, [activity(tool), excluded, activity(tool, "manual")])
    assert any("Matched pairs" in r.message and r.message.endswith(": 1") for r in caplog.records)


def two_pairs(tool):
    first = [activity(tool), activity(tool, "manual")]
    second = [deepcopy(a) for a in first]
    for a in second:
        a["id"] += "-2"
        a["assetProfile"]["symbol"] = "MSFT"
    return first + second


def test_later_missing_source_aborts_before_any_pair_mutation(tool, monkeypatch, caplog):
    caplog.set_level("INFO")
    acts = two_pairs(tool)
    del acts[-1]["assetProfile"]["dataSource"]
    writes = []
    monkeypatch.setattr(tool, "put_comment", lambda *args, **kwargs: writes.append("PUT") or True)
    monkeypatch.setattr(tool, "delete_activity", lambda *args, **kwargs: writes.append("DELETE") or True)
    with pytest.raises(RuntimeError, match="data source"):
        run_cleanup(tool, monkeypatch, acts, apply=True)
    assert writes == []
    assert not any("Matched pairs" in r.message for r in caplog.records)


@pytest.mark.parametrize("changed", ["missing-source", "changed-source", "changed-symbol", "invalid-profile",
                                   "non-object", "invalid-json"])
def test_later_invalid_fresh_profile_is_controlled_after_first_pair(tool, monkeypatch, changed):
    acts = two_pairs(tool)
    second = deepcopy(acts[-1])
    if changed == "missing-source":
        del second["assetProfile"]["dataSource"]
    elif changed == "changed-source":
        second["assetProfile"]["dataSource"] = "MANUAL"
    elif changed == "changed-symbol":
        second["assetProfile"]["symbol"] = "OTHER"
    elif changed == "invalid-profile":
        second["assetProfile"] = None
    elif changed == "non-object":
        second = None
    fresh = iter([deepcopy(acts[1]), second])
    def response(*args, **kwargs):
        obj = next(fresh)
        def json_body():
            if changed == "invalid-json" and obj["id"].endswith("-2"):
                raise ValueError("invalid JSON")
            return obj
        return SimpleNamespace(status_code=200, json=json_body)
    monkeypatch.setattr(tool.requests, "get", response)
    writes = []
    monkeypatch.setattr(tool, "put_comment", lambda cfg, a, *args, **kwargs: writes.append(("PUT", a["id"])) or True)
    monkeypatch.setattr(tool, "delete_activity", lambda cfg, ident, *args, **kwargs: writes.append(("DELETE", ident)) or True)
    with pytest.raises(SystemExit) as exc:
        run_cleanup(tool, monkeypatch, acts, apply=True)
    assert exc.value.code == 1
    assert writes == [("PUT", "manual"), ("DELETE", "synced")]
