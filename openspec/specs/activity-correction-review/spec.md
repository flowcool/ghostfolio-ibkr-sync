# activity-correction-review Specification

## Purpose
Let an operator approve exact IBKR activity corrections in a persistent YAML file. Apply approved one-to-one replacements during normal runs, with readback and a private recovery journal.

## Requirements

### Requirement: Optional persistent review file

`ACTIVITY_REVIEW_FILE` SHALL enable review only when its ENV value is nonblank. The path SHALL name a regular YAML file in a persistent writable directory. A missing file SHALL be created after valid input acquisition. A missing parent, unreadable existing file, invalid schema or unsafe path SHALL NOT be treated as an empty review. No existing file SHALL be cleared as recovery from a parse error.

When disabled, the connector SHALL create no review file or journal and send no correction requests. Existing import selection, cash handling and diagnostic behavior SHALL remain unchanged. Identity reading SHALL still support comments produced by an earlier enabled run.

The review SHALL publish schema 2 with keyed `reference_updates` and `activity_corrections` sections in one file. The first section SHALL contain comment-only changes. Derive the section from rebuilt proposed changes; file edits SHALL NOT choose the operation. Each proposal SHALL show its execution path and an association evidence level: `exact`, `probable` or `blocked`. The level SHALL NOT approve a monetary value or authorize a request. Keep full current/proposed values and the full comment visible. Schema 1 SHALL remain readable, but its approvals SHALL be cleared once before publishing the new display contract. The journal format and pending write fences SHALL remain compatible. An older runtime SHALL refuse schema 2 rather than treat it as an empty file. The review SHALL be one versioned document with keyed proposals. Each proposal SHALL show its stable key, verified source account/event, destination account/activity ID, match reason, current values, full proposed values, changed fields, status and `approve`. Values SHALL be plain English and exact plain-decimal text. The file SHALL contain no credentials. Money SHALL NOT be reduced to the rounded values printed by the dividend diagnostic.

#### Scenario: Opt-in and invalid file
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_config` runs with unset/blank paths, a new valid path, an unreadable file, invalid YAML and missing parent
- **THEN** disabled runs retain their baseline, a valid path creates the review, and invalid existing state is preserved with ERROR and no affected-account financial writes.

### Requirement: Source events and candidate selection

Review SHALL cover supported BUY, SELL and DIVIDEND events. A trade SHALL be one source-account/tradeID event. A dividend SHALL be one source-account/actionID event after the complete existing cash, withholding and quantity validations. Several cash portions of that same action SHALL retain the current proven conversion. Separate fills or actions SHALL NOT be combined to fit one destination activity. Invalid, conflicting, zero/negative-net, incomplete or future source events SHALL NOT become writable proposals.

An exact recognized reference SHALL select the identified event before proximity. A current reference with different values SHALL still produce a proposal. An exact current reference with the expected values SHALL produce no new proposal or PUT. An eligible legacy reference SHALL produce a proposal even if only its reference needs updating. Replacing a legacy-global trade marker SHALL require proof that it does not expose a previously suppressed event in another configured source account. Conflicting, occupied or unproven ownership SHALL be visible and non-actionable. When review is enabled, acquire and validate all configured reports before correction dispatch. Reuse that run inventory rather than fetching reports again during account processing. A failed or incomplete report SHALL make legacy-global reference replacement non-actionable wherever cross-account suppression cannot be proved safe. Other independently safe accounts and corrections SHALL continue. Complete acquisition alone SHALL NOT prove historical coverage outside the report windows; insufficient historical evidence SHALL keep the replacement non-actionable.

Without an exact recognized reference, candidates SHALL have the same verified destination account, BUY/SELL/DIVIDEND type, resolved security and supported denomination. A nonempty conflicting ISIN SHALL exclude a candidate. Active YAHOO/account requirements SHALL remain. A row with another source event's recognized reference SHALL NOT become a proximity candidate.

Calendar-date distance SHALL be at most two days for BUY/SELL and three days for DIVIDEND, inclusive. Use the existing import-matching UTC calendar dates; show those dates and the timezone context. No quantity, price, gross or fee threshold SHALL exclude a candidate. Candidate order and proposal keys SHALL be deterministic. Several candidates SHALL remain visible; confidence or amount agreement SHALL NOT grant approval.

#### Scenario: Exact and probable candidates
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_candidates` covers each type, window edges, same-ISIN aliases, wrong accounts/types/currencies, inactive profiles, different event references, exact IDs outside the window and financial differences
- **THEN** only eligible candidates appear; exact references bypass date proximity; recognized but discrepant events are reviewed; financial differences remain visible without automatic correction.

