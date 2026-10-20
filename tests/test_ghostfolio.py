"""Offline tests: Ghostfolio API helpers (requests mocked, no network)."""
import logging

import pytest

import requests
from ghostfolio_ibkr_sync import ghostfolio

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
            raise requests.HTTPError(str(self.status_code))


def activity(profile_key="assetProfile", **kw):
    """Build a valid current or legacy activity fixture with field overrides."""
    a = {"type": "BUY", "quantity": 10, "comment": None, "accountId": "acc", "date": "2026-08-01T00:00:00.000Z",
         profile_key: {"symbol": "KO", "isin": "US1912161007", "dataSource": "YAHOO"}}
    a.update(kw)
    return a


def serve(monkeypatch, body, status=200):
    """Stub Ghostfolio GET requests with an isolated response body."""
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(body, status))


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
    trade_ids, div_comments, pos = ghostfolio.ghost_get_existing_orders(CFG)
    assert trade_ids == {"T1", "T2"}
    assert div_comments == {("acc", "dividend#US1912161007#2026-07-15")}   # keyed by accountId
    assert pos["qty"][("acc", "KO")] == pytest.approx(9.0)                  # 10 - 4 - 3 + 6
    assert pos["manual_buys"][("acc", "KO")] == [["2026-07-01", 6.0]]       # IBKR#T1 buy is not manual
    assert pos["manual_sells"][("acc", "KO")] == [["2026-08-01", 3.0]]
    assert pos["isin_symbols"][("acc", "US1912161007")] == {"KO"}
    assert pos["dividend_dates"][("acc", "KO")] == []                    # connector rows are not proximity candidates


@pytest.mark.parametrize("comment,activity_type,expected", [
    ("IBKR#v2#U1:TRADE:T-1", "BUY", ("U1", "TRADE", "T-1")),
    ("IBKR#v2#U_2:TRADE:T.2", "SELL", ("U_2", "TRADE", "T.2")),
    ("IBKR#v2#U-3:DIVIDEND:A_1", "DIVIDEND", ("U-3", "DIVIDEND", "A_1")),
    ("IBKR#legacy", "BUY", None),
    ("IBKR#V2#U1:TRADE:T1", "BUY", None),
    (None, "BUY", None),
])
def test_versioned_identity_reader_accepts_legacy_and_strict_v2(
        comment, activity_type, expected):
    assert ghostfolio.parse_versioned_activity_identity(comment, activity_type) == expected


@pytest.mark.parametrize("comment,activity_type", [
    ("IBKR#v", "BUY"),
    ("IBKR#v0#U1:TRADE:T1", "BUY"),
    ("IBKR#v02#U1:TRADE:T1", "BUY"),
    ("IBKR#v3#U1:TRADE:T1", "BUY"),
    ("IBKR#v2#U/1:TRADE:T1", "BUY"),
    ("IBKR#v2#U1:trade:T1", "BUY"),
    ("IBKR#v2#U1:TRADE:T/1", "BUY"),
    ("IBKR#v2#U1:TRADE:T1:extra", "BUY"),
    ("IBKR#v2#U1:TRADE:T1", "DIVIDEND"),
    ("IBKR#v2#U1:DIVIDEND:A1", "BUY"),
    ("IBKR#v2#U1:TRADE:T1", None),
])
def test_versioned_identity_reader_rejects_invalid_reserved_grammar_and_type(
        comment, activity_type):
    with pytest.raises(ghostfolio.InvalidActivityIdentityError,
                       match="Invalid reserved activity identity"):
        ghostfolio.parse_versioned_activity_identity(comment, activity_type)


def test_versioned_identity_reader_builds_global_source_account_index(monkeypatch):
    trade_comment = "IBKR#v2#U1:TRADE:T1"
    dividend_comment = "IBKR#v2#U2:DIVIDEND:A1"
    acts = [
        activity(accountId="same-destination", comment=trade_comment),
        activity(type="DIVIDEND", accountId="same-destination", comment=dividend_comment),
        activity(comment="IBKR#legacy-trade"),
    ]
    serve(monkeypatch, {"activities": acts, "count": len(acts)})
    trade_ids, div_comments, pos = ghostfolio.ghost_get_existing_orders(
        {**CFG, "dry_run": True})
    assert trade_ids == {"legacy-trade"}
    assert div_comments == set()
    assert pos["versioned_identities"] == {
        ("U1", trade_comment), ("U2", dividend_comment),
    }
    assert pos["dividend_dates"][("same-destination", "KO")] == []
    assert pos["dividend_evidence"] == []


