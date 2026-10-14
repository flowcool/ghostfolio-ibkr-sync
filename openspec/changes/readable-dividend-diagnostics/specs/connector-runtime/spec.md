## MODIFIED Requirements

### Requirement: Historical dividend comparison

Every truthy DRY_RUN SHALL compare cash distributions with existing target-account dividend sets, before deduplication hides them. Cash establishes gross/withholding; current exact accrual association establishes quantity. Missing/conflicting evidence SHALL remain uncertain. Comparisons SHALL use common currency units and exact decimal values and never sum component quantities.

The diagnostic SHALL retain original JSON decimal numeric evidence from the existing GET before float decoding; reconstructing evidence from decoded floats SHALL NOT establish exactness. The existing import/position numeric path, return shape, indexes, read count and failure contract SHALL remain unchanged. Destination gross SHALL be exact stored quantity × unitPrice, summed only within a complete representation; fees SHALL use the same representation. Source gross SHALL remain exact cash payments; source fee SHALL use the existing max(0,-cash withholding) convention. Raw signed withholding/refund rows and their total SHALL remain separate evidence. Gross/fee deltas SHALL be destination minus source after normalization; a gross or fee delta whose absolute value is below half a minor unit of the source currency SHALL be classified rounding noise and SHALL stay counted in the summary and visible at DEBUG; every other nonzero delta, and every quantity delta, SHALL remain visible without tolerance or display rounding suppression.

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

## ADDED Requirements

### Requirement: Readable dividend report

Findings that need an operator check or give information SHALL be logged at INFO in English plain words, with the reason, the source and destination values, one action line, and the statement that nothing was written. No finding line SHALL contain a Python representation (`Decimal(...)`, list brackets, exponent notation); decimals SHALL print in plain form. Findings in the coherent and outside-window classes SHALL log at DEBUG only.

The classes SHALL be: to check (quantity difference; gross or fee difference of exactly one minor unit with equal quantity, named "minimal difference, cause unknown"; legacy-comment destination row with the same security and local day as a compared group, named "probable duplicate"; any other amount difference), information (outside window; unsupported currency; exact split; an absent source skipped by historical comment together with a destination row outside proven coverage that has the same security, day, gross and fee, reported as one line) and noise. A probable duplicate and an exact split SHALL keep their category uncertain. A destination partition whose rows sum exactly to the source gross and fee SHALL read "total equal to IBKR, split over N rows" and SHALL NOT be called a proven split.

After the findings, one INFO line SHALL read "N to check, N informational, N noise", followed by the detail of each item to check. Findings SHALL NOT change exits or notifications. Detecting amounts revised by IBKR after first import is out of scope; a revised amount appears as an amount difference.

Baseline: the DRY_RUN of 2026-10-14 on query 1492040 gave 114 findings: 28 coherent, 56 outside window, 11 differences (4 quantity, 6 one-yen, 1 sub-cent), 17 uncertain (10 legacy, 3 splits, 2 KRW, 2 outside coverage), 2 absent.

#### Scenario: Classes from synthetic inputs
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'dividend_readable_classes or dividend_readable_pairs'` runs sub-half-unit, one-unit and larger deltas, quantity deltas, legacy twins, equal-total splits and absent/outside-coverage pairs
- **THEN** each lands in its class, noise stays counted, and uncertain categories are unchanged.

#### Scenario: Plain report
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'dividend_readable_report'` formats a quantity difference with two legacy twins
- **THEN** the block shows both sides, the probable-duplicate sentence, an action line and "Nothing was written", and contains no `Decimal(` or exponent text.

#### Scenario: Real read-only acceptance
- **WHEN** the operator-authorized DRY_RUN on the production query runs with a private log
- **THEN** zero writes occur, `rg -c "Decimal\(|[0-9]E-[0-9]" <log>` prints 0, and the summary reads 20 to check, the information and noise counts, matching the baseline.
