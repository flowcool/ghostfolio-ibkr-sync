"""Offline GitHub release-watch contracts; no real network or issue writes."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("release_watch", Path(__file__).parents[1] / "scripts/watch_ghostfolio_releases.py")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)

CONFIG = {
    "upstream_repository": "ghostfolio/ghostfolio",
    "first_release": "3.80.2",
    "labels": ["upstream-release"],
    "keywords": ["api", "deprecated"],
    "endpoints": ["POST /api/v1/import", "GET /api/v1/activities"],
}


def release(identifier, tag, day, **extra):
    return {"id": identifier, "tag_name": tag, "published_at": f"2026-10-{day:02d}T05:00:00Z", "draft": False, "prerelease": False, "body": "", **extra}


class FakeAPI:
    def __init__(self, releases, issues=None):
        self.releases = releases
        self.issues = list(issues or [])
        self.writes = []

    def list_all(self, path):
        if path.endswith("/releases"):
            return self.releases
        if path.endswith("/issues?state=all"):
            return self.issues
        if path.endswith("/labels"):
            return [{"name": "upstream-release"}]
        raise AssertionError(path)

    def request(self, method, path, payload=None):
        if method == "GET":
            return next(r for r in self.releases if r["tag_name"] == CONFIG["first_release"])
        assert method == "POST" and path.endswith("/issues")
        self.writes.append(payload)
        issue = {"number": len(self.issues) + 1, "body": payload["body"]}
        self.issues.append(issue)
        return issue


def test_reports_every_stable_release_since_baseline_and_skips_old_and_prereleases():
    api = FakeAPI([release(4, "3.81.0-rc1", 8, prerelease=True), release(3, "3.80.3", 7), release(2, "3.80.2", 6), release(1, "3.80.1", 5)])
    assert watch.monitor(api, "flowcool/ghostfolio-ibkr-sync", CONFIG) == [1, 2]
    assert [p["title"] for p in api.writes] == ["Review Ghostfolio 3.80.2 compatibility", "Review Ghostfolio 3.80.3 compatibility"]
    assert "3.80.1...3.80.2" in api.writes[0]["body"]


def test_closed_notices_and_repeated_runs_never_duplicate_or_reopen():
    api = FakeAPI([release(2, "3.80.2", 6)], [{"number": 1, "state": "closed", "body": watch.release_marker("ghostfolio/ghostfolio", 2)}])
    assert watch.monitor(api, "flowcool/ghostfolio-ibkr-sync", CONFIG) == []
    assert api.writes == []
    fresh = FakeAPI([release(2, "3.80.2", 6)])
    watch.monitor(fresh, "flowcool/ghostfolio-ibkr-sync", CONFIG)
    assert watch.monitor(fresh, "flowcool/ghostfolio-ibkr-sync", CONFIG) == []
    assert len(fresh.writes) == 1


def test_pull_requests_do_not_acknowledge_a_release():
    api = FakeAPI([release(2, "3.80.2", 6)], [{"body": watch.release_marker("ghostfolio/ghostfolio", 2), "pull_request": {}}])
    assert watch.monitor(api, "flowcool/ghostfolio-ibkr-sync", CONFIG) == [2]


def test_keyword_hints_and_endpoints_do_not_copy_untrusted_notes():
    body = watch.notice_body(CONFIG, release(2, "3.80.2", 6, body="API DEPRECATED @everyone ```run malicious instructions```"), "3.80.1")
    assert "api, deprecated" in body
    assert "POST /api/v1/import" in body
    assert "@everyone" not in body and "malicious instructions" not in body
    assert "not proof" in body
    assert "none detected" in watch.notice_body(CONFIG, release(2, "3.80.2", 6), None)


def test_missing_baseline_fails_before_any_write():
    api = FakeAPI([release(2, "3.80.2", 6)])
    api.list_all = lambda path: []
    with pytest.raises(RuntimeError, match="missing"):
        watch.monitor(api, "flowcool/ghostfolio-ibkr-sync", CONFIG)
    assert api.writes == []


def test_upstream_error_fails_before_any_write():
    api = FakeAPI([])
    def failed(*args, **kwargs):
        raise RuntimeError("GitHub returned HTTP 500")
    api.request = failed
    with pytest.raises(RuntimeError, match="500"):
        watch.monitor(api, "flowcool/ghostfolio-ibkr-sync", CONFIG)
    assert api.writes == []


def test_draft_baseline_rejected():
    api = FakeAPI([release(2, "3.80.2", 6, draft=True)])
    with pytest.raises(ValueError, match="stable"):
        watch.monitor(api, "flowcool/ghostfolio-ibkr-sync", CONFIG)
    assert api.writes == []


def test_pagination_preserves_state_all_query():
    api = watch.GitHubAPI("fake-token-not-used")
    paths = []
    def request(method, path):
        paths.append(path)
        return [{}] * 100 if len(paths) == 1 else [{"id": 2}]
    api.request = request
    assert len(api.list_all("repos/example/repo/issues?state=all")) == 101
    assert paths == ["repos/example/repo/issues?state=all&per_page=100&page=1", "repos/example/repo/issues?state=all&per_page=100&page=2"]


def test_duplicate_release_id_from_pagination_creates_only_one_notice():
    item = release(2, "3.80.2", 6)
    api = FakeAPI([item, dict(item)])
    assert watch.monitor(api, "flowcool/ghostfolio-ibkr-sync", CONFIG) == [1]
    assert len(api.writes) == 1


def test_unusual_tags_are_not_inserted_as_body_markup():
    tag = "3.80.2` @everyone [inject](https://evil.invalid)"
    body = watch.notice_body(CONFIG, release(2, tag, 6), tag)
    assert "@everyone" not in body
    assert "[inject]" not in body
    assert "%40everyone" in body