def test_count_mismatch_refuses_to_sync(monkeypatch):
    serve(monkeypatch, {"activities": [activity()], "count": 2})
    with pytest.raises(RuntimeError, match="incomplete list"):
        ghostfolio.ghost_get_existing_orders(CFG)


def test_redacted_activities_refuse_to_sync(monkeypatch):
    serve(monkeypatch, {"activities": [activity(quantity=None)], "count": 1})
    with pytest.raises(RuntimeError, match="redacted"):
        ghostfolio.ghost_get_existing_orders(CFG)


def test_http_error_propagates(monkeypatch):
    serve(monkeypatch, {}, status=500)
    with pytest.raises(requests.HTTPError):
        ghostfolio.ghost_get_existing_orders(CFG)


def test_existing_activities_reject_redirect_without_following(monkeypatch):
    calls = []

    def get(*args, **kwargs):
        calls.append(kwargs)
        return Resp({}, 302)

    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(RuntimeError, match="Ghostfolio request redirected"):
        ghostfolio.ghost_get_existing_orders(CFG)
    assert calls == [{"headers": ghostfolio.ghost_headers("tok"), "timeout": 60, "allow_redirects": False}]


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

    def _post(url, headers, json, timeout, **kwargs):
        sent.append(json["activities"])
        return next(it)
    monkeypatch.setattr(requests, "post", _post)
    return sent


def test_import_with_nothing_to_do_sends_nothing(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("POST must not be sent"))
    assert ghostfolio.ghost_import_activities(CFG, []) == ([], True)


def test_dry_run_never_posts(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("POST must not be sent"))
    acts = [{"type": "BUY"}]
    assert ghostfolio.ghost_import_activities({**CFG, "dry_run": True}, acts) == (acts, True)


def test_short_import_acceptance_full_response_is_clean(monkeypatch):
    acts = [import_candidate("IBKR#1"), import_candidate("IBKR#2")]
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp({"activities": [created(a) for a in acts]}, 201))
    assert ghostfolio.ghost_import_activities(CFG, acts) == (acts, True)


def test_unknown_400_fails_hard_without_retry(monkeypatch):
    """A non per-symbol 400 (e.g. too many activities) fails hard, no retry."""
    sent = sequence_post(monkeypatch, [Resp({"message": ["Too many activities (1 at most)"]}, 400)])
    assert ghostfolio.ghost_import_activities(CFG, [{"symbol": "KO"}]) == ([], False)
    assert len(sent) == 1                                                   # no retry


def test_import_network_error_returns_false(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(requests, "post", boom)
    assert ghostfolio.ghost_import_activities(CFG, [{"symbol": "KO"}]) == ([], False)


def test_import_rejects_redirect_without_following(monkeypatch, caplog):
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs)
        return Resp({}, 302)

    monkeypatch.setattr(requests, "post", post)
    assert ghostfolio.ghost_import_activities(CFG, [import_candidate()]) == ([], False)
    assert "Ghostfolio request redirected" in caplog.text
    assert calls == [{"headers": ghostfolio.ghost_headers("tok"), "json": {"activities": [import_candidate()]},
                      "timeout": 60, "allow_redirects": False}]


def test_short_import_acceptance_known_subset_fails_without_retry(
        monkeypatch, caplog):
    acts = [import_candidate("IBKR#1"), import_candidate("IBKR#2")]
    sent = sequence_post(monkeypatch, [Resp({"activities": [created(acts[1])]}, 201)])

    assert ghostfolio.ghost_import_activities(CFG, acts) == ([acts[1]], False)
    assert len(sent) == 1
    assert "IBKR#1" in caplog.text
    assert "IBKR#2" not in caplog.text
    assert "inspect Ghostfolio before rerun" in caplog.text
    assert [record.levelno for record in caplog.records
            if "accepted only" in record.message] == [logging.ERROR]


# --- unresolved-symbol drop-and-retry -------------------------------------

def test_parse_unresolved_symbol():
    assert ghostfolio.parse_unresolved_symbol(_unresolved_400("XYZ")) == "XYZ"
    # Raw escaped JSON text (no decoded body) still parses.
    assert ghostfolio.parse_unresolved_symbol(None, 'symbol (\\"XYZ\\") cannot be resolved '
                                           'by the data source (\\"YAHOO\\")') == "XYZ"
    # Not a per-symbol resolution error -> None (must not be retried).
    assert ghostfolio.parse_unresolved_symbol({"message": ["Too many activities (1 at most)"]}) is None
    assert ghostfolio.parse_unresolved_symbol(None, "") is None


