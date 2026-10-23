## Design

Keep `activity_review.open_review`, `refresh_proposals`, `publish_review` and the existing journal. Normalize schema 1 and schema 2 into the existing internal proposal map. Publish two schema-2 sections. Clear legacy approvals when the displayed contract changes. Derive the section and evidence level from rebuilt evidence. Keep full proposed values and comments visible. Only literal yes authorizes dispatch; non-null skipped choices produce a warning. Import holds remain unchanged.

Use `identity_migration.migration_evidence`, `classify_history`, `bind_selection` and `prove_selection` to stage exact historical reference-only proposals and prepare the selected subset offline. Retain dates, amounts, IDs and notes in those proposals. The normal connector must not execute maintenance proposals. The maintenance command must rebuild each selected proposal and bind the review bytes into its manifest. Prepare and apply hold the shared lock. Apply requires the file, rebuilds that selected manifest, journals consent keys, then removes confirmed selections. Re-staging clears historical approvals and prunes stale maintenance entries. An arbitrary subset never inherits the full-batch proof.

Share only pure preservation comparison. Retain raw preimages and fingerprints for tamper detection. Exclude explicitly named server timestamps and derived fields from drift checks; compare unknown fields strictly. Apply this to all snapshot rows, inspection and rollback. Keep both journal formats readable and both separately authorized execution paths.

Use synthetic HTTP tests for section tampering, schema migration, literal yes, stale approval, pending recovery, exact-subset selection, metadata churn, unknown-field drift and reverse preservation. Run the common offline gate. Ask an external Claude to challenge the final diff. Runtime correction activation stays disabled.

## Recovery and limits

An older runtime refuses schema 2. Keep a private copy before upgrade. Never edit or remove a pending journal to resume. Historical preparation requires stopped cooperating review writers; the operation approval separately requires destination writer exclusion and settlement. Production execution still needs image qualification, exact readback, measured pacing and its own GO.
