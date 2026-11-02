# Tasks

## 1. Align coverage classification and messages

- [x] 1.1 Classify destination rows outside proven source coverage as
  informational and preserve the no-correction companion message. Add the
  synthetic 15-row regression that checks detailed blocks, summary counts and
  required-action state. Files: `ghostfolio_ibkr_sync/diagnostics.py`,
  `tests/test_dividend_diagnostics.py`. Requirement: connector-runtime —
  outside coverage is informational. Verify with
  `python -m pytest -q tests/test_dividend_diagnostics.py -k 'dividend_coverage_message_consistency or dividend_evidence_limitation_message_consistency or operator_action_diagnostic_warning_and_summary'`.

## 2. Update operator wording

- [x] 2.1 State the coverage rule in the dividend diagnostic section of
  `docs/configuration.md`. Check that it states the informational count,
  no-correction action and notification rule with
  `rg -n -A 5 "Missing source coverage" docs/configuration.md`.

## 3. Complete offline validation

- [x] 3.1 Run the focused tests, the complete offline suite and
  `bash scripts/check.sh`. Inspect the semantic diff and record the preview
  count (15 coverage items versus 12 triage candidate pairs: 6 manual and 6 reject) in the
  delivery note.
