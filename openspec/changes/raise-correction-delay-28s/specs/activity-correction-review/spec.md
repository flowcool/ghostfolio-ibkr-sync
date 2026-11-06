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
per run with a twenty-eight-second minimum inter-correction delay. The value comes from the RC2 lab maximum chain of 18.19 seconds with a 1.5x margin; a longer chain requires a new release. Stable promotion
SHALL require the exact RC image to pass the versioned empty and golden burst
qualification gate. The qualified lab record SHALL bind the accepted ceiling
and delay to the connector release. Ghostfolio image and version SHALL NOT be
qualification dimensions. Each release SHALL record its observed lab Ghostfolio
version as information. A version or image change SHALL NOT invalidate
qualification. If a future background chain exceeds D, exact readback and
stop-on-uncertainty SHALL still protect data; a new release SHALL raise D. There SHALL be no ENV bypass above that
ceiling or below that delay. A future lower-only setting MAY reduce the dispatch
count; it SHALL never increase the count or reduce the qualified delay. If a lab observes a longer background chain, a new release SHALL revise the values. Each
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
