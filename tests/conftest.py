import pytest


@pytest.fixture(autouse=True)
def no_real_notifications(monkeypatch):
    """A developer's APPRISE_URLS must never make a test send a real notification."""
    for k in ("APPRISE_URLS", "APPRISE_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)
