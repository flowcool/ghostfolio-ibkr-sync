## ADDED Requirements

### Requirement: Unique legacy allocation inside partial dividend coverage

For a two-action dividend group with exactly one uniquely covered v2 action, review SHALL permit only the missing action's uniquely proven legacy destination to bypass partial coverage. Require the mapped account, active YAHOO security, matching ISIN when present, exact effective currency, exact structured quantity, same payment day and exact gross or the proven converter representation. Require complete associated cash, explicit withholding and accrual evidence. No profile tolerance SHALL establish this allocation.

There SHALL be exactly one legacy candidate and no additional destination candidate or conflicting identity. Missing evidence, duplicate identities, two candidates, amount mismatch or conflicting account/security context SHALL retain the block. A literal yes SHALL NOT bypass that block.

The qualified proposal SHALL replace the legacy comment with the missing v2 identity and expose the reviewed fee. It SHALL preserve destination IDs, ownership, tags, notes, quantity, unit price and stored timestamp. Bind approval to the full group and relevant destination evidence. Revalidate before dispatch. The existing v2 sibling SHALL remain blocked until fresh destination evidence proves complete identity coverage. Then normal review SHALL resume. Ordinary imports SHALL remain suppressed throughout. Existing manual/profile authority, journaling, exact readback and uncertainty rules SHALL apply.

Baseline: `test_review_source_scope_partial_dividend_coverage_and_action_conflict` and the partial guard in `refresh_proposals` refuse partial groups. The new exception is limited to the independent proof above.

#### Scenario: Three mixed dividend shapes

- **WHEN** `python -m pytest -q tests/test_mixed_dividend_review.py -k shapes` tests one reversal, repeated accrual revisions, and posted/reversed accruals, with the missing action before or after its sibling
- **THEN** each group has exactly one actionable missing-action proposal and no import; confirmation retains both destination IDs and permits normal sibling review.

#### Scenario: Ambiguity retains the guard

- **WHEN** `python -m pytest -q tests/test_mixed_dividend_review.py -k blocked` tests extra candidates, duplicate identities, quantity/gross/date/currency/account/security mismatch and missing tax/accrual evidence
- **THEN** the group stays blocked, yes gives no authority, and no new dividend is imported.

#### Scenario: Fresh evidence and recovery

- **WHEN** `python -m pytest -q tests/test_mixed_dividend_review.py -k dispatch` tests changed group evidence, exact confirmation, restart and uncertain readback
- **THEN** changed proof clears approval, exact confirmation journals the update, restart sends no duplicate request, and uncertainty stops later writes without resend.
