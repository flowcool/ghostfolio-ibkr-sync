"""Offline dependency release-watch contracts; no real network or issue writes."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "dependency_watch", Path(__file__).parents[1] / "scripts/watch_dependency_releases.py")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)

REPO = "flowcool/ghostfolio-ibkr-sync"
SUPERCRONIC = {"ecosystem": "github", "name": "aptible/supercronic", "version": "0.2.49"}
PINS = [SUPERCRONIC]


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



def new_release_api(issues=None):
    return FakeAPI(issues, supercronic=[{"tag_name": "v0.2.50", "published_at": "2026-10-01T00:00:00Z"}])


def test_one_supercronic_notice_then_zero_on_second_run():
    api = new_release_api()
    assert watch.monitor(api, REPO, PINS) == [1]
    assert watch.monitor(api, REPO, PINS) == []
    assert len(api.writes) == 1
    assert api.writes[0]["title"] == "Review aptible/supercronic 0.2.50 (pinned 0.2.49)"
    assert api.writes[0]["labels"] == ["dependency-release"]
    assert "both architecture SHA256 pins" in api.writes[0]["body"]
    assert "Dependabot" not in api.writes[0]["body"]


def test_python_versions_produce_zero_notices_and_no_metadata_reads():
    # Any PyPI metadata read or issue lookup fails through FakeAPI.list_all.
    api = new_release_api()
    python = [{"ecosystem": "pypi", "name": "markdown", "version": "3.10.3"}]
    assert watch.monitor(api, REPO, python) == []
    assert api.writes == []
    assert watch.monitor(api, REPO, python + PINS) == [1]
    assert len(api.writes) == 1


def test_unrelated_binaries_are_not_watched():
    api = new_release_api()
    assert watch.monitor(api, REPO, [{"ecosystem": "github", "name": "other/binary", "version": "1"}]) == []
    assert api.writes == []


def test_closed_notices_never_duplicate_or_reopen():
    api = new_release_api([{"number": 9, "state": "closed",
                            "body": watch.release_marker(SUPERCRONIC, "0.2.50")}])
    assert watch.monitor(api, REPO, PINS) == []
    assert api.writes == []


def test_equivalent_versions_open_one_notice_and_closed_spelling_acknowledges_it():
    api = FakeAPI(supercronic=[{"tag_name": "v0.2.49.0"}, {"tag_name": "v0.2.50"}, {"tag_name": "v0.2.50.0"}])
    assert watch.monitor(api, REPO, PINS) == [1]
    closed = new_release_api([{"state": "closed", "body": watch.release_marker(SUPERCRONIC, "0.2.50.0")}])
    assert watch.monitor(closed, REPO, PINS) == []


def test_other_dependency_markers_do_not_acknowledge_supercronic():
    pin = {"ecosystem": "github", "name": "other/binary"}
    api = new_release_api([{"body": watch.release_marker(pin, "0.2.50")}])
    assert len(watch.monitor(api, REPO, PINS)) == 1


def test_pull_requests_do_not_acknowledge_a_release():
    api = new_release_api([{"body": watch.release_marker(SUPERCRONIC, "0.2.50"), "pull_request": {}}])
    assert len(watch.monitor(api, REPO, PINS)) == 1


def test_supercronic_releases_skip_drafts_prereleases_and_non_numeric_tags():
    api = FakeAPI(supercronic=[{"tag_name": "v0.2.49"}, {"tag_name": "v0.2.50", "published_at": "2026-10-01T00:00:00Z"},
                               {"tag_name": "v0.3.0", "prerelease": True}, {"tag_name": "v0.4.0", "draft": True},
                               {"tag_name": "nightly"}, {"tag_name": "v0.5.0rc1"}])
    assert watch.monitor(api, REPO, PINS) == [1]
    body = api.writes[0]["body"]
    assert "https://github.com/aptible/supercronic/releases/tag/v0.2.50" in body
    assert "patch version change" in body


@pytest.mark.parametrize("version,level", [("0.2.50", "patch"), ("0.3.0", "minor"), ("1.0.0", "major")])
def test_version_change_level(version, level):
    assert f"{level} version change" in watch.notice_body(SUPERCRONIC, {"version": version}, [])


def test_patch_after_a_two_part_pin_is_a_patch():
    pin = {**SUPERCRONIC, "version": "2.0"}
    assert "patch version change" in watch.notice_body(pin, {"version": "2.0.1"}, [])


def test_untrusted_timestamp_is_never_copied_as_markup():
    api = FakeAPI(supercronic=[{"tag_name": "v0.2.50", "published_at": "@everyone [x](https://evil.invalid)"}])
    watch.monitor(api, REPO, PINS)
    body = api.writes[0]["body"]
    assert "evil.invalid" not in body and "@everyone" not in body
    assert "Published: unknown" in body


def test_new_issues_are_capped_and_the_rest_follow_next_run():
    api = FakeAPI(supercronic=[{"tag_name": f"v0.2.{i}"} for i in range(50, 65)])
    assert len(watch.monitor(api, REPO, PINS)) == 10
    assert len(watch.monitor(api, REPO, PINS)) == 5
    assert len(api.writes) == 15


def test_nothing_new_makes_no_issue_or_label_call():
    api = FakeAPI()
    assert watch.monitor(api, REPO, PINS) == []
    assert api.writes == []


def test_fetch_failure_stops_before_any_write():
    api = FakeAPI()
    def broken(path):
        raise RuntimeError("GitHub returned HTTP 503")
    api.list_all = broken
    with pytest.raises(RuntimeError, match="503"):
        watch.monitor(api, REPO, PINS)
    assert api.writes == []


def test_invalid_repository_is_rejected():
    with pytest.raises(ValueError):
        watch.monitor(FakeAPI(), "not a repo", PINS)


def test_only_supercronic_pin_is_read_without_requirements(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM python\nARG SUPERCRONIC_VERSION=v0.2.49\n")
    assert watch.read_pins(tmp_path) == PINS
    (tmp_path / "requirements.txt").write_text("arbitrary unpinned Python package\n")
    assert watch.read_pins(tmp_path) == PINS


def test_real_repository_pin_is_readable():
    assert watch.read_pins() == [{**SUPERCRONIC, "version": "0.2.51"}]


@pytest.mark.parametrize("dockerfile", ["FROM python\n", "ARG SUPERCRONIC_VERSION=v0.2.49rc1\n",
                                        "ARG SUPERCRONIC_VERSION=latest\n"])
def test_unsupported_or_missing_supercronic_pin_fails(tmp_path, dockerfile):
    (tmp_path / "Dockerfile").write_text(dockerfile)
    with pytest.raises(ValueError, match="SUPERCRONIC_VERSION"):
        watch.read_pins(tmp_path)
