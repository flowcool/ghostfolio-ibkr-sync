---
description: Python conventions for the ghostfolio_ibkr_sync package
globs: ["*.py"]
---

- Package code (`ghostfolio_ibkr_sync/`) is fully typed and passes strict mypy and Ruff via `scripts/check.sh`; tests keep relaxed typing; never change runtime behavior to satisfy a type (use narrow annotations or `cast`)
- Logging: `log.warning` for operational skips, `log.error` for failures, `log.debug` for verbose
- Never log a token or credential
- Errors: `raise RuntimeError(...)` with explicit message, never silent `return` on failure
- One module per concern under `ghostfolio_ibkr_sync/` (`models`, `config`, `ibkr`, `ghostfolio`, `sync`, `diagnostics`, `outcome`, `notify`, `app`, `__main__`); shared immutable models live in `models` to avoid import cycles; the legacy single file is gone, no launcher
- Tests: `pytest` in `tests/` (offline, pure functions, requests mocked; dev-only deps in `requirements-dev.txt`, never in the image). Run `.venv/bin/python -m pytest -q` before commit. A logic change ships with a test; live-data checks stay in `/test-sync` and the review-pr A/B dry run
- Functional style with module-level functions; no behavior classes. Frozen dataclasses and typed dicts only for settings, financial records and external JSON
- Run the app as `python -m ghostfolio_ibkr_sync` (Docker only); the image installs the package
