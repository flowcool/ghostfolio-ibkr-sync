"""Offline correction review acceptance. Sources and destinations are synthetic."""
import os
from copy import deepcopy
from decimal import Decimal
from _sync_helpers import report, trade_xml, div_xml, ISIN_KO
import json
import requests

import pytest

from ghostfolio_ibkr_sync import activity_review as review


def test_review_config_private_file_literal_yes_and_edit_detection(tmp_path):
    path = tmp_path / "review.yaml"
    state = review.open_review(str(path), [])
    try:
        assert not path.exists()
        review.publish_review(state, {"version": 1, "proposals": {}})
        assert path.stat().st_mode & 0o777 == 0o600
        path.write_text("# operator edit\nversion: 1\nproposals: {}\n")
        with pytest.raises(RuntimeError, match="changed"):
            review.publish_review(state, {"version": 1, "proposals": {}})
    finally:
        review.close_review(state)
    assert review.read_yaml(b"approve: yes")["approve"] == "yes"
    assert review.read_yaml(b"approve: true")["approve"] is True


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "permissions", "parent"])
def test_review_config_refuses_unsafe_paths(tmp_path, kind):
    source = tmp_path / "mapping.yaml"
    source.write_text("source: protected")
    source.chmod(0o600)
    path = tmp_path / "review.yaml"
    if kind == "symlink":
        path.symlink_to(source)
    elif kind == "hardlink":
        os.link(source, path)
    elif kind == "permissions":
        path.write_text("version: 1\nproposals: {}\n")
        path.chmod(0o644)
    else:
        path = tmp_path / "absent" / "review.yaml"
    with pytest.raises(RuntimeError):
        review.open_review(str(path), [str(source)])
    assert source.read_text() == "source: protected"


def test_review_config_duplicate_keys_and_no_boolean_yes_coercion():
    with pytest.raises(RuntimeError):
        review.read_yaml(b"version: 1\nversion: 2\n")
    assert review.read_yaml(b"approve: 'yes'")["approve"] == "yes"


@pytest.mark.parametrize("activity_type,kind", [("BUY", "TRADE"), ("SELL", "TRADE"), ("DIVIDEND", "DIVIDEND")])
def test_review_reference_notes_survive_disabled_reader(activity_type, kind):
    from ghostfolio_ibkr_sync.ghostfolio import index_existing_activities, parse_versioned_activity_identity
    marker = f"IBKR#v2#U1:{kind}:T1"
    comment = marker + "\n\nMy café 🐢\nsecond line"
    assert parse_versioned_activity_identity(comment, activity_type) == ("U1", kind, "T1")
    row = {"id": "row1", "type": activity_type, "quantity": 3, "accountId": "acc",
           "comment": comment, "date": "2026-08-01T00:00:00Z",
           "assetProfile": {"symbol": "KO", "dataSource": "YAHOO"}}
    _, _, positions = index_existing_activities({"activities": [row], "count": 1})
    assert positions["versioned_identities"] == {("U1", marker)}


@pytest.mark.parametrize("suffix", ["\nnotes", "\n\n", "\n\n\nnotes", "\n\nIBKR#v2#U1:TRADE:T2"])
def test_review_reference_rejects_ambiguous_reserved_positions(suffix):
    from ghostfolio_ibkr_sync.ghostfolio import parse_versioned_activity_identity
    with pytest.raises(RuntimeError):
        parse_versioned_activity_identity("IBKR#v2#U1:TRADE:T1" + suffix, "BUY")




def source_events(xml=None, account="U1", target="acc", mapping=None):
    return review.source_events(xml or report(trade_xml("T1")), account, target, mapping or {})


def destination(comment=None, **changes):
    row = {"id": "row1", "accountId": "acc", "userId": "owner", "type": "BUY",
           "date": "2026-08-01T10:00:00Z", "currency": "USD", "quantity": Decimal("1"),
           "unitPrice": Decimal("60"), "fee": Decimal("1"), "comment": comment,
           "createdAt": "2026-08-01T12:00:00.000Z", "updatedAt": "2026-08-01T12:00:00.000Z",
           "accountUserId": "owner", "symbolProfileId": "profile1",
           "account": {"id": "acc", "balance": Decimal("123"), "updatedAt": "2026-08-01T12:00:00Z"},
           "value": Decimal("60"), "valueInBaseCurrency": Decimal("54"),
           "feeInBaseCurrency": Decimal("0.9"), "feeInAssetProfileCurrency": Decimal("1"),
           "unitPriceInAssetProfileCurrency": Decimal("60"),
           "tags": [{"id": "tag1", "name": "Keep"}],
           "assetProfile": {"id": "profile1", "symbol": "KO", "isin": ISIN_KO, "dataSource": "YAHOO"}}
    row.update(changes)
    return row


def test_review_candidates_exact_difference_and_manual_notes():
    events = source_events()
    marker = "IBKR#v2#U1:TRADE:T1"
    exact = destination(marker, date="2020-01-01T00:00:00Z")
    proposals, held = review.refresh_proposals({}, events, [exact], {"U1": "acc"})
    proposal = next(iter(proposals.values()))
    assert proposal["match reason"] == "exact reference"
    assert proposal["proposed values"]["quantity"] == "10"
    assert proposal["changed fields"] == ["date", "quantity"]
    assert held == {marker}
    manual = destination("My café 🐢")
    proposals, _ = review.refresh_proposals({}, events, [manual], {"U1": "acc"})
    assert next(iter(proposals.values()))["proposed values"]["comment"] == marker + "\n\nMy café 🐢"


@pytest.mark.parametrize("days,eligible", [(-3, False), (-2, True), (2, True), (3, False)])
def test_review_candidates_trade_utc_window_edges(days, eligible):
    from datetime import datetime, timedelta, UTC
    row = destination(date=(datetime(2026, 8, 1, 10, tzinfo=UTC) + timedelta(days=days)).isoformat())
    proposals, _ = review.refresh_proposals({}, source_events(), [row], {"U1": "acc"})
    assert bool(proposals) is eligible


@pytest.mark.parametrize("change", [{"accountId": "other"}, {"type": "SELL"}, {"currency": "EUR"},
                                    {"comment": "IBKR#v2#U1:TRADE:T2"}, {"isDraft": True}])
def test_review_candidates_exclude_ineligible_rows(change):
    proposals, _ = review.refresh_proposals({}, source_events(), [destination(**change)], {"U1": "acc"})
    assert not proposals


def test_review_source_scope_legacy_global_requires_historical_proof():
    proposals, _ = review.refresh_proposals({}, source_events(), [destination("IBKR#T1")], {"U1": "acc"})
    proposal = next(iter(proposals.values()))
    assert proposal["status"] == "historical cross-account coverage unavailable"
    assert proposal["actionable"] is False


def test_review_candidates_dividend_uses_one_action_and_three_day_window():
    events = source_events(report(divs=div_xml()))
    assert list(events) == ["IBKR#v2#U1:DIVIDEND:A1"]
    row = destination(type="DIVIDEND", date="2026-07-18T00:00:00Z")
    proposals, _ = review.refresh_proposals({}, events, [row], {"U1": "acc"})
    assert len(proposals) == 1
    assert next(iter(proposals.values()))["proposed values"]["unitPrice"] == "0.25"



def preview(rows=None):
    return review.refresh_proposals({}, source_events(), rows or [destination()], {"U1": "acc"})[0]


