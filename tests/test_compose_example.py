"""Offline checks for the README's scheduled Compose example."""
from pathlib import Path

import yaml


def compose_example():
    readme = (Path(__file__).resolve().parents[1] / 'README.md').read_text()
    # Deliberately coupled to this heading and its first YAML fence; fail on drift.
    section = readme.split('## Docker Compose / Portainer\n', 1)[1]
    return yaml.safe_load(section.split('```yaml\n', 1)[1].split('```', 1)[0])


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
