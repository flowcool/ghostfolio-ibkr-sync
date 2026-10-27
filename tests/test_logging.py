"""Application log streams through the CLI setup, with synthetic work."""
import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING"])
def test_operator_action_logging_streams_and_evidence(level):
    code = """
import logging
from ghostfolio_ibkr_sync import __main__ as cli
from ghostfolio_ibkr_sync.ibkr import log_lab_evidence

def synthetic():
    for level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL):
        logging.getLogger('synthetic').log(level, 'CANARY_LEVEL_%s', logging.getLevelName(level))
    logging.getLogger('urllib3').debug('BROKER_SECRET')
    log_lab_evidence('window', {'line': 'one\\ntwo'})
    return 0
cli.main = synthetic
raise SystemExit(cli.run())
"""
    env = {"PATH": os.environ["PATH"], "LOG_LEVEL": level}
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    for name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        marker = "CANARY_LEVEL_" + name
        visible = (level == "DEBUG" or name != "DEBUG") and (level != "WARNING" or name not in ("DEBUG", "INFO"))
        stream = result.stdout if name in ("DEBUG", "INFO") else result.stderr
        other = result.stderr if name in ("DEBUG", "INFO") else result.stdout
        assert stream.count(marker) == int(visible)
        assert marker not in other
    assert "BROKER_SECRET" not in result.stdout + result.stderr
    lines = [line for line in result.stdout.splitlines() if "LAB_EVIDENCE " in line]
    assert len(lines) == int(level == "DEBUG")
    if lines:
        assert "[DEBUG] LAB_EVIDENCE " in lines[0]
        assert json.loads(lines[0].split("LAB_EVIDENCE ", 1)[1]) == {"kind": "window", "value": {"line": "one\ntwo"}}