def test_review_approval_refresh_stale_unavailable_and_deleted_entries():
    proposals = preview()
    key = next(iter(proposals))
    proposals[key]["approve"] = "yes"
    refreshed, held = review.refresh_proposals(proposals, source_events(), [destination()], {"U1": "acc"})
    assert refreshed[key]["approve"] == "yes" and held
    absent, _ = review.refresh_proposals(refreshed, {}, [destination()], {"U1": "acc"})
    assert absent[key]["status"] == "source unavailable" and absent[key]["approve"] == "yes"
    restored, _ = review.refresh_proposals(absent, source_events(), [destination()], {"U1": "acc"})
    assert restored[key]["approve"] == "yes"
    changed, _ = review.refresh_proposals(restored, source_events(), [destination(quantity=Decimal("2"))], {"U1": "acc"})
    assert changed[key]["approve"] is None
    rediscovered = preview()
    assert rediscovered[key]["approve"] is None


def test_review_candidate_release_requires_positive_assignment_and_new_discovery():
    old = preview()
    assigned = destination("IBKR#v2#U1:TRADE:OTHER")
    proposals, held = review.refresh_proposals(old, source_events(), [assigned], {"U1": "acc"})
    assert proposals == {} and held == set()
    missing, held = review.refresh_proposals(old, source_events(), [], {"U1": "acc"})
    assert held == {"IBKR#v2#U1:TRADE:T1"}
    assert next(iter(missing.values()))["actionable"] is False
    fresh, held = review.refresh_proposals(old, source_events(), [assigned, destination(id="new")], {"U1": "acc"})
    assert len(fresh) == 1 and next(iter(fresh.values()))["activity id"] == "new"
    assert held


@pytest.mark.parametrize("approval", [True, False, "true", "no", "y", "YES", 1, ""])
def test_review_approval_non_yes_choice_skips_bound_account(approval):
    old = preview()
    next(iter(old.values()))["approve"] = approval
    approved, blocked = review.approved_proposals(old)
    assert approved == [] and blocked == set()


def test_review_approval_one_source_two_targets_refused_before_dispatch():
    old = preview([destination(), destination(id="row2")])
    for item in old.values():
        item["approve"] = "yes"
    approved, blocked = review.approved_proposals(old)
    assert approved == [] and blocked == {"acc"}




class ReviewServer:
    """HTTP boundary with a mutable synthetic destination and recorded wire writes."""
    def __init__(self, monkeypatch, rows=None, outcome="success"):
        self.rows = deepcopy(rows or [destination()])
        self.writes = []
        self.outcome = outcome
        self.reads = 0
        self.waits = []
        monkeypatch.setattr(requests, "get", self.get)
        monkeypatch.setattr(requests, "put", self.put)
        monkeypatch.setattr(requests, "post", self.unexpected)
        monkeypatch.setattr(requests, "delete", self.unexpected)
        monkeypatch.setattr(review.time, "sleep", self.waits.append)

    def unexpected(self, *args, **kwargs):
        pytest.fail("Unexpected financial request")

    def get(self, url, **kwargs):
        assert kwargs["allow_redirects"] is False
        self.reads += 1
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"activities": self.rows, "count": len(self.rows)}, default=float).encode()
        return response

    def put(self, url, **kwargs):
        assert kwargs["allow_redirects"] is False and kwargs["timeout"]
        payload = kwargs["json"]
        self.writes.append(deepcopy(payload))
        if self.outcome != "unchanged":
            row = next(row for row in self.rows if row["id"] == payload["id"])
            row.update({key: Decimal(str(value)) if key in review.NUMBERS else value
                        for key, value in payload.items() if key in review.REPLACED and key != "symbol"})
            row["assetProfile"]["symbol"] = payload["symbol"]
            row["updatedAt"] = "2026-08-02T00:00:00Z"
            row["value"] = row["quantity"] * row["unitPrice"]
            row["valueInBaseCurrency"] = row["value"] * Decimal("0.91")
            row["feeInBaseCurrency"] = row["fee"] * Decimal("0.91")
            row["unitPriceInAssetProfileCurrency"] = row["unitPrice"]
            row["feeInAssetProfileCurrency"] = row["fee"]
        if self.outcome in ("timeout", "unchanged"):
            raise requests.Timeout("synthetic timeout")
        response = requests.Response()
        response.status_code = 200
        return response


def run_review(tmp_path, monkeypatch, *, outcome="success", approval="yes", dry_run=False, rows=None):
    path = tmp_path / "review.yaml"
    server = ReviewServer(monkeypatch, rows, outcome)
    proposals = preview(rows)
    for item in proposals.values():
        item["approve"] = approval
    path.write_text(__import__("yaml").safe_dump(review.encode_review({"version": 1, "proposals": proposals})))
    path.chmod(0o600)
    state = review.open_review(str(path), [])
    config = {"ghost_host": "http://ghost", "ghost_token": "secret", "dry_run": dry_run,
              "activity_review_file": str(path)}
    # This is an isolated execution-budget fixture, not image qualification.
    monkeypatch.setattr(review, "QUALIFIED_EXECUTION", ("synthetic-image", 2, 0.5))
    blocked, held = review.process_review(state, config, source_events(), {"U1": "acc"})
    return server, state, config, blocked, held


def test_review_replacement_journal_then_exact_readback(tmp_path, monkeypatch):
    server, state, _, blocked, held = run_review(tmp_path, monkeypatch)
    try:
        assert not blocked and not held
        assert len(server.writes) == 1
        payload = server.writes[0]
        assert set(payload) == {*review.REPLACED, "id", "accountId", "dataSource", "tags"}
        assert payload["quantity"] == 10 and payload["tags"] == ["tag1"]
        assert state["document"]["proposals"] == {}
        entry = next(iter(state["journal"]["entries"].values()))
        assert entry["status"] == "confirmed" and entry["before"]["quantity"] == "1"
        assert entry["after"]["quantity"] == "10"
    finally:
        review.close_review(state)


def test_review_recovery_timeout_applied_is_confirmed_without_retry(tmp_path, monkeypatch):
    server, state, _, blocked, held = run_review(tmp_path, monkeypatch, outcome="timeout")
    try:
        assert not blocked and not held and len(server.writes) == 1
        assert next(iter(state["journal"]["entries"].values()))["status"] == "confirmed"
    finally:
        review.close_review(state)


def test_review_recovery_permanent_before_restart_and_manual_resolution(tmp_path, monkeypatch):
    server, state, config, blocked, held = run_review(tmp_path, monkeypatch, outcome="unchanged")
    path = state["path"]
    assert blocked == {"acc"} and held and server.waits == [2, 5, 10]
    assert len(server.writes) == 1
    review.close_review(state)
    state = review.open_review(str(path), [])
    try:
        blocked, _ = review.process_review(state, config, source_events(), {"U1": "acc"})
        assert blocked == {"acc"} and len(server.writes) == 1
        entry = next(iter(state["journal"]["entries"].values()))
        server.rows = [deepcopy(entry["after"])]
        # Convert saved decimal evidence back into synthetic JSON numbers.
        for field in review.NUMBERS:
            server.rows[0][field] = Decimal(server.rows[0][field])
        blocked, held = review.process_review(state, config, source_events(), {"U1": "acc"})
        assert blocked == set() and held == set() and len(server.writes) == 1
    finally:
        review.close_review(state)