def test_unresolved_symbol_is_dropped_and_batch_retried(monkeypatch):
    acts = [import_candidate("IBKR#1"), {**import_candidate("IBKR#2"), "symbol": "BADSYM"},
            {**import_candidate("IBKR#3"), "symbol": "AAPL"}]
    sent = sequence_post(monkeypatch, [
        Resp(_unresolved_400("BADSYM", index=1), 400),
        Resp({"activities": [created(acts[0]), created(acts[2])]}, 201),
    ])
    imported, ok = ghostfolio.ghost_import_activities(CFG, acts)
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
    assert ghostfolio.ghost_import_activities(CFG, acts) == ([], False)


def test_unmatched_rejected_symbol_aborts_without_looping(monkeypatch):
    """A rejected symbol absent from the batch must not spin the retry loop."""
    acts = [{"symbol": "KO"}]
    sent = sequence_post(monkeypatch, [Resp(_unresolved_400("NOTSENT"), 400)] * 5)
    assert ghostfolio.ghost_import_activities(CFG, acts) == ([], False)
    assert len(sent) == 1                                                   # aborted, no loop


# --- account lookup and cash balance -------------------------------------

def test_account_read_timeout_preserves_write_timeout(monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append(("GET", url, kwargs["timeout"]))
        if url.endswith("/api/v1/account"):
            return Resp({"accounts": [{"id": "9", "name": "IBKR"}]})
        return Resp({"id": "9", "currency": "EUR", "name": "IBKR", "platformId": "p1"})

    def put(url, **kwargs):
        calls.append(("PUT", url, kwargs["timeout"]))
        return Resp({}, 200)

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "put", put)
    assert ghostfolio.ghost_find_account_id(CFG, "IBKR") == "9"
    assert ghostfolio.ghost_update_cash_balance(CFG, "9", 123.456, "EUR") is True
    assert calls == [
        ("GET", f"{CFG['ghost_host']}/api/v1/account", 120),
        ("GET", f"{CFG['ghost_host']}/api/v1/account/9", 120),
        ("PUT", f"{CFG['ghost_host']}/api/v1/account/9", 30),
    ]


@pytest.mark.parametrize("dry_run", [True, False])
def test_account_read_timeout_never_retries_or_writes(monkeypatch, dry_run):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs["timeout"]))
        raise requests.ReadTimeout("synthetic slow account read")

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "put", lambda *a, **k: pytest.fail("no PUT after read timeout"))
    with pytest.raises(requests.ReadTimeout):
        ghostfolio.ghost_update_cash_balance({**CFG, "dry_run": dry_run}, "9", 1.0, "EUR")
    assert calls == [(f"{CFG['ghost_host']}/api/v1/account/9", 120)]


def test_find_account_by_name_and_missing_account(monkeypatch):
    serve(monkeypatch, {"accounts": [{"id": "1", "name": "IBKR"}, {"id": "2", "name": "PEA"}]})
    assert ghostfolio.ghost_find_account_id(CFG, "PEA") == "2"
    assert ghostfolio.ghost_find_account_id(CFG, "nope") is None


def test_accounts_reject_redirect_without_following(monkeypatch):
    calls = []

    def get(*args, **kwargs):
        calls.append(kwargs)
        return Resp({}, 302)

    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(RuntimeError, match="Ghostfolio request redirected"):
        ghostfolio.ghost_get_accounts(CFG)
    assert calls == [{"headers": ghostfolio.ghost_headers("tok"), "timeout": 120, "allow_redirects": False}]


def test_cash_balance_payload_is_the_five_whitelisted_fields(monkeypatch):
    sent = {}
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(
        {"id": "9", "currency": "EUR", "name": "IBKR", "platformId": "p1", "comment": "x",
         "isExcluded": False, "balance": 1, "value": 5}))
    monkeypatch.setattr(requests, "put", lambda url, headers, json, timeout, **kwargs: sent.update(json) or Resp({}, 200))
    assert ghostfolio.ghost_update_cash_balance(CFG, "9", 123.456, "EUR") is True
    assert sent == {"balance": 123.456, "currency": "EUR", "id": "9", "name": "IBKR", "platformId": "p1"}


