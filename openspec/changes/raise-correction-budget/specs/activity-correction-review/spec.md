# Spec Delta

## MODIFIED Requirements

### Requirement: Verified correction and dependent import state

A known or uncertain correction failure SHALL stop the whole financial run after
the first dispatched correction that cannot be confirmed. The connector SHALL
retain the pending journal entry, the account fence, the approved proposal and
all later deferred proposals. Earlier confirmed corrections SHALL remain
explicit. No later correction, import, cash or platform write SHALL be sent in
that run. A later run SHALL inspect the unresolved journal before any financial
write. No resend is allowed.

Manual, automatic and comment-only correction PUTs SHALL share one digest-bound
finite budget across all configured accounts. The shipped candidate is five
corrections per run with a fifteen-second minimum inter-correction delay. These
values SHALL remain activation candidates until the exact image passes the burst
qualification gate. The qualified lab record SHALL bind the accepted ceiling
and delay to the destination digest. There SHALL be no ENV bypass above that
ceiling. A future lower-only setting MAY reduce the dispatch count; it SHALL
never increase the count or reduce the qualified delay. Each request SHALL
complete bounded exact readback before the next PUT. The connector SHALL stop at
the qualified limit and retain unchanged approvals and related import holds
without requesting another approval.

The exact image qualification SHALL measure request-bound market-data and
portfolio-cache completion. It SHALL use the versioned empty and golden lab
scenarios, dispatch the accepted count consecutively, prove exact readback before
each next PUT, and stop on the first failed or uncertain correction without a
resend. Synthetic HTTP mocks SHALL not qualify the image.

#### Scenario: Burst budget and shared account ceiling

- **WHEN** the offline review tests approve more than five corrections across two
  destination accounts
- **THEN** at most five PUTs dispatch in one run, the budget is shared across
  accounts, each PUT is followed by exact readback, and the remaining approvals
  retain their holds for a later run.

#### Scenario: First uncertainty stops the financial run

- **WHEN** the first dispatched correction stays in the before/unknown state
  after bounded recovery
- **THEN** exactly one PUT is sent, the v3 journal remains pending, later
  corrections remain approved and deferred, no later account import or cash PUT
  is sent, and the completed run uses the existing single redacted failure
  notification.

#### Scenario: Exact update acceptance and account fencing

- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_acceptance` mocks successful, normalized, redirected, rejected and partial correction sequences across two accounts
- **THEN** only exact readback confirms updates, failed corrections stop the run,
  the pending account fence remains, and confirmed earlier rows stay recorded.

#### Scenario: Qualified correction execution budget

- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_execution_budget` mocks the candidate limit and delay with more approved proposals than the run can dispatch
- **THEN** PUTs remain sequential, each is verified before the next, the finite
  shared limit and delay are obeyed, and deferred approvals remain unchanged.

#### Scenario: Corrected holdings before later sales

- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_holdings` corrects BUY/SELL quantities or symbols before selecting later trades
- **THEN** positions and reference indexes reflect replacement effects once, no
  corrected event is imported again, and subsequent sales use verified holdings.

#### Scenario: Review actions do not change correction authority

- **WHEN** `python -m pytest -q tests/test_activity_review.py -k operator_action_review` covers pending, blocked, historical, uncertain and budget-deferred proposals
- **THEN** required intervention notifies without authorizing corrections, and
  automatic budget deferral does not request another approval.

### Requirement: Bounded read-only recovery after uncertainty

The existing bounded reads of 0, 2, 5 and 10 seconds SHALL remain the recovery budget.
They are not a completion signal for Ghostfolio background jobs. Ghostfolio 3.96.0
does not expose a completion endpoint for the market-data and portfolio-cache
chain through the activity API. A fixed qualified inter-correction delay plus
exact readback is therefore the connector completion gate.

#### Scenario: Delayed background job before the next PUT

- **WHEN** the offline Ghostfolio mock delays the derived row update after a PUT
- **THEN** the connector waits for exact expected-after readback, honors the
  qualified inter-correction delay, and sends no second PUT before the first
  correction is confirmed.

#### Scenario: Delayed update and unresolved result

- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_recovery` mocks delayed success, unchanged state, drift, missing rows, repeated read errors and a restart with pending intent
- **THEN** waits are bounded, eventual exact success is confirmed, each logical
  request sends at most one PUT, unresolved rows remain blocked across runs and
  no repeated correction can overwrite later edits.