def test_review_simulation_keeps_yes_and_has_no_applied_journal(tmp_path, monkeypatch):
    server, state, _, blocked, held = run_review(tmp_path, monkeypatch, dry_run=True)
    try:
        assert not server.writes and not blocked and held
        assert next(iter(state["document"]["proposals"].values()))["approve"] == "yes"
        assert not state["journal_path"].exists()
    finally:
        review.close_review(state)



def test_review_replacement_all_types_preserve_tags_notes_and_full_instants(tmp_path, monkeypatch):
    from ghostfolio_ibkr_sync import sync
    for side in ("BUY", "SELL", "DIVIDEND"):
        directory = tmp_path / side
        directory.mkdir()
        xml = report(divs=div_xml()) if side == "DIVIDEND" else report(trade_xml("T1", side))
        events = source_events(xml)
        day = "2026-07-15T00:00:00Z" if side == "DIVIDEND" else "2026-08-01T10:00:00Z"
        row = destination("My notes", type=side, date=day)
        server = ReviewServer(monkeypatch, [row])
        path = directory / "review.yaml"
        state = review.open_review(str(path), [])
        config = {"ghost_host": "http://ghost", "ghost_token": "t", "dry_run": False, "activity_review_file": str(path)}
        monkeypatch.setattr(review, "QUALIFIED_EXECUTION", ("synthetic", 2, 0))
        try:
            review.process_review(state, config, events, {"U1": "acc"})
            proposals = deepcopy(state["document"])
            for item in proposals["proposals"].values():
                item["approve"] = "yes"
            review.publish_review(state, proposals)
            blocked, held = review.process_review(state, config, events, {"U1": "acc"})
            assert not blocked and not held
            assert len(server.writes) == 1
            assert server.rows[0]["comment"].endswith("\n\nMy notes")
            assert server.rows[0]["tags"] == [{"id": "tag1", "name": "Keep"}]
            assert server.rows[0]["userId"] == "owner"
        finally:
            review.close_review(state)


def test_review_persistence_second_process_lock_and_atomic_failure(tmp_path, monkeypatch):
    state = review.open_review(str(tmp_path / "review.yaml"), [])
    try:
        with pytest.raises((RuntimeError, OSError)):
            review.open_review(str(state["path"]), [])
        review.publish_review(state, {"version": 1, "proposals": {}})
        original = state["path"].read_bytes()
        def fail(*args):
            raise OSError("synthetic disk failure")
        monkeypatch.setattr(os, "replace", fail)
        with pytest.raises(OSError):
            review.publish_review(state, {"version": 1, "proposals": {"x": {}}})
        assert state["path"].read_bytes() == original
    finally:
        review.close_review(state)


def test_review_qualification_no_invented_live_budget(tmp_path, monkeypatch):
    server, state, config, _, _ = run_review(tmp_path, monkeypatch, dry_run=True)
    config["dry_run"] = False
    monkeypatch.setattr(review, "QUALIFIED_EXECUTION", None)
    try:
        blocked, held = review.process_review(state, config, source_events(), {"U1": "acc"})
        assert not blocked and held and not server.writes
        assert next(iter(state["document"]["proposals"].values()))["approve"] == "yes"
    finally:
        review.close_review(state)


def test_review_simulation_cannot_resolve_pending_journal(tmp_path, monkeypatch):
    server, state, config, blocked, held = run_review(tmp_path, monkeypatch, outcome="unchanged")
    entry = next(iter(state["journal"]["entries"].values()))
    before_journal = state["journal_path"].read_bytes()
    server.rows = [deepcopy(entry["after"])]
    for field in review.NUMBERS:
        server.rows[0][field] = Decimal(server.rows[0][field])
    config["dry_run"] = True
    try:
        blocked, held = review.process_review(state, config, source_events(), {"U1": "acc"})
        assert blocked == {"acc"} and held and len(server.writes) == 1
        assert state["journal_path"].read_bytes() == before_journal
        assert next(iter(state["document"]["proposals"].values()))["approve"] == "yes"
    finally:
        review.close_review(state)


def test_review_replacement_exact_numeric_and_date_equivalence():
    row = destination("IBKR#v2#U1:TRADE:T1", quantity=Decimal("10.000"), date="2026-08-01T12:00:00.000+02:00")
    proposals, held = review.refresh_proposals({}, source_events(), [row], {"U1": "acc"})
    assert proposals == {} and held == set()
    row["date"] = "2026-08-01T10:00:01Z"
    proposals, _ = review.refresh_proposals({}, source_events(), [row], {"U1": "acc"})
    assert next(iter(proposals.values()))["changed fields"] == ["date"]


def test_review_persistence_reverse_only_unchanged_confirmed_rows(tmp_path, monkeypatch):
    server, state, _, _, _ = run_review(tmp_path, monkeypatch)
    try:
        entry = next(iter(state["journal"]["entries"].values()))
        reverse = review.inspect_reverse(entry, server.rows[0])
        assert reverse["quantity"] == 1 and reverse["comment"] is None
        server.rows[0]["quantity"] = Decimal("99")
        with pytest.raises(RuntimeError):
            review.inspect_reverse(entry, server.rows[0])
        assert len(server.writes) == 1
    finally:
        review.close_review(state)



def test_review_execution_budget_sequential_limit_delay_and_deferred_yes(tmp_path, monkeypatch):
    xml = report("".join(trade_xml(f"T{i}", date=f"202608{day:02};100000") for i, day in [(1, 1), (2, 10), (3, 20)]))
    events = source_events(xml)
    rows = [destination(id=f"row{i}", date=f"2026-08-{day:02}T10:00:00Z") for i, day in [(1, 1), (2, 10), (3, 20)]]
    server = ReviewServer(monkeypatch, rows)
    proposals, _ = review.refresh_proposals({}, events, rows, {"U1": "acc"})
    for item in proposals.values():
        item["approve"] = "yes"
    path = tmp_path / "review.yaml"
    path.write_text(__import__("yaml").safe_dump(review.encode_review({"version": 1, "proposals": proposals})))
    path.chmod(0o600)
    state = review.open_review(str(path), [])
    monkeypatch.setattr(review, "QUALIFIED_EXECUTION", ("synthetic", 2, 0.5))
    config = {"ghost_host": "http://ghost", "ghost_token": "t", "dry_run": False, "activity_review_file": str(path)}
    try:
        blocked, held = review.process_review(state, config, events, {"U1": "acc"})
        assert not blocked and len(held) == 1 and len(server.writes) == 2
        assert server.waits == [0.5]
        assert len(state["document"]["proposals"]) == 1
        assert next(iter(state["document"]["proposals"].values()))["approve"] == "yes"
        assert all(entry["status"] == "confirmed" for entry in state["journal"]["entries"].values())
    finally:
        review.close_review(state)



class RuntimeServer(ReviewServer):
    def __init__(self, monkeypatch, rows=None, outcome="success", accounts=None):
        super().__init__(monkeypatch, rows, outcome)
        self.accounts = accounts or [{"id": "acc", "name": "Account", "currency": "USD", "balance": 0}]
        self.cash = []

    def get(self, url, **kwargs):
        if "/api/v1/account" in url:
            data = ({"accounts": self.accounts} if url.endswith("/account")
                    else next(account for account in self.accounts if url.endswith("/" + account["id"])))
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps(data).encode()
            return response
        return super().get(url, **kwargs)

    def put(self, url, **kwargs):
        if "/api/v1/account/" in url:
            self.cash.append(kwargs["json"])
            response = requests.Response()
            response.status_code = 200
            response._content = b"{}"
            return response
        return super().put(url, **kwargs)


