"""Offline tests: Ghostfolio API helpers (requests mocked, no network)."""
import pytest

import ibkr_to_ghostfolio as m

CFG = {"ghost_host": "http://ghost:3333", "ghost_token": "tok", "dry_run": False}


class Resp:
    def __init__(self, body=None, status=200, text=""):
        self._body, self.status_code, self.text = body, status, text

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise m.requests.HTTPError(str(self.status_code))


def activity(profile_key="assetProfile", **kw):
    """Build a valid current or legacy activity fixture with field overrides."""
    a = {"type": "BUY", "quantity": 10, "comment": None, "accountId": "acc", "date": "2026-08-01T00:00:00.000Z",
         profile_key: {"symbol": "KO", "isin": "US1912161007"}}
    a.update(kw)
    return a


def serve(monkeypatch, body, status=200):
    """Stub Ghostfolio GET requests with an isolated response body."""
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: Resp(body, status))


# --- existing activities (duplicate protection) --------------------------

@pytest.mark.parametrize("profile_key", ["assetProfile", "SymbolProfile"])
def test_existing_activities_are_indexed(monkeypatch, profile_key):
    """Both profile formats populate trade IDs and account reconciliation indexes."""
    acts = [activity(comment="IBKR#T1"),
            activity(type="SELL", quantity=4, comment="IBKR#T2"),
            activity(type="SELL", quantity=3),                              # manual sell
            activity(quantity=6, date="2026-07-01T00:00:00.000Z"),          # manual buy
            activity(type="DIVIDEND", quantity=100, comment="dividend#US1912161007#2026-07-15")]
    if profile_key == "SymbolProfile":
        for row in acts:
            row[profile_key] = row.pop("assetProfile")
    serve(monkeypatch, {"activities": acts, "count": len(acts)})
    trade_ids, div_comments, pos = m.ghost_get_existing_orders(CFG)
    assert trade_ids == {"T1", "T2"}
    assert div_comments == {("acc", "dividend#US1912161007#2026-07-15")}   # keyed by accountId
    assert pos["qty"][("acc", "KO")] == pytest.approx(9.0)                  # 10 - 4 - 3 + 6
    assert pos["manual_buys"][("acc", "KO")] == [["2026-07-01", 6.0]]       # IBKR#T1 buy is not manual
    assert pos["manual_sells"][("acc", "KO")] == [["2026-08-01", 3.0]]
    assert pos["isin_symbols"][("acc", "US1912161007")] == {"KO"}
    assert pos["dividend_dates"][("acc", "KO")] == ["2026-08-01"]


def test_count_mismatch_refuses_to_sync(monkeypatch):
    serve(monkeypatch, {"activities": [activity()], "count": 2})
    with pytest.raises(RuntimeError, match="incomplete list"):
        m.ghost_get_existing_orders(CFG)


def test_redacted_activities_refuse_to_sync(monkeypatch):
    serve(monkeypatch, {"activities": [activity(quantity=None)], "count": 1})
    with pytest.raises(RuntimeError, match="redacted"):
        m.ghost_get_existing_orders(CFG)


def test_http_error_propagates(monkeypatch):
    serve(monkeypatch, {}, status=500)
    with pytest.raises(m.requests.HTTPError):
        m.ghost_get_existing_orders(CFG)


# --- import ---------------------------------------------------------------

def _unresolved_400(symbol, index=0):
    """A Ghostfolio import 400 body for a symbol the data source cannot resolve."""
    return {"error": "Bad Request", "statusCode": 400,
            "message": [f'activities.{index}.symbol ("{symbol}") '
                        f'cannot be resolved by the data source ("YAHOO")']}


def sequence_post(monkeypatch, responses):
    """Serve the given responses to successive POSTs; record the sent batches."""
    sent = []
    it = iter(responses)

    def _post(url, headers, json, timeout):
        sent.append(json["activities"])
        return next(it)
    monkeypatch.setattr(m.requests, "post", _post)
    return sent


