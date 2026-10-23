## MODIFIED Requirements

### Requirement: Optional persistent review file

`ACTIVITY_REVIEW_FILE` SHALL enable review only when its ENV value is nonblank. The path SHALL name a regular YAML file in a persistent writable directory. A missing file SHALL be created after valid input acquisition. A missing parent, unreadable existing file, invalid schema or unsafe path SHALL NOT be treated as an empty review. No existing file SHALL be cleared as recovery from a parse error.

When disabled, the connector SHALL create no review file or journal and send no correction requests. Existing import selection, cash handling and diagnostic behavior SHALL remain unchanged. Identity reading SHALL still support comments produced by an earlier enabled run.

The review SHALL publish schema 2 with keyed `reference_updates` and `activity_corrections` sections in one file. The first section SHALL contain comment-only changes. Derive the section from rebuilt proposed changes; file edits SHALL NOT choose the operation. Each proposal SHALL show its execution path and an association evidence level: `exact`, `probable` or `blocked`. The level SHALL NOT approve a monetary value or authorize a request. Keep full current/proposed values and the full comment visible. Schema 1 SHALL remain readable, but its approvals SHALL be cleared once before publishing the new display contract. The journal format and pending write fences SHALL remain compatible. An older runtime SHALL refuse schema 2 rather than treat it as an empty file. The review SHALL be one versioned document with keyed proposals. Each proposal SHALL show its stable key, verified source account/event, destination account/activity ID, match reason, current values, full proposed values, changed fields, status and `approve`. Values SHALL be plain English and exact plain-decimal text. The file SHALL contain no credentials. Money SHALL NOT be reduced to the rounded values printed by the dividend diagnostic.

#### Scenario: Opt-in and invalid file
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_config` runs with unset/blank paths, a new valid path, an unreadable file, invalid YAML and missing parent
- **THEN** disabled runs retain their baseline, a valid path creates the review, and invalid existing state is preserved with ERROR and no affected-account financial writes.

### Requirement: Approval and one-to-one conflicts

Only the literal lowercase scalar `yes` in `approve` SHALL authorize a displayed correction, whether plain or quoted YAML. All other approval values SHALL skip that proposal for the cycle. Non-null skipped choices SHALL produce a warning. They SHALL NOT create rejection state or a correspondence table, release import holds, or fail the account. Unknown fields and invalid file bindings SHALL remain validation errors. The parser SHALL distinguish a plain `yes` token from a literal `true`; generic YAML truthiness SHALL NOT authorize writes.

The operator SHALL edit only `approve`. Editing another proposal field SHALL NOT turn it into a replacement input: fresh evidence SHALL reconstruct the expected proposal and clear any invalid approval. A proposal generated during the current run SHALL start blank. Only an unchanged actionable proposal already approved when the run read the file SHALL be eligible for dispatch. Changed section, evidence level, execution path or actionability SHALL clear approval. A blocked proposal SHALL never execute, including when it contains yes.

Approvals SHALL form a one-to-one set across the complete review. More than one approved destination for one source event, or more than one approved event for one destination, SHALL refuse every conflicting correction before dispatch. Unselected candidates SHALL remain pending until a selected correction is confirmed; they SHALL NOT be silently selected or deleted as duplicates.

#### Scenario: Literal approval and conflicting choices
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_approval` covers blank, plain/quoted yes, boolean values, edited payloads, new candidates and both conflict directions in either order
- **THEN** only an unchanged reviewed yes can authorize one correction; conflicting approvals issue no PUT; all pending choices remain inspectable.

### Requirement: Durable files and recovery evidence

The file and journal SHALL be private, versioned keyed YAML in the configured persistent directory. Derive journal and companion lock paths from the review filename. Exclude credentials. Journal each proposal's complete preimage, expected replacement, input bindings, request state and verified result. The journal SHALL be recovery evidence only; normal deduplication SHALL use Ghostfolio references, never a separate correspondence table.

Use exclusive runtime locking and atomic, synced file replacement. File paths SHALL reject symlinks, collisions with broker/mapping/evidence inputs and unsafe existing permissions. Concurrent runs sharing the same review SHALL not dispatch overlapping corrections. Detect operator edits before dispatch and before publication; do not overwrite edits or reuse an approval changed during the run. If persistence fails after a possible PUT, retain uncertainty rather than forgetting intent. If a review is globally unreadable or cannot be locked, all accounts using it SHALL stop before financial writes. File-level syntax/schema errors or an unbound unknown proposal SHALL stop all accounts sharing that file; a valid keyed proposal with any non-yes approve value SHALL be skipped without releasing its related import hold. Operators SHALL edit the review between runs. Advisory locks and byte comparisons detect cooperating writers and observed changes, but cannot prevent an arbitrary editor from racing the final check and replacement. Do not claim atomic compare-and-swap against uncooperative editors. If a concurrent edit is detected, preserve the operator file and pending intent, stop affected dispatch, and report ERROR.

Removing a confirmed proposal SHALL follow durable success recording. If the process stops between these steps, the next run SHALL finish local cleanup without another PUT. The journal SHALL support offline inspection and an exact reverse payload for an unchanged corrected row. Reversal SHALL require separate explicit authority and fresh checks; it SHALL never run automatically. Reverting software SHALL NOT be described as restoring financial data.

#### Scenario: Crash, file edit and rollback evidence
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_persistence` exercises process interruption before/after intent, after PUT, after verification, disk failure, concurrent editor/run, unsafe paths and changed rows during reversal inspection
- **THEN** intent is recoverable, approved edits are not lost, confirmed updates are never replayed, and reverse evidence is available only for unchanged journal-owned rows without automatic reversal.