def runtime_environment(tmp_path, monkeypatch, xml=None):
    from ghostfolio_ibkr_sync import app
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text("symbol_mapping: {}\n")
    for key, value in {"IBKR_TOKEN": "synthetic", "IBKR_ACCOUNT_IDS": "U1", "IBKR_QUERY_IDS": "Q1",
                       "GHOST_ACCOUNT_NAMES": "Account", "GHOST_TOKEN": "synthetic", "GHOST_HOST": "http://ghost",
                       "DRY_RUN": "false", "MAPPING_FILE": str(mapping)}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("GHOST_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ACTIVITY_REVIEW_FILE", raising=False)
    fetched = []
    def fetch(token, query):
        fetched.append(query)
        return xml or report(trade_xml("T1"))
    monkeypatch.setattr(app, "fetch_flex_report", fetch)
    return app, fetched


def test_review_runtime_contract_disabled_enabled_then_disabled_notes(tmp_path, monkeypatch):
    from ghostfolio_ibkr_sync.outcome import new_run_outcome
    app, fetched = runtime_environment(tmp_path, monkeypatch)
    server = RuntimeServer(monkeypatch, [destination("IBKR#v2#U1:TRADE:T1")])
    path = tmp_path / "review.yaml"
    assert app.run_sync(new_run_outcome()) == 0
    assert not path.exists() and not server.writes
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(path))
    assert app.run_sync(new_run_outcome()) == 0
    document = review.decode_review(review.read_yaml(path.read_bytes()))
    assert len(document["proposals"]) == 1
    item = next(iter(document["proposals"].values()))
    item["approve"] = "yes"
    path.write_text(__import__("yaml").safe_dump(review.encode_review(document)))
    monkeypatch.setattr(review, "QUALIFIED_EXECUTION", ("synthetic", 2, 0))
    assert app.run_sync(new_run_outcome()) == 0
    assert len(server.writes) == 1 and len(server.cash) == 3
    server.rows[0]["comment"] += "\n\nUser note"
    monkeypatch.delenv("ACTIVITY_REVIEW_FILE")
    assert app.run_sync(new_run_outcome()) == 0
    assert len(server.writes) == 1 and len(server.cash) == 4
    assert fetched == ["Q1"] * 4  # No second acquisition during account processing.


@pytest.mark.parametrize("limit,delay", [(1, 0), (2, 0.5)])
def test_review_runtime_budget_defers_then_resumes_without_resend(tmp_path, monkeypatch, limit, delay):
    from ghostfolio_ibkr_sync.outcome import new_run_outcome

    days = [(1, 1), (2, 10), (3, 20)]
    xml = report("".join(trade_xml(f"T{i}", date=f"202608{day:02};100000") for i, day in days)
                 + trade_xml("T4", date="20260830;100000"))
    app, fetched = runtime_environment(tmp_path, monkeypatch, xml)
    rows = [destination(f"IBKR#v2#U1:TRADE:T{i}", id=f"row{i}",
                        date=f"2026-08-{day:02}T10:00:00Z") for i, day in days]
    server = RuntimeServer(monkeypatch, rows)
    imports = []

    def import_new(url, **kwargs):
        assert url == "http://ghost/api/v1/import" and kwargs["allow_redirects"] is False
        submitted = kwargs["json"]["activities"]
        assert len(submitted) == 1 and submitted[0]["comment"] == "IBKR#v2#U1:TRADE:T4"
        imports.extend(deepcopy(submitted))
        payload = {key: value for key, value in submitted[0].items() if key != "symbol"}
        created = destination(id="row4", **payload)
        server.rows.append(created)
        response = requests.Response()
        response.status_code = 201
        response._content = json.dumps({"activities": [created]}, default=float).encode()
        return response

    monkeypatch.setattr(requests, "post", import_new)
    path = tmp_path / "review.yaml"
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(path))
    monkeypatch.setenv("DRY_RUN", "true")
    # These budgets are test inputs. The shipped activation stays unset.
    monkeypatch.setattr(review, "QUALIFIED_EXECUTION", ("synthetic-only", limit, delay))
    assert app.run_sync(new_run_outcome()) == 0
    document = review.decode_review(review.read_yaml(path.read_bytes()))
    assert len(document["proposals"]) == 3
    for proposal in document["proposals"].values():
        proposal["approve"] = "yes"
    path.write_text(__import__("yaml").safe_dump(review.encode_review(document)))
    monkeypatch.setenv("DRY_RUN", "false")
    expected_pending = {key: deepcopy(value) for key, value in document["proposals"].items()}
    server.cash.clear()

    passes = 0
    while expected_pending:
        passes += 1
        previous = len(server.writes)
        outcome = new_run_outcome()
        assert app.run_sync(outcome) == 0
        assert outcome["accounts_failed"] == 0
        assert len(server.writes) - previous == min(limit, len(expected_pending))
        assert len(server.cash) == passes  # Ordinary cash processing still runs.
        assert len(imports) == 1  # Unrelated new activity imports despite deferred approvals.
        document = review.decode_review(review.read_yaml(path.read_bytes()))
        assert document["proposals"] == {key: value for key, value in expected_pending.items()
                                         if key in document["proposals"]}
        assert len(document["proposals"]) == max(0, len(expected_pending) - limit)
        expected_pending = document["proposals"]

    assert len(server.writes) == 3
    assert {payload["id"] for payload in server.writes} == {"row1", "row2", "row3"}
    assert server.waits == ([0.5] if limit == 2 else [])
    # A fresh normal run reopens the journal and cannot resend a consumed yes.
    assert app.run_sync(new_run_outcome()) == 0
    assert len(server.writes) == 3 and len(server.cash) == passes + 1
    assert len(imports) == 1
    assert fetched == ["Q1"] * (passes + 2)


def test_review_acceptance_failure_fences_cash_other_account_continues(tmp_path, monkeypatch):
    from ghostfolio_ibkr_sync.outcome import new_run_outcome
    app, fetched = runtime_environment(tmp_path, monkeypatch)
    monkeypatch.setenv("IBKR_ACCOUNT_IDS", "U1,U2")
    monkeypatch.setenv("IBKR_QUERY_IDS", "Q1,Q2")
    monkeypatch.setenv("GHOST_ACCOUNT_NAMES", "Account,Other")
    def fetch(token, query):
        fetched.append(query)
        return report(trade_xml("T1" if query == "Q1" else "T2"), source_account="U1" if query == "Q1" else "U2")
    monkeypatch.setattr(app, "fetch_flex_report", fetch)
    rows = [destination(), destination("IBKR#v2#U2:TRADE:T2", id="row2", accountId="other", quantity=Decimal("10"))]
    server = RuntimeServer(monkeypatch, rows, "unchanged", [
        {"id": "acc", "name": "Account", "currency": "USD"},
        {"id": "other", "name": "Other", "currency": "USD"}])
    path = tmp_path / "review.yaml"
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(path))
    assert app.run_sync(new_run_outcome()) == 0
    document = review.decode_review(review.read_yaml(path.read_bytes()))
    next(iter(document["proposals"].values()))["approve"] = "yes"
    path.write_text(__import__("yaml").safe_dump(review.encode_review(document)))
    monkeypatch.setattr(review, "QUALIFIED_EXECUTION", ("synthetic", 2, 0))
    server.cash.clear()
    outcome = new_run_outcome()
    assert app.run_sync(outcome) == 1
    assert [cash["id"] for cash in server.cash] == ["other"]
    assert outcome["accounts_failed"] == 1
    assert fetched == ["Q1", "Q2", "Q1", "Q2"]
    assert len(server.writes) == 1