def test_cash_balance_get_rejects_redirect_without_following(monkeypatch):
    calls = []

    def get(*args, **kwargs):
        calls.append(kwargs)
        return Resp({}, 302)

    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(RuntimeError, match="Ghostfolio request redirected"):
        ghostfolio.ghost_update_cash_balance(CFG, "9", 123.456, "EUR")
    assert calls == [{"headers": ghostfolio.ghost_headers("tok"), "timeout": 120, "allow_redirects": False}]


def test_cash_balance_put_rejects_redirect_without_following(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(
        {"id": "9", "currency": "EUR", "name": "IBKR", "platformId": "p1"}))

    def put(*args, **kwargs):
        calls.append(kwargs)
        return Resp({}, 302)

    monkeypatch.setattr(requests, "put", put)
    assert ghostfolio.ghost_update_cash_balance(CFG, "9", 123.456, "EUR") is False
    assert "Ghostfolio request redirected" in caplog.text
    assert calls[0]["allow_redirects"] is False


def test_cash_currency_guard_dry_run_reads_but_never_writes(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(
        {"id": "9", "currency": "EUR", "name": "IBKR", "platformId": "p1"}))
    monkeypatch.setattr(requests, "put", lambda *a, **k: pytest.fail("no PUT in dry run"))
    assert ghostfolio.ghost_update_cash_balance({**CFG, "dry_run": True}, "9", 1.0, "EUR") is True
    assert "[DRY RUN] would set cash balance" in caplog.text


def test_cash_currency_guard_dry_run_reports_a_mismatch(monkeypatch, caplog):
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(
        {"id": "9", "currency": "EUR", "name": "IBKR", "platformId": "p1"}))
    monkeypatch.setattr(requests, "put", lambda *a, **k: pytest.fail("no PUT in dry run"))
    assert ghostfolio.ghost_update_cash_balance({**CFG, "dry_run": True}, "9", 1.0, "USD") is False
    assert "USD" in caplog.text and "EUR" in caplog.text


def test_cash_currency_guard_mismatch_sends_no_put(monkeypatch, caplog):
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(
        {"id": "9", "currency": "EUR", "name": "IBKR", "platformId": "p1"}))
    monkeypatch.setattr(requests, "put", lambda *a, **k: pytest.fail("no PUT on mismatch"))
    assert ghostfolio.ghost_update_cash_balance(CFG, "9", 123.456, "USD") is False
    assert "USD" in caplog.text and "EUR" in caplog.text


@pytest.mark.parametrize("currency", [None, ""])
def test_cash_currency_guard_absent_base_currency_sends_no_put(monkeypatch, caplog, currency):
    monkeypatch.setattr(requests, "put", lambda *a, **k: pytest.fail("no PUT without currency"))
    assert ghostfolio.ghost_update_cash_balance(CFG, "9", 123.456, currency) is False
    assert "CurrencyPrimary" in caplog.text


def test_cash_currency_guard_match_keeps_the_update_and_log(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(
        {"id": "9", "currency": "EUR", "name": "IBKR", "platformId": "p1"}))
    monkeypatch.setattr(requests, "put", lambda *a, **k: Resp({}, 200))
    assert ghostfolio.ghost_update_cash_balance(CFG, "9", 123.456, "EUR") is True
    assert "Updated cash balance for account 9" in caplog.text


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
        ghostfolio.ghost_get_existing_orders(CFG)


@pytest.mark.parametrize("kind", ["BUY", "SELL", "DIVIDEND"])
def test_missing_required_profile_refuses_to_sync(monkeypatch, kind):
    """Reject investment activities when neither profile key is available."""
    row = activity(type=kind)
    row.pop("assetProfile")
    serve(monkeypatch, {"activities": [row], "count": 1})
    with pytest.raises(RuntimeError, match="asset profile symbol"):
        ghostfolio.ghost_get_existing_orders(CFG)


def test_current_profile_takes_precedence_over_legacy(monkeypatch):
    """Index the current profile when a conflicting legacy profile is also present."""
    row = activity(SymbolProfile={"symbol": "STALE", "isin": "STALE"})
    serve(monkeypatch, {"activities": [row], "count": 1})
    _, _, pos = ghostfolio.ghost_get_existing_orders(CFG)
    assert dict(pos["qty"]) == {("acc", "KO"): 10}
    assert dict(pos["isin_symbols"]) == {("acc", "US1912161007"): {"KO"}}


