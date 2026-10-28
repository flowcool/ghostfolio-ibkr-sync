# Design

## Context

See proposal.md. `source_events`, `refresh_proposals` and `process_review` already separate discovery from dispatch. Today blocked exceptions can erase differences. `dividend_action_conflict` runs before conformity checks. Legacy trade aliases are always marked unsafe. Manual duplicate filters run after review.

## Goals / Non-Goals

Implement the approved profiles with pure typed functions. Keep one operator file. Preserve existing financial conversion and exact update transport. No new service, dependency or aggregate-write engine.

## Decisions

- Add `activity_reconciliation.py` for profile constants, exact gross comparison, local dates and pair eligibility. Reuse `config.load`, `Settings`, `source_events`, `convert_trade_to_activity` and `convert_dividend_actions`. Use `Decimal` and bounded reproduction of existing float operations. Do not invent another converter.
- Extend `refresh_proposals` to compute differences before blockers, classify conforming identities and build the complete source/target graph. Apply explicit mapping, reference precedence and mutual uniqueness before auto-selection. Reuse `marker_of` and `replacement_comment`; separate comment-only migration from later financial correction. Keep that migration within the same execution budget.
- Publish compact schema 3 through `decode_review`/`encode_review`. Use `decision: null|yes|reject`. Preserve full exact pending evidence and rejected-pair bindings in a private derived `.state.yaml`. Write journal v2 authority; retain v1 recovery. Bind each displayed key, revision and decision to internal evidence. Publish state before the operator view under `open_review` locking and `atomic_yaml`; retain previous bindings for recoverable view lag; refuse unknown mismatches. Provide simulation-only state rebuild with cleared decisions and intact journals.
- Extend `process_review` to record manual or profile authority. Reuse `update_payload`, `expected_row`, `recovery_read` and `ghost_update_reviewed_activity`. Tolerances select a pair; they never weaken readback.
- Carry valid rejected activity IDs per source event through `filter_trades_by_holdings` and dividend selection. Extend transient manual/dividend indexes with target IDs. Do not globally remove a rejected activity. Reuse `report_review_outcome` and `outcome` for counts and instructions. Adapt `identity_migration.py` to the shared compact view without weakening offline maintenance.

## Risks / Trade-offs

Threshold matches accept operator-selected uncertainty. Label their authority. State/view interruption adds a recovery case; test every publication boundary. Shared helper changes need downstream review, not automatic DEGIRO propagation.

## Migration Plan

Read schemas 1/2; retain private evidence and journals; clear old approvals once; publish schema 3. Default automation stays off. Require isolated exact-image acceptance before activation. Stop writers before downgrade. Keep a schema-3 reader until unresolved requests settle. Reverting code does not undo data; reverse writes retain separate authority. Revert the planning commit to roll back this proposal.