def test_review_holdings_replacement_changes_position_once_before_later_sell(tmp_path, monkeypatch):
    from ghostfolio_ibkr_sync import app, ghostfolio
    server, state, config, blocked, held = run_review(tmp_path, monkeypatch)
    try:
        ids, comments, positions = ghostfolio.ghost_get_existing_orders(config)
        assert positions["qty"][("acc", "KO")] == 10
        xml = report(trade_xml("T1") + trade_xml("T2", "SELL", 10, date="20260802;100000"))
        activities, _, _, ok = app.select_account_activities(xml, "U1", "acc", {}, ids, comments, positions, review_holds=held)
        assert ok and [(row["type"], row["quantity"]) for row in activities] == [("SELL", 10)]
    finally:
        review.close_review(state)



def test_review_source_scope_partial_dividend_coverage_and_action_conflict():
    cash = div_xml() + div_xml().replace('actionID="A1"', 'actionID="A2"')
    events = source_events(report(divs=cash))
    assert len(events) == 2
    row = destination("IBKR#v2#U1:DIVIDEND:A1", type="DIVIDEND", date="2026-07-15T00:00:00Z")
    proposals, _ = review.refresh_proposals({}, events, [row], {"U1": "acc"})
    assert proposals
    assert all(not item["actionable"] for item in proposals.values())
    assert any("Partial" in item["status"] for item in proposals.values())
    unrelated = destination("IBKR#v2#U1:DIVIDEND:OTHER", type="DIVIDEND", date="2026-07-15T00:00:00Z", id="other")
    manual = destination(type="DIVIDEND", date="2026-07-15T00:00:00Z")
    proposals, _ = review.refresh_proposals({}, source_events(report(divs=div_xml())), [unrelated, manual], {"U1": "acc"})
    assert next(iter(proposals.values()))["actionable"] is False


@pytest.mark.parametrize("comment", ["IBKR#T1\n\nLegacy notes", "dividend#KO#2026-07-15\n\nLegacy notes",
                                    "  trailing whitespace ", "emoji " + "🐢" * 1000])
def test_review_reference_unsupported_preservation_has_no_actionable_proposal(comment):
    proposals = preview([destination(comment)])
    assert proposals and all(not item["actionable"] for item in proposals.values())


def test_review_replacement_wire_decimal_does_not_round_preserved_values():
    row = destination(quantity=Decimal("1.0000000000000000000000000001"))
    proposals = preview([row])
    assert not next(iter(proposals.values()))["actionable"]
    assert review.plain(Decimal("1.0000000000000000000000000001")) == "1.0000000000000000000000000001"
    expected = review.plain(destination())
    observed = destination(fee=Decimal("1.0000000000000000000000000001"))
    assert not review.row_matches(observed, expected)


def test_review_approval_two_events_one_target_are_both_refused():
    proposals = preview()
    first = next(iter(proposals.values()))
    first["approve"] = "yes"
    second = deepcopy(first)
    second["source event"] = "IBKR#v2#U1:TRADE:T2"
    second["key"] = "another"
    proposals["another"] = second
    approved, blocked = review.approved_proposals(proposals)
    assert not approved and blocked == {"acc"}


def test_review_stale_operator_payload_and_unknown_fields_never_authorize():
    old = preview()
    item = next(iter(old.values()))
    item["approve"] = "yes"
    item["proposed values"]["quantity"] = "10000"
    refreshed, _ = review.refresh_proposals(old, source_events(), [destination()], {"U1": "acc"})
    assert next(iter(refreshed.values()))["approve"] is None
    assert next(iter(refreshed.values()))["proposed values"]["quantity"] == "10"
    item["unknown"] = "field"
    with pytest.raises(RuntimeError):
        review.refresh_proposals(old, source_events(), [destination()], {"U1": "acc"})


def test_review_persistence_editor_after_put_preserves_pending_intent(tmp_path, monkeypatch):
    server, state, config, _, _ = run_review(tmp_path, monkeypatch, dry_run=True)
    original_put = server.put
    def edited_after_put(url, **kwargs):
        result = original_put(url, **kwargs)
        state["path"].write_bytes(state["path"].read_bytes() + b"# concurrent editor\n")
        return result
    monkeypatch.setattr(requests, "put", edited_after_put)
    config["dry_run"] = False
    try:
        with pytest.raises(RuntimeError, match="changed"):
            review.process_review(state, config, source_events(), {"U1": "acc"})
        assert state["path"].read_bytes().endswith(b"# concurrent editor\n")
        journal = review.read_yaml(state["journal_path"].read_bytes())
        assert next(iter(journal["entries"].values()))["status"] == "pending"
        assert len(server.writes) == 1
    finally:
        review.close_review(state)



def test_review_config_all_failed_acquisitions_do_not_initialize_file(tmp_path, monkeypatch):
    from ghostfolio_ibkr_sync.outcome import new_run_outcome
    app, _ = runtime_environment(tmp_path, monkeypatch)
    RuntimeServer(monkeypatch, [destination("IBKR#v2#U1:TRADE:T1")])
    def fail(*args):
        raise RuntimeError("synthetic report unavailable")
    monkeypatch.setattr(app, "fetch_flex_report", fail)
    path = tmp_path / "review.yaml"
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(path))
    assert app.run_sync(new_run_outcome()) == 1
    assert not path.exists() and not path.with_suffix(".yaml.journal.yaml").exists()


@pytest.mark.parametrize("value", ["", " ", "/persistent/review.yaml"])
def test_review_config_opt_in_env(tmp_path, monkeypatch, value):
    from ghostfolio_ibkr_sync.config import load
    runtime_environment(tmp_path, monkeypatch)
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", value)
    assert load().activity_review_file == (value.strip() or None)


def test_review_persistence_confirmed_before_cleanup_cannot_reuse_consumed_yes(tmp_path, monkeypatch):
    server, state, config, _, _ = run_review(tmp_path, monkeypatch, dry_run=True)
    original_review = deepcopy(state["document"])
    config["dry_run"] = False
    try:
        review.process_review(state, config, source_events(), {"U1": "acc"})
        assert len(server.writes) == 1
        # Simulate interruption after durable confirmation but before review cleanup,
        # followed by a separate manual edit restoring the old row.
        server.rows = [destination()]
        review.publish_review(state, original_review)
        review.process_review(state, config, source_events(), {"U1": "acc"})
        assert len(server.writes) == 1
        item = next(iter(state["document"]["proposals"].values()))
        assert item["approve"] is None
        assert item["review revision"] != next(iter(original_review["proposals"].values()))["review revision"]
    finally:
        review.close_review(state)