#### Scenario: No aggregate correction or ownership transfer
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_source_scope` covers split trade fills, one-action PIL portions, distinct dividend actions, legacy aggregates, reference collisions, complete/failed/partial source acquisition and legacy-global suppression across accounts
- **THEN** only proven one-event/one-activity corrections are actionable; no sum-of-fills, aggregate split, second payout, ownership transfer or newly exposed cross-account import is authorized.

### Requirement: Approval and one-to-one conflicts

Only the literal lowercase scalar `yes` in `approve` SHALL authorize a displayed correction, whether plain or quoted YAML. All other approval values SHALL skip that proposal for the cycle. Non-null skipped choices SHALL produce a warning. They SHALL NOT create rejection state or a correspondence table, release import holds, or fail the account. Unknown fields and invalid file bindings SHALL remain validation errors. The parser SHALL distinguish a plain `yes` token from a literal `true`; generic YAML truthiness SHALL NOT authorize writes.

The operator SHALL edit only `approve`. Editing another proposal field SHALL NOT turn it into a replacement input: fresh evidence SHALL reconstruct the expected proposal and clear any invalid approval. A proposal generated during the current run SHALL start blank. Only an unchanged actionable proposal already approved when the run read the file SHALL be eligible for dispatch. Changed section, evidence level, execution path or actionability SHALL clear approval. A blocked proposal SHALL never execute, including when it contains yes.

Approvals SHALL form a one-to-one set across the complete review. More than one approved destination for one source event, or more than one approved event for one destination, SHALL refuse every conflicting correction before dispatch. Unselected candidates SHALL remain pending until a selected correction is confirmed; they SHALL NOT be silently selected or deleted as duplicates.

#### Scenario: Literal approval and conflicting choices
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_approval` covers blank, plain/quoted yes, boolean values, edited payloads, new candidates and both conflict directions in either order
- **THEN** only an unchanged reviewed yes can authorize one correction; conflicting approvals issue no PUT; all pending choices remain inspectable.

### Requirement: Pending proposals and file refresh

Every run SHALL read valid approvals, verify or apply eligible corrections, remove confirmed proposals and discover new candidates. It SHALL retain stable pending keys without duplicate entries. Pending probable matches SHALL exclude the related new source import, while unrelated operations continue through existing gates. With no rejection choice, a false probable match SHALL require manual resolution in Ghostfolio. Deleting a pending file entry SHALL NOT authorize import: rediscovery SHALL create a blank proposal.

After a selected correction is confirmed, all alternatives for that same source event SHALL leave the pending review. No alternative destination SHALL be modified. Verified manual correction of the selected event to the expected reference and values SHALL also satisfy a proposal without PUT.

If every former candidate now demonstrably belongs to another identified source event, remove those alternatives and release the related import hold. Require fresh, valid ownership/reference evidence for every former candidate. Rebuild candidate and identity indexes, discover any new eligible candidates, then run ordinary import selection. Release SHALL NOT promise an import or bypass its existing gates. A candidate assigned to A SHALL no longer hold a distinct event B solely because B previously matched it. If any candidate remains eligible, retain its pending hold. Disappearance, deactivation, malformed references, unreadable or unsupported destination state SHALL NOT count as assignment to another event. Retain a visible non-actionable proposal in those cases; do not authorize replacement creation.

A changed source event, proposed replacement, destination activity, account/owner, tags, notes, mapping or identity occupancy SHALL invalidate approval. The connector SHALL refresh the displayed proposal, clear `approve` and state the change. Changed report acquisition times, unrelated report rows or window endpoints alone SHALL NOT invalidate unchanged event evidence.

If a previously reviewed event is absent from the current report, its proposal SHALL remain with `source unavailable`. No correction SHALL use cached source data. A still-valid yes SHALL remain suspended until the event returns; changed event values on return SHALL clear it.

