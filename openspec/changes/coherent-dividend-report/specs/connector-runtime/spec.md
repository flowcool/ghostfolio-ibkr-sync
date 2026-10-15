# Spec Delta

## MODIFIED Requirements

### Requirement: Historical dividend comparison

Every truthy DRY_RUN SHALL compare cash distributions with existing target-account dividend sets, before deduplication hides them. Cash establishes gross/withholding; current exact accrual association establishes quantity. Missing/conflicting evidence SHALL remain uncertain. Comparisons SHALL use common currency units and exact decimal values and never sum component quantities.

The diagnostic SHALL retain original JSON decimal numeric evidence from the existing GET before float decoding; reconstructing evidence from decoded floats SHALL NOT establish exactness. The existing import/position numeric path, return shape, indexes, read count and failure contract SHALL remain unchanged. Destination gross SHALL be exact stored quantity × unitPrice, summed only within a complete representation; fees SHALL use the same representation. Source gross SHALL remain exact cash payments; source fee SHALL use the existing max(0,-cash withholding) convention. Raw signed withholding/refund rows and their total SHALL remain separate evidence. For a source group with exactly one net-positive action, the finite `grossRate` on the unique matched payment `Re` SHALL be retained as declared-rate evidence. Other source shapes SHALL have no group declared-rate evidence. The rate SHALL NOT replace cash gross.

Gross/fee deltas SHALL be destination minus source after normalization. A gross or fee delta whose absolute value is below half a minor unit of the source currency SHALL be classified rounding noise and SHALL stay counted in the summary and visible at DEBUG. Every other nonzero delta, and every quantity delta, SHALL remain visible without comparison tolerance. No percentage threshold SHALL apply. Display rounding SHALL NOT change classification.

A nonempty activity currency SHALL determine the denomination of its price and fee. Only null activity currency SHALL permit fallback to a supported profile currency, with explicit provenance. Each supported currency SHALL have an explicit minor-unit definition; JPY and KRW SHALL use one whole unit. Missing currency, conflicting currencies and a code without a minor-unit definition SHALL remain three distinct uncertain reasons. Major/minor market units SHALL be normalized exactly without overwriting activity denomination; a GBP activity with a GBp profile SHALL NOT be rescaled as though its activity values were GBp.

The report SHALL distinguish coherent single/component sets, probable repeated representations, quantity/monetary differences, absent destination records, uncertain identity and outside-report-window history. Findings can overlap. Either the canonical `dividend#<ISIN>#<date>` comment or the legacy `dividend#<resolved-symbol>#<date>` comment SHALL claim the same source group when the account, resolved security and local day agree. The same active/id/data-source/symbol/date/ISIN checks SHALL then apply. A claimed legacy row SHALL produce one source block and SHALL NOT also produce an absent-source or unmatched-destination block. Proximity and timezone explanations alone SHALL remain uncertain. Inactive/unsupported records SHALL NOT certify matches. Every source group and unmatched target dividend SHALL be accounted for; no finding authorizes repair.

A complete representation SHALL cover one whole source payment group as a single activity or cover every independently identified source component exactly once as a component set. Only identity/coverage-proven partitions SHALL be evaluated; amount equality SHALL NOT establish completeness and arbitrary subset search SHALL NOT be used. A complete representation with quantity/gross/fee disagreement SHALL retain its discrepancies; coherent SHALL require exact agreement on all supported quantities, gross and fee. Two or more distinct complete representations of the same source group SHALL be probable repetition even with discrepancies; incomplete or unproven partitions SHALL remain uncertain. Assignment SHALL be globally unique across source groups: no destination activity SHALL certify two groups. Contested ownership SHALL leave all affected comparisons uncertain, independent of processing order.

#### Scenario: Payment representations
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k representations` runs synthetic whole-payment, component, decimal, tax and currency cases
- **THEN** components remain distinct from repetition; disputed ownership stays uncertain; currency provenance and exact deltas remain independent.

#### Scenario: Incomplete identity
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k evidence` runs missing/conflicting accruals, absent rows, non-identity legacy comments, timezone shifts, inactive rows and older history
- **THEN** coverage and uncertainty stay explicit; only a legacy symbol comment that passes the identity contract claims the source group.

#### Scenario: Legacy comment identity
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k coherent_dividend_legacy_identity` runs canonical and legacy symbol comments with passing and failing identity checks
- **THEN** a valid legacy comment owns one source block; a failed check stays in that block; no row is reported twice.

#### Scenario: Currency states and declared rate
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k 'coherent_dividend_currency or coherent_dividend_declared_rate'` runs KRW, JPY, missing, conflicting and unknown currency cases plus one-action, multi-action and missing-rate evidence
- **THEN** KRW and JPY compare with one-unit precision; each invalid state has the correct reason; only the one-action matched-Re rate is retained.

Baseline: current `tests/test_dividend_diagnostics.py` preserves exact cash and destination evidence. The saved 2026-10-15 Flex evidence shows legacy symbol comments reported twice, two equal-KRW contexts reported unsupported, and six one-JPY cash-versus-declared-rate gaps.

