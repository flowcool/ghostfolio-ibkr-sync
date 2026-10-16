# Tasks

Execution order: complete `dividend-proximity-amount-evidence`, then the separate Python 3.12 → 3.14 migration, before task 1.1. This refactor stays in the v3.0.0 RC series. Restart the 10-day production soak on the resulting RC.

Every task requires the full `scripts/check.sh` plus its targeted check below. Moved tests change only imports and patch targets; their assertions remain identical. Add separate tests for changed launch contracts. Use synthetic inputs, mocked HTTP, and isolated containers only.

## 1. Foundation and configuration

- [x] 1.1 Create the package, immutable models, typed settings, Ruff/mypy configuration, and common check script. Pin Ruff, mypy, types-requests, and types-PyYAML in `requirements-dev.txt` for strict application mypy. Extract `load_config` and notification settings without changing ENV validation. Acceptance: `scripts/check.sh` plus `.venv/bin/python -m pytest -q tests/test_auth.py tests/test_notify.py -k 'config or settings or timeout or disables'`.

## 2. External adapters

- [x] 2.1 Extract typed IBKR fetch, response guards, Flex parsing, and dividend prerequisites. Acceptance: `scripts/check.sh` plus `.venv/bin/python -m pytest -q tests/test_parsing.py tests/test_orchestration.py -k 'flex or prerequisite'`.
- [x] 2.2 Extract typed Ghostfolio authentication, reads, imports, and cash updates. Acceptance: `scripts/check.sh` plus `.venv/bin/python -m pytest -q tests/test_ghostfolio.py tests/test_auth.py`.

## 3. Financial decisions

- [ ] 3.1 Extract mapping, conversion, holding checks, deduplication, and import acceptance as typed functions. Acceptance: `scripts/check.sh` plus `.venv/bin/python -m pytest -q tests/test_conversion.py tests/test_filters.py`.
- [ ] 3.2 Extract historical dividend evidence and comparison. Acceptance: `scripts/check.sh` plus `.venv/bin/python -m pytest -q tests/test_dividend_diagnostics.py -k 'historical or representations or evidence'`.
- [ ] 3.3 Extract finding classification, proposed matches, formatting, and logging. Acceptance: `scripts/check.sh` plus `.venv/bin/python -m pytest -q tests/test_dividend_diagnostics.py tests/test_check_dividend_report.py`.

## 4. Orchestration and delivery

- [ ] 4.1 Extract account processing, outcomes, notifications, finalization, and run orchestration. Acceptance: `scripts/check.sh` plus `.venv/bin/python -m pytest -q tests/test_orchestration.py tests/test_finalize.py tests/test_outcome.py tests/test_notify.py`.
- [ ] 4.2 Switch Dockerfile and entrypoint.sh (one-off and CRON) to the installed package: `pip install --no-deps .` and `python -m ghostfolio_ibkr_sync`. Set the notification worker argv to `[sys.executable, "-I", "-m", "ghostfolio_ibkr_sync", "--notify-worker"]`; remove the `__file__` spawn guard. Update `cleanup_dividends.py`, `cleanup_duplicates.py`, and `cleanup_recovery.py` to import `activity_is_active` from the package. Delete `ibkr_to_ghostfolio.py` without a compatibility launcher. Adapt `scripts/check_container_runtime.sh` and its synthetic probe: replace the old file ownership/mount assumptions, retain hardened one-off/scheduled checks, and prove installed worker startup with its production argv, malformed stdin, exit 10, no credentials, and no network. Acceptance: `scripts/check.sh` plus `.venv/bin/python -m pytest -q tests/test_notify.py tests/test_cleanup.py tests/test_cleanup_recovery.py tests/test_entrypoint.py tests/test_dockerfile.py` and `docker build -t ibkr-refactor:check . && bash scripts/check_container_runtime.sh ibkr-refactor:check`.
- [ ] 4.3 Update README.md, AGENTS.md, CONTRIBUTING.md, the context in openspec/config.yaml, .claude/rules/python-conventions.md, ADR 0001 (mark superseded), and upgrading-to-3.0.md. Document Docker-only execution with `docker exec <container> python -m ghostfolio_ibkr_sync`, removal without a launcher, and the 10-day production soak restart on the refactored v3.0.0 RC. Update docs/adr/0007-pinned-degiro-core.md: DEGIRO stays pinned to the last single-file commit; future propagation requires a separate DEGIRO change because its `check_core` hardcodes `source_path`. Do not modify DEGIRO. Acceptance: `scripts/check.sh` plus `openspec validate modularize-typed-python-runtime --strict` and a targeted documentation diff review against these decisions.
