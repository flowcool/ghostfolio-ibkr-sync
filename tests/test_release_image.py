"""Offline release-candidate metadata contracts; no registry, git or network."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release_image = load("release_image", "release_image.py")
verify_release_image = load("verify_release_image", "verify_release_image.py")


def event(tag, prerelease, draft=False, action="published"):
    return {"action": action, "release": {"tag_name": tag, "prerelease": prerelease, "draft": draft}}


@pytest.mark.parametrize("tag,prerelease,version", [
    ("v3.0.0-rc.1", True, "3.0.0-rc.1"),
    ("v3.10.20-rc.12", True, "3.10.20-rc.12"),
    ("v3.0.0", False, "3.0.0"),
])
def test_release_candidate_metadata_accepts(tag, prerelease, version):
    assert release_image.release_metadata(event(tag, prerelease)) == (tag, version)


@pytest.mark.parametrize("tag,prerelease,draft,action", [
    ("v3.0.0-rc.0", True, False, "published"),
    ("v3.0.0-rc.01", True, False, "published"),
    ("v3.0.0-beta.1", True, False, "published"),
    ("v03.0.0-rc.1", True, False, "published"),
    ("v3.00.0-rc.1", True, False, "published"),
    ("v3.0.0-rc.1", False, False, "published"),
    ("v3.0.0", True, False, "published"),
    ("v3.0.0-rc.1", True, True, "published"),
    ("v3.0.0", False, True, "published"),
    ("v3.0.0-rc.1", True, False, "created"),
    ("v3.0.0-rc.1-extra", True, False, "published"),
    ("3.0.0-rc.1", True, False, "published"),
    ("v3.0.0-rc.1", None, False, "published"),
    (None, True, False, "published"),
])
def test_release_candidate_metadata_refuses(tag, prerelease, draft, action):
    with pytest.raises(RuntimeError):
        release_image.release_metadata(event(tag, prerelease, draft, action))


def test_release_candidate_metadata_refuses_missing_draft_flag():
    payload = event("v3.0.0-rc.1", True)
    del payload["release"]["draft"]
    with pytest.raises(RuntimeError):
        release_image.release_metadata(payload)


def test_release_candidate_metadata_assemble_version(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "digests").mkdir()
    for arch in ("amd64", "arm64"):
        (tmp_path / "digests" / (arch + ".txt")).write_text("sha256:" + "a" * 64)
    calls = []

    def fake_check_output(command, **kwargs):
        calls.append(command)
        return b"{}"

    monkeypatch.setattr(verify_release_image.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(verify_release_image.subprocess, "run", lambda *a, **k: calls.append(a[0]))
    for version in ("3.0.0-rc.0", "3.0.0-rc.01", "3.0.0-beta.1", "3.0.0-rc.1-x", "3.0.0-rc."):
        with pytest.raises(RuntimeError):
            verify_release_image.assemble("ghcr.io/o/r", version)
    assert not calls
    # A valid RC passes validation; the empty fake index then fails closed on the native manifest.
    with pytest.raises(RuntimeError, match="native image manifest"):
        verify_release_image.assemble("ghcr.io/o/r", "3.0.0-rc.1")
    assert calls