### Requirement: Diagnostic execution and visibility

The diagnostic SHALL use existing reads, ENV and logs without persistence or financial writes. INFO SHALL summarize coverage/categories; anomaly/uncertainty details SHALL include reasons, activity IDs and source references with quantities/monetary deltas when supported. The per-account import line SHALL include the same `to check`, `informational` and `noise` counts as the dividend report, so its duplicate count cannot be mistaken for the report result. Logs remain private. Findings SHALL NOT alter exits/notifications; technical failures retain current behavior. Live runs SHALL NOT execute the diagnostic. README SHALL explain one-off Docker DRY_RUN without CRON, categories, limits and unchanged financial state.

#### Scenario: Dry-run report
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic or coherent_dividend_import_summary'` runs mocked dry and live accounts
- **THEN** dry-run details and the import line expose identical report counts without writes; live behavior, exits and notifications remain unchanged.

Baseline: the 2026-10-15 real dry-run import line reported duplicate skips while the report separately reported items to check, without a link between the numbers.

### Requirement: Actionable historical dividend evidence

The source `YYYYMMDD` SHALL remain the IBKR business day. Historical identity SHALL compare it with the destination instant's calendar day in `TZ`. An absent destination profile ISIN SHALL be unavailable evidence and SHALL NOT block amount comparison; a nonempty conflict SHALL fail identity.

Dry-run details SHALL name each failed or unavailable active/id/data-source/symbol/date/ISIN check with expected/observed values. Human blocks SHALL show security, source and destination UTC/local dates, activity IDs, and supported quantity/gross/fee/currency. INFO SHALL count failed checks. A row with the account's legacy `dividend#<symbol>#<date>` comment SHALL enter the source group's identity checks and SHALL NOT remain a canonically absent source. A truly absent source skipped by import deduplication SHALL name the actual skip path and available weak-candidate values: another historical comment that did not qualify as report identity, or proximity. Neither skip label SHALL certify identity. A finding left uncertain by missing, unsupported or conflicting currency context SHALL keep the distinct reason and SHALL show observed source/destination currency and provenance. Outside-window rows SHALL show destination security, date and values. No finding SHALL repair data or change import selection.

#### Scenario: Separate identity checks and local dates
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_identity'` exercises all six checks, local dates, absent ISIN and conflicting ISIN
- **THEN** each check exposes expected/observed values; missing ISIN permits comparison; conflicting ISIN blocks it.

#### Scenario: Actionable private report
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k 'historical_diagnostic_actionable or coherent_dividend_legacy_identity'` exercises outside-window rows, legacy identity and proximity skips
- **THEN** private details and aggregate counts expose the required evidence; every destination row appears in one block.

#### Scenario: Skip cause and observed currency
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k 'historical_diagnostic_skip_cause or coherent_dividend_currency'` exercises historical/proximity candidates and missing, conflicting, supported and unknown currencies
- **THEN** residual skip causes stay non-certifying; equal KRW compares; each invalid currency state keeps its distinct reason and provenance.

#### Scenario: Legacy identity and residual skip causes
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'coherent_dividend_legacy_identity or historical_diagnostic_skip_cause'` exercises a valid old symbol comment, an old comment with a failed identity check, and sources with only non-identity historical or proximity candidates
- **THEN** each old symbol row appears in one source block; only the residual cases use skip-cause wording; import selection is unchanged.

#### Scenario: Real read-only acceptance
- **WHEN** an operator-authorized real `DRY_RUN=1 LOG_LEVEL=DEBUG` captures a private log from the implemented change
- **THEN** zero financial writes occur; every source and destination row is accounted for once; currency reasons state the observed condition; no amount-based component identity is invented.

Baseline: current offline identity tests cover the six checks. The saved 2026-10-15 report shows two blocks for each old symbol-comment row.

### Requirement: Readable dividend report

Each finding SHALL use English plain words, one `Action:` line and the statement that nothing was written. A block SHALL NOT include a second `Proposed action:` line. No report block or summary line SHALL contain a Python representation, including `Decimal(...)`, dict/list syntax, exponent notation or the word `None` as a value. Missing values SHALL read `unavailable`. Category, failed-check and unavailable-check summaries SHALL use deterministic plain `name:count` text, or `none` when empty.

Every monetary value shown in a block, including gross, fee and monetary deltas on both the source and destination sides, SHALL be quantized for display to the common currency minor unit with round-half-away-from-zero. Quantities SHALL retain their exact plain-decimal display. Display rounding SHALL NOT change comparison, category or action.

The classes SHALL remain coherent, information, noise, outside window and to check. `unsupported currency` SHALL appear only when a nonempty code has no explicit minor-unit definition. Missing currency SHALL read `missing currency`; unequal supported codes SHALL read `conflicting currencies`. A source and destination that both use KRW SHALL be comparable, not unsupported.

A complete single legacy activity with equal quantity and fee SHALL be `legacy declared-rate rounding` information when its Ghostfolio gross equals quantity × the matched payment `Re` `grossRate` and the paid cash gross differs by exactly one minor unit. Its reason SHALL state that the legacy row uses the declared rate and IBKR paid a rounded cash amount. Its sole action SHALL read `No action: IBKR rounding accepted.` The block SHALL stay visible at INFO as audit information. It SHALL NOT suggest that IBKR revised the amount after import. A one-minor-unit fee difference, or any one-minor-unit gross difference outside this proven pattern, SHALL remain to check as `minimal difference, cause unknown`. No finding SHALL automatically correct an activity.

After informational findings, one INFO line SHALL read `N to check, N informational, N noise`, followed by each item to check. Findings SHALL NOT change exits or notifications.

#### Scenario: Plain, quantized, single-action report
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py tests/test_check_dividend_report.py -k 'coherent_dividend_format or check_dividend_report'` formats decimals, unavailable values, empty/nonempty summaries and blocks with match proposals
- **THEN** monetary text uses the currency minor unit; quantities stay exact; each block has one action; the checker reports zero violations.

