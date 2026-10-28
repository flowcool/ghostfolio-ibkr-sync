# Tasks

Commands below are future offline acceptance, not current passing evidence. Runtime paths are under `ghostfolio_ibkr_sync/`. Every slice includes synthetic tests and mocked HTTP. Slices changing existing behavior also update and run their affected tests/test_activity_review.py scenarios: review_candidates, review_approval, review_source_scope, review_refresh and review_simulation; do not defer these updates to integration. Requirement names refer to this change’s delta specs.

## 1. Profile configuration and financial limits

- [x] 1.1 Add validated default-off profiles, exact gross limits and quantity rules. Document the ENV and limits in docs/configuration.md. Requirements: Explicit reconciliation profiles; Bounded gross differences and exact quantities. Files: config.py, models.py, activity_reconciliation.py, tests/test_activity_reconciliation.py. Verify: `python -m pytest -q tests/test_activity_reconciliation.py -k "profile_config or financial_limits"`.

## 2. Proven numerical representations

- [x] 2.1 Reuse conversion, reproduce bounded calculation residue and normalize GBP/GBp without rounding payloads. Document accepted causes in docs/activity-review.md. Requirements: Proven calculation residue without payload rounding. Files: activity_reconciliation.py, sync.py, tests/test_activity_reconciliation.py. Verify: `python -m pytest -q tests/test_activity_reconciliation.py -k "numeric_residue"`.

## 3. Complete candidate graph

- [x] 3.1 Build complete candidate graphs with reference precedence, local calendar windows and mutual uniqueness. Include DST, invalid TZ, collisions and competing candidates. Requirements: Unique matching and business dates. Files: activity_reconciliation.py, activity_review.py, tests/test_activity_reconciliation.py. Verify: `python -m pytest -q tests/test_activity_reconciliation.py tests/test_activity_review.py -k "unique_matching or review_candidates"`.

## 4. Mapping-owned reference migration

- [x] 4.1 Permit unique comment-only legacy migration under mapping authority; preserve every other field and reselect after confirmation. Document mapping responsibility. Requirements: Mapping-owned historical identity. Files: activity_review.py, app.py, tests/test_activity_reconciliation.py. Verify: `python -m pytest -q tests/test_activity_reconciliation.py tests/test_activity_review.py -k "legacy_migration or review_source_scope"`.

## 5. Conformity and dividend conflicts

- [x] 5.1 Classify conforming v2 identities before unrelated context guards. Name actual counterparts; retain partial-source holds. Cover distinct legacy dividend pairs and signed tax cases. Requirements: Relevant conflicts and conforming activities. Files: activity_review.py, sync.py, tests/test_activity_reconciliation.py. Verify: `python -m pytest -q tests/test_activity_reconciliation.py -k "conformity"`.

## 6. Compact review and private state

- [ ] 6.1 Publish schema 3 and private bound state. Test schema-1/2 migration, journal v1/v2, stale decisions, missing state, simulation rebuild via identity_migration.py rebuild-review, its profile cooldown and every publication boundary. Land the shared identity_migration.py schema reader here so maintenance stays green; finish its selection adapter in 10.1. Document backup and downgrade recovery. Requirements: activity-correction-review: Optional persistent review file; Durable files and recovery evidence. Files: activity_review.py, identity_migration.py, tests/test_activity_reconciliation.py, tests/test_identity_migration.py. Verify: `python -m pytest -q tests/test_activity_reconciliation.py tests/test_identity_migration.py tests/test_activity_review.py -k "compact_review or shared_review or review_persistence or review_refresh"`.

## 7. Persistent pair rejection

- [ ] 7.1 Bind rejection to relevant evidence and carry target IDs into ordinary trade/dividend selection. Test all-rejected import release, new candidates, stale rejection and other events sharing a target. Document decision editing. Requirements: activity-correction-review: Pending proposals and file refresh. Files: activity_review.py, sync.py, ghostfolio.py, tests/test_activity_reconciliation.py. Verify: `python -m pytest -q tests/test_activity_reconciliation.py tests/test_activity_review.py -k "pair_rejection or review_refresh"`.

## 8. Qualified profile dispatch

- [ ] 8.1 Integrate fresh automatic authority with manual decisions, shared finite budget, journal intent, exact readback and no-resend recovery. Test off, dry-run, conflicts and account fences. Document activation qualification. Requirements: Bounded execution and visible outcomes; activity-correction-review: Verified correction and dependent import state. Files: activity_review.py, app.py, tests/test_activity_reconciliation.py. Verify: `python -m pytest -q tests/test_activity_reconciliation.py tests/test_activity_review.py -k "profile_execution or review_approval or review_simulation"`.

## 9. Grouped diagnosis and outcomes

- [ ] 9.1 Display source/target group counts and exact differences, distinct authority and truthful outcomes. Cover four source fills versus two targets; no aggregate correction. Keep external notifications redacted. Requirements: Grouped diagnosis without aggregate correction; connector-runtime: Final operational result. Files: activity_review.py, app.py, notify.py, outcome.py, tests/test_activity_reconciliation.py. Verify: `python -m pytest -q tests/test_activity_reconciliation.py -k "group_diagnosis or profile_execution"`.

## 10. Historical maintenance compatibility

- [ ] 10.1 Adapt root identity_migration.py, identity_maintenance.py and shared review codecs to compact decisions and private evidence. Keep separate operation authority and exact selected-subset replay. Requirement: connector-runtime, Historical maintenance from the shared approval file; scenario Shared compact maintenance adapter. Update docs/activity-review.md commands and synthetic examples. Verify: `python -m pytest -q tests/test_identity_migration.py -k 'shared_review or preservation'`.

## 11. Integrated compatibility

- [ ] 11.1 Prove unchanged disabled behavior, retained reader generations, recovery and all profile paths together. Requirements: all three delta specs and their named scenarios. Verify: `bash scripts/check.sh` and `python -m pytest -q`. Reconcile README.md and required user docs with delivered behavior. Update ADR 0002/0003 references and proposed ADR 0009 status only when implemented. Reconcile affected repository guidance with the approved exception through its policy-confirmation rule. Archive the completed change in the final implementation commit and repair ADR links; verify `openspec validate --all --strict` and `git diff --check`. Record pending exact-image qualification separately; offline success grants no financial or publication authority.
