## MODIFIED Requirements

### Requirement: Verified correction and dependent import state

Before each dispatch, fresh unredacted destination evidence SHALL match the approved source/target context and unchanged reference occupancy. Require a complete source event in the current report and current destination ownership. The request SHALL include only fields accepted by the qualified update API. No raw GET response SHALL be sent as a PUT. Existing authentication, host validation, redirect rejection and credential protection SHALL apply.

Before the request, durably record its intent and full before/after evidence in the journal. After the request, readback SHALL prove every approved value and every preserved destination field. A successful status alone SHALL NOT confirm completion. Changes to numeric values or UTC instants, changed owner/account, tags, unsupported profile effects or financial differences SHALL fail verification. Equivalent numeric and timestamp representations defined above SHALL NOT fail verification. Comments and preserved note text SHALL remain exact; trimming is not an equivalent representation. Only confirmed corrections SHALL affect real holdings/identity state. Rebuild that state before ordinary selection and sales checks; replacement of a BUY SHALL NOT add its full quantity a second time.

A known or uncertain correction failure SHALL stop later financial writes for the same account, including imports, cash and platform updates. Earlier confirmed corrections SHALL remain explicit. Later accounts SHALL continue if their own evidence and files remain valid. Ordinary import failures outside this correction path SHALL retain existing independent-cash behavior. Pending proposals alone SHALL warn without failing the account. Those requiring intervention SHALL join the repeated consolidated notification under connector-runtime. Approved proposals deferred solely by the qualified execution limit SHALL not request another approval. Correction failures SHALL fail the account and enter the existing single Failure summary without financial details.

Correction PUTs SHALL be sequential. Each request SHALL complete exact readback before dispatching the next. Activation qualification SHALL establish a finite per-run correction limit and any minimum inter-request delay for the exact destination image, including market-data/background effects. Record the qualified limits in the shipped configuration and operator guidance; do not invent a safe production default from mocks. Stop at the qualified limit without failing the account, preserve unchanged approvals and proposals for the next run, and retain their related import holds. No interactive prompt or separate bulk command SHALL replace normal-run processing.

#### Scenario: Exact update acceptance and account fencing
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_acceptance` mocks successful, normalized, redirected, rejected and partial correction sequences across two accounts
- **THEN** only exact readback confirms updates, failed accounts send no later financial requests, confirmed earlier rows stay recorded, and the other account continues with the existing single failure notification.

#### Scenario: Qualified correction execution budget
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_execution_budget` mocks the qualified limit and delay with more approved proposals than the run can dispatch
- **THEN** PUTs remain sequential, each is verified before the next, the finite limit and delay are obeyed, and deferred approvals remain unchanged without duplicate import or false failure.

#### Scenario: Corrected holdings before later sales
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_holdings` corrects BUY/SELL quantities or symbols before selecting later trades
- **THEN** positions and reference indexes reflect replacement effects once, no corrected event is imported again, and subsequent sales use verified refreshed holdings.


#### Scenario: Review actions do not change correction authority
- **WHEN** `python -m pytest -q tests/test_activity_review.py -k operator_action_review` covers pending, blocked, historical, uncertain and budget-deferred proposals
- **THEN** required intervention notifies without authorizing corrections; automatic budget deferral does not request another approval.

## ADDED Requirements

### Requirement: Safe review instructions

Each review report requiring user intervention SHALL identify ACTIVITY_REVIEW_FILE and its actual configured container path. Name the generated section and proposal key where available, reason, held scope and safe action. Count unique held source events separately from candidates/proposals. Group repeated reasons without losing affected keys or distinct execution paths. Do not invent a Docker host path or inspect the Docker socket. User documentation SHALL show volume-mapping resolution.

For eligible unapproved normal-run proposals, instruct the user to read current/proposed values and execution path, then edit only approve between runs if the correction is intended. State that only lowercase literal yes approves that exact eligible proposal. Never recommend bulk approval. Blocked, source-unavailable, conflicting or unqualified proposals SHALL name required proof and state that yes cannot make them executable. Historical-maintenance proposals SHALL point to documented preparation and separate operation authorization; normal sync cannot execute them. Uncertain requests SHALL point to preserved journal/readback evidence and prohibit resend, journal deletion or journal edits as release instructions. False matches SHALL retain documented manual resolution without granting cleanup authority.

Approved work awaiting the qualified per-run limit SHALL report remaining automatic work and its hold. Do not request approval again or force reruns. Simulation SHALL explain that approval executes no financial write in that cycle. Instructions SHALL NOT change qualification, approval, recovery, locking, financial effects or exits. Required actions SHALL join the one per-run notification; keys, paths and financial comparisons remain only in private logs/files.

Baseline: docs/activity-review.md documents two sections and execution paths. The production warning names only the internal path and held-event count.

#### Scenario: Distinct safe instructions from one shared file
- **WHEN** `python -m pytest -q tests/test_activity_review.py -k operator_action_review` creates normal-run, historical, blocked, invalid-choice, stale, source-unavailable, uncertain and approved-budget-deferred cases at a custom path
- **THEN** logs show path, section/key, reason and next action; event counts do not assume candidate counts; no bulk yes, fabricated host path, maintenance permission or uncertainty reset is suggested; financial requests and exits remain unchanged.
