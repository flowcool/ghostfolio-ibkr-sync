#!/bin/bash
# Common local and CI gate: lint, strict application typing, offline tests.
# Extra arguments go to pytest. PYTHON selects the interpreter (default: .venv).
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -z "${PYTHON:-}" ]; then
    if [ -x .venv/bin/python ]; then PYTHON=.venv/bin/python; else PYTHON=python; fi
fi
"$PYTHON" -m ruff check .
"$PYTHON" -m mypy
"$PYTHON" -m pytest -q "$@"
