from pathlib import Path
import subprocess

import pytest


@pytest.fixture
def run_entrypoint(tmp_path):
    """Run only synthetic executables, with all writes isolated from /app."""
    source = Path(__file__).resolve().parents[1] / 'entrypoint.sh'
    script = tmp_path / 'entrypoint.sh'
    crontab = tmp_path / 'crontab'
    script.write_text(source.read_text().replace('/app/crontab', str(crontab)))
    calls = tmp_path / 'calls'
    supercronic = tmp_path / 'supercronic'
    supercronic.write_text(
        '#!/bin/bash\n'
        'if [ "$1" = -test ]; then\n'
        '    echo test >> "$CALLS"\n'
        '    if [ "$VALIDATION_STATUS" != 0 ]; then\n'
        '        echo synthetic-validator-output >&2\n'
        '        exit "$VALIDATION_STATUS"\n'
        '    fi\n'
        'else\n'
        '    echo run >> "$CALLS"\n'
        '    cat "$1"\n'
        'fi\n'
    )
    supercronic.chmod(0o755)
    python = tmp_path / 'python'
    python.write_text('#!/bin/bash\nprintf "python %s\\n" "$1" >> "$CALLS"\n')
    python.chmod(0o755)

    def run(cron=None, validation_status=0):
        # Do not inherit developer credentials, notifications or scheduler settings.
        env = {
            'PATH': f'{tmp_path}:/usr/bin:/bin',
            'APP_VERSION': 'test',
            'CALLS': str(calls),
            'VALIDATION_STATUS': str(validation_status),
        }
        if cron is not None:
            env['CRON'] = cron
        result = subprocess.run(
            ['/bin/bash', str(script)], env=env, capture_output=True,
            text=True, timeout=5,
        )
        return result, crontab, calls

    return run


@pytest.mark.parametrize('cron', [
    '0 6 * * *', '*/5 * * * *', '0,30 6-18/2 * * 1-5', '0\t6\t*\t*\t*',
])
def test_valid_cron_is_written_and_tested_before_start(run_entrypoint, cron):
    result, crontab, calls = run_entrypoint(cron)
    assert result.returncode == 0
    assert crontab.read_text() == f'{cron} python /app/ibkr_to_ghostfolio.py\n'
    assert calls.read_text().splitlines() == ['test', 'run']


@pytest.mark.parametrize('cron', [
    '* * * *', '* * * * * *', '@daily', '0 6 * * MON',
    '0 6 * * *; echo injected', '0 6 * * $(id)',
    '0 6 * * *\n* * * * * echo injected', '0 6 * * *\r',
    ' 0 6 * * *', '0 6 * * * ', '0  6 * * *', '0 6 * * ?',
])
def test_invalid_cron_is_rejected_without_echoing_input(run_entrypoint, cron):
    result, crontab, calls = run_entrypoint(cron)
    assert result.returncode == 1
    assert result.stderr == 'Invalid CRON: expected five numeric schedule fields\n'
    assert result.stdout == 'ghostfolio-ibkr-sync version test\n'
    assert not crontab.exists()
    assert not calls.exists()


def test_supercronic_validation_failure_prevents_start(run_entrypoint):
    result, crontab, calls = run_entrypoint('99 99 * * *', validation_status=1)
    assert result.returncode == 1
    assert result.stderr == 'Invalid CRON: schedule validation failed\n'
    assert result.stdout == 'ghostfolio-ibkr-sync version test\n'
    assert calls.read_text().splitlines() == ['test']


@pytest.mark.parametrize('cron', [None, ''])
def test_no_cron_preserves_one_off_run(run_entrypoint, cron):
    result, crontab, calls = run_entrypoint(cron)
    assert result.returncode == 0
    assert calls.read_text() == 'python /app/ibkr_to_ghostfolio.py\n'
    assert not crontab.exists()
