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


A, B, C = "a" * 40, "b" * 40, "c" * 40


def test_release_candidate_stable_commit_refuses_later_commit():
    tags = {"v3.0.0-rc.1": A, "v3.0.0-rc.2": B}
    with pytest.raises(RuntimeError, match=r"v3\.0\.0 .*v3\.0\.0-rc\.2"):
        release_image.stable_follows_release_candidate("v3.0.0", tags, C)
    release_image.stable_follows_release_candidate("v3.0.0", tags, B)


def test_release_candidate_stable_commit_highest_is_numeric():
    tags = {"v3.0.0-rc.9": A, "v3.0.0-rc.10": B}
    release_image.stable_follows_release_candidate("v3.0.0", tags, B)
    with pytest.raises(RuntimeError, match=r"v3\.0\.0-rc\.10"):
        release_image.stable_follows_release_candidate("v3.0.0", tags, A)


def test_release_candidate_stable_commit_ignores_malformed_and_other_versions():
    tags = {"v3.0.0-rc.1": A, "v3.0.0-rc.0": B, "v3.0.0-rc.01": B, "v3.0.0-beta.1": B,
            "v3.0.0-rc.2-x": B, "v3.0.01-rc.5": B, "v3.0.10-rc.9": B, "v3.0.0-rc.": B}
    release_image.stable_follows_release_candidate("v3.0.0", tags, A)


def test_release_candidate_stable_commit_without_rc_proceeds():
    release_image.stable_follows_release_candidate("v3.0.0", {}, C)
    release_image.stable_follows_release_candidate("v3.0.0", {"v3.0.1-rc.1": A}, C)


def test_release_candidate_stable_commit_skips_rc_tags():
    release_image.stable_follows_release_candidate("v3.0.0-rc.2", {"v3.0.0-rc.3": A}, C)


def test_release_candidate_stable_commit_git_wrapper(monkeypatch):
    commits = {"v3.0.0-rc.1": A, "v3.0.0-rc.2": B}
    calls = []

    def fake_check_output(command, **kwargs):
        calls.append(command)
        if command[:3] == ["git", "tag", "--list"]:
            assert command[3] == "v3.0.0-rc.*"
            return "\n".join(commits) + "\n"
        return commits[command[2][:-len("^{commit}")]] + "\n"

    monkeypatch.setattr(release_image.subprocess, "check_output", fake_check_output)
    assert release_image.release_candidate_commits("v3.0.0") == commits


@pytest.mark.parametrize('tag', ['v3.0.0', 'v3.0.0-rc.1', 'v3.0.0-rc.12'])
def test_release_identity_target_version(tag):
    assert release_image.release_identity(tag, A) == ('3.0.0', A)


@pytest.mark.parametrize('tag,commit', [
    ('v03.0.0-rc.1', A), ('v3.0.0-rc.0', A), ('v3.0.0-extra', A),
    ('v3.0.0', ''), ('v3.0.0', None), ('v3.0.0', 'abc1234'),
    ('v3.0.0', 'A' * 40), ('v3.0.0', A + '\n'),
])
def test_release_identity_refuses_invalid_input(tag, commit):
    with pytest.raises(RuntimeError):
        release_image.release_identity(tag, commit)


def image_config(arch='amd64', legacy=False):
    version = 'v3.0.0-rc.2' if legacy else '3.0.0'
    return {'architecture': arch, 'os': 'linux', 'config': {
        'Labels': {'org.opencontainers.image.source': 'https://github.com/o/r',
                   'org.opencontainers.image.version': version,
                   'org.opencontainers.image.revision': A},
        'Env': ['PATH=/bin', 'APP_VERSION=' + version] + ([] if legacy else ['APP_REVISION=' + A]),
    }}


@pytest.mark.parametrize('arch', ['amd64', 'arm64'])
@pytest.mark.parametrize('legacy', [False, True])
def test_release_identity_complete_forms(arch, legacy):
    assert release_image.verify_image_identity(image_config(arch, legacy), 'v3.0.0-rc.2', A,
                                               'o/r', arch, allow_legacy=True) == ('legacy' if legacy else 'target')
    if legacy:
        with pytest.raises(RuntimeError):
            release_image.verify_image_identity(image_config(arch, legacy), 'v3.0.0-rc.2', A, 'o/r', arch)


@pytest.mark.parametrize('field,value', [
    ('APP_VERSION', '3.0.1'), ('APP_VERSION', 'v3.0.0-rc.2'),
    ('APP_REVISION', B), ('APP_REVISION', ''), ('APP_REVISION', None),
    ('org.opencontainers.image.version', 'v3.0.0-rc.2'),
    ('org.opencontainers.image.revision', B), ('org.opencontainers.image.source', 'https://github.com/wrong/repo'),
])
def test_release_identity_refuses_mismatch(field, value):
    config = image_config()
    if field.startswith('APP_'):
        config['config']['Env'] = [s for s in config['config']['Env'] if not s.startswith(field + '=')]
        if value is not None:
            config['config']['Env'].append(field + '=' + value)
    else:
        config['config']['Labels'][field] = value
    with pytest.raises(RuntimeError):
        release_image.verify_image_identity(config, 'v3.0.0-rc.2', A, 'o/r', 'amd64', allow_legacy=True)


def test_release_identity_refuses_ambiguous_and_legacy_mixed():
    config = image_config()
    config['config']['Env'].append('APP_VERSION=3.0.0')
    with pytest.raises(RuntimeError):
        release_image.verify_image_identity(config, 'v3.0.0-rc.2', A, 'o/r', 'amd64')
    config = image_config(legacy=True)
    config['config']['Env'].append('APP_REVISION=' + A)
    with pytest.raises(RuntimeError):
        release_image.verify_image_identity(config, 'v3.0.0-rc.2', A, 'o/r', 'amd64', allow_legacy=True)


@pytest.mark.parametrize('mode', ['target', 'legacy', 'mismatch', 'mixed_architectures'])
def test_release_identity_promotion_before_writes(monkeypatch, mode):
    import hashlib
    import json
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    promotion = load('identity_promotion', 'promote_release_image.py')
    native = {'amd64': 'sha256:' + 'd' * 64, 'arm64': 'sha256:' + 'e' * 64}
    raw = json.dumps({'manifests': [
        {'platform': {'os': 'linux', 'architecture': arch}, 'digest': digest}
        for arch, digest in native.items()]}).encode()
    digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
    selected = ('v3.0.0', '3.0.0', 'v3.0.0-rc.2',
                {'repository': 'o/r', 'commit': A, 'digest': digest, 'native': native})
    calls = []

    def output(*args):
        if '--raw' in args:
            return raw
        arch = next(a for a, d in native.items() if args[-1].endswith(d))
        config = image_config(arch, mode == 'legacy' or (mode == 'mixed_architectures' and arch == 'arm64'))
        if mode == 'mismatch':
            config['config']['Env'][-1] = 'APP_REVISION=' + B
        return json.dumps(config).encode()

    monkeypatch.setattr(promotion, 'output', output)
    monkeypatch.setattr(promotion.subprocess, 'run', lambda command, **kwargs: calls.append(command))
    if mode in ('target', 'legacy'):
        assert promotion.promote(selected, verify_only=True) == raw
    else:
        with pytest.raises(RuntimeError):
            promotion.promote(selected)
    assert len(calls) == 1 and calls[0][:2] == ['cosign', 'verify']
