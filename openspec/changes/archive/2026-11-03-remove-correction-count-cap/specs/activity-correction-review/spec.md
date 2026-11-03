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
write. An unresolved journal entry SHALL stop the whole financial run on later
runs, including when its destination account is no longer configured.
No resend is allowed.

Pending proposals alone SHALL warn without failing the account. Those requiring intervention SHALL join the repeated consolidated notification under connector-runtime. Manual approvals and automatic work deferred after an unresolved correction SHALL not request another approval. Automatic work SHALL be freshly re-evaluated next run, never treated as retained user consent. Correction failures SHALL enter the existing single Failure summary without financial details.

Manual, automatic and comment-only corrections SHALL apply every currently
eligible approved or profile-authorized proposal in one connector run, across
all configured accounts. There SHALL be no per-run correction count cap.
Each next correction SHALL wait at least twenty-eight seconds after the previous
confirmed correction. Each PUT SHALL complete bounded exact readback before
the next PUT. No ENV setting SHALL lower the delay or add a correction count
cap. There SHALL be no additional run duration bound. Existing process-level
and request timeouts remain unchanged. Simulation SHALL preview every eligible
correction without consuming approvals. Queue position SHALL describe execution
order; currently eligible work SHALL have one remaining eligible run.

Stable promotion SHALL require the exact RC image to pass the versioned empty
and golden lab qualification. Each lab SHALL prove a chain of at least thirty
corrections in one account and across two accounts. Every request gap SHALL be
at least D=28 seconds. Every request-bound market-data and portfolio-cache
completion chain SHALL complete within D/1.5 seconds. Exact readback SHALL
precede each next PUT. An injected uncertainty at position k SHALL stop all
later financial writes without resend and retain journal v3 and later approvals.
Synthetic HTTP mocks SHALL NOT qualify the image.

Ghostfolio image and version SHALL NOT be qualification dimensions. Record the
observed version as information. A destination image or version change SHALL
NOT invalidate qualification. If a future background chain exceeds D, exact
readback and stop-on-uncertainty SHALL still protect data. A new connector
release SHALL raise D when the lab margin no longer passes.

#### Scenario: Exact update acceptance and account fencing
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_acceptance` mocks successful, normalized, redirected, rejected and partial correction sequences across two accounts
- **THEN** only exact readback confirms updates, a failed or uncertain correction stops the whole financial run, confirmed earlier rows stay recorded, and the pending account fence remains with the existing single failure notification.

#### Scenario: Qualified correction execution budget
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_execution_chain` exercises 1, 5 and 32 approved corrections with delayed destination updates
- **THEN** all corrections dispatch in one run, exact readback precedes each next PUT, D=28 seconds is preserved, simulation previews all corrections, and restart sends no correction again.

#### Scenario: Corrected holdings before later sales
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_holdings` corrects BUY/SELL quantities or symbols before selecting later trades
- **THEN** positions and reference indexes reflect replacement effects once, no corrected event is imported again, and subsequent sales use verified refreshed holdings.

#### Scenario: Review actions do not change correction authority
- **WHEN** `python -m pytest -q tests/test_activity_review.py -k operator_action_review` covers pending, blocked, historical, uncertain and deferred proposals
- **THEN** required intervention notifies without authorizing corrections; automatic deferral does not request another approval.

#### Scenario: Burst budget and shared account ceiling
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_execution_chain` approves corrections across two accounts
- **THEN** all eligible corrections execute with the same fixed delay and exact readback; an uncertainty in either account stops all later financial writes.

#### Scenario: First uncertainty stops the financial run

- **WHEN** the first dispatched correction stays in the before/unknown state
  after bounded recovery
- **THEN** exactly one PUT is sent, the v3 journal remains pending, later
  corrections remain approved and deferred, no later account import or cash PUT
  is sent, and the completed run uses the existing single redacted failure
  notification.

### Requirement: Safe review instructions

Each review report requiring user intervention SHALL identify ACTIVITY_REVIEW_FILE and its actual configured container path. Name the generated section and proposal key where available, reason, held scope and safe action. Count unique held source events separately from candidates/proposals. Group repeated reasons without losing affected keys or distinct execution paths. Do not invent a Docker host path or inspect the Docker socket. User documentation SHALL show volume-mapping resolution.

For eligible unapproved normal-run proposals, instruct the user to read current/proposed values and execution path, then edit only decision between runs if the correction is intended. State that only lowercase literal yes approves that exact eligible proposal. Never recommend bulk approval. Blocked, source-unavailable, conflicting or unqualified proposals SHALL name required proof and state that yes cannot make them executable. Historical-maintenance proposals SHALL point to documented preparation and separate operation authorization; normal sync cannot execute them. Uncertain requests SHALL point to preserved journal/readback evidence and prohibit resend, journal deletion or journal edits as release instructions. False matches SHALL offer the bound reject choice and explain that all-rejected events without a recognized reference still claiming them can resume ordinary import, without granting cleanup authority.

Manually approved or profile-authorized work deferred after an unresolved correction SHALL report remaining automatic work and its hold. Do not request approval again or force reruns. Simulation SHALL explain that approval executes no financial write in that cycle. Instructions SHALL explain profile authority separately from manual consent. Presentation alone SHALL NOT change qualification, recovery, locking, financial effects or exits. Required actions SHALL join the one per-run notification; keys, paths and financial comparisons remain only in private logs/files.

Baseline: docs/activity-review.md documents two sections and execution paths. The production warning names only the internal path and held-event count.

#### Scenario: Distinct safe instructions from one shared file
- **WHEN** `python -m pytest -q tests/test_activity_review.py -k operator_action_review` creates normal-run, historical, blocked, invalid-choice, stale, source-unavailable, uncertain and approved-deferred cases at a custom path
- **THEN** logs show path, section/key, reason and next action; event counts do not assume candidate counts; no bulk yes, fabricated host path, maintenance permission or uncertainty reset is suggested; financial requests and exits remain unchanged.
