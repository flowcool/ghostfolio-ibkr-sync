"""Recovery failure matrix; synthetic HTTP and private isolated filesystem only."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
import yaml

import cleanup_duplicates
import cleanup_dividends
import cleanup_recovery as recovery

CFG = {"ghost_host": "http://synthetic", "ghost_token": "fake"}


@pytest.fixture(params=[cleanup_duplicates, cleanup_dividends], ids=["trades", "dividends"])
def world(request, monkeypatch, tmp_path):
    tool = request.param
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected unmocked network")
    monkeypatch.setattr(tool.requests.sessions.Session, "request", forbidden)
    monkeypatch.chdir(tmp_path)
    dividend = tool is cleanup_dividends
    manual = {"id": "manual", "userId": "owner", "accountId": "acc", "currency": "USD",
              "type": "DIVIDEND" if dividend else "BUY", "quantity": 1, "unitPrice": 10,
              "fee": 0, "comment": None, "date": "2026-01-01T00:00:00Z", "tags": [],
              "assetProfile": {"symbol": "KO", "dataSource": "YAHOO"}}
    synced = {**deepcopy(manual), "id": "synced",
              "comment": "dividend#ISIN#2026-01-01" if dividend else "IBKR#one"}
    state = {"tool": tool, "manual": manual, "synced": synced,
             "rows": {"manual": deepcopy(manual), "synced": deepcopy(synced)},
             "calls": [], "path": tmp_path / "journal.yaml", "put": "ok", "delete": "ok"}
    def get(url, **kwargs):
        row = state["rows"].get(url.rsplit("/", 1)[1])
        return SimpleNamespace(status_code=404 if row is None else 200, json=lambda: deepcopy(row))
    def put(url, **kwargs):
        ident = url.rsplit("/", 1)[1]
        state["calls"].append("PUT")
        if state["put"] in ("ok", "timeout-committed"):
            state["rows"][ident]["comment"] = kwargs["json"]["comment"]
        if state["put"].startswith("timeout"):
            raise tool.requests.Timeout("synthetic timeout")
        return SimpleNamespace(status_code=503 if state["put"] == "failure" else 200, text="synthetic")
    def delete(url, **kwargs):
        state["calls"].append("DELETE")
        if state["delete"] in ("ok", "timeout-committed"):
            state["rows"].pop(url.rsplit("/", 1)[1], None)
        if state["delete"].startswith("timeout"):
            raise tool.requests.Timeout("synthetic timeout")
        return SimpleNamespace(status_code=503 if state["delete"] == "failure" else 200, text="synthetic")
    monkeypatch.setattr(tool.requests, "get", get)
    monkeypatch.setattr(tool.requests, "put", put)
    monkeypatch.setattr(tool.requests, "delete", delete)
    return state


def apply(world):
    recovery.process_pairs(world["tool"], CFG, [(world["synced"], world["manual"])], world["path"])


def resume(world, write=True):
    recovery.resume_cleanup(world["tool"], CFG, world["path"], apply=write)


def journal(world):
    return yaml.safe_load(world["path"].read_text())


def test_success_journals_preimages_and_repeat_resume_is_idempotent(world):
    apply(world)
    assert world["calls"] == ["PUT", "DELETE"]
    doc = journal(world)
    pair = doc["pairs"]["synced"]
    assert pair["manual_preimage"]["comment"] is None
    assert pair["synced_preimage"] == world["synced"]
    assert pair["put"] == pair["delete"] == "succeeded"
    assert world["path"].stat().st_mode & 0o777 == 0o600
    resume(world)
    assert world["calls"] == ["PUT", "DELETE"]


@pytest.mark.parametrize("stage", ["put", "delete"])
@pytest.mark.parametrize("outcome", ["failure", "timeout-before", "timeout-committed"])
def test_partial_and_unknown_outcomes_inspect_then_resume_exact_current_state(world, stage, outcome):
    world[stage] = outcome
    with pytest.raises(RuntimeError, match="unresolved"):
        apply(world)
    doc = journal(world)
    assert doc["pairs"]["synced"][stage] == "unknown"
    original_doc = world["path"].read_bytes()
    calls = list(world["calls"])
    resume(world, write=False)
    assert world["calls"] == calls and world["path"].read_bytes() == original_doc
    world[stage] = "ok"
    resume(world)
    assert "synced" not in world["rows"]
    assert world["rows"]["manual"]["comment"] == world["synced"]["comment"]
    expected_puts = 2 if stage == "put" and outcome != "timeout-committed" else 1
    assert world["calls"].count("PUT") == expected_puts
    pair = journal(world)["pairs"]["synced"]
    assert pair["put"] == pair["delete"] == "succeeded"
    done_calls = list(world["calls"])
    resume(world)
    assert world["calls"] == done_calls


@pytest.mark.parametrize("row", ["manual", "synced"])
@pytest.mark.parametrize("field", ["quantity", "fee", "userId", "accountId", "currency", "comment", "tags"])
def test_changed_record_or_owner_refuses_recovery_before_write(world, row, field):
    world["delete"] = "failure"
    with pytest.raises(RuntimeError):
        apply(world)
    world["rows"][row][field] = ([{"id": "changed"}] if field == "tags" else
                                99 if field in ("quantity", "fee") else "changed")
    calls = list(world["calls"])
    with pytest.raises(RuntimeError):
        resume(world)
    assert world["calls"] == calls


@pytest.mark.parametrize("row", ["manual", "synced"])
def test_missing_original_owner_refuses_apply_without_any_write(world, row):
    del world[row]["userId"]
    with pytest.raises(RuntimeError, match="owner"):
        apply(world)
    assert world["calls"] == [] and not world["path"].exists()


def test_missing_manual_cannot_be_treated_as_completed(world):
    apply(world)
    del world["rows"]["manual"]
    calls = list(world["calls"])
    with pytest.raises(RuntimeError, match="missing"):
        resume(world)
    assert world["calls"] == calls


@pytest.mark.parametrize("change", ["host", "tool", "schema", "pair-key", "state", "owner"])
def test_invalid_journal_refused_before_http_mutation(world, change):
    apply(world)
    doc = journal(world)
    if change in ("host", "tool", "schema"):
        doc[change] = "wrong"
    elif change == "pair-key":
        doc["pairs"]["wrong"] = doc["pairs"].pop("synced")
    elif change == "state":
        doc["pairs"]["synced"]["put"] = "wrong"
    else:
        doc["pairs"]["synced"]["synced_preimage"]["userId"] = "another"
    world["path"].write_text(yaml.safe_dump(doc))
    calls = list(world["calls"])
    with pytest.raises(RuntimeError):
        resume(world)
    assert world["calls"] == calls


def test_journal_create_failure_prevents_any_mutation(world, monkeypatch):
    monkeypatch.setattr(recovery, "write_journal", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        apply(world)
    assert world["calls"] == []


def test_journal_update_failure_before_put_prevents_any_mutation(world, monkeypatch):
    real = recovery.write_journal
    def write(path, doc, create=False):
        if not create:
            raise OSError("disk")
        real(path, doc, create)
    monkeypatch.setattr(recovery, "write_journal", write)
    with pytest.raises(OSError):
        apply(world)
    assert world["calls"] == []
    assert journal(world)["pairs"]["synced"]["put"] == "not_attempted"


def test_journal_update_failure_after_put_leaves_durable_unknown_and_safe_resume(world, monkeypatch):
    real = recovery.write_journal
    def write(path, doc, create=False):
        if doc["pairs"]["synced"]["put"] == "succeeded":
            raise OSError("disk")
        real(path, doc, create)
    monkeypatch.setattr(recovery, "write_journal", write)
    with pytest.raises(OSError):
        apply(world)
    assert world["calls"] == ["PUT"]
    assert journal(world)["pairs"]["synced"]["put"] == "unknown"
    monkeypatch.setattr(recovery, "write_journal", real)
    resume(world)
    assert world["calls"] == ["PUT", "DELETE"]


def test_existing_journal_not_overwritten(world):
    world["path"].write_text("keep")
    with pytest.raises(FileExistsError):
        apply(world)
    assert world["path"].read_text() == "keep" and world["calls"] == []


def test_exclusive_lock_refuses_second_resume(world):
    apply(world)
    fd = recovery.lock_journal(world["path"])
    try:
        with pytest.raises(RuntimeError, match="in use"):
            resume(world)
    finally:
        recovery.os.close(fd)


def test_cli_inspection_requires_no_apply(world, monkeypatch):
    world["delete"] = "failure"
    with pytest.raises(RuntimeError):
        apply(world)
    monkeypatch.setattr(world["tool"], "load_config", lambda: CFG)
    monkeypatch.setattr(world["tool"].sys, "argv", ["cleanup", "--resume", str(world["path"])])
    calls = list(world["calls"])
    world["tool"].main()
    assert world["calls"] == calls


def test_tool_identity_works_when_invoked_as_main(world):
    tool = SimpleNamespace(__file__=world["tool"].__file__, __name__="__main__")
    assert recovery.tool_name(tool) == world["tool"].__name__



def test_journal_update_failure_after_delete_is_recovered_as_complete(world, monkeypatch):
    real = recovery.write_journal
    def write(path, doc, create=False):
        if doc["pairs"]["synced"]["delete"] == "succeeded":
            raise OSError("disk")
        real(path, doc, create)
    monkeypatch.setattr(recovery, "write_journal", write)
    with pytest.raises(OSError):
        apply(world)
    assert world["calls"] == ["PUT", "DELETE"]
    assert journal(world)["pairs"]["synced"]["delete"] == "unknown"
    monkeypatch.setattr(recovery, "write_journal", real)
    resume(world)
    assert world["calls"] == ["PUT", "DELETE"]
    assert journal(world)["pairs"]["synced"]["delete"] == "succeeded"


def test_world_readable_journal_refused(world):
    apply(world)
    world["path"].chmod(0o644)
    with pytest.raises(RuntimeError, match="private permissions"):
        resume(world)


def test_symlink_journal_refused(world):
    apply(world)
    link = world["path"].parent / "link.yaml"
    link.symlink_to(world["path"])
    with pytest.raises(RuntimeError, match="Symlink"):
        recovery.resume_cleanup(world["tool"], CFG, link, apply=True)


def test_changed_second_pair_aborts_before_first_mutation(world):
    tool = world["tool"]
    first = {"manual_preimage": world["manual"], "synced_preimage": world["synced"],
             "new_comment": world["synced"]["comment"], "put": "not_attempted", "delete": "not_attempted"}
    second = deepcopy(first)
    second["manual_preimage"]["id"] = "manual-2"
    second["synced_preimage"]["id"] = "synced-2"
    world["rows"]["manual-2"] = {**deepcopy(second["manual_preimage"]), "quantity": 99}
    world["rows"]["synced-2"] = deepcopy(second["synced_preimage"])
    doc = {"schema": 1, "tool": recovery.tool_name(tool), "host": CFG["ghost_host"],
           "pairs": {"synced": first, "synced-2": second}}
    recovery.write_journal(world["path"], doc, create=True)
    with pytest.raises(RuntimeError, match="changed"):
        resume(world)
    assert world["calls"] == []



def test_completion_between_reads_records_both_inferred_outcomes(world, monkeypatch):
    world["put"] = "timeout-committed"
    with pytest.raises(RuntimeError):
        apply(world)
    real = recovery.pair_state
    reads = []
    def read(*args):
        reads.append(1)
        if len(reads) == 3:
            world["rows"].pop("synced", None)
        return real(*args)
    monkeypatch.setattr(recovery, "pair_state", read)
    resume(world)
    pair = journal(world)["pairs"]["synced"]
    assert pair["put"] == pair["delete"] == "succeeded"
    assert world["calls"] == ["PUT"]


def test_failed_inferred_put_persistence_prevents_recovery_delete(world, monkeypatch):
    world["put"] = "timeout-committed"
    with pytest.raises(RuntimeError):
        apply(world)
    real = recovery.write_journal
    def write(path, doc, create=False):
        if doc["pairs"]["synced"]["put"] == "succeeded":
            raise OSError("disk")
        real(path, doc, create)
    monkeypatch.setattr(recovery, "write_journal", write)
    with pytest.raises(OSError):
        resume(world)
    assert world["calls"] == ["PUT"] and "synced" in world["rows"]
    assert journal(world)["pairs"]["synced"]["put"] == "unknown"


@pytest.mark.parametrize("world", [cleanup_dividends], indirect=True, ids=["dividends"])
@pytest.mark.parametrize("state", ["untagged", "tagged", "complete"])
def test_wide_date_legacy_journal_can_be_inspected_but_never_applied(world, state):
    synced = deepcopy(world["synced"])
    synced["date"] = "2026-01-29T00:00:00Z"
    synced["comment"] = "dividend#ISIN#2026-01-29"
    world["rows"]["synced"] = deepcopy(synced)
    if state != "untagged":
        world["rows"]["manual"]["comment"] = synced["comment"]
    if state == "complete":
        world["rows"].pop("synced")
    doc = {"schema": 1, "tool": "cleanup_dividends", "host": CFG["ghost_host"],
           "pairs": {"synced": {"manual_preimage": world["manual"], "synced_preimage": synced,
                                 "new_comment": synced["comment"],
                                 "put": "unknown", "delete": "unknown"}}}
    recovery.write_journal(world["path"], doc, create=True)
    before = world["path"].read_bytes()
    rows = deepcopy(world["rows"])
    resume(world, write=False)
    with pytest.raises(RuntimeError, match="Wide-date dividend"):
        resume(world)
    assert world["calls"] == []
    assert world["rows"] == rows
    assert world["path"].read_bytes() == before


@pytest.mark.parametrize("world", [cleanup_dividends], indirect=True, ids=["dividends"])
def test_wide_date_later_journal_pair_blocks_all_mutations(world):
    first = {"manual_preimage": world["manual"], "synced_preimage": world["synced"],
             "new_comment": world["synced"]["comment"],
             "put": "not_attempted", "delete": "not_attempted"}
    second = deepcopy(first)
    second["manual_preimage"]["id"] = "manual-2"
    second["synced_preimage"]["id"] = "synced-2"
    second["synced_preimage"]["date"] = "2026-01-29T00:00:00Z"
    second["synced_preimage"]["comment"] = second["new_comment"] = "dividend#ISIN#2026-01-29"
    for row in (second["manual_preimage"], second["synced_preimage"]):
        world["rows"][row["id"]] = deepcopy(row)
    doc = {"schema": 1, "tool": "cleanup_dividends", "host": CFG["ghost_host"],
           "pairs": {"synced": first, "synced-2": second}}
    recovery.write_journal(world["path"], doc, create=True)
    before = world["path"].read_bytes()
    with pytest.raises(RuntimeError, match="Wide-date dividend"):
        resume(world)
    assert world["calls"] == []
    assert world["path"].read_bytes() == before
