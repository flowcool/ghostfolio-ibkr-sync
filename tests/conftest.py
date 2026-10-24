import pytest


@pytest.fixture(autouse=True)
def no_real_notifications(monkeypatch):
    """A developer's APPRISE_URLS must never make a test send a real notification."""
    for k in ("APPRISE_URLS", "APPRISE_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def valid_timezone(monkeypatch):
    """A valid IANA TZ keeps tests out of the forced-preview path unless they unset it."""
    monkeypatch.setenv("TZ", "UTC")


@pytest.fixture(autouse=True)
def corporate_state_baseline(monkeypatch, tmp_path_factory, request):
    """Existing runtime tests use an initialized private synthetic state volume.

    Corporate-action tests exercise explicit unset/unsafe/bootstrap variants.
    No source or destination implementation is mocked by this fixture.
    """
    if request.module.__name__ == "test_corporate_actions":
        monkeypatch.delenv("CORPORATE_ACTION_STATE_FILE", raising=False)
        monkeypatch.delenv("CORPORATE_ACTION_EVIDENCE_FILE", raising=False)
        return
    directory=tmp_path_factory.mktemp("corporate-state")
    directory.chmod(0o700)
    path=directory/"state.yaml"
    path.write_text("version: 1\nreports: {}\nfindings: {}\n")
    path.chmod(0o600)
    monkeypatch.setenv("CORPORATE_ACTION_STATE_FILE",str(path))
    monkeypatch.delenv("CORPORATE_ACTION_EVIDENCE_FILE", raising=False)


@pytest.fixture(autouse=True)
def no_unmocked_http(monkeypatch):
    """Offline acceptance must fail before any real network request."""
    import requests
    def refuse(*args,**kwargs):
        raise AssertionError("Offline tests require an HTTP double")
    monkeypatch.setattr(requests.sessions.Session,"request",refuse)