def test_import_with_nothing_to_do_sends_nothing(monkeypatch):
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: pytest.fail("POST must not be sent"))
    assert m.ghost_import_activities(CFG, []) == ([], True)


def test_dry_run_never_posts(monkeypatch):
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: pytest.fail("POST must not be sent"))
    acts = [{"type": "BUY"}]
    assert m.ghost_import_activities({**CFG, "dry_run": True}, acts) == (acts, True)


def test_import_success_returns_all_activities(monkeypatch):
    acts = [import_candidate("IBKR#1"), import_candidate("IBKR#2")]
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: Resp({"activities": [created(a) for a in acts]}, 201))
    assert m.ghost_import_activities(CFG, acts) == (acts, True)


def test_unknown_400_fails_hard_without_retry(monkeypatch):
    """A non per-symbol 400 (e.g. too many activities) fails hard, no retry."""
    sent = sequence_post(monkeypatch, [Resp({"message": ["Too many activities (1 at most)"]}, 400)])
    assert m.ghost_import_activities(CFG, [{"symbol": "KO"}]) == ([], False)
    assert len(sent) == 1                                                   # no retry


def test_import_network_error_returns_false(monkeypatch):
    def boom(*a, **k):
        raise m.requests.ConnectionError("down")
    monkeypatch.setattr(m.requests, "post", boom)
    assert m.ghost_import_activities(CFG, [{"symbol": "KO"}]) == ([], False)


def test_import_short_accepted_count_is_not_a_failure(monkeypatch):
    acts = [import_candidate("IBKR#1"), import_candidate("IBKR#2")]
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: Resp({"activities": [created(acts[1])]}, 201))
    assert m.ghost_import_activities(CFG, acts) == ([acts[1]], True)


# --- unresolved-symbol drop-and-retry -------------------------------------

def test_parse_unresolved_symbol():
    assert m.parse_unresolved_symbol(_unresolved_400("XYZ")) == "XYZ"
    # Raw escaped JSON text (no decoded body) still parses.
    assert m.parse_unresolved_symbol(None, 'symbol (\\"XYZ\\") cannot be resolved '
                                           'by the data source (\\"YAHOO\\")') == "XYZ"
    # Not a per-symbol resolution error -> None (must not be retried).
    assert m.parse_unresolved_symbol({"message": ["Too many activities (1 at most)"]}) is None
    assert m.parse_unresolved_symbol(None, "") is None


def test_unresolved_symbol_is_dropped_and_batch_retried(monkeypatch):
    acts = [import_candidate("IBKR#1"), {**import_candidate("IBKR#2"), "symbol": "BADSYM"},
            {**import_candidate("IBKR#3"), "symbol": "AAPL"}]
    sent = sequence_post(monkeypatch, [
        Resp(_unresolved_400("BADSYM", index=1), 400),
        Resp({"activities": [created(acts[0]), created(acts[2])]}, 201),
    ])
    imported, ok = m.ghost_import_activities(CFG, acts)
    assert [a["symbol"] for a in imported] == ["KO", "AAPL"]                 # BADSYM dropped
    assert ok is False                                                      # degraded -> exit 1
    assert len(sent) == 2                                                   # one retry
    assert [a["symbol"] for a in sent[1]] == ["KO", "AAPL"]                 # retry excludes BADSYM


def test_all_symbols_unresolved_imports_nothing(monkeypatch):
    acts = [{"symbol": "BAD1"}, {"symbol": "BAD2"}]
    sequence_post(monkeypatch, [
        Resp(_unresolved_400("BAD1"), 400),
        Resp(_unresolved_400("BAD2"), 400),
    ])
    assert m.ghost_import_activities(CFG, acts) == ([], False)


def test_unmatched_rejected_symbol_aborts_without_looping(monkeypatch):
    """A rejected symbol absent from the batch must not spin the retry loop."""
    acts = [{"symbol": "KO"}]
    sent = sequence_post(monkeypatch, [Resp(_unresolved_400("NOTSENT"), 400)] * 5)
    assert m.ghost_import_activities(CFG, acts) == ([], False)
    assert len(sent) == 1                                                   # aborted, no loop


