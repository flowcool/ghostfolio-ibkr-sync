"""Offline dependency release-watch contracts; no real network or issue writes."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "dependency_watch", Path(__file__).parents[1] / "scripts/watch_dependency_releases.py")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)

REPO = "flowcool/ghostfolio-ibkr-sync"
PINS = [{"ecosystem": "pypi", "name": "markdown", "version": "3.10.3"},
        {"ecosystem": "pypi", "name": "apprise", "version": "2.0.1"},
        {"ecosystem": "github", "name": "aptible/supercronic", "version": "0.2.49"}]


def files(day="2026-09-25T13:46:22Z", yanked=False):
    return [{"upload_time_iso_8601": day, "yanked": yanked}]


PYPI = {
    "markdown": ({"releases": {"3.10.3": files(), "3.11": files(), "3.12rc1": files(),
                               "3.12.post1": files(), "3.13": files(yanked=True), "3.14": []},
                  "info": {"project_urls": {"Changelog": "https://python-markdown.github.io/changelog/",
                                            "Homepage": "https://example.org/",
                                            "Release notes": "https://evil.invalid/x)[y](z"}}}),
    "apprise": ({"releases": {"1.13.1": files(), "2.0.1": files(), "3.0.0": files()}, "info": {}}),
}


class FakeAPI:
    def __init__(self, issues=None, supercronic=None):
        self.issues = list(issues or [])
        self.supercronic = supercronic or [{"tag_name": "v0.2.49", "published_at": "2026-08-01T00:00:00Z"}]
        self.writes = []

    def list_all(self, path):
        if path.endswith("/issues?state=all"):
            return self.issues
        if path.endswith("/labels"):
            return [{"name": "dependency-release"}]
        if path == "repos/aptible/supercronic/releases":
            return self.supercronic
        raise AssertionError(path)

    def request(self, method, path, payload=None):
        assert method == "POST" and path.endswith("/issues"), path
        self.writes.append(payload)
        issue = {"number": len(self.issues) + 1, "body": payload["body"]}
        self.issues.append(issue)
        return issue


def fetch(name):
    return watch.pypi_releases(name, fetch=lambda url: PYPI[url.split("/")[-2]])


def test_one_issue_per_newer_stable_release_ignoring_pre_post_yanked_and_empty():
    api = FakeAPI()
    assert watch.monitor(api, REPO, PINS, fetch_pypi=fetch) == [1, 2]
    assert [p["title"] for p in api.writes] == ["Review markdown 3.11 (pinned 3.10.3)",
                                                "Review apprise 3.0.0 (pinned 2.0.1)"]
    assert all(p["labels"] == ["dependency-release"] for p in api.writes)


def test_major_bump_is_flagged_and_minor_is_not():
    api = FakeAPI()
    watch.monitor(api, REPO, PINS, fetch_pypi=fetch)
    assert "minor version change" in api.writes[0]["body"]
    assert "major version change: breaking changes are likely" in api.writes[1]["body"]


def test_repeated_runs_and_closed_issues_never_duplicate_or_reopen():
    api = FakeAPI()
    watch.monitor(api, REPO, PINS, fetch_pypi=fetch)
    assert watch.monitor(api, REPO, PINS, fetch_pypi=fetch) == []
    closed = FakeAPI([{"number": 9, "state": "closed",
                       "body": watch.release_marker(PINS[0], "3.11") + watch.release_marker(PINS[1], "3.0.0")}])
    assert watch.monitor(closed, REPO, PINS, fetch_pypi=fetch) == []
    assert closed.writes == []


def test_pull_requests_do_not_acknowledge_a_release():
    api = FakeAPI([{"body": watch.release_marker(PINS[0], "3.11"), "pull_request": {}}])
    assert len(watch.monitor(api, REPO, PINS[:1], fetch_pypi=fetch)) == 1


def test_supercronic_releases_come_from_github_and_skip_drafts_and_prereleases():
    api = FakeAPI(supercronic=[{"tag_name": "v0.2.49"}, {"tag_name": "v0.2.50", "published_at": "2026-10-01T00:00:00Z"},
                               {"tag_name": "v0.3.0", "prerelease": True}, {"tag_name": "v0.4.0", "draft": True},
                               {"tag_name": "nightly"}])
    assert len(watch.monitor(api, REPO, PINS[2:], fetch_pypi=fetch)) == 1
    body = api.writes[0]["body"]
    assert "https://github.com/aptible/supercronic/releases/tag/v0.2.50" in body
    assert "patch version change" in body


def test_untrusted_metadata_is_never_copied_as_markup():
    api = FakeAPI(supercronic=[{"tag_name": "v0.2.50", "published_at": "@everyone [x](https://evil.invalid)"}])
    watch.monitor(api, REPO, PINS, fetch_pypi=fetch)
    bodies = "\n".join(p["body"] for p in api.writes)
    assert "https://python-markdown.github.io/changelog/" in bodies      # changelog-like and safe
    assert "example.org" not in bodies                                    # not a changelog label
    assert "evil.invalid" not in bodies and "@everyone" not in bodies     # markup or mentions dropped
    assert "Published: unknown" in bodies


def test_new_issues_per_run_are_capped_and_the_rest_follow_next_run():
    many = {"releases": {f"1.{i}": files() for i in range(15)}, "info": {}}
    pins = [{"ecosystem": "pypi", "name": "pkg", "version": "1.0"}]
    api = FakeAPI()
    fetch_many = lambda name: watch.pypi_releases(name, fetch=lambda url: many)
    assert len(watch.monitor(api, REPO, pins, fetch_pypi=fetch_many)) == watch.MAX_NEW_ISSUES_PER_RUN
    assert len(watch.monitor(api, REPO, pins, fetch_pypi=fetch_many)) == 4
    assert [p["title"] for p in api.writes][:2] == ["Review pkg 1.1 (pinned 1.0)", "Review pkg 1.2 (pinned 1.0)"]


def test_nothing_new_makes_no_issue_or_label_call():
    api = FakeAPI()
    up_to_date = [{"ecosystem": "pypi", "name": "apprise", "version": "3.0.0"}]
    assert watch.monitor(api, REPO, up_to_date, fetch_pypi=fetch) == []
    assert api.writes == []


def test_fetch_failure_stops_before_any_write():
    def broken(name):
        raise RuntimeError("GET https://pypi.org/pypi/markdown/json returned HTTP 503")
    api = FakeAPI()
    with pytest.raises(RuntimeError, match="503"):
        watch.monitor(api, REPO, PINS, fetch_pypi=broken)
    assert api.writes == []


def test_invalid_repository_or_package_names_are_rejected():
    with pytest.raises(ValueError):
        watch.monitor(FakeAPI(), "not a repo", PINS, fetch_pypi=fetch)
    with pytest.raises(ValueError):
        watch.monitor(FakeAPI(), REPO, [{"ecosystem": "pypi", "name": "../x", "version": "1"}], fetch_pypi=fetch)


def test_pins_are_read_from_requirements_and_dockerfile(tmp_path):
    (tmp_path / "requirements.txt").write_text("# comment\nRequests==2.34.2\n    # via x\npyyaml==6.0.3\n")
    (tmp_path / "Dockerfile").write_text("FROM python\nARG SUPERCRONIC_VERSION=v0.2.49\n")
    assert watch.read_pins(tmp_path) == [
        {"ecosystem": "pypi", "name": "requests", "version": "2.34.2"},
        {"ecosystem": "pypi", "name": "pyyaml", "version": "6.0.3"},
        {"ecosystem": "github", "name": "aptible/supercronic", "version": "0.2.49"}]


def test_real_repository_pins_are_readable():
    pins = watch.read_pins()
    assert any(p["name"] == "requests" for p in pins) and pins[-1]["name"] == "aptible/supercronic"


@pytest.mark.parametrize("requirements,dockerfile", [
    ("requests==2.34.2rc1\n", "ARG SUPERCRONIC_VERSION=v0.2.49\n"),
    ("requests==2.34.2\n", "FROM python\n"),
    ("", "ARG SUPERCRONIC_VERSION=v0.2.49\n")])
def test_unsupported_or_missing_pins_fail_loudly(tmp_path, requirements, dockerfile):
    (tmp_path / "requirements.txt").write_text(requirements)
    (tmp_path / "Dockerfile").write_text(dockerfile)
    with pytest.raises(ValueError):
        watch.read_pins(tmp_path)