#### Scenario: Repeated runs and manual resolution
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_refresh` runs repeated inventories, deleted entries, several candidates, confirmed/manual corrections and changed/deleted/inactive targets
- **THEN** pending entries persist once, related imports remain excluded, unrelated imports continue, confirmed events and fully reassigned candidate sets leave the review under their respective release rules, without modifying alternatives.

#### Scenario: Candidate assigned to another event
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_candidate_release` covers A and B sharing a candidate, verified assignment to A, all/partial candidate assignment, newly discovered candidates and missing/inactive/unreadable targets
- **THEN** B resumes ordinary selection only after every former candidate is proven assigned elsewhere and no new pending candidate exists; no assignment is inferred from disappearance, and ordinary duplicate/holdings gates still apply.

#### Scenario: Stale approval or unavailable source
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_stale` changes each bound field, removes an event from a shorter report, restores it unchanged and then restores it revised
- **THEN** changed evidence clears approval, absent source suspends correction without losing the proposal, unchanged restored evidence can resume, and revised restored evidence requires a new yes.

### Requirement: Exact replacement and reference preservation

An approved update SHALL replace the existing activity's date, security, type, denomination, quantity, unit price, fee and connector reference with the validated current IBKR conversion. The full proposed comment SHALL be visible before approval. Keep the destination activity ID, destination account, owner and tags. Do not delete or create an activity for a correction. Preserve non-reference user text and all other destination fields outside the explicitly approved changes. Dates/scaling/fee clamps SHALL use the normal import conversion; diagnostic tolerance SHALL grant no write authority.

Define proposed numbers from the exact JSON payload that the current conversion and qualified serializer will send. Show that value as plain-decimal text without additional report rounding. Parse destination response bytes as exact decimals in live and simulated review. Compare numeric values exactly: `1`, `1.0` and `1e0` are equal; financial tolerances SHALL NOT apply. Do not reconstruct destination evidence from already decoded floats. Refuse non-finite values, transport overflow/underflow or loss of any preserved numeric value. A repeating source quotient is represented by the existing conversion's transmitted value, not by an invented exact rational payload.

Compare dates as full UTC instants. Equivalent offsets and fractional-second spellings are equal. A different time on the same UTC day remains a difference. Proposed trade times and dividend midnight SHALL follow existing conversion. UTC calendar dates alone SHALL control proximity. Missing timezone evidence or unsupported precision SHALL make exact correction non-actionable.

The canonical v2 reference SHALL occupy the first comment line. If user text exists, append one blank line and that preserved text. Recognized historical references SHALL be removed only when the entire comment is exactly the proven legacy `IBKR#<tradeID>` or `dividend#<key>#<date>` marker. Validate the identifier/key/date against the source and existing supported format; exclude reserved versioned forms from the legacy trade grammar. For example, whole-comment `IBKR#12345` can be upgraded when trade 12345 is proven; `IBKR#12345\n\nMy note` is not a supported legacy reference position and SHALL remain non-actionable rather than be guessed. Canonical v2 supports either the whole comment or the first line followed by exactly one blank separator line and preserved notes. Legacy aggregate references remain excluded by the one-event source-scope requirement. Text that merely mentions a reference SHALL remain user text. Ambiguous, multiple or malformed reserved references SHALL be refused, not guessed. No comment truncation SHALL be allowed. If API trimming, length or encoding prevents preserving the proposed comment, keep the proposal non-actionable with the reason.

All readers SHALL extract the reference from that first line without treating user text as identity. The original whole-comment v2 forms and legacy readers SHALL remain compatible. Unknown reserved versions and invalid identity segments SHALL still stop before writes. Identity comparison SHALL use the extracted marker, not the full notes-bearing comment. This behavior SHALL remain available when review is later disabled.

#### Scenario: Full correction and preserved metadata
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_replacement` covers BUY, SELL, DIVIDEND, fractional amounts, supported minor-unit denominations and each changed field
- **THEN** only the displayed replacement fields change, preserved metadata remains exact, there is no POST/DELETE, and no report rounding changes the payload. Include repeating dividend quotients, exact wire decimals, equivalent numeric/date spellings, changed intraday times and unpreservable transport values; representation changes alone do not fail readback.

#### Scenario: Reference upgrade and user notes
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_reference` covers manual notes, every recognized legacy form, v2 with notes, reference-like prose, Unicode text, boundary lengths, trimming and malformed/duplicate markers
- **THEN** exact old references are replaced, notes survive, all readers deduplicate the canonical first-line identity, and unsupported comments remain visible without a PUT.

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

