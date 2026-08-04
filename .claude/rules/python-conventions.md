---
description: Python conventions for ibkr_to_ghostfolio.py
globs: ["*.py"]
---

- No type hints — match existing style
- Logging: `log.warning` for operational skips, `log.error` for failures, `log.debug` for verbose
- Never log a token or credential
- Errors: `raise RuntimeError(...)` with explicit message, never silent `return` on failure
- Mono-file: do not create additional modules without strong justification
- No test suite: tests are manual (see `/test-sync` skill)
- No classes — functional style with module-level functions