@pytest.mark.parametrize("profile", [None, {}, {"symbol": ""}])
def test_invalid_current_profile_does_not_fall_back_to_legacy(monkeypatch, profile):
    """An invalid current profile must fail even when the legacy profile is valid."""
    row = activity(assetProfile=profile, SymbolProfile={"symbol": "KO"})
    serve(monkeypatch, {"activities": [row], "count": 1})
    with pytest.raises(RuntimeError, match="asset profile symbol"):
        ghostfolio.ghost_get_existing_orders(CFG)


def test_noninvestment_activity_does_not_require_profile(monkeypatch):
    """Accept noninvestment activities without an asset profile."""
    serve(monkeypatch, {"activities": [{"type": "FEE", "quantity": 1}], "count": 1})
    ids, comments, pos = ghostfolio.ghost_get_existing_orders(CFG)
    assert ids == comments == set()
    assert all(not values for values in pos.values())


@pytest.mark.parametrize("quantity", [float("inf"), float("nan"), "bad", -1])
def test_invalid_existing_holdings_fail_closed(monkeypatch, quantity):
    serve(monkeypatch, {"activities": [activity(quantity=quantity)], "count": 1})
    with pytest.raises(RuntimeError, match="holding quantity"):
        ghostfolio.ghost_get_existing_orders(CFG)


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
def test_short_import_acceptance_unknown_response_is_not_assumed_and_blocks_target(
        monkeypatch, body):
    cfg = {**CFG}
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp(body, 201))
    assert ghostfolio.ghost_import_activities(cfg, [import_candidate()]) == ([], False)
    assert cfg["_uncertain_import_accounts"] == {"synthetic"}


def test_short_import_acceptance_empty_created_list_fails_without_uncertainty(
        monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp({"activities": []}, 201))
    cfg = {**CFG, "_uncertain_import_accounts": set()}
    assert ghostfolio.ghost_import_activities(cfg, [import_candidate()]) == ([], False)
    assert not cfg["_uncertain_import_accounts"]


def test_short_import_acceptance_maps_created_rows_despite_enriched_profile(
        monkeypatch):
    candidate = import_candidate()
    server_row = {**created(candidate), "date": "2026-08-01T00:00:00.000Z",
                  "assetProfile": {"symbol": "CANONICAL", "dataSource": "YAHOO"}}
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp({"activities": [server_row]}, 201))
    assert ghostfolio.ghost_import_activities({**CFG}, [candidate]) == ([{**candidate, "symbol": "CANONICAL"}], True)


@pytest.mark.parametrize("field,value", [("id", None), ("id", ""), ("date", None), ("date", "bad"),
                                        ("date", "2026-08-02T00:00:00Z"),
                                        ("date", "2026-08-01T00:00:00"),
                                        ("assetProfile", None),
                                        ("assetProfile", {"symbol": "KO", "dataSource": "MANUAL"}),
                                        ("assetProfile", {"symbol": "", "dataSource": "YAHOO"})])
def test_short_import_acceptance_requires_created_identity_date_and_source(
        monkeypatch, field, value):
    candidate = import_candidate()
    row = created(candidate)
    row[field] = value
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp({"activities": [row]}, 201))
    cfg = {**CFG}
    assert ghostfolio.ghost_import_activities(cfg, [candidate]) == ([], False)
    assert cfg["_uncertain_import_accounts"] == {"synthetic"}


@pytest.mark.parametrize("field", ["quantity", "unitPrice", "fee"])
@pytest.mark.parametrize("value", [True, False, None, float("nan"), float("inf"), "1"])
def test_short_import_acceptance_requires_numeric_finite_financial_evidence(
        field, value):
    candidate = {**import_candidate(), field: 1}
    row = {**created(candidate), field: value}
    with pytest.raises(RuntimeError, match="financial evidence"):
        ghostfolio.accepted_import_subset([candidate], {"activities": [row]})


def test_short_import_acceptance_rejects_repeated_created_id():
    first, second = import_candidate("IBKR#1"), import_candidate("IBKR#2")
    rows = [created(first), {**created(second), "id": created(first)["id"]}]
    with pytest.raises(RuntimeError, match="created identity"):
        ghostfolio.accepted_import_subset([first, second], {"activities": rows})


