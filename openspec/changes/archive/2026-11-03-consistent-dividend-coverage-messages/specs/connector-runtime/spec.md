## ADDED Requirements

### Requirement: Consistent dividend coverage messages

An activity outside proven IBKR source coverage SHALL remain visible as an
informational diagnostic. Its block SHALL use the `information` class and one
`No action needed.` line. It SHALL NOT enter the `to check` count or the
`dividend_check` required-action notification. The same rule SHALL apply to all
existing named diagnostic evidence limitations. An explicit outside-window
finding SHALL retain its debug visibility and SHALL request no correction.
A concrete source/destination discrepancy SHALL remain a required manual action with its existing evidence
and resolution instruction. The detailed report, summary and required-action
notification SHALL use the same classification for the same input.

Baseline: the saved 4.1.0 preview emitted 15 `destination outside proven source
coverage` blocks as `Dividend to check` with a manual fix action, while the
companion evidence message said that no user correction was requested. The
triage file contains 12 dividend candidate pairs: six manual assignments and
six rejected crossed pairs across three groups. Those review pairs are not
historical coverage findings.

#### Scenario: Outside coverage is informational

- **WHEN** `python -m pytest -q tests/test_dividend_diagnostics.py -k dividend_coverage_message_consistency` runs the synthetic 15-row case
- **THEN** the report has 0 to-check and 15 informational findings, each block
  says `Dividend information: evidence limitation` and `Action: No action needed`,
  and the outcome has no `dividend_check` action or notification. A mixed case
  with one concrete discrepancy has one warning, one to-check item and one
  `dividend_check` action in one notification. Active and inactive rows use
  the same rule.

#### Scenario: Concrete discrepancy remains required

- **WHEN** `python -m pytest -q tests/test_dividend_diagnostics.py -k operator_action_diagnostic_warning_and_summary` runs the existing amount-difference case
- **THEN** the finding remains `to_check`, emits a warning and records one
  `dividend_check` action.

#### Scenario: Other named limitations remain consistent

- **WHEN** `python -m pytest -q tests/test_dividend_diagnostics.py -k dividend_evidence_limitation_message_consistency` runs all existing limitation reasons
- **THEN** each limitation has an informational or outside-window block, one
  `No action needed.` line, no to-check count and no required-action notification.

#### Scenario: Operator reads the coverage rule

- **WHEN** `rg -n -A 5 'Missing source coverage' docs/configuration.md` runs
- **THEN** the guide states the informational count, no-correction action and
  notification rule.

## MODIFIED Requirements

### Requirement: Readable dividend report

Each finding SHALL use English plain words, one `Action:` line and the statement that nothing was written. A block SHALL NOT include a second `Proposed action:` line. No report block or summary line SHALL contain a Python representation, including `Decimal(...)`, dict/list syntax, exponent notation or the word `None` as a value. Missing values SHALL read `unavailable`. Category, failed-check and unavailable-check summaries SHALL use deterministic plain `name:count` text, or `none` when empty.

Every monetary value shown in a block, including gross, fee and monetary deltas on both the source and destination sides, SHALL be quantized for display to the common currency minor unit with round-half-away-from-zero. Quantities SHALL retain their exact plain-decimal display. Display rounding SHALL NOT change comparison, category or action.

The classes SHALL remain coherent, information, noise, outside window and to check. `unsupported currency` SHALL appear only when a nonempty code has no explicit minor-unit definition. Missing currency SHALL read `missing currency`; unequal supported codes SHALL read `conflicting currencies`. A source and destination that both use KRW SHALL be comparable, not unsupported.

A complete single legacy activity with equal quantity and fee SHALL be `legacy declared-rate rounding` information when its Ghostfolio gross equals quantity × the matched payment `Re` `grossRate` and the paid cash gross differs by exactly one minor unit. Its reason SHALL state that the legacy row uses the declared rate and IBKR paid a rounded cash amount. Its sole action SHALL read `No action: IBKR rounding accepted.` The block SHALL stay visible at INFO as audit information. It SHALL NOT suggest that IBKR revised the amount after import. A one-minor-unit fee difference, or any one-minor-unit gross difference outside this proven pattern, SHALL remain to check as `minimal difference, cause unknown`. No finding SHALL automatically correct an activity.

After informational findings, one INFO line SHALL read `N to check, N informational, N noise`, followed by each item to check at WARNING or above. Findings SHALL NOT change exits. Items to check SHALL join the required-action notification. Information and noise alone SHALL not trigger it. Named diagnostic evidence limitations
SHALL be informational and SHALL state that no correction is requested. Explicit
outside-window findings SHALL retain debug visibility without a correction request.

#### Scenario: Plain, quantized, single-action report
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py tests/test_check_dividend_report.py -k 'coherent_dividend_format or check_dividend_report'` formats decimals, unavailable values, empty/nonempty summaries and blocks with match proposals
- **THEN** monetary text uses the currency minor unit; quantities stay exact; each block has one action; the checker reports zero violations.

#### Scenario: Classes from synthetic inputs
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k 'dividend_readable_classes or dividend_readable_pairs or coherent_dividend_one_jpy'` runs noise, one-unit, larger, quantity, legacy, split, absent and unsupported cases
- **THEN** existing classes stay stable except the complete declared-rate one-unit pattern and named diagnostic evidence limitations. These become information with their known reasons and no-action results.

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

#### Scenario: Required-action reporting compatibility
- **WHEN** `python -m pytest -q tests -k operator_action` exercises this requirement with synthetic inputs and mocked HTTP
- **THEN** required actions emit at least WARNING and join one configured notification; financial selection, payloads, account fences and exit codes remain unchanged.
