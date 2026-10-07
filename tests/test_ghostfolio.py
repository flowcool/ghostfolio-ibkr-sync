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
    assert div_comments == {"dividend#US1912161007#2026-07-15"}
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

def test_import_with_nothing_to_do_sends_nothing(monkeypatch):
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: pytest.fail("POST must not be sent"))
    assert m.ghost_import_activities(CFG, []) is True


def test_dry_run_never_posts(monkeypatch):
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: pytest.fail("POST must not be sent"))
    assert m.ghost_import_activities({**CFG, "dry_run": True}, [{"type": "BUY"}]) is True


def test_import_http_error_returns_false(monkeypatch):
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: Resp({}, 400, "bad symbol"))
    assert m.ghost_import_activities(CFG, [{"type": "BUY"}]) is False


def test_import_network_error_returns_false(monkeypatch):
    def boom(*a, **k):
        raise m.requests.ConnectionError("down")
    monkeypatch.setattr(m.requests, "post", boom)
    assert m.ghost_import_activities(CFG, [{"type": "BUY"}]) is False


def test_import_short_accepted_count_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(m.requests, "post", lambda *a, **k: Resp({"activities": [{}]}, 201))
    assert m.ghost_import_activities(CFG, [{"a": 1}, {"a": 2}]) is True


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
