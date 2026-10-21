# Tasks

Execution order: 1.1 → 1.2 → 2.1 → 2.2 → 3.1 → 3.2 → 3.3 → 4.1 → 4.2 → 4.3 → 5.1 → 5.2 → 6.1. One fresh implementation session per task. Each task includes its own regression tests and required user documentation.

All requirements and scenarios below refer to `specs/connector-runtime/spec.md` in this change. These are future acceptance commands; zero collected tests is failure. This planning session implements none of them.

Implementation uses synthetic data and mocked HTTP. Replaying existing local captures is read-only. No task authorizes real broker access, Ghostfolio writes, migrations, releases or deployment. A task is complete only after its acceptance passes and its PR merges. Update only that task's checkbox.

G1–G7 qualification remains explicit. A missing required source case or image-backed proof blocks enablement, not independent offline implementation. Unknown global actionID uniqueness is informational because the account segment remains in every identity. Do not invent a feature flag or a vendor guarantee to bypass a gate.

Publication, both isolated labs, current destination-version confirmation and actual rc.5 rollback/preservation proofs belong to the separately gated release work, outside this implementation checklist. The release owner must obtain a validated operation plan and Florent GO; publish the immutable RC before lab validation, and require both lab scenarios on that same digest before production soak or stable promotion. Production preview, recovery, historical conversion and stable promotion retain separate approvals.

The release owner also requires a complete saved migration-input replay and all required G1–G7 evidence. Archive this change and replay acceptance on main after all checklist tasks close, before the release. No lab-proof, internal-tooling or process-automation task is added here.

## 1. Strict identities and account state

- [x] 1.1 Write strict source-account trade identities. Implement the shared v2 formatter and trade writing. Require every candidate accountId to match the verified report account before any financial write. Reject unsafe segments and comments over 2000 ASCII characters without transformation or legacy fallback. Keep historical reader acceptance unchanged. Document the Flex accountId prerequisite and exact formats. Verify: `.venv/bin/python -m pytest -q tests -k 'v2_identity_writer or v2_comment_limits or versioned_identity_reader'`.
  - Requirements: Versioned activity identity reader; Destination comment compatibility gates.
  - Scenarios: Write account-scoped identities; Comment boundaries.
  - Files: `ghostfolio_ibkr_sync/{ghostfolio,sync,ibkr,models,app}.py; tests/{test_ghostfolio,test_conversion,test_orchestration}.py; README.md; docs/ibkr-setup.md`.
- [x] 1.2 Keep accepted and manual state account-scoped. Update accepted state by parsed identity kind. Dividends never change holdings or the legacy-global trade set. Scope ephemeral manual matches by source account and show v2 manual-tag advice. Preserve accepted-subset and simulated-state boundaries, including omitted buys before sales. Amend ADR 0002 for this state behavior. Verify: `.venv/bin/python -m pytest -q tests -k 'v2_accepted_state'`.
  - Requirements: Versioned activity identity reader.
  - Scenarios: Same-run accepted state.
  - Files: `ghostfolio_ibkr_sync/{app,sync,ghostfolio,models}.py; tests/{test_orchestration,test_filters,test_ghostfolio}.py; docs/adr/0002-comment-and-proximity-deduplication.md`.

## 2. Dividend quantities and cash partition

- [x] 2.1 Validate quantity separately for each cash action. Extract per-action quantity validation from the group-wide scalar validator. Keep cash as payment authority, exact Decimal associations, one unique matching Re and positive finite numeric conversion. Permit unequal quantities across distinct actions without summing quantities inside an action. Preserve zero/negative action and currency protections. Verify: `.venv/bin/python -m pytest -q tests -k 'dividend_structured_quantity or dividend_structured_numeric or v2_action_quantity'`.
  - Requirements: Flex selection and conversion.
  - Scenarios: Quantity association; Final numeric limits; Components and money.
  - Files: `ghostfolio_ibkr_sync/{sync,ibkr,models}.py; tests/{test_conversion,test_parsing}.py`.
