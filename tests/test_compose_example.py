"""Offline checks for the README's scheduled Compose example."""
from pathlib import Path

import pytest
import yaml


def compose_example():
    readme = (Path(__file__).resolve().parents[1] / 'README.md').read_text(encoding='utf-8')
    heading = '## Docker Compose / Portainer\n'
    assert heading in readme, 'README Compose section not found'
    section = readme.split(heading, 1)[1].split('\n## ', 1)[0]
    expected = {'ibkr-sync-individual', 'ibkr-sync-joint'}
    for fenced in section.split('```yaml\n')[1:]:
        parsed = yaml.safe_load(fenced.split('```', 1)[0])
        services = parsed.get('services') if isinstance(parsed, dict) else None
        if isinstance(services, dict) and expected <= set(services):
            return parsed
    raise AssertionError('README scheduled Compose YAML block not found')


def test_compose_helper_selects_scheduled_services_not_first_block(monkeypatch):
    readme = ('## Docker Compose / Portainer\n'
              '```yaml\nservices: {unrelated: {}}\n```\n'
              '```yaml\nservices: {ibkr-sync-individual: {}, ibkr-sync-joint: {}}\n```\n')
    monkeypatch.setattr(Path, 'read_text', lambda *args, **kwargs: readme)
    assert set(compose_example()['services']) == {'ibkr-sync-individual', 'ibkr-sync-joint'}


@pytest.mark.parametrize('readme', [
    '', '## Docker Compose / Portainer\n```yaml\n[]\n```\n',
    '## Docker Compose / Portainer\n```yaml\nservices: {unrelated: {}}\n```\n',
])
def test_compose_helper_rejects_missing_scheduled_example(monkeypatch, readme):
    monkeypatch.setattr(Path, 'read_text', lambda *args, **kwargs: readme)
    with pytest.raises(AssertionError, match='README .* not found'):
        compose_example()


def test_compose_services_use_read_only_hardening_and_tmpfs():
    services = compose_example()['services']
    assert len(services) == 2
    for service in services.values():
        assert service['read_only'] is True
        assert service['cap_drop'] == ['ALL']
        assert service['security_opt'] == ['no-new-privileges:true']
        assert service['tmpfs'] == ['/tmp:rw,noexec,nosuid,size=16m,mode=1777']
        assert service['volumes'] == ['./mapping.yaml:/app/mapping.yaml:ro']
        assert service['image'] == 'ghcr.io/flowcool/ghostfolio-ibkr-sync:latest'


def test_compose_credentials_require_operator_values_not_inline_secrets():
    for service in compose_example()['services'].values():
        env = service['environment']
        assert env['IBKR_TOKEN'] == '${IBKR_TOKEN:?Set IBKR_TOKEN}'
        assert env['GHOST_ACCESS_TOKEN'] == '${GHOST_ACCESS_TOKEN:?Set GHOST_ACCESS_TOKEN}'
        assert 'GHOST_TOKEN' not in env
