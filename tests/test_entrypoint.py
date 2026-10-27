from pathlib import Path
import subprocess

import pytest


@pytest.fixture
def run_entrypoint(tmp_path):
    """Run only synthetic executables, with all writes isolated from /app."""
    source = Path(__file__).resolve().parents[1] / 'entrypoint.sh'
    script = tmp_path / 'entrypoint.sh'
    crontab = tmp_path / 'crontab'
    created_paths = tmp_path / 'crontab-paths'
    script.write_text(source.read_text())
    mktemp = tmp_path / 'mktemp'
    mktemp.write_text(
        '#!/bin/bash\n'
        '[ "$1" = /tmp/ibkr-crontab.XXXXXX ] || exit 1\n'
        '[ "$MKTEMP_STATUS" = 0 ] || exit "$MKTEMP_STATUS"\n'
        'created=$(/usr/bin/mktemp "$RUNTIME_DIR/ibkr-crontab.XXXXXX") || exit 1\n'
        'printf "%s\\n" "$created" >> "$CRONTAB_PATHS"\n'
        'printf "%s\\n" "$created"\n'
    )
    mktemp.chmod(0o755)
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
        '    printf "%s\\n" "$*" >> "$RUNTIME_DIR/scheduler-args"\n'
        '    shift 2\n'
        '    umask > "$RUNTIME_DIR/runtime-umask"\n'
        '    cat "$1"\n'
        'fi\n'
    )
    supercronic.chmod(0o755)
    python = tmp_path / 'python'
    python.write_text('#!/bin/bash\nprintf "python %s\\n" "$*" >> "$CALLS"\n')
    python.chmod(0o755)

    def run(cron=None, validation_status=0, mktemp_status=0):
        # Do not inherit developer credentials, notifications or scheduler settings.
        env = {
            'PATH': f'{tmp_path}:/usr/bin:/bin',
            'APP_VERSION': 'test',
            'CALLS': str(calls),
            'VALIDATION_STATUS': str(validation_status),
            'MKTEMP_STATUS': str(mktemp_status),
            'RUNTIME_DIR': str(tmp_path),
            'CRONTAB_PATHS': str(created_paths),
        }
        if cron is not None:
            env['CRON'] = cron
        result = subprocess.run(
            ['/bin/bash', str(script)], env=env, capture_output=True,
            text=True, timeout=5,
        )
        generated = (Path(created_paths.read_text().splitlines()[-1])
                     if created_paths.exists() else crontab)
        return result, generated, calls

    return run


@pytest.mark.parametrize('cron', [
    '0 6 * * *', '*/5 * * * *', '0,30 6-18/2 * * 1-5', '0\t6\t*\t*\t*',
])
def test_valid_cron_is_written_and_tested_before_start(run_entrypoint, cron):
    result, crontab, calls = run_entrypoint(cron)
    assert result.returncode == 0
    assert crontab.read_text() == f'{cron} python -m ghostfolio_ibkr_sync\n'
    assert calls.read_text().splitlines() == ['test', 'run']
    assert crontab.stat().st_mode & 0o777 == 0o600


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
    assert result.stdout == 'ghostfolio-ibkr-sync build test\n'
    assert not crontab.exists()
    assert not calls.exists()


def test_supercronic_validation_failure_prevents_start(run_entrypoint):
    result, crontab, calls = run_entrypoint('99 99 * * *', validation_status=1)
    assert result.returncode == 1
    assert result.stderr == 'Invalid CRON: schedule validation failed\n'
    assert result.stdout == 'ghostfolio-ibkr-sync build test\n'
    assert calls.read_text().splitlines() == ['test']


def test_crontab_creation_failure_prevents_start(run_entrypoint):
    result, crontab, calls = run_entrypoint('0 6 * * *', mktemp_status=1)
    assert result.returncode == 1
    assert result.stderr == 'Could not create runtime crontab\n'
    assert not crontab.exists()
    assert not calls.exists()


def test_repeated_scheduled_starts_keep_unique_crontabs(run_entrypoint):
    first, first_path, calls = run_entrypoint('0 6 * * *')
    second, second_path, calls = run_entrypoint('5 6 * * *')
    assert first.returncode == second.returncode == 0
    assert first_path != second_path
    assert first_path.read_text() == '0 6 * * * python -m ghostfolio_ibkr_sync\n'
    assert second_path.read_text() == '5 6 * * * python -m ghostfolio_ibkr_sync\n'
    assert calls.read_text().splitlines() == ['test', 'run', 'test', 'run']


def test_private_crontab_umask_is_not_inherited_by_scheduler(run_entrypoint):
    baseline = subprocess.run(
        ['/bin/bash', '-c', 'umask'], capture_output=True, text=True, timeout=5,
        env={'PATH': '/usr/bin:/bin'},
    )
    result, crontab, calls = run_entrypoint('0 6 * * *')
    assert result.returncode == baseline.returncode == 0
    assert (crontab.parent / 'runtime-umask').read_text() == baseline.stdout
    assert crontab.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('cron', [None, ''])
def test_no_cron_preserves_one_off_run(run_entrypoint, cron):
    result, crontab, calls = run_entrypoint(cron)
    assert result.returncode == 0
    assert calls.read_text() == 'python -m ghostfolio_ibkr_sync\n'
    assert not crontab.exists()


def test_operator_action_logging_scheduler_flags_and_build(run_entrypoint):
    result, crontab, calls = run_entrypoint('* * * * *')
    assert result.returncode == 0
    assert 'ghostfolio-ibkr-sync build test' in result.stdout
    assert '-passthrough-logs -split-logs' in (calls.parent / 'scheduler-args').read_text()
