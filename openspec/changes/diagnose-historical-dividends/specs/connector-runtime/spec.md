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

Every truthy DRY_RUN SHALL compare cash distributions with existing target-account dividend sets, before deduplication hides them. Cash establishes gross/withholding; current exact accrual association establishes quantity. Missing/conflicting evidence SHALL remain uncertain. Comparisons SHALL use common currency units and exact decimal values and never sum component quantities.

The diagnostic SHALL retain original JSON decimal numeric evidence from the existing GET before float decoding; reconstructing evidence from decoded floats SHALL NOT establish exactness. The existing import/position numeric path, return shape, indexes, read count and failure contract SHALL remain unchanged. Destination gross SHALL be exact stored quantity × unitPrice, summed only within a complete representation; fees SHALL use the same representation. Source gross SHALL remain exact cash payments; source fee SHALL use the existing max(0,-cash withholding) convention. Raw signed withholding/refund rows and their total SHALL remain separate evidence. Gross/fee deltas SHALL be destination minus source after normalization; every nonzero delta SHALL remain visible without tolerance or display rounding suppression.

A nonempty activity currency SHALL determine the denomination of its price and fee. Only null activity currency SHALL permit fallback to a supported profile currency, with explicit provenance. Missing/invalid/unsupported context SHALL remain uncertain. Major/minor units SHALL be normalized exactly without overwriting activity denomination; a GBP activity with a GBp profile SHALL NOT be rescaled as though its activity values were GBp.

The report SHALL distinguish coherent single/component sets, probable repeated representations, quantity/monetary differences, absent destination records, uncertain identity and outside-report-window history. Findings can overlap. Canonical account/comment identity SHALL require consistent security/date evidence; proximity, legacy-symbol or timezone explanations alone SHALL remain uncertain. Inactive/unsupported records SHALL NOT certify matches. Every source group and unmatched target dividend SHALL be accounted for; no finding authorizes repair.

A complete representation SHALL cover one whole source payment group as a single activity or cover every independently identified source component exactly once as a component set. Only identity/coverage-proven partitions SHALL be evaluated; amount equality SHALL NOT establish completeness and arbitrary subset search SHALL NOT be used. A complete representation with quantity/gross/fee disagreement SHALL retain its discrepancies; coherent SHALL require exact agreement on all supported quantities, gross and fee. Two or more distinct complete representations of the same source group SHALL be probable repetition even with discrepancies; incomplete or unproven partitions SHALL remain uncertain. Assignment SHALL be globally unique across source groups: no destination activity SHALL certify two groups. Contested ownership SHALL leave all affected comparisons uncertain, independent of processing order.

#### Scenario: Payment representations
- **WHEN** synthetic inputs cover ordinary/bonus, split PIL, whole-payment versus component sets, repeated sets with monetary discrepancies, incomplete partitions, disputed cross-group ownership, fractional quantities, sub-float decimal differences, signed tax/refunds, null activity currency, GBP/GBp denomination differences and unsupported currency context
- **THEN** components remain distinct from repetition; complete-but-discrepant representations are not coherent; disputed ownership stays uncertain in either processing order; currency provenance, quantity differences, signed exact monetary deltas and raw tax/refund evidence are reported independently.

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

Check: `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic or representations or evidence or dividend_structured_input or ghostfolio or finalize'`; this also selects existing compatibility/outcome regressions, including both dividend rejection/failure cases in `tests/test_finalize.py`.