@pytest.mark.parametrize("boundary", [
    "before_intent", "after_intent", "before_dispatch", "after_apply",
    "after_confirmation", "after_cleanup",
])
def test_review_runtime_sigkill_restart_never_repeats_request(tmp_path, monkeypatch, boundary):
    """Kill a real process; retain only its durable files and synthetic server state.

    This proves offline runtime recovery. It does not qualify a destination image
    or replace the installed-image lab gate. The test-only budget is never shipped.
    """
    import signal
    import socket
    from ghostfolio_ibkr_sync.outcome import new_run_outcome

    def no_network(*args, **kwargs):
        pytest.fail("Offline recovery attempted network access")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    app, _ = runtime_environment(tmp_path, monkeypatch)
    server = RuntimeServer(monkeypatch, [destination("My café 🐢")])
    path = tmp_path / "review.yaml"
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(path))
    assert app.run_sync(new_run_outcome()) == 0
    document = review.decode_review(review.read_yaml(path.read_bytes()))
    next(iter(document["proposals"].values()))["approve"] = "yes"
    path.write_text(__import__("yaml").safe_dump(review.encode_review(document)))
    monkeypatch.setattr(review, "QUALIFIED_EXECUTION", ("synthetic-only", 1, 0))
    remote = tmp_path / "synthetic-server.json"
    requests_file = tmp_path / "synthetic-requests"
    remote.write_text(json.dumps(server.rows, default=float))

    def kill():
        os.kill(os.getpid(), signal.SIGKILL)

    pid = os.fork()
    if pid == 0:
        try:
            original_journal = review.publish_journal
            original_review = review.publish_review
            original_put = server.put

            def journal(state):
                status = next(iter(state["journal"]["entries"].values()))["status"]
                if boundary == "before_intent" and status == "pending":
                    kill()
                original_journal(state)
                if ((boundary == "after_intent" and status == "pending")
                        or (boundary == "after_confirmation" and status == "confirmed")):
                    kill()

            def publish(state, document):
                original_review(state, document)
                if (boundary == "after_cleanup" and not document["proposals"]
                        and state["journal"]["entries"]):
                    kill()

            def put(url, **kwargs):
                if "/api/v1/activities/" not in url:
                    return original_put(url, **kwargs)
                if boundary == "before_dispatch":
                    kill()
                # A separate file represents a server-side durable receipt.
                with requests_file.open("a") as receipt:
                    receipt.write("PUT\n")
                    receipt.flush()
                    os.fsync(receipt.fileno())
                response = original_put(url, **kwargs)
                with remote.open("w") as saved:
                    json.dump(server.rows, saved, default=float)
                    saved.flush()
                    os.fsync(saved.fileno())
                if boundary == "after_apply":
                    kill()
                return response

            review.publish_journal = journal
            review.publish_review = publish
            monkeypatch.setattr(requests, "put", put)
            app.run_sync(new_run_outcome())
        finally:
            os._exit(99)  # A missed boundary must fail in the parent.
    _, status = os.waitpid(pid, 0)
    assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL
    rows = json.loads(remote.read_text(), parse_float=Decimal, parse_int=Decimal)
    restarted = RuntimeServer(monkeypatch, rows)
    outcome = new_run_outcome()
    code = app.run_sync(outcome)
    pending_before = boundary in ("after_intent", "before_dispatch")
    assert code == (1 if pending_before else 0)
    assert len(restarted.writes) == (1 if boundary == "before_intent" else 0)
    sent = len(requests_file.read_text().splitlines()) if requests_file.exists() else 0
    assert sent + len(restarted.writes) == (0 if pending_before else 1)
    journal = review.read_yaml(path.with_suffix(".yaml.journal.yaml").read_bytes())
    entry = next(iter(journal["entries"].values()))
    assert entry["status"] == ("pending" if pending_before else "confirmed")
    if pending_before:
        assert not restarted.cash
        # Repeated restarts cannot turn a saved approval into a resend.
        assert app.run_sync(new_run_outcome()) == 1
        assert not restarted.writes and not restarted.cash
    else:
        assert restarted.rows[0]["comment"].endswith("\n\nMy café 🐢")
        assert app.run_sync(new_run_outcome()) == 0
        assert len(restarted.writes) == (1 if boundary == "before_intent" else 0)


def test_review_runtime_duplicate_reference_approval_never_dispatches(tmp_path, monkeypatch):
    from ghostfolio_ibkr_sync.outcome import new_run_outcome

    app, _ = runtime_environment(tmp_path, monkeypatch)
    marker = "IBKR#v2#U1:TRADE:T1"
    rows = [destination(marker), destination(marker, id="duplicate")]
    server = RuntimeServer(monkeypatch, rows)
    path = tmp_path / "review.yaml"
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(path))
    assert app.run_sync(new_run_outcome()) == 0
    document = review.decode_review(review.read_yaml(path.read_bytes()))
    assert document["proposals"]
    for proposal in document["proposals"].values():
        proposal["approve"] = "yes"
    path.write_text(__import__("yaml").safe_dump(review.encode_review(document)))
    monkeypatch.setattr(review, "QUALIFIED_EXECUTION", ("synthetic-only", 1, 0))
    assert app.run_sync(new_run_outcome()) == 0
    assert not server.writes and server.rows == rows
    refreshed = review.decode_review(review.read_yaml(path.read_bytes()))
    assert all(not item["actionable"] for item in refreshed["proposals"].values())
    assert not path.with_suffix(".yaml.journal.yaml").exists()


@pytest.mark.parametrize("drift", ["quantity", "userId", "tags", "comment", "missing"])
def test_review_acceptance_readback_drift_fences_account(tmp_path, monkeypatch, drift):
    server, state, config, _, _ = run_review(tmp_path, monkeypatch, dry_run=True)
    original_put = server.put
    def drifted(url, **kwargs):
        response = original_put(url, **kwargs)
        if drift == "missing":
            server.rows = []
        elif drift == "quantity":
            server.rows[0][drift] = Decimal("99")
        elif drift == "tags":
            server.rows[0][drift] = []
        else:
            server.rows[0][drift] = "changed"
        return response
    monkeypatch.setattr(requests, "put", drifted)
    config["dry_run"] = False
    try:
        blocked, _ = review.process_review(state, config, source_events(), {"U1": "acc"})
        assert blocked == {"acc"} and len(server.writes) == 1
        assert next(iter(state["journal"]["entries"].values()))["status"] == "pending"
    finally:
        review.close_review(state)



def test_review_runtime_contract_missing_dividend_section_keeps_trade_and_cash(tmp_path, monkeypatch):
    from ghostfolio_ibkr_sync.outcome import new_run_outcome
    app, _ = runtime_environment(tmp_path, monkeypatch, report(trade_xml("T1") + trade_xml("T2", symbol="PEP", isin="US7134481081"), cash_section=False))
    server = RuntimeServer(monkeypatch, [destination("IBKR#v2#U1:TRADE:T1", quantity=Decimal("10"))])
    imports = []
    def imported(url, **kwargs):
        imports.extend(deepcopy(kwargs["json"]["activities"]))
        created = [{**item, "id": f"created-{index}",
                    "assetProfile": {"symbol": item["symbol"], "dataSource": "YAHOO"}}
                   for index, item in enumerate(imports)]
        response = requests.Response()
        response.status_code = 201
        response._content = json.dumps({"activities": created}).encode()
        return response
    monkeypatch.setattr(requests, "post", imported)
    path = tmp_path / "review.yaml"
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(path))
    assert app.run_sync(new_run_outcome()) == 1
    assert [cash["id"] for cash in server.cash] == ["acc"]
    assert [item["comment"] for item in imports] == ["IBKR#v2#U1:TRADE:T2"]
    assert not server.writes
    assert path.exists() and review.decode_review(review.read_yaml(path.read_bytes()))["proposals"] == {}


@pytest.mark.parametrize("drift", ["updatedAt", "account", "value", "valueInBaseCurrency",
                                   "feeInBaseCurrency", "unitPriceInAssetProfileCurrency",
                                   "feeInAssetProfileCurrency"])