### Requirement: Bounded read-only recovery after uncertainty

A timeout, interrupted connection, crash with pending intent or unavailable readback SHALL retain an unresolved journal entry. Recovery SHALL read the activity immediately, then after waits of 2, 5 and 10 seconds while its state remains unchanged or unreadable. Reads SHALL have finite request timeouts and no automatic retry loop. The waits are a connector budget, not proof that a delayed write has settled.

Exact expected-after state SHALL confirm the correction and allow pending-file cleanup. Exact before state SHALL permit only continued read-only checking: it SHALL NOT authorize another PUT. A different state, missing row or unreadable result after the bounded checks SHALL log ERROR, preserve the proposal/journal and stop later writes on that account. Later runs SHALL inspect unresolved requests before any account financial writes. They SHALL NOT resend the correction merely because yes remains or the old row is visible. There SHALL be no interactive recovery prompt, abandon/reset switch or retry approval in this flow. Only fresh exact expected-after evidence SHALL resolve an uncertain entry, including when a separately authorized manual correction in Ghostfolio produced that state. Release the account only after every unresolved entry is resolved. An unresolved before state SHALL NOT be relabeled as a proven failed write. Do not direct the operator to delete or edit the journal to resume. Logs SHALL identify the affected account/activity, expected values, observed differences or unavailable evidence, and the retained write block, without credentials. Existing notifications SHALL retain their financial-detail redaction. This flow SHALL NOT send another PUT for an unresolved logical request. It cannot guarantee progress if expected-after state never appears; preserve the block rather than infer settlement.

#### Scenario: Delayed update and unresolved result
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_recovery` mocks delayed success, unchanged state, drift, missing rows, repeated read errors and a restart with pending intent
- **THEN** waits are bounded, eventual exact success is confirmed, each logical request sends at most one PUT, unresolved rows remain blocked across runs and no repeated correction can overwrite later edits. Include manual expected-after correction, permanent before state and drift: only complete expected-after evidence releases the block, no prompt/reset/abandon path is exposed, and other accounts continue.

### Requirement: Durable files and recovery evidence

The file and journal SHALL be private, versioned keyed YAML in the configured persistent directory. Derive journal and companion lock paths from the review filename. Exclude credentials. Journal each proposal's complete preimage, expected replacement, input bindings, request state and verified result. The journal SHALL be recovery evidence only; normal deduplication SHALL use Ghostfolio references, never a separate correspondence table.

Use exclusive runtime locking and atomic, synced file replacement. File paths SHALL reject symlinks, collisions with broker/mapping/evidence inputs and unsafe existing permissions. Concurrent runs sharing the same review SHALL not dispatch overlapping corrections. Detect operator edits before dispatch and before publication; do not overwrite edits or reuse an approval changed during the run. If persistence fails after a possible PUT, retain uncertainty rather than forgetting intent. If a review is globally unreadable or cannot be locked, all accounts using it SHALL stop before financial writes. File-level syntax/schema errors or an unbound unknown proposal SHALL stop all accounts sharing that file; a valid keyed proposal with any non-yes approve value SHALL be skipped without releasing its related import hold. Operators SHALL edit the review between runs. Advisory locks and byte comparisons detect cooperating writers and observed changes, but cannot prevent an arbitrary editor from racing the final check and replacement. Do not claim atomic compare-and-swap against uncooperative editors. If a concurrent edit is detected, preserve the operator file and pending intent, stop affected dispatch, and report ERROR.

Removing a confirmed proposal SHALL follow durable success recording. If the process stops between these steps, the next run SHALL finish local cleanup without another PUT. The journal SHALL support offline inspection and an exact reverse payload for an unchanged corrected row. Reversal SHALL require separate explicit authority and fresh checks; it SHALL never run automatically. Reverting software SHALL NOT be described as restoring financial data.

#### Scenario: Crash, file edit and rollback evidence
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_persistence` exercises process interruption before/after intent, after PUT, after verification, disk failure, concurrent editor/run, unsafe paths and changed rows during reversal inspection
- **THEN** intent is recoverable, approved edits are not lost, confirmed updates are never replayed, and reverse evidence is available only for unchanged journal-owned rows without automatic reversal.

