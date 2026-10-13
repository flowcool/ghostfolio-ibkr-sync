# Design

## Context

See proposal.md. The saved report has no negative payment rows, explicit quantities or payment identifiers. Correction association needs conservative synthetic coverage. Quantities are inferred, not independently observed holdings.

## Goals / Non-Goals

**Goals:** recover supported quantities, retain uncertainty and prepare reversible operator corrections.

**Non-Goals:** change grouping/comments, infer entitlement from current holdings or redesign shared helpers.

## Decisions

`parse_cash_dividends` retains signed rows. Ordinary/bonus labels define separate distributions; dividend/PIL rows are portions within a distribution, even with equal rates. Cancel only uniquely compatible opposite rows with the same type, label, currency and rate. Duplicate candidates, partial reversals or incompatible surviving rates remain uncertain. Evaluate surviving portions after cancellation; never use the cancelled rate. This replaces guessing from the last row.

`convert_dividend_to_activity` reuses rounding, total-derived price, withholding and `minor_unit_conversion`; validate rate currency and finite representable results. Label rounded equality as inferred agreement. Missing entitlement evidence stays unresolved.

`ghost_get_existing_orders` retains comparison evidence; `process_account` compares before deduplication. Only unique active same-account canonical identities support repair proposals. Proximity suppresses duplicates; it does not prove payment identity.

Reuse YAML atomic-write/lock primitives from `cleanup_recovery.py`, not its deletion-pair semantics. Persist exceptions/proposals keyed by source account, target account and dividend identity through `DIVIDEND_RECONCILIATION_FILE` (default `dividend-reconciliation.yaml`); README requires a private durable mount. Store hashes, signed evidence, reasons and observed/proposed values; no credentials. Refuse source/output collisions and stale proposals. Storage failure degrades and blocks uncertain dividend imports.

`record_failure`, `build_failure_summary` and `finalize_run` report unresolved reconciliation through existing sanitized summaries. Ordinary warnings stay unchanged.

Extend `cleanup_dividends.py` with offline `--reconcile FLEX_XML --snapshot GHOST_JSON --account-id ID --journal PLAN`, explicit `--resume PLAN --apply`, and `--restore PLAN --apply`. Typed correction journals cannot enter duplicate-deletion paths. Inspection writes no activities. Reuse fresh-record checks, record originals before PUT and verify readback; uncertainty requires explicit recovery. No DELETE or reinjection for quantity repair.

## Risks / Trade-offs

Incomplete evidence → open exception; leaving the report window never resolves it. No conditional API write → quiet writers and fresh checks. Missing storage → degradation, never silent provisional import. Private evidence stays outside Git.

## Migration Plan

Configure storage before separately authorized deployment. Revert implementation/image for runtime rollback; imports remain. Historical rollback uses verified journal originals under explicit maintenance. Revert this document commit for proposal rollback.