# --- account lookup and cash balance -------------------------------------

def test_find_account_by_name_and_missing_account(monkeypatch):
    serve(monkeypatch, {"accounts": [{"id": "1", "name": "IBKR"}, {"id": "2", "name": "PEA"}]})
    assert m.ghost_find_account_id(CFG, "PEA") == "2"
    assert m.ghost_find_account_id(CFG, "nope") is None


def test_cash_balance_payload_is_the_five_whitelisted_fields(monkeypatch):
    sent = {}
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: Resp(
        {"id": "9", "currency": "EUR", "name": "IBKR", "platformId": "p1", "comment": "x",
         "isExcluded": False, "balance": 1, "value": 5}))
    monkeypatch.setattr(m.requests, "put", lambda url, headers, json, timeout: sent.update(json) or Resp({}, 200))
    assert m.ghost_update_cash_balance(CFG, "9", 123.456) is True
    assert sent == {"balance": 123.456, "currency": "EUR", "id": "9", "name": "IBKR", "platformId": "p1"}


def test_cash_balance_dry_run_does_not_touch_the_api(monkeypatch):
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: pytest.fail("no API call in dry run"))
    assert m.ghost_update_cash_balance({**CFG, "dry_run": True}, "9", 1.0) is True


@pytest.mark.parametrize("kind", ["BUY", "SELL", "DIVIDEND"])
@pytest.mark.parametrize("profile_key", ["assetProfile", "SymbolProfile"])
@pytest.mark.parametrize("profile", [None, [], "bad", {}, {"symbol": None},
                                      {"symbol": 123}, {"symbol": ""}, {"symbol": "  "}])
def test_required_asset_profile_is_validated(monkeypatch, kind, profile_key, profile):
    """Reject malformed symbols on every investment type and supported profile key."""
    row = activity(type=kind)
    row.pop("assetProfile")
    row[profile_key] = profile
    serve(monkeypatch, {"activities": [row], "count": 1})
    with pytest.raises(RuntimeError, match="missing or invalid asset profile symbol"):
        m.ghost_get_existing_orders(CFG)


@pytest.mark.parametrize("kind", ["BUY", "SELL", "DIVIDEND"])
def test_missing_required_profile_refuses_to_sync(monkeypatch, kind):
    """Reject investment activities when neither profile key is available."""
    row = activity(type=kind)
    row.pop("assetProfile")
    serve(monkeypatch, {"activities": [row], "count": 1})
    with pytest.raises(RuntimeError, match="asset profile symbol"):
        m.ghost_get_existing_orders(CFG)


def test_current_profile_takes_precedence_over_legacy(monkeypatch):
    """Index the current profile when a conflicting legacy profile is also present."""
    row = activity(SymbolProfile={"symbol": "STALE", "isin": "STALE"})
    serve(monkeypatch, {"activities": [row], "count": 1})
    _, _, pos = m.ghost_get_existing_orders(CFG)
    assert dict(pos["qty"]) == {("acc", "KO"): 10}
    assert dict(pos["isin_symbols"]) == {("acc", "US1912161007"): {"KO"}}


@pytest.mark.parametrize("profile", [None, {}, {"symbol": ""}])
def test_invalid_current_profile_does_not_fall_back_to_legacy(monkeypatch, profile):
    """An invalid current profile must fail even when the legacy profile is valid."""
    row = activity(assetProfile=profile, SymbolProfile={"symbol": "KO"})
    serve(monkeypatch, {"activities": [row], "count": 1})
    with pytest.raises(RuntimeError, match="asset profile symbol"):
        m.ghost_get_existing_orders(CFG)


def test_noninvestment_activity_does_not_require_profile(monkeypatch):
    """Accept noninvestment activities without an asset profile."""
    serve(monkeypatch, {"activities": [{"type": "FEE", "quantity": 1}], "count": 1})
    ids, comments, pos = m.ghost_get_existing_orders(CFG)
    assert ids == comments == set()
    assert all(not values for values in pos.values())