- [x] 2.2 Write one dividend per proven action. Partition new security/day candidates by verified account/action. Join tax by the approved account/action/contract/currency/day keys and optional exDate. Conserve cash totals before per-action fee clamps. Prevalidate the entire group before dispatch. Fail affected accounts for partition errors while safe trades, cash and later accounts continue. Preserve tax-only not-payable behavior. Document per-action dividends and complete input requirements. Verify: `.venv/bin/python -m pytest -q tests -k 'v2_event_partition or v2_partition_isolation or dividend_structured_input or unknown_trade_side'`.
  - Requirements: Flex selection and conversion; Enriched dividend input and local rejection.
  - Scenarios: Selected records; Action partition and withholding; Partition failure isolation; Compatibility and isolation.
  - Files: `ghostfolio_ibkr_sync/{sync,ibkr,models,app}.py; tests/{test_conversion,test_parsing,test_orchestration}.py; README.md; docs/ibkr-setup.md`.

## 3. Mixed-history protection and explicit recovery

- [x] 3.1 Protect mixed history and action-context conflicts. Preserve legacy-global trades, account-local historical dividend precedence and complete v2 coverage. Retain partial-coverage refusal. Before no-coverage import, block detectable same-source/security/day action conflicts, including unknown overlap context. Keep v2 dividends out of proximity and historical diagnostics. Expose recurring partial failures and the limits of legacy precedence and revision detection in upgrade guidance. Verify: `.venv/bin/python -m pytest -q tests -k 'v2_generation_dedup or v2_action_conflict or versioned_identity_reader'`.
  - Requirements: Dividend action coverage; Enriched dividend input and local rejection.
  - Scenarios: Complete, partial and absent coverage; Historical generations and conservative precedence; Replaced identity or additional same-day event.
  - Files: `ghostfolio_ibkr_sync/{ghostfolio,sync,app,models,diagnostics}.py; tests/{test_filters,test_orchestration,test_dividend_proximity,test_dividend_diagnostics}.py; docs/adr/0002-comment-and-proximity-deduplication.md; docs/upgrading-to-3.0.md`.
- [x] 3.2 Preview exact missing actions for explicit recovery. Add the versioned offline recovery preview. Read complete saved source and destination evidence without credentials or HTTP. Produce a private, deterministic reviewed manifest containing only exact missing identities and financial fields. Preserve accepted rows; reject changed evidence, unresolved requests and incomplete action coverage evidence. Document preview inputs and the separate operation authorization. Verify: `.venv/bin/python -m pytest -q tests -k 'v2_partial_recovery_preview'`.
  - Requirements: Dividend action coverage.
  - Scenarios: Bounded recovery after partial acceptance.
  - Files: `identity_recovery.py (new); identity_maintenance.py (new shared offline helper); tests/test_identity_recovery.py (new); docs/cleanup.md`.
- [x] 3.3 Submit bounded recovery only through explicit maintenance. Add the explicit recovery submission path with stopped competing writers, settled requests, approved manifest and durable journal. Submit only missing action payloads. Stop on uncertain or partial results without automatic retry; require complete coverage readback and zero normal-simulation reinsertions. Exercise all requests through mocks and document the versioned command and stop conditions. Flag downstream propagation if a shared request helper changes. Verify: `.venv/bin/python -m pytest -q tests -k 'v2_partial_recovery'`.
  - Requirements: Dividend action coverage.
  - Scenarios: Bounded recovery after partial acceptance.
  - Files: `identity_recovery.py; identity_maintenance.py; cleanup_recovery.py; ghostfolio_ibkr_sync/ghostfolio.py only if shared request support is needed; tests/test_identity_recovery.py; docs/cleanup.md`.

## 4. Offline historical migration preview

- [x] 4.1 Add an isolated deterministic migration preview. Provide the outside-image preview CLI using the shared pure rules and offline readers. Validate keyed YAML, exact JSON decimals, complete snapshot metadata and inventory/mapping/TZ inputs. Deny network and credential loading even with DRY_RUN=false. Reject existing outputs, overlaps and symlinks; write only a new 0700 directory with 0600 files. Document the runnable interface. Verify: `.venv/bin/python -m pytest -q tests -k 'v2_migration_offline'`.
  - Requirements: Offline historical identity migration preview.
  - Scenarios: Offline and deterministic boundary.
  - Files: `identity_migration.py (new); identity_maintenance.py; tests/test_identity_migration.py (new); docs/cleanup.md`.
- [x] 4.2 Select only exact unique historical replacements. Classify every source event and historical row once. Permit only exact unique 1-to-1 trade or one-action dividend comments with proven ownership, security, account, date and exact money/quantity. Require both fee-clamp projections to equal the stored fee. Exclude aggregates, ambiguity, manual/inactive/unsupported rows, occupied v2 identities and partial groups. Keep full exclusion evidence visible and document eligibility. Verify: `.venv/bin/python -m pytest -q tests -k 'v2_migration_preview'`.
  - Requirements: Offline historical identity migration preview; Flex selection and conversion.
  - Scenarios: Exact migration preview.
  - Files: `identity_migration.py; identity_maintenance.py; tests/test_identity_migration.py; docs/cleanup.md`.
