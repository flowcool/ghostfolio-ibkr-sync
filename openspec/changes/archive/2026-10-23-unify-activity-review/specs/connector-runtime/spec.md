## ADDED Requirements

### Requirement: Historical maintenance from the shared approval file

Historical reference-only maintenance SHALL use the same schema-2 approval file as normal activity review. The offline `identity_migration.py review` command SHALL stage only exact eligible comment replacements with preserved dates, financial fields, IDs, accounts, tags and notes. It SHALL name the historical maintenance execution path. Normal sync SHALL NOT dispatch those staged maintenance approvals. Both commands SHALL refuse staging or preparation when the shared journal contains a pending request. The operator SHALL stop cooperating review writers before staging, editing or preparing a historical selection.

`identity_migration.py prepare` SHALL select only literal yes entries for historical reference-only maintenance. It SHALL rebuild each selected proposal from saved source and destination evidence. Changed evidence, bindings or proposal content SHALL refuse preparation. Unselected entries SHALL produce no correspondence or rejection state. It SHALL re-run complete import selection for the exact selected subset, including full payloads and holdings decisions. Equality for a larger set SHALL NOT replace that proof. Refused selections SHALL not produce an apply manifest. The manifest SHALL bind the approval-file bytes and selected keys. Preparation and apply SHALL hold the shared review lock. Apply SHALL require that file and SHALL refuse plain preview manifests. Successful apply SHALL remove confirmed selections from the file. The maintenance journal SHALL retain their consent keys and revisions. Re-staging SHALL remove stale historical proposals and clear historical approvals, including after rollback; consumed consent SHALL never be resurrected. Apply SHALL revalidate this same file and rebuild the selected manifest before any request. This file consent SHALL NOT replace separate operation authorization, preservation qualification, writer exclusion, settlement or pacing evidence. Existing inspection and journal-owned rollback SHALL remain available.

Community documentation SHALL describe the two sections, evidence levels, skip behavior, both execution paths, exact commands, schema compatibility and recovery. Examples SHALL use synthetic identifiers and SHALL distinguish preparation from production permission.

#### Scenario: Exact approved subset and community commands
- **WHEN** `python -m pytest -q tests/test_identity_migration.py -k shared_review` stages historical proposals, changes approval choices and prepares a subset using mocked saved evidence
- **THEN** only exact yes entries reach the selected manifest, the exact subset passes its own selection replay, changed evidence is refused, no network request occurs, and documented command arguments match the CLI.

### Requirement: Stable preservation with raw tamper evidence

Historical apply, inspect and rollback SHALL compare preserved activity business values exactly. They SHALL ignore only enumerated server metadata and derived values supported by the pinned API schema and retained paired reads. Unknown fields SHALL remain in comparison. Equivalent numeric representations and UTC timestamps SHALL compare equal without a financial tolerance. Raw preimages, manifest hashes and journal fingerprints SHALL remain tamper evidence. Stable comparison SHALL cover every snapshot row during a batch. A pending request SHALL remain uncertain regardless of comparison outcome and SHALL never be retried automatically.

#### Scenario: Metadata and business drift
- **WHEN** `python -m pytest -q tests/test_identity_migration.py -k preservation` simulates comment changes, server timestamps, derived values, exact numeric normalization, unknown fields and financial drift
- **THEN** metadata alone does not fail readback, business or unknown-field drift refuses further writes, raw tamper evidence remains checked, and reverse execution applies the same preservation rule.
