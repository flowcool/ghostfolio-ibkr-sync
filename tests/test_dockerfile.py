"""Offline regression checks for the image's supply-chain controls."""
from pathlib import Path
import re
import shlex

import pytest


def dockerfile():
    return (Path(__file__).resolve().parents[1] / 'Dockerfile').read_text()


def test_python_base_keeps_tag_and_pins_digest():
    assert re.fullmatch(r'FROM python:3\.12-slim@sha256:[0-9a-f]{64}',
                        dockerfile().splitlines()[0])


def test_supercronic_download_requires_https_and_tls_minimum():
    line = next(line.strip() for line in dockerfile().splitlines()
                if line.strip().startswith('curl '))
    args = shlex.split(line.split(' && ', 1)[0])
    assert args[args.index('--proto') + 1] == '=https'
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