- [x] 4.3 Prove migration preserves complete import selection. Require reports for every configured source account and affected window. Replay the complete selected payload set and holdings decisions before and after simulated comment replacements. Reject any difference, including a released legacy-global trade suppression. Bind hashes, mapping, image/version, tool revision and ordered row fingerprints in the manifest. Document invalidation after configuration changes and the limit for future undeclared accounts. Verify: `.venv/bin/python -m pytest -q tests -k 'v2_migration_selection or v2_migration_preview or v2_migration_offline'`.
  - Requirements: Offline historical identity migration preview.
  - Scenarios: Exact migration preview; Offline and deterministic boundary.
  - Files: `identity_migration.py; identity_maintenance.py; ghostfolio_ibkr_sync/{sync,app}.py only to expose existing pure selection rules; tests/test_identity_migration.py; docs/cleanup.md`.

## 5. Explicit comment maintenance and rollback

- [ ] 5.1 Apply only reviewed comment replacements. Add explicit apply with manifest hash, backup and writer-exclusion prerequisites, fresh ownership/occupancy checks and durable per-row pending journal state. Reuse atomic persistence and locks; never the cleanup delete executor. Construct a whitelisted full PUT payload and verify unchanged financial/date/tag/profile context through mocked readback. Stop on stale or uncertain results. Keep G5 preservation and measured pacing qualification pending until image-backed proof; no default live batch limits. Document the command and its authorization boundary. Verify: `.venv/bin/python -m pytest -q tests -k 'v2_migration_apply_rollback and not rollback_only'`.
  - Requirements: Explicit maintenance conversion and rollback boundary.
  - Scenarios: Guarded conversion and reverse conversion.
  - Files: `identity_migration.py; identity_maintenance.py; cleanup_recovery.py; cleanup_duplicates.py only for qualified payload/journal reuse; tests/test_identity_migration.py; docs/cleanup.md`.
- [ ] 5.2 Restore only unchanged journal-owned comments. Add guarded rollback and resume inspection. Require exact recorded v2 ownership and unchanged full context; preserve newly imported v2 activities. Keep timeout uncertainty until independent completion/cancellation proof; old-comment or absent-row readback alone is insufficient. Test delayed requests, partial completion, drift, numeric normalization and reverse PUT preservation. Document comment reversal, safe halt and the rc.5 reader floor. Verify: `.venv/bin/python -m pytest -q tests -k 'v2_migration_apply_rollback'`.
  - Requirements: Explicit maintenance conversion and rollback boundary.
  - Scenarios: Guarded conversion and reverse conversion.
  - Files: `identity_migration.py; identity_maintenance.py; tests/test_identity_migration.py; docs/cleanup.md; docs/upgrading-to-3.0.md`.

## 6. Integration and compatibility

- [ ] 6.1 Check qualification status and cross-connector compatibility. Add the full synthetic mixed-generation and counterexample matrix and replay saved local inputs without publishing private data. Record G1-G7 evidence status, bounded source windows/cases and exact missing proofs in the owning Beads notes; synthetic PASS never certifies vendor lifetime or image behavior. Compare the pinned sibling mechanisms and flag any shared-helper propagation; change no sibling pin or writer. Verify combined upgrade/release guidance, source prerequisites, old cleanup exclusion and the pending image-backed rollback/preservation gates. Run the full repository check as well as the focused matrix. Verify: `.venv/bin/python -m pytest -q tests -k 'v2_source_qualification or v2_release_compatibility' && scripts/check.sh`.
  - Requirements: Source identity evidence gates; Destination comment compatibility gates; Writer release order and sibling compatibility.
  - Scenarios: Source qualification remains bounded; Mixed-history rollback and downstream boundary.
  - Files: `ghostfolio_ibkr_sync/{sync,ghostfolio,app}.py only for integration fixes; tests/{test_ghostfolio,test_orchestration,test_conversion,test_identity_migration,test_identity_recovery}.py; README.md; docs/{upgrading-to-3.0,releasing,cleanup}.md; docs/adr/0002-comment-and-proximity-deduplication.md`.
