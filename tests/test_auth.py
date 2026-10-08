"""Offline tests: Ghostfolio credential selection and the security-token exchange."""
import pytest

import ibkr_to_ghostfolio as m

SECRET = "CANARY-ACCESS-7f3a"        # synthetic security token
BEARER_SECRET = "CANARY-BEARER-91c2"  # synthetic value a server might echo


@pytest.fixture
def env(monkeypatch):
    for k, v in {"IBKR_TOKEN": "tok", "IBKR_ACCOUNT_IDS": "U1", "IBKR_QUERY_IDS": "q1",
                 "GHOST_HOST": "http://ghost:3333/", "MAPPING_FILE": ""}.items():
        monkeypatch.setenv(k, v)
    for k in ("GHOST_TOKEN", "GHOST_ACCESS_TOKEN", "GHOST_ACCOUNT_NAMES", "DRY_RUN"):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


# --- credential selection -----------------------------------------------------

def test_legacy_token_is_used_verbatim(env):
    env.setenv("GHOST_TOKEN", " legacy-jwt ")
    cfg = m.load_config()
    assert cfg["ghost_token"] == " legacy-jwt " and cfg["ghost_access_token"] is None


def test_access_token_is_kept_verbatim_and_no_bearer_yet(env):
    env.setenv("GHOST_ACCESS_TOKEN", f" {SECRET}é ")
    cfg = m.load_config()
    assert cfg["ghost_access_token"] == f" {SECRET}é " and cfg["ghost_token"] is None


@pytest.mark.parametrize("token,access", [(None, None), ("", ""), ("  ", "\t\n"), ("", None)])
def test_absent_empty_or_blank_credentials_are_missing(env, token, access):
    for k, v in (("GHOST_TOKEN", token), ("GHOST_ACCESS_TOKEN", access)):
        if v is not None:
            env.setenv(k, v)
    with pytest.raises(RuntimeError, match="GHOST_TOKEN or GHOST_ACCESS_TOKEN"):
        m.load_config()


@pytest.mark.parametrize("token,access,mode", [("   ", SECRET, "access"), ("jwt", " ", "legacy")])
def test_blank_variable_counts_as_unset_beside_the_other(env, token, access, mode):
    env.setenv("GHOST_TOKEN", token)
    env.setenv("GHOST_ACCESS_TOKEN", access)
    cfg = m.load_config()
    assert (cfg["ghost_access_token"] is not None) == (mode == "access")


def test_both_credentials_conflict_without_echoing_them(env):
    env.setenv("GHOST_TOKEN", BEARER_SECRET)
    env.setenv("GHOST_ACCESS_TOKEN", SECRET)
    with pytest.raises(RuntimeError, match="only one of") as e:
        m.load_config()
    assert SECRET not in str(e.value) and BEARER_SECRET not in str(e.value)


def test_missing_credential_is_named_among_the_other_missing_variables(env):
    env.delenv("IBKR_TOKEN")
    with pytest.raises(RuntimeError, match="IBKR_TOKEN, GHOST_TOKEN or GHOST_ACCESS_TOKEN"):
        m.load_config()


@pytest.mark.parametrize("host", [
    "ftp://ghost:3333", "ghost:3333", "http://", "http://:3333",
    f"http://user:{SECRET}@ghost:3333", "http://@ghost", "http://ghost:3333?x=1",
    "http://ghost:3333/#frag", "http://gho st:3333", "http://ghost:3333/a b",
    "http://ghost\\evil.example", "http://ghost:99999", "http://ghost:abc",
    "http://ghost:3333/\x01", "http://ghost:3333/\x7f", "http://[::1"])
def test_access_mode_rejects_unsafe_hosts_with_a_fixed_message(env, host):
    env.setenv("GHOST_ACCESS_TOKEN", SECRET)
    env.setenv("GHOST_HOST", host)
    with pytest.raises(RuntimeError, match="GHOST_HOST must be") as e:
        m.load_config()
    assert SECRET not in str(e.value)


@pytest.mark.parametrize("host", ["http://ghost:3333", "https://pf.example.com/ghostfolio/",
                                  "http://192.168.2.117:3333", "http://[::1]:3333"])
def test_access_mode_accepts_plain_http_and_https_hosts(env, host):
    env.setenv("GHOST_ACCESS_TOKEN", SECRET)
    env.setenv("GHOST_HOST", host)
    assert m.load_config()["ghost_host"] == host.rstrip("/")