def test_review_stale_server_changes_keep_approval_and_reverse_evidence(tmp_path, monkeypatch, drift):
    rows = [destination()]
    proposals = preview(rows)
    item = next(iter(proposals.values()))
    item["approve"] = "yes"
    changed = deepcopy(rows)
    if drift == "account":
        changed[0]["account"]["balance"] = Decimal("999")
    else:
        changed[0][drift] = "changed"
    refreshed, _ = review.refresh_proposals(proposals, source_events(), changed, {"U1": "acc"})
    assert refreshed[item["key"]]["approve"] == "yes"
    assert refreshed[item["key"]]["review revision"] == item["review revision"]
    server, state, _, blocked, held = run_review(tmp_path, monkeypatch, rows=changed)
    try:
        assert not blocked and not held and len(server.writes) == 1
        entry = next(iter(state["journal"]["entries"].values()))
        assert entry["status"] == "confirmed"
        assert review.inspect_reverse(entry, server.rows[0])["quantity"] == 1
    finally:
        review.close_review(state)


@pytest.mark.parametrize("field,value", [("accountId", "other"), ("accountUserId", "other"),
    ("userId", "other"), ("symbolProfileId", "other"), ("comment", "changed"),
    ("quantity", Decimal("2")), ("date", "2026-08-01T10:00:01Z"), ("tags", []),
    ("assetProfile", {"id": "other", "symbol": "KO", "dataSource": "YAHOO"})])
def test_review_stale_activity_owned_changes_clear_approval(field, value):
    proposals = preview()
    next(iter(proposals.values()))["approve"] = "yes"
    refreshed, _ = review.refresh_proposals(proposals, source_events(), [destination(**{field: value})], {"U1": "acc"})
    assert refreshed and all(item["approve"] is None for item in refreshed.values())
    assert not review.row_matches(destination(**{field: value}), review.values_of(destination()))


@pytest.mark.parametrize("pending", [False, True])
def test_review_recovery_removed_account_keeps_journal_and_other_account(tmp_path, monkeypatch, pending, caplog):
    server, state, config, _, _ = run_review(tmp_path, monkeypatch, outcome="unchanged" if pending else "success")
    try:
        journal_before = state["journal_path"].read_bytes()
        other = destination("IBKR#v2#U2:TRADE:T1", id="row2", accountId="other", quantity=Decimal("10"))
        server.rows.append(other)
        events = source_events(report(trade_xml("T1"), source_account="U2"), account="U2", target="other")
        blocked, held = review.process_review(state, config, events, {"U2": "other"})
        assert blocked == ({"acc"} if pending else set())
        assert "other" not in blocked
        assert held == ({"IBKR#v2#U1:TRADE:T1"} if pending else set())
        assert state["journal_path"].read_bytes() == journal_before
        assert len(server.writes) == 1
        if pending:
            assert "no configured destination account acc" in caplog.text
            assert next(iter(state["document"]["proposals"].values()))["approve"] == "yes"
    finally:
        review.close_review(state)


@pytest.mark.parametrize("error", [RuntimeError, OSError])
@pytest.mark.parametrize("enabled", [False, True])
def test_review_runtime_contract_unrelated_errors_keep_traceback(tmp_path, monkeypatch, caplog, error, enabled):
    from ghostfolio_ibkr_sync.outcome import new_run_outcome
    app, _ = runtime_environment(tmp_path, monkeypatch)
    if enabled:
        monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(tmp_path / "review.yaml"))
    def fail(*args):
        raise error("synthetic unrelated failure")
    monkeypatch.setattr(app, "run_configured_sync", fail)
    monkeypatch.setattr(app, "finalize_run", lambda outcome, code: None)
    assert app.main() == 1
    record = next(record for record in caplog.records if record.getMessage() == "Sync failed with an unhandled error")
    assert record.exc_info is not None
    # Direct invocation preserves the exception for the main() boundary.
    with pytest.raises(error):
        app.run_sync(new_run_outcome())


def test_review_config_failure_has_review_outcome(tmp_path, monkeypatch):
    from ghostfolio_ibkr_sync.outcome import new_run_outcome
    app, _ = runtime_environment(tmp_path, monkeypatch)
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(tmp_path / "absent" / "review.yaml"))
    outcome = new_run_outcome()
    assert app.run_sync(outcome) == 1
    assert outcome["failures"] == [{"stage": "review", "reason": "review_unavailable", "ordinal": None}]


@pytest.mark.parametrize("pending", [False, True])
def test_review_runtime_removed_account_allows_remaining_cash(tmp_path, monkeypatch, pending):
    from ghostfolio_ibkr_sync.outcome import new_run_outcome
    app, _ = runtime_environment(tmp_path, monkeypatch)
    rows = [destination(), destination("IBKR#v2#U2:TRADE:T2", id="row2", accountId="other", quantity=Decimal("10"))]
    server = RuntimeServer(monkeypatch, rows, "unchanged" if pending else "success", [
        {"id": "acc", "name": "Account", "currency": "USD"},
        {"id": "other", "name": "Other", "currency": "USD"}])
    monkeypatch.setattr(app, "fetch_flex_report", lambda token, query:
        report(trade_xml("T1" if query == "Q1" else "T2"), source_account="U1" if query == "Q1" else "U2"))
    path = tmp_path / "review.yaml"
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(path))
    assert app.run_sync(new_run_outcome()) == 0
    document = review.decode_review(review.read_yaml(path.read_bytes()))
    next(iter(document["proposals"].values()))["approve"] = "yes"
    path.write_text(__import__("yaml").safe_dump(review.encode_review(document)))
    monkeypatch.setattr(review, "QUALIFIED_EXECUTION", ("synthetic", 2, 0))
    assert app.run_sync(new_run_outcome()) == (1 if pending else 0)
    monkeypatch.setenv("IBKR_ACCOUNT_IDS", "U2")
    monkeypatch.setenv("IBKR_QUERY_IDS", "Q2")
    monkeypatch.setenv("GHOST_ACCOUNT_NAMES", "Other")
    server.cash.clear()
    assert app.run_sync(new_run_outcome()) == 0
    assert [cash["id"] for cash in server.cash] == ["other"]
    assert len(server.writes) == 1


@pytest.mark.parametrize("invalid", [False, True])
def test_review_recovery_diagnostic_reports_only_stable_drift(monkeypatch, caplog, invalid):
    row = destination(quantity=Decimal("99"), updatedAt="2026-08-03T00:00:00Z")
    row["account"]["balance"] = Decimal("999")
    row["valueInBaseCurrency"] = Decimal("9999")
    if invalid:
        row["date"] = "unsupported date"
    monkeypatch.setattr(review, "snapshot_rows", lambda config: [row])
    monkeypatch.setattr(review.time, "sleep", lambda wait: None)
    # Historical journals may contain the original full GET row.
    entry = {"activity id": "row1", "destination account": "acc",
             "before": review.plain(destination()), "after": review.plain(destination(quantity=Decimal("10")))}
    matched, observed = review.recovery_read({}, entry)
    assert not matched and observed is row
    diagnostic = next(record for record in caplog.records if "observed differences" in record.msg)
    assert diagnostic.args[-1] == (["unavailable activity evidence"] if invalid else ["quantity"])


