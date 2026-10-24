"""Offline checks for the canonical scheduled Compose example."""
from pathlib import Path
import re

import pytest
import yaml


def compose_example():
    compose = (Path(__file__).resolve().parents[1] / 'compose.yaml').read_text(encoding='utf-8')
    expected = {'ibkr-sync-individual', 'ibkr-sync-joint'}
    parsed = yaml.safe_load(compose)
    services = parsed.get('services') if isinstance(parsed, dict) else None
    if isinstance(services, dict) and expected <= set(services):
        return parsed
    raise AssertionError('canonical scheduled Compose YAML not found')


def test_compose_helper_selects_scheduled_services_not_first_block(monkeypatch):
    compose = 'services: {ibkr-sync-individual: {}, ibkr-sync-joint: {}}\n'
    monkeypatch.setattr(Path, 'read_text', lambda *args, **kwargs: compose)
    assert set(compose_example()['services']) == {'ibkr-sync-individual', 'ibkr-sync-joint'}


@pytest.mark.parametrize('compose', [
    '', '[]\n', 'services: {unrelated: {}}\n',
])
def test_compose_helper_rejects_missing_scheduled_example(monkeypatch, compose):
    monkeypatch.setattr(Path, 'read_text', lambda *args, **kwargs: compose)
    with pytest.raises(AssertionError, match='canonical .* not found'):
        compose_example()


def test_compose_services_use_read_only_hardening_and_tmpfs():
    services = compose_example()['services']
    assert len(services) == 2
    for name, service in services.items():
        assert service['user'] == '10001:10001'
        assert service['read_only'] is True
        assert service['cap_drop'] == ['ALL']
        assert service['security_opt'] == ['no-new-privileges:true']
        assert service['tmpfs'] == ['/tmp:rw,noexec,nosuid,size=16m,mode=1777']
        assert service['volumes'] == ['./mapping.yaml:/app/mapping.yaml:ro',
                                      './state/' + ('joint' if name.endswith('joint') else 'individual') + ':/state']
        assert service['environment']['CORPORATE_ACTION_STATE_FILE'] == '/state/corporate-actions.yaml'
        assert service['image'] == 'ghcr.io/flowcool/ghostfolio-ibkr-sync:latest'


def test_compose_credentials_require_operator_values_not_inline_secrets():
    for service in compose_example()['services'].values():
        env = service['environment']
        assert env['IBKR_TOKEN'] == '${IBKR_TOKEN:?Set IBKR_TOKEN}'
        assert env['GHOST_ACCESS_TOKEN'] == '${GHOST_ACCESS_TOKEN:?Set GHOST_ACCESS_TOKEN}'
        assert 'GHOST_TOKEN' not in env


# The suffix is optional so a bare reference (implicit tag) is caught and rejected.
IMAGE_REF = re.compile(r'ghcr\.io/flowcool/ghostfolio-ibkr-sync(?![\w./-])([:@][^\s`\'"]*)?')
# Release CI moves :latest only to the current stable release, so it never needs a
# bump PR; a digest pins one exact artifact. A version tag in the Compose file would age.
ALLOWED_REF = re.compile(r':latest|@sha256:(?:[0-9a-f]{64}|\.\.\.|<[^>]+>)')


def stale_image_refs(text):
    return [ref for ref in IMAGE_REF.findall(text) if not ALLOWED_REF.fullmatch(ref)]


def test_readme_image_refs_use_latest_or_digest():
    readme = (Path(__file__).resolve().parents[1] / 'README.md').read_text(encoding='utf-8')
    assert IMAGE_REF.findall(readme)
    assert stale_image_refs(readme) == []


def test_readme_version_tag_is_rejected():
    assert stale_image_refs('image: ghcr.io/flowcool/ghostfolio-ibkr-sync:2.4.1\n') == [':2.4.1']


def test_readme_bare_reference_is_rejected():
    text = 'image: ghcr.io/flowcool/ghostfolio-ibkr-sync:latest\nimage: ghcr.io/flowcool/ghostfolio-ibkr-sync\n'
    assert stale_image_refs(text) == ['']


def test_readme_sub_path_image_is_ignored():
    text = 'image: ghcr.io/flowcool/ghostfolio-ibkr-sync:latest\nimage: ghcr.io/flowcool/ghostfolio-ibkr-sync/sidecar:1\n'
    assert stale_image_refs(text) == []