def test_legacy_mode_keeps_its_previous_host_handling(env):
    env.setenv("GHOST_TOKEN", "jwt")
    env.setenv("GHOST_HOST", "http://ghost:3333?legacy")
    assert m.load_config()["ghost_host"] == "http://ghost:3333?legacy"


def test_load_config_never_calls_the_network(env):
    def boom(*a, **k):
        raise AssertionError("no request expected")
    env.setattr(m.requests, "post", boom)
    env.setattr(m.requests, "get", boom)
    env.setenv("GHOST_ACCESS_TOKEN", SECRET)
    m.load_config()


# --- token exchange -----------------------------------------------------------

class Resp:
    def __init__(self, status=201, body=None, text=None):
        self.status_code = status
        self._body = body
        self.text = text if text is not None else repr(body)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def script_post(monkeypatch, outcome):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    monkeypatch.setattr(m.requests, "post", post)
    return calls


def test_exchange_posts_once_without_redirects_with_both_timeouts(monkeypatch):
    calls = script_post(monkeypatch, Resp(201, {"authToken": "eyJ.abc-_.def"}))
    assert m.ghost_exchange_access_token("http://ghost:3333", SECRET) == "eyJ.abc-_.def"
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == "http://ghost:3333/api/v1/auth/anonymous"
    assert kwargs["json"] == {"accessToken": SECRET}
    assert kwargs["allow_redirects"] is False
    connect, read = kwargs["timeout"]
    assert connect > 0 and read > 0


def test_exchange_refuses_an_unsafe_host_before_sending_anything(monkeypatch):
    calls = script_post(monkeypatch, Resp(201, {"authToken": "x"}))
    with pytest.raises(RuntimeError, match="GHOST_HOST must be"):
        m.ghost_exchange_access_token("http://u:p@ghost", SECRET)
    assert calls == []


@pytest.mark.parametrize("outcome,reason", [
    (m.requests.ConnectionError(f"refused {SECRET}"), "network error"),
    (m.requests.Timeout(f"read timed out {SECRET}"), "network error"),
    (Resp(403, {"message": f"Forbidden {SECRET}"}), "HTTP 403"),
    (Resp(302, None, text=f"see http://evil/?t={SECRET}"), "HTTP 302"),
    (Resp(500, ValueError("x"), text=f"<html>{SECRET}</html>"), "HTTP 500"),
    (Resp(201, ValueError(f"bad json {SECRET}")), "not JSON"),
    (Resp(201, [BEARER_SECRET]), "no usable authToken"),
    (Resp(201, {"token": BEARER_SECRET}), "no usable authToken"),
    (Resp(201, {"authToken": ""}), "no usable authToken"),
    (Resp(201, {"authToken": None}), "no usable authToken"),
    (Resp(201, {"authToken": 12345}), "no usable authToken"),
    (Resp(201, {"authToken": f"{BEARER_SECRET} x"}), "no usable authToken"),
    (Resp(201, {"authToken": f"{BEARER_SECRET}\r\nX-Injected: 1"}), "no usable authToken"),
    (Resp(201, {"authToken": f"{BEARER_SECRET}é"}), "no usable authToken"),
])
def test_exchange_failures_raise_fixed_messages_without_secrets(monkeypatch, caplog, outcome, reason):
    script_post(monkeypatch, outcome)
    with pytest.raises(RuntimeError) as e:
        m.ghost_exchange_access_token("http://ghost:3333", SECRET)
    message = str(e.value)
    assert message.startswith("Ghostfolio login failed:") and reason in message
    assert SECRET not in message and BEARER_SECRET not in message
    assert e.value.__cause__ is None
    assert SECRET not in caplog.text and BEARER_SECRET not in caplog.text


# --- per-run authentication in main --------------------------------------------

def access_env(env, dry_run=False):
    env.setenv("GHOST_ACCESS_TOKEN", SECRET)
    if dry_run:
        env.setenv("DRY_RUN", "1")
    return env


def record_startup(monkeypatch, tokens=("bearer-1", "bearer-2", "bearer-3"), fail=None):
    """Stub every startup step; return the ordered list of what happened."""
    events = []
    issued = iter(tokens)

    def exchange(host, access_token):
        events.append(("exchange", host, access_token))
        if fail:
            raise fail
        return next(issued)

    def existing(cfg):
        events.append(("existing", cfg["ghost_token"]))
        return set(), set(), {"qty": {}}

    def process(cfg, ibkr_id, *a):
        events.append(("account", ibkr_id, cfg["ghost_token"]))
        return {}, True
    monkeypatch.setattr(m, "ghost_exchange_access_token", exchange)
    monkeypatch.setattr(m, "ghost_get_existing_orders", existing)
    monkeypatch.setattr(m, "process_account", process)
    return events


