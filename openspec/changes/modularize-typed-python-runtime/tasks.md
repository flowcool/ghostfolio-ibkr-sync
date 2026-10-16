# Tasks

Execution order: complete `dividend-proximity-amount-evidence`, then the separate Python 3.14 change, before task 1.1.

## 1. Foundation and configuration

- [ ] 1.1 Create the package, immutable models, typed settings, pinned Ruff/mypy configuration, and common check script; extract `load_config` and notification settings with unchanged ENV validation. Verify `scripts/check.sh` passes.

## 2. External adapters

- [ ] 2.1 Extract typed IBKR fetch, response guards, Flex parsing, and dividend prerequisites. Verify `.venv/bin/python -m pytest -q tests/test_parsing.py tests/test_orchestration.py -k 'flex or prerequisite'` passes.
- [ ] 2.2 Extract typed Ghostfolio authentication, reads, imports, and cash updates. Verify `.venv/bin/python -m pytest -q tests/test_ghostfolio.py tests/test_auth.py` passes.

## 3. Financial decisions

- [ ] 3.1 Extract mapping, conversion, holding checks, deduplication, and import acceptance as typed functions. Verify `.venv/bin/python -m pytest -q tests/test_conversion.py tests/test_filters.py` passes.
- [ ] 3.2 Extract historical dividend evidence and comparison. Verify `.venv/bin/python -m pytest -q tests/test_dividend_diagnostics.py -k 'historical or representations or evidence'` passes.
- [ ] 3.3 Extract finding classification, proposed matches, formatting, and logging. Verify `.venv/bin/python -m pytest -q tests/test_dividend_diagnostics.py tests/test_check_dividend_report.py` passes.

## 4. Orchestration and delivery

- [ ] 4.1 Extract account processing, outcomes, notifications, finalization, and run orchestration. Verify `.venv/bin/python -m pytest -q tests/test_orchestration.py tests/test_finalize.py tests/test_outcome.py tests/test_notify.py` passes.
- [ ] 4.2 Switch Docker and CRON to `python -m ghostfolio_ibkr_sync`; remove the old script; update tests, README, contributor guidance, architecture rules, ADRs, and upgrade documentation. Verify `scripts/check.sh` and `docker build -t ibkr-refactor:check . && bash scripts/check_container_runtime.sh ibkr-refactor:check` pass.
