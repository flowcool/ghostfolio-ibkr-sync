# Spec Delta

## MODIFIED Requirements

### Requirement: Enriched dividend input and local rejection

Processing SHALL extract cash identity without quantity checks, deduplicate by account/comment/proximity, then validate new candidates; existing activities remain untouched and unverified by import selection. A separate dry-run diagnostic SHALL compare historical evidence without changing that selection.

ChangeInDividendAccruals SHALL be mandatory. Required attributes SHALL cover candidate payment/relevant accrual keys, plus `quantity/code/date/payDate/reportDate` on relevant accruals. Nonempty key mismatches SHALL exclude unrelated accruals; missing keys SHALL NOT prove irrelevance. Unrelated rows SHALL NOT block candidates. Withholding SHALL retain cash grouping without accrual-schema requirements. Missing section/relevant attributes SHALL block account dividends; present-but-empty evidence SHALL reject affected groups. Empty sections without payments SHALL be valid.

Rejections SHALL log distinct incompatibility/missing/contradiction reasons, never mark rejected payments imported, leave trades/cash operating, and SHALL NOT change success/exit/notifications. Other failures SHALL retain existing behavior.

#### Scenario: Compatibility and isolation
- **WHEN** old/empty/short-window exports, malformed unrelated rows beside valid candidates, relevant missing attributes versus empty values, and existing dividends with invalid/conflicting quantities are processed
- **THEN** identity→dedup→quantity order, rejection scopes/logs/retries, unrelated-row isolation and unchanged outcomes are asserted.

Check: `.venv/bin/python -m pytest -v tests -k dividend_structured_input`.

## ADDED Requirements

### Requirement: Historical dividend comparison

Every truthy DRY_RUN SHALL compare cash distributions with existing target-account dividend sets, before deduplication hides them. Cash establishes gross/withholding; current exact accrual association establishes quantity. Missing/conflicting evidence SHALL remain uncertain. Comparisons SHALL use common currency units and decimal values, retain every nonzero gross/fee difference without tolerance, and never sum component quantities.

The report SHALL distinguish coherent single/component sets, probable repeated representations, quantity/monetary differences, absent destination records, uncertain identity and outside-report-window history. Findings can overlap. Canonical account/comment identity SHALL require consistent security/date evidence; proximity, legacy-symbol or timezone explanations alone SHALL remain uncertain. Inactive/unsupported records SHALL NOT certify matches. Every source group and unmatched target dividend SHALL be accounted for; no finding authorizes repair.

#### Scenario: Payment representations
- **WHEN** synthetic inputs cover ordinary/bonus, split PIL, repeated sets, fractional quantities, rounding differences and minor units
- **THEN** components remain distinct from repetition; quantities and exact monetary deltas are reported independently.

Check: `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k representations`.

#### Scenario: Incomplete identity
- **WHEN** fixtures include missing/conflicting accruals, absent destination rows, legacy comments, timezone shifts, inactive rows and older history
- **THEN** coverage and uncertainty are explicit; no weak match is certified.

Check: `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k evidence`.

### Requirement: Diagnostic execution and visibility

The diagnostic SHALL use existing reads, ENV and logs without persistence or financial writes. INFO SHALL summarize coverage/categories; anomaly/uncertainty details SHALL include reasons, activity IDs and source references with quantities/monetary deltas when supported. Logs remain private. Findings SHALL NOT alter exits/notifications; technical failures retain current behavior. Live runs SHALL NOT execute the diagnostic. README SHALL explain one-off Docker DRY_RUN without CRON, categories, limits and unchanged financial state.

#### Scenario: Dry-run report
- **WHEN** mocked runs exercise dry/live modes, anomalies and read failures
- **THEN** dry-run logs contain summary/details without financial writes/notifications; anomalies preserve success; technical failures retain failure; live behavior remains unchanged.

Check: `.venv/bin/python -m pytest -v tests/test_orchestration.py -k historical_diagnostic`.