def test_access_mode_authenticates_once_before_any_ghostfolio_or_ibkr_call(env):
    events = record_startup(access_env(env))
    assert m.main() == 0
    assert events == [("exchange", "http://ghost:3333", SECRET),
                      ("existing", "bearer-1"), ("account", "U1", "bearer-1")]


def test_each_invocation_issues_a_fresh_bearer(env):
    events = record_startup(access_env(env))
    assert m.main() == 0 and m.main() == 0
    assert [e for e in events if e[0] == "exchange"] == [("exchange", "http://ghost:3333", SECRET)] * 2
    assert [e[2] for e in events if e[0] == "account"] == ["bearer-1", "bearer-2"]


def test_invalid_mapping_prevents_the_exchange(env, tmp_path):
    access_env(env).setenv("MAPPING_FILE", str(tmp_path / "missing.yaml"))
    events = record_startup(env)
    assert m.main() == 1
    assert events == []


def test_authentication_failure_stops_before_reads_accounts_and_writes(env, caplog):
    events = record_startup(access_env(env), fail=RuntimeError("Ghostfolio login failed: HTTP 403"))
    assert m.main() == 1
    assert [e[0] for e in events] == ["exchange"]
    assert any("Ghostfolio login failed: HTTP 403" in r.message for r in caplog.records)
    assert SECRET not in caplog.text


def test_unauthorised_read_after_login_is_not_retried_with_a_new_login(env):
    access_env(env)
    logins = []
    env.setattr(m, "ghost_exchange_access_token", lambda h, t: logins.append(1) or "bearer")
    def unauthorised(cfg):
        raise m.requests.HTTPError("401 Client Error")
    env.setattr(m, "ghost_get_existing_orders", unauthorised)
    assert m.main() == 1
    assert logins == [1]


def test_legacy_mode_never_logs_in_and_uses_the_token_as_bearer(env):
    env.setenv("GHOST_TOKEN", "legacy-jwt")
    events = record_startup(env)
    assert m.main() == 0
    assert events == [("existing", "legacy-jwt"), ("account", "U1", "legacy-jwt")]


def test_access_mode_dry_run_logs_in_reads_with_the_bearer_and_writes_nothing(env):
    """Real helpers end to end, only the HTTP layer and the IBKR fetch faked."""
    access_env(env, dry_run=True)
    reads, writes, logins = [], [], []

    class R:
        def __init__(self, body, status=200):
            self.status_code, self._body, self.text = status, body, ""
        def json(self):
            return self._body
        def raise_for_status(self):
            pass

    def post(url, **kw):
        if url.endswith("/api/v1/auth/anonymous"):
            logins.append(kw["json"])
            return R({"authToken": "fresh-bearer"}, 201)
        writes.append(("POST", url))
        return R({}, 201)

    def get(url, headers=None, **kw):
        reads.append((url, headers["Authorization"]))
        if url.endswith("/api/v1/activities"):
            return R({"activities": [], "count": 0})
        return R([{"id": "gf-1", "name": "U1"}])

    env.setattr(m.requests, "post", post)
    env.setattr(m.requests, "get", get)
    env.setattr(m.requests, "put", lambda url, **kw: writes.append(("PUT", url)))
    env.setattr(m.requests, "delete", lambda url, **kw: writes.append(("DELETE", url)))
    trade = ('<Trade tradeID="T1" symbol="KO" isin="US1912161007" assetCategory="STK" buySell="BUY" '
             'quantity="10" tradePrice="60" ibCommission="-1" currency="USD" dateTime="20260801;100000"/>')
    div = ('<CashTransaction type="Dividends" levelOfDetail="DETAIL" amount="25" dateTime="20260715" '
           'isin="US1912161007" symbol="KO" currency="USD" description="KO CASH DIVIDEND"/>')
    xml = (f"<FlexQueryResponse><FlexStatements><FlexStatement><Trades>{trade}</Trades>"
           f"<CashTransactions>{div}</CashTransactions><CashReport>"
           '<CashReportCurrency currency="BASE_SUMMARY" endingCash="100"/></CashReport>'
           "</FlexStatement></FlexStatements></FlexQueryResponse>")
    env.setattr(m, "fetch_flex_report", lambda *a, **k: xml)

    assert m.main() == 0
    assert logins == [{"accessToken": SECRET}]
    assert writes == []
    assert reads and all(auth == "Bearer fresh-bearer" for _, auth in reads)
