# Tasks

Execution order: 1.1 → 2.1 → 3.1. Synthetic inputs/mocked HTTP only; README updates per slice.

## 1. Coherent dry-run comparison

- [x] 1.1 Deliver retained dividend evidence, account-scoped single/component comparison and dry-run summary in ibkr_to_ghostfolio.py, tests/test_dividend_diagnostics.py, tests/test_orchestration.py and README. Check `.venv/bin/python -m pytest -v tests -k historical_diagnostic_coherent`; cover exact JSON retention before float decoding, activity/profile currency precedence and provenance; assert unchanged reader return tuple/indexes, validation/failure behavior, numeric import path, read count, live behavior, deduplication and zero financial writes.

## 2. Repetition and differences

- [x] 2.1 Deliver representation/quantity/money details and README categories in the same runtime/diagnostic test files. Check `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k representations`; cover identity-proven whole-payment/component completeness, exact coherence, ordinary/bonus, PIL, competing complete sets with discrepancies, incomplete partitions and globally unique assignment; contested ownership stays uncertain in either order, with no arbitrary subset search. Include fractional quantities, sub-float exact deltas with destination-minus-source sign, fee=max(0,-cash withholding), separate signed tax/refund evidence, null activity currency fallback, GBP/GBp denomination differences and unsupported currency context.

## 3. Uncertainty and compatibility

- [ ] 3.1 Deliver evidence coverage/uncertainty and documented Docker/log limits in runtime, diagnostic/orchestration tests, tests/test_finalize.py and README. Check `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic or representations or evidence or dividend_structured_input or ghostfolio or finalize'`; cover legacy/timezone/inactive/outside-window/absent/conflicting cases, read failures, unchanged exits/notifications and all diagnostic scenarios plus existing reader, compatibility and outcome regressions across tests/, explicitly including both dividend rejection/failure tests in tests/test_finalize.py. Select every new diagnostic test through the historical_diagnostic, representations or evidence names.
