---
description: Python conventions for ibkr_to_ghostfolio.py
globs: ["*.py"]
---

- No type hints — match existing style
- Logging: `log.warning` for operational skips, `log.error` for failures, `log.debug` for verbose
- Never log a token or credential
- Errors: `raise RuntimeError(...)` with explicit message, never silent `return` on failure
- Mono-file: do not create additional modules without strong justification
- Tests: `pytest` in `tests/` (offline, pure functions, requests mocked; dev-only deps in `requirements-dev.txt`, never in the image). Run `.venv/bin/python -m pytest -q` before commit. A logic change ships with a test; live-data checks stay in `/test-sync` and the review-pr A/B dry run
- No classes — functional style with module-level functions
