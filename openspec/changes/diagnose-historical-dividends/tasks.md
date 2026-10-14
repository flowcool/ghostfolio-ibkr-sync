# Tasks

Execution order: 1.1 → 2.1 → 3.1. Synthetic inputs/mocked HTTP only; README updates per slice.

## 1. Coherent dry-run comparison

- [ ] 1.1 Deliver retained dividend evidence, account-scoped single/component comparison and dry-run summary in ibkr_to_ghostfolio.py, tests/test_dividend_diagnostics.py, tests/test_orchestration.py and README. Check `.venv/bin/python -m pytest -v tests -k historical_diagnostic_coherent`; assert unchanged live behavior, reads, deduplication and zero financial writes.

## 2. Repetition and differences

- [ ] 2.1 Deliver representation/quantity/money details and README categories in the same runtime/diagnostic test files. Check `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k representations`; cover ordinary/bonus, PIL, competing sets, fractional quantities, exact deltas and scaling.

## 3. Uncertainty and compatibility

- [ ] 3.1 Deliver evidence coverage/uncertainty and documented Docker/log limits in runtime, diagnostic/orchestration tests and README. Check `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py tests/test_orchestration.py -k 'historical_diagnostic or representations or evidence or dividend_structured_input'`; cover legacy/timezone/inactive/outside-window/absent/conflicting cases, read failures, unchanged exits/notifications and all diagnostic scenarios.
