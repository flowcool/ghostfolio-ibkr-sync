# Spec Delta

## MODIFIED Requirements

### Requirement: Verified correction and dependent import state

Before each dispatch, fresh unredacted destination evidence SHALL match the manually approved or freshly profile-authorized source/target context and unchanged reference occupancy. Require a complete source event in the current report and current destination ownership. The request SHALL include only fields accepted by the qualified update API. No raw GET response SHALL be sent as a PUT. Existing authentication, host validation, redirect rejection and credential protection SHALL apply.

Before the request, durably record its intent, full before/after evidence and manual or profile authority in the journal. Profile authority SHALL include the selected profile, policy version and exact eligibility inputs. Match tolerances SHALL NOT weaken expected-after or preserved-field verification. After the request, readback SHALL prove every approved value and every preserved destination field. A successful status alone SHALL NOT confirm completion. Changes to numeric values or UTC instants, changed owner/account, tags, unsupported profile effects or financial differences SHALL fail verification. Equivalent numeric and timestamp representations defined above SHALL NOT fail verification. Comments and preserved note text SHALL remain exact; trimming is not an equivalent representation. Only confirmed corrections SHALL affect real holdings/identity state. Rebuild that state before ordinary selection and sales checks; replacement of a BUY SHALL NOT add its full quantity a second time.

A known or uncertain correction failure SHALL stop the whole financial run after
the first dispatched correction that cannot be confirmed. The connector SHALL
retain the pending journal entry, the account fence, the approved proposal and
all later deferred proposals. Earlier confirmed corrections SHALL remain
explicit. No later correction, import, cash or platform write SHALL be sent in
that run. A later run SHALL inspect the unresolved journal before any financial
write. No resend is allowed.

Pending proposals alone SHALL warn without failing the account. Those requiring intervention SHALL join the repeated consolidated notification under connector-runtime. Manual approvals and automatic work deferred solely by the qualified execution limit SHALL not request another approval. Automatic work SHALL be freshly re-evaluated next run, never treated as retained user consent. Correction failures SHALL enter the existing single Failure summary without financial details.

Manual, automatic and comment-only correction PUTs SHALL share one connector-qualified
finite budget across all configured accounts. The RC activates five corrections
per run with a fifteen-second minimum inter-correction delay. Stable promotion
SHALL require the exact RC image to pass the versioned empty and golden burst
qualification gate. The qualified lab record SHALL bind the accepted ceiling
and delay to the connector release. Ghostfolio image and version SHALL NOT be
qualification dimensions. Each release SHALL record its observed lab Ghostfolio
version as information. A version or image change SHALL NOT invalidate
qualification. If a future background chain exceeds D, exact readback and
stop-on-uncertainty SHALL still protect data; a new release SHALL raise D. There SHALL be no ENV bypass above that
ceiling or below that delay. A future lower-only setting MAY reduce the dispatch
count; it SHALL never increase the count or reduce the qualified delay. If the
lab observes a longer background chain, a new RC SHALL revise the values. Each
request SHALL complete bounded exact readback before the next PUT. The connector
SHALL stop at the qualified limit and retain unchanged approvals and related
import holds without requesting another approval.

The connector qualification SHALL measure request-bound market-data and
portfolio-cache completion. It SHALL use the versioned empty and golden lab
scenarios, dispatch the accepted count consecutively, prove exact readback before
each next PUT, and stop on the first failed or uncertain correction without a
resend. Synthetic HTTP mocks SHALL not qualify the image.

#### Scenario: Exact update acceptance and account fencing
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_acceptance` mocks successful, normalized, redirected, rejected and partial correction sequences across two accounts
- **THEN** only exact readback confirms updates, a failed or uncertain correction stops the whole financial run, confirmed earlier rows stay recorded, and the pending account fence remains with the existing single failure notification.

#### Scenario: Qualified correction execution budget
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_execution_budget` mocks the qualified limit and delay with more approved proposals than the run can dispatch
- **THEN** PUTs remain sequential, each is verified before the next, the finite limit and delay are obeyed, and deferred approvals remain unchanged without duplicate import or false failure.