### Requirement: Simulation and activation qualification

Simulation SHALL create and refresh proposals, validate approvals and display exact intended replacements. It SHALL send no financial POST/PUT/DELETE and create no applied journal result. Valid approvals SHALL remain unconsumed. Stale approvals SHALL be cleared using the same rules as live runs. Simulated correction effects SHALL remain isolated from real state. Simulation may display that an unresolved journal now matches expected-after, but SHALL NOT resolve that journal, consume its yes, remove its proposal or release its real account fence. A later live run SHALL revalidate and record observed completion without another PUT.

README SHALL document the ENV opt-in, persistent-volume permissions, YAML example, sole yes choice, import holds, manual false-match handling, stale/unavailable status, logs, recovery journal and disabling procedure. Activation SHALL require exact-image isolated qualification of full updates, notes and tags, profile/background effects, duplicate references, restart recovery and no repeat writes. Existing empty/golden release acceptance remains required under its own authority; no new mandatory duration gate is introduced. Source inspection and mocks SHALL NOT be presented as image qualification. A failed preservation case SHALL keep affected corrections unavailable.

#### Scenario: Review without financial writes
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_simulation` exercises blank/yes/stale proposals, forced preview and unresolved journals
- **THEN** the YAML is updated, valid yes remains, no financial mutation occurs and neither real accepted-state indexes nor journal results claim a simulated correction.

#### Scenario: Operator guidance and isolated qualification
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_qualification` replays the compatibility contract offline, and the separately authorized exact-image empty/golden acceptance is later evaluated
- **THEN** offline results and actual image evidence are distinguished; missing preservation, recovery or reader-rollback proof blocks real enablement rather than weakening the approved contract.

All test commands above name acceptance tests to implement. They are not evidence of existing feature delivery. Baseline evidence is the README, existing filter/index tests and the pinned update controller/service/DTO cited in connector-runtime.

### Requirement: Safe review instructions

Each review report requiring user intervention SHALL identify ACTIVITY_REVIEW_FILE and its actual configured container path. Name the generated section and proposal key where available, reason, held scope and safe action. Count unique held source events separately from candidates/proposals. Group repeated reasons without losing affected keys or distinct execution paths. Do not invent a Docker host path or inspect the Docker socket. User documentation SHALL show volume-mapping resolution.

For eligible unapproved normal-run proposals, instruct the user to read current/proposed values and execution path, then edit only approve between runs if the correction is intended. State that only lowercase literal yes approves that exact eligible proposal. Never recommend bulk approval. Blocked, source-unavailable, conflicting or unqualified proposals SHALL name required proof and state that yes cannot make them executable. Historical-maintenance proposals SHALL point to documented preparation and separate operation authorization; normal sync cannot execute them. Uncertain requests SHALL point to preserved journal/readback evidence and prohibit resend, journal deletion or journal edits as release instructions. False matches SHALL retain documented manual resolution without granting cleanup authority.

Approved work awaiting the qualified per-run limit SHALL report remaining automatic work and its hold. Do not request approval again or force reruns. Simulation SHALL explain that approval executes no financial write in that cycle. Instructions SHALL NOT change qualification, approval, recovery, locking, financial effects or exits. Required actions SHALL join the one per-run notification; keys, paths and financial comparisons remain only in private logs/files.

Baseline: docs/activity-review.md documents two sections and execution paths. The production warning names only the internal path and held-event count.

#### Scenario: Distinct safe instructions from one shared file
- **WHEN** `python -m pytest -q tests/test_activity_review.py -k operator_action_review` creates normal-run, historical, blocked, invalid-choice, stale, source-unavailable, uncertain and approved-budget-deferred cases at a custom path
- **THEN** logs show path, section/key, reason and next action; event counts do not assume candidate counts; no bulk yes, fabricated host path, maintenance permission or uncertainty reset is suggested; financial requests and exits remain unchanged.
