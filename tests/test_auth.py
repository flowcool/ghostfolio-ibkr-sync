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