#### Scenario: Corrected holdings before later sales
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_holdings` corrects BUY/SELL quantities or symbols before selecting later trades
- **THEN** positions and reference indexes reflect replacement effects once, no corrected event is imported again, and subsequent sales use verified refreshed holdings.

#### Scenario: Review actions do not change correction authority
- **WHEN** `python -m pytest -q tests/test_activity_review.py -k operator_action_review` covers pending, blocked, historical, uncertain and budget-deferred proposals
- **THEN** required intervention notifies without authorizing corrections; automatic budget deferral does not request another approval.

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

### Requirement: Bounded read-only recovery after uncertainty

The existing bounded reads of 0, 2, 5 and 10 seconds SHALL remain the recovery budget.
They are not a completion signal for Ghostfolio background jobs. Ghostfolio 3.96.0
does not expose a completion endpoint for the market-data and portfolio-cache
chain through the activity API. A fixed qualified inter-correction delay plus
exact readback is therefore the connector completion gate.

A timeout, interrupted connection, crash with pending intent or unavailable readback SHALL retain an unresolved journal entry. Recovery SHALL read the activity immediately, then after waits of 2, 5 and 10 seconds while its state remains unchanged or unreadable. Reads SHALL have finite request timeouts and no automatic retry loop. The waits are a connector budget, not proof that a delayed write has settled.

Exact expected-after state SHALL confirm the correction and allow pending-file cleanup. Exact before state SHALL permit only continued read-only checking: it SHALL NOT authorize another PUT. A different state, missing row or unreadable result after the bounded checks SHALL log ERROR, preserve the proposal/journal and stop later writes on that account. Later runs SHALL inspect unresolved requests before any account financial writes. They SHALL NOT resend the correction merely because yes remains or the old row is visible. There SHALL be no interactive recovery prompt, abandon/reset switch or retry approval in this flow. Only fresh exact expected-after evidence SHALL resolve an uncertain entry, including when a separately authorized manual correction in Ghostfolio produced that state. Release the account only after every unresolved entry is resolved. An unresolved before state SHALL NOT be relabeled as a proven failed write. Do not direct the operator to delete or edit the journal to resume. Logs SHALL identify the affected account/activity, expected values, observed differences or unavailable evidence, and the retained write block, without credentials. Existing notifications SHALL retain their financial-detail redaction. This flow SHALL NOT send another PUT for an unresolved logical request. It cannot guarantee progress if expected-after state never appears; preserve the block rather than infer settlement.

#### Scenario: Delayed update and unresolved result
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_recovery` mocks delayed success, unchanged state, drift, missing rows, repeated read errors and a restart with pending intent
- **THEN** waits are bounded, eventual exact success is confirmed, each logical request sends at most one PUT, unresolved rows remain blocked across runs and no repeated correction can overwrite later edits. Include manual expected-after correction, permanent before state and drift: only complete expected-after evidence releases the block, no prompt/reset/abandon path is exposed, and other accounts continue.

#### Scenario: Delayed background job before the next PUT

- **WHEN** the offline Ghostfolio mock delays the derived row update after a PUT
- **THEN** the connector waits for exact expected-after readback, honors the
  qualified inter-correction delay, and sends no second PUT before the first
  correction is confirmed.

### Requirement: Simulation and activation qualification

Simulation SHALL create and refresh proposals, validate manual decisions, evaluate the active profile and display exact intended replacements and authority. It SHALL send no financial POST/PUT/DELETE and create no applied journal result. Valid approvals SHALL remain unconsumed. Stale approvals SHALL be cleared using the same rules as live runs. Simulated correction effects SHALL remain isolated from real state. Simulation may display that an unresolved journal now matches expected-after, but SHALL NOT resolve that journal, consume its yes, remove its proposal or release its real account fence. A later live run SHALL revalidate and record observed completion without another PUT.

README SHALL link directly to the activity-review guide. That guide SHALL document the ENV opt-in, persistent-volume permissions, YAML example, literal yes/reject decisions, profile limits, import holds, durable false-match rejection, stale/unavailable status, logs, recovery journal and disabling procedure. Activation SHALL require isolated qualification of full updates in the exact connector release, notes and tags, profile/background effects, duplicate references, restart recovery and no repeat writes. Existing empty/golden release acceptance remains required under its own authority; no new mandatory duration gate is introduced. Source inspection and mocks SHALL NOT be presented as image qualification. A failed preservation case SHALL keep affected corrections unavailable.

#### Scenario: Review without financial writes
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_simulation` exercises blank/yes/stale proposals, forced preview and unresolved journals
- **THEN** the YAML is updated, valid yes remains, no financial mutation occurs and neither real accepted-state indexes nor journal results claim a simulated correction.

#### Scenario: Operator guidance and isolated qualification
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_qualification` replays the compatibility contract offline, and the separately authorized exact-image empty/golden acceptance is later evaluated
- **THEN** offline results and actual image evidence are distinguished; missing preservation, recovery or reader-rollback proof blocks real enablement rather than weakening the approved contract.

All test commands above name acceptance tests to implement. They are not evidence of existing feature delivery. Baseline evidence is the README, existing filter/index tests and the pinned update controller/service/DTO cited in connector-runtime.