def test_review_schema_two_sections_and_legacy_approval_clear(tmp_path):
    proposals = preview()
    key = next(iter(proposals))
    proposals[key]["approve"] = "yes"
    path = tmp_path / "activities.yaml"
    path.write_text(__import__("yaml").safe_dump({"version": 1, "proposals": proposals}))
    path.chmod(0o600)
    state = review.open_review(str(path), [])
    try:
        assert state["document"]["proposals"][key]["approve"] is None
        review.publish_review(state, state["document"])
        disk = review.read_yaml(path.read_bytes())
        assert set(disk) == {"version", *review.SECTIONS} and disk["version"] == 2
        assert key in disk["activity_corrections"] and not disk["reference_updates"]
        assert disk["activity_corrections"][key]["evidence level"] == "probable"
    finally:
        review.close_review(state)


def test_review_schema_two_section_move_and_duplicate_are_refused():
    document = review.encode_review({"version": 1, "proposals": preview()})
    key, item = next(iter(document["activity_corrections"].items()))
    document["reference_updates"][key] = item
    with pytest.raises(RuntimeError, match="misplaced"):
        review.decode_review(document)


def test_review_blocked_yes_cannot_become_approval():
    events = source_events()
    row = destination("IBKR#T1")
    old, _ = review.refresh_proposals({}, events, [row], {"U1": "acc"})
    key = next(iter(old))
    old[key]["approve"] = "yes"
    assert old[key]["evidence level"] == "blocked"
    next(iter(events.values()))["legacy safe"] = True
    fresh, _ = review.refresh_proposals(old, events, [row], {"U1": "acc"})
    assert fresh[key]["actionable"] is True and fresh[key]["approve"] is None


def test_review_replacement_unknown_stored_field_drift_is_visible():
    row = destination(unknownStoredField={"value": "keep"})
    before = review.values_of(row)
    assert review.row_matches(row, before)
    row["unknownStoredField"]["value"] = "changed"
    assert not review.row_matches(row, before)


def test_review_pending_request_survives_display_revision_change(tmp_path, monkeypatch):
    server, state, config, blocked, _ = run_review(tmp_path, monkeypatch, outcome="unchanged")
    assert blocked == {"acc"} and len(server.writes) == 1
    document = deepcopy(state["document"])
    item = next(iter(document["proposals"].values()))
    item["review revision"] = "f" * 32
    item["section"] = "reference_updates"
    item["evidence level"] = "blocked"
    item["approve"] = "yes"
    review.publish_review(state, document)
    path = state["path"]
    review.close_review(state)
    state = review.open_review(str(path), [])
    try:
        blocked, held = review.process_review(state, config, source_events(), {"U1": "acc"})
        assert blocked == {"acc"} and held and len(server.writes) == 1
        assert next(iter(state["journal"]["entries"].values()))["status"] == "pending"
    finally:
        review.close_review(state)


def test_review_non_yes_warns_without_releasing_hold(caplog):
    proposals = preview()
    item = next(iter(proposals.values()))
    item["approve"] = "no"
    approved, blocked = review.approved_proposals(proposals)
    assert not approved and not blocked
    refreshed, held = review.refresh_proposals(proposals, source_events(), [destination()], {"U1": "acc"})
    assert held and next(iter(refreshed.values()))["approve"] == "no"
    assert "only literal yes approves" in caplog.text


@pytest.mark.parametrize("scalar", ["-1", "1.2", "1e0", "0x10", ".inf", "2026-01-01", "true", "no", "Yes", "on"])
def test_review_approval_other_scalar_values_skip_without_file_error(scalar):
    proposals = preview()
    item = next(iter(proposals.values()))
    item["approve"] = review.read_yaml(("approve: " + scalar).encode())["approve"]
    assert review.approved_proposals(proposals) == ([], set())


def test_review_schema_round_trip_nested_signed_decimal_values(tmp_path):
    row = destination()
    row["assetProfile"].update(countries=[{"weight": Decimal("0.50"), "name": "Example"}],
                               negative=Decimal("-0.25"), nullable=None)
    proposals = preview([row])
    path = tmp_path / "activities.yaml"
    state = review.open_review(str(path), [])
    try:
        review.publish_review(state, {"version": 1, "proposals": proposals})
        decoded = review.decode_review(review.read_yaml(path.read_bytes()))
        assert decoded == state["document"]
    finally:
        review.close_review(state)


def test_review_real_snapshot_parser_round_trip_nested_numbers(tmp_path, monkeypatch):
    row = destination()
    row["assetProfile"].update(countries=[{"weight": Decimal("0.50")}], negative=Decimal("-0.25"))
    ReviewServer(monkeypatch, [row])
    config = {"ghost_host": "http://ghost", "ghost_token": "secret",
              "activity_review_file": str(tmp_path / "activities.yaml")}
    rows = review.snapshot_rows(config)
    assert isinstance(rows[0]["assetProfile"]["negative"], Decimal)
    assert isinstance(rows[0]["assetProfile"]["countries"][0]["weight"], Decimal)
    proposals = review.refresh_proposals({}, source_events(), rows, {"U1": "acc"})[0]
    state = review.open_review(str(tmp_path / "activities.yaml"), [])
    try:
        review.publish_review(state, {"version": 1, "proposals": proposals})
        assert review.decode_review(review.read_yaml(state["path"].read_bytes())) == state["document"]
    finally:
        review.close_review(state)


@pytest.mark.parametrize("field,before,after", [
    ("dateOfFirstActivity", "2026-07-31T10:00:00Z", "2026-07-01T10:00:00Z"),
    ("watchedByCount", Decimal("1"), Decimal("2")),
])
def test_review_derived_profile_changes_keep_approval(field, before, after):
    row = destination()
    row["assetProfile"][field] = before
    old = preview([row])
    key = next(iter(old))
    old[key]["approve"] = "yes"
    row["assetProfile"][field] = after
    refreshed, held = review.refresh_proposals(old, source_events(), [row], {"U1": "acc"})
    assert held
    assert refreshed[key]["approve"] == "yes"
    assert refreshed[key]["binding"] == old[key]["binding"]
    assert refreshed[key]["review revision"] == old[key]["review revision"]


def test_review_date_correction_confirms_after_derived_profile_recalculation(tmp_path, monkeypatch):
    row = destination(date="2026-07-31T10:00:00Z")
    row["assetProfile"].update(dateOfFirstActivity=row["date"], watchedByCount=Decimal("1"))
    original_put = ReviewServer.put
    def recalculate(self, url, **kwargs):
        response = original_put(self, url, **kwargs)
        self.rows[0]["assetProfile"].update(dateOfFirstActivity=self.rows[0]["date"],
                                            watchedByCount=Decimal("2"))
        return response
    monkeypatch.setattr(ReviewServer, "put", recalculate)
    server, state, config, blocked, held = run_review(tmp_path, monkeypatch, rows=[row])
    try:
        assert not blocked and not held
        assert len(server.writes) == 1
        assert server.rows[0]["date"] != row["date"]
        assert server.rows[0]["assetProfile"]["dateOfFirstActivity"] == server.rows[0]["date"]
        entry = next(iter(state["journal"]["entries"].values()))
        assert entry["status"] == "confirmed"
        assert review.instant(review.inspect_reverse(entry, server.rows[0])["date"]) == review.instant(row["date"])
        blocked, held = review.process_review(state, config, source_events(), {"U1": "acc"})
        assert not blocked and not held and len(server.writes) == 1
    finally:
        review.close_review(state)