@pytest.mark.parametrize("quantity", [float("inf"), float("nan"), "bad", -1])
def test_invalid_existing_holdings_fail_closed(monkeypatch, quantity):
    serve(monkeypatch, {"activities": [activity(quantity=quantity)], "count": 1})
    with pytest.raises(RuntimeError, match="holding quantity"):
        m.ghost_get_existing_orders(CFG)


def import_candidate(comment="IBKR#one"):
    return {"accountId": "synthetic", "comment": comment, "symbol": "KO", "type": "BUY",
            "quantity": 10, "unitPrice": 60, "fee": 1, "currency": "USD", "dataSource": "YAHOO",
            "date": "2026-08-01T00:00:00Z"}


def created(candidate):
    return {**candidate, "id": "created-" + candidate["comment"],
            "assetProfile": {"symbol": candidate["symbol"], "dataSource": candidate["dataSource"]}}


@pytest.mark.parametrize("body", [None, {}, {"activities": [{}]},
                                     {"activities": [import_candidate("unknown")]},
                                     {"activities": [import_candidate(), import_candidate()]},
                                     {"activities": [{**import_candidate(), "quantity": 99}]},
                                     {"activities": [{**import_candidate(), "error": "duplicate"}]}])
def test_unknown_acceptance_is_not_assumed_and_blocks_target(monkeypatch, body):
    cfg = {**CFG}
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: Resp(body, 201))
    assert m.ghost_import_activities(cfg, [import_candidate()]) == ([], False)
    assert cfg["_uncertain_import_accounts"] == {"synthetic"}


def test_server_empty_created_list_changes_no_bookkeeping(monkeypatch):
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: Resp({"activities": []}, 201))
    assert m.ghost_import_activities({**CFG}, [import_candidate()]) == ([], True)


def test_created_rows_map_to_original_candidates_despite_enriched_profile(monkeypatch):
    candidate = import_candidate()
    server_row = {**created(candidate), "date": "2026-08-01T00:00:00.000Z",
                  "assetProfile": {"symbol": "CANONICAL", "dataSource": "YAHOO"}}
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: Resp({"activities": [server_row]}, 201))
    assert m.ghost_import_activities({**CFG}, [candidate]) == ([candidate], True)


@pytest.mark.parametrize("field,value", [("id", None), ("id", ""), ("date", None), ("date", "bad"),
                                        ("date", "2026-08-02T00:00:00Z"),
                                        ("date", "2026-08-01T00:00:00"),
                                        ("assetProfile", None),
                                        ("assetProfile", {"symbol": "KO", "dataSource": "MANUAL"}),
                                        ("assetProfile", {"symbol": "", "dataSource": "YAHOO"})])
def test_created_identity_date_and_source_required(monkeypatch, field, value):
    candidate = import_candidate()
    row = created(candidate)
    row[field] = value
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: Resp({"activities": [row]}, 201))
    cfg = {**CFG}
    assert m.ghost_import_activities(cfg, [candidate]) == ([], False)
    assert cfg["_uncertain_import_accounts"] == {"synthetic"}


@pytest.mark.parametrize("field", ["quantity", "unitPrice", "fee"])
@pytest.mark.parametrize("value", [True, False, None, float("nan"), float("inf"), "1"])
def test_response_financial_evidence_is_numeric_finite_and_not_boolean(field, value):
    candidate = {**import_candidate(), field: 1}
    row = {**created(candidate), field: value}
    with pytest.raises(RuntimeError, match="financial evidence"):
        m.accepted_import_subset([candidate], {"activities": [row]})


def test_repeated_created_id_does_not_prove_two_created_buys():
    first, second = import_candidate("IBKR#1"), import_candidate("IBKR#2")
    rows = [created(first), {**created(second), "id": created(first)["id"]}]
    with pytest.raises(RuntimeError, match="created identity"):
        m.accepted_import_subset([first, second], {"activities": rows})
