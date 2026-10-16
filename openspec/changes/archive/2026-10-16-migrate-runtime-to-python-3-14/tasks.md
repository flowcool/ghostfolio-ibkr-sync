# Tasks

## 1. Python 3.14 runtime baseline

- [x] 1.1 Recreate the local `.venv` on Python 3.14 (`uv venv --python 3.14 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt`). Change the Docker base and digest, all seven workflow pins, and both Renovate ranges to Python 3.14. Keep both requirements files unchanged. Update the focused repository checks, name the new tests `test_python_runtime_baseline_*`, and make `scripts/check_container_runtime.sh` assert CPython 3.14 inside the image. Update README, CONTRIBUTING, and `docs/upstreams.md` to state the new supported baseline without blocking Python 3.12. Verify with `.venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 14)' && .venv/bin/python -m pytest -q tests -k python_runtime_baseline && .venv/bin/python -m pytest -q && docker build -t ibkr-python314:check . && bash scripts/check_container_runtime.sh ibkr-python314:check && openspec validate migrate-runtime-to-python-3-14 --strict`.