#### Scenario: Classes from synthetic inputs
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k 'dividend_readable_classes or dividend_readable_pairs or coherent_dividend_one_jpy'` runs noise, one-unit, larger, quantity, legacy, split, absent and unsupported cases
- **THEN** existing classes stay stable except the complete declared-rate one-unit pattern, which becomes information with its known reason and no-action audit result.

#### Scenario: Plain report
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py tests/test_check_dividend_report.py -k 'dividend_readable_report or coherent_dividend_format or coherent_dividend_action'` formats source, destination, identity, summary and match text
- **THEN** all values are plain, monetary values are quantized, missing values read `unavailable`, and each block has one action.

#### Scenario: Correct currency reasons
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k coherent_dividend_currency` formats equal KRW, missing currency, conflicting supported codes and an unknown code
- **THEN** only the unknown code reads `unsupported currency`; equal KRW compares; the other states use their distinct reasons.

#### Scenario: One-JPY legacy row
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k coherent_dividend_one_jpy` runs equal quantity and fee, Ghostfolio gross equal to quantity × `grossRate`, paid cash gross one JPY higher or lower, and one-JPY fee or incomplete-pattern boundaries
- **THEN** the proven gross pattern gives one visible information block with the declared-rate rounding reason and `No action: IBKR rounding accepted.`; one-unit fee differences and other cases that fail one condition remain to check as `minimal difference, cause unknown`.

#### Scenario: Real read-only acceptance
- **WHEN** the operator-authorized real dry-run log is passed to `python3 scripts/check_dividend_report.py <private-log>` and every emitted dividend block is then read
- **THEN** the checker exits 0 with zero violations, and the closing evidence reports the reading verdict for every block without exposing private amounts or identifiers.

Baseline: `scripts/check_dividend_report.py` currently detects Python representations, float noise, contradictory actions, duplicate rows and false unsupported-currency reasons in the saved 2026-10-15 report.

### Requirement: Proposed dividend match

Under DRY_RUN, every dividend item to check that has a candidate SHALL carry one `Proposed match` section. The section SHALL show the IBKR dividend and candidate Ghostfolio rows side by side, each row labelled Keep, Duplicate or Differs. Confidence SHALL be strong for the same security, local day, gross and fee, or weak for a candidate without equal gross and fee. With no candidate it SHALL read `no confident match`. Weak proposals SHALL label no row Keep.

The proposed-match section SHALL NOT contain an action line. The enclosing block's single `Action:` line SHALL name the row and operation, or state that no action is needed. A legacy symbol-comment row that owns the source group SHALL appear once as the compared row; it SHALL NOT receive a second legacy-twin block. The proposal SHALL NOT write, repair or change import selection, classes, categories, summary counts, exits or notifications. Text SHALL follow the report's plain and quantized display rules.

#### Scenario: Strong match with a legacy twin
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k 'dividend_match_strong or coherent_dividend_action'` formats a canonical row with a separate free-text legacy twin
- **THEN** labels and confidence remain correct; the block has one `Action:` line and no `Proposed action:` line.

#### Scenario: Weak and absent
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k 'dividend_match_weak or coherent_dividend_action'` runs one-unit, quantity, proximity and no-candidate cases
- **THEN** weak proposals keep no row; absent stays no confident match; every block has one action.

#### Scenario: Display only
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k 'dividend_match_unchanged or coherent_dividend_format'` compares findings before and after formatting
- **THEN** classes, categories, summary counts, exits and notifications are unchanged; displayed amounts are quantized and plain.

#### Scenario: Real read-only acceptance
- **WHEN** the operator-authorized real dry-run log is read after `python3 scripts/check_dividend_report.py <private-log>` exits 0
- **THEN** each to-check block has a proposal or no confident match, exactly one action, and no duplicate legacy-identity block.

Baseline: current proposed-match tests preserve classification, while the saved 2026-10-15 report shows blocks where `Action: No action needed` conflicts with a manual `Proposed action`.
