"""Offline regression checks for the image's supply-chain controls."""
from pathlib import Path
import json
import re
import shlex

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYTHON_WORKFLOWS = {
    'docker-publish.yml': 2,
    'release-image.yml': 3,
    'dependency-release-watch.yml': 1,
    'upstream-release-watch.yml': 1,
}


def dockerfile():
    return (ROOT / 'Dockerfile').read_text()


def test_python_base_keeps_tag_and_pins_digest():
    assert re.fullmatch(r'FROM python:3\.14-slim@sha256:[0-9a-f]{64}',
                        dockerfile().splitlines()[0])


def test_python_runtime_baseline_docker_base_is_3_14():
    test_python_base_keeps_tag_and_pins_digest()


def test_python_runtime_baseline_all_workflow_pins_are_3_14():
    pins = {}
    for path in sorted((ROOT / '.github' / 'workflows').glob('*.yml')):
        versions = re.findall(r'python-version:\s*"([^"]+)"', path.read_text())
        if versions:
            pins[path.name] = versions
    assert pins == {name: ['3.14'] * count
                    for name, count in PYTHON_WORKFLOWS.items()}


def test_python_runtime_baseline_renovate_ranges_are_3_14():
    rules = json.loads((ROOT / 'renovate.json').read_text())['packageRules']
    ranges = {rule['matchManagers'][0]: rule['allowedVersions'] for rule in rules
              if rule.get('matchPackageNames') == ['python']}
    assert ranges == {'dockerfile': '/^3\\.14(?:\\.|-|$)/',
                      'github-actions': '>=3.14 <3.15'}
    assert re.search(ranges['dockerfile'][1:-1], '3.14-slim')
    assert not re.search(ranges['dockerfile'][1:-1], '3.15-slim')


def test_python_runtime_baseline_public_guidance_names_3_14():
    readme = (ROOT / 'README.md').read_text()
    assert 'Python 3.14+ with the pinned packages' in readme
    assert '(CI and the container use Python 3.14)' in readme
    assert 'CI and the container use Python 3.14.' in (
        ROOT / 'CONTRIBUTING.md').read_text()
    assert 'Python 3.14 slim with an immutable digest' in (
        ROOT / 'docs' / 'upstreams.md').read_text()
    for name in ('README.md', 'CONTRIBUTING.md', 'docs/upstreams.md'):
        assert '3.12' not in (ROOT / name).read_text()


def test_supercronic_download_requires_https_and_tls_minimum():
    line = next(line.strip() for line in dockerfile().splitlines()
                if line.strip().startswith('curl '))
    args = shlex.split(line.split(' && ', 1)[0])
    assert args[args.index('--proto') + 1] == '=https'
    assert args[args.index('--proto-redir') + 1] == '=https'
    assert '--tlsv1.2' in args
    assert '-fsSLO' in args
    assert args[-1] == ('https://github.com/aptible/supercronic/releases/download/'
                        '${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH}')


@pytest.mark.parametrize('arch,checksum', [
    ('amd64', 'a53ae236602c7338aba3fbaff40bda6300eae3b9fedb8261eb06cfe3724430c1'),
    ('arm64', '02aa0cb229ba09050cba6638059dadb9eedc2276632ea43d6a57a2f8c1629dd5'),
])
def test_existing_architecture_checksum_gate_is_preserved(arch, checksum):
    source = dockerfile()
    assert 'ARG SUPERCRONIC_VERSION=v0.2.49' in source
    assert f'ARG SUPERCRONIC_SHA256SUM_{arch}={checksum}' in source
    assert f'{arch}) EXPECTED="${{SUPERCRONIC_SHA256SUM_{arch}}}" ;;' in source
    assert 'echo "${EXPECTED}  supercronic-linux-${TARGETARCH}" | sha256sum -c - &&' in source