@pytest.mark.parametrize("scope", ["activity", "account"])
@pytest.mark.parametrize("flag", ["draft-tag", "exclude-tag", "isDraft", "isExcluded"])
def test_inactive_ids_kept_but_no_position_manual_or_dividend_evidence(monkeypatch, scope, flag):
    rows = [activity(comment="IBKR#B"), activity(),
            activity(type="DIVIDEND", comment="dividend#KO#2026-08-01")]
    for row in rows:
        context = row if scope == "activity" else row.setdefault("account", {})
        if flag.endswith("tag"):
            context["tags"] = [{"id": "0c077abd-eca2-4cbb-818c-6cefbf2d169a" if flag == "draft-tag"
                                else "f2e868af-8333-459f-b161-cbc6544c24bd"}]
        else:
            context[flag] = True
    serve(monkeypatch, {"activities": rows, "count": len(rows)})
    ids, comments, pos = ghostfolio.ghost_get_existing_orders(CFG)
    assert ids == {"B"} and comments == {("acc", "dividend#KO#2026-08-01")}
    assert all(not values for values in pos.values())


def test_other_source_cannot_back_yahoo_holding_or_manual_match(monkeypatch):
    row = activity()
    row["assetProfile"]["dataSource"] = "MANUAL"
    serve(monkeypatch, {"activities": [row], "count": 1})
    _, _, pos = ghostfolio.ghost_get_existing_orders(CFG)
    assert all(not values for values in pos.values())


@pytest.mark.parametrize("bad", [None, "bad", [{"id": None}], [None]])
def test_malformed_eligibility_tags_fail_closed(monkeypatch, bad):
    row = activity(tags=bad)
    serve(monkeypatch, {"activities": [row], "count": 1})
    with pytest.raises(RuntimeError, match="eligibility"):
        ghostfolio.ghost_get_existing_orders(CFG)


def test_missing_source_refuses_position_context(monkeypatch):
    row = activity()
    del row["assetProfile"]["dataSource"]
    serve(monkeypatch, {"activities": [row], "count": 1})
    with pytest.raises(RuntimeError, match="data source"):
        ghostfolio.ghost_get_existing_orders(CFG)


def test_excluded_empty_target_account_is_not_syncable(monkeypatch):
    serve(monkeypatch, {"accounts": [{"id": "excluded", "name": "IBKR",
                                     "tags": [{"id": "f2e868af-8333-459f-b161-cbc6544c24bd"}]}]})
    with pytest.raises(RuntimeError, match="excluded"):
        ghostfolio.ghost_find_account_id(CFG, "IBKR")


def test_created_inactive_row_does_not_contribute_active_holding():
    candidate = import_candidate()
    row = {**created(candidate), "tags": [{"id": "0c077abd-eca2-4cbb-818c-6cefbf2d169a"}]}
    with pytest.raises(RuntimeError, match="inactive"):
        ghostfolio.accepted_import_subset([candidate], {"activities": [row]})



def test_exact_import_shape_without_tags_does_not_hide_future_draft():
    candidate = {**import_candidate(), "date": "2099-08-01T00:00:00Z"}
    with pytest.raises(RuntimeError, match="inactive"):
        ghostfolio.accepted_import_subset([candidate], {"activities": [created(candidate)]})


@pytest.mark.parametrize("profile_key", ["assetProfile", "SymbolProfile"])
def test_created_response_accepts_current_and_legacy_profiles(monkeypatch, profile_key):
    candidate = import_candidate()
    row = created(candidate)
    if profile_key == "SymbolProfile":
        row[profile_key] = row.pop("assetProfile")
    else:
        row["SymbolProfile"] = {"symbol": "STALE", "dataSource": "MANUAL"}
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp({"activities": [row]}, 201))
    cfg = {**CFG, "_uncertain_import_accounts": set()}
    assert ghostfolio.ghost_import_activities(cfg, [candidate]) == ([candidate], True)
    assert not cfg.get("_uncertain_import_accounts")


@pytest.mark.parametrize("profile", [None, {}, [], {"symbol": "", "dataSource": "YAHOO"},
                                     {"symbol": "KO", "dataSource": "MANUAL"}])
def test_created_response_invalid_current_profile_cannot_use_legacy(monkeypatch, profile):
    candidate = import_candidate()
    row = {**created(candidate), "assetProfile": profile,
           "SymbolProfile": {"symbol": "KO", "dataSource": "YAHOO"}}
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp({"activities": [row]}, 201))
    cfg = {**CFG, "_uncertain_import_accounts": set()}
    assert ghostfolio.ghost_import_activities(cfg, [candidate]) == ([], False)
    assert cfg["_uncertain_import_accounts"] == {"synthetic"}
