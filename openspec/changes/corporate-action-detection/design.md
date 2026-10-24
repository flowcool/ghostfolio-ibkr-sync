# Design

## Context

See proposal.md. Stored activities and effective holdings differ. Existing source-account checks and uncertain-write fences remain stronger than trade-only holds.

## Goals / Non-Goals

Produce reproducible evidence and candidate-specific decisions. No corporate-action executor or automatic conversion.

## Decisions

- Add corporate_actions functions using ibkr parsing and sync.resolve_symbol. Require CorporateActions; absent holds account BUY/SELL, selected-empty records bounded coverage. Parse description ratios as candidates. Verify forward deltas against independent pre-event source quantities; reconcile reverse legs. Unknown dates, effects or identities remain held. No mandatory OpenPositions.
- Reuse ghost_get_existing_orders with exact wire decimals in live and simulation. Read profiles/holdings and restricted export version metadata once when native proof is needed. Verify stable >=3.91.0 and non-admin image-backed read permissions before native enablement. The existing probe used an admin-capable user. Compare calculated quantities with bounded holding reads; no cache flush or epsilon.
- Keep identity rows separate from effective holdings in index_existing_activities. Reuse filter_trades_by_holdings and rejected_sell_symbols. Prove target-account units and profile-wide effects. Other-broker history is not required solely for profile sharing. Explicit old/new ISIN mappings plus linked legs and unique target ownership establish continuity; mapping alone is insufficient. Hold unmatched pre-event raw candidates in normalized histories.
- Generalize prepare_review_sources before process_review in run_configured_sync. Validate source accounts before target lookup; acquire each report once, preserve per-account failure isolation. Pass holds into process_account. Re-evaluate affected evidence after each confirmed correction and before subsequent dispatch. Existing pending-write fences still win.
- Read optional CORPORATE_ACTION_EVIDENCE_FILE for operator-verified effective dates with official HTTPS references and private source-document hashes. Retain immutable bytes; never fetch these URLs or treat date evidence as financial authority. Missing proof keeps the event held.
- Reuse activity_review.safe_path, atomic_yaml and lock patterns. CORPORATE_ACTION_STATE_FILE binds immutable private report objects in a companion directory to acquisition hashes/scope. Retain unresolved events and reconstruct conclusions from source bytes plus fresh destination reads. Hashes detect drift, not coordinated tampering. Simulation bootstraps valid state; missing/unwritable state degrades simulation and blocks live BUY/SELL. Preserve surviving evidence on recovery. Bootstrap cannot prove lifetime completeness.
- Extend finalize_run and send_notification. Separate companion delivery fingerprints from hold-critical state. Reacquire/revalidate its lock after confirmed send; failure repeats notification without changing financial decisions. Timeout remains unconfirmed. No exactly-once claim.

## Risks / Trade-offs

Historical gaps or unsupported effects can keep scoped holds until evidence or separately approved support exists. Date ambiguity holds boundary candidates. Source retention costs storage. README must explain prerequisites and recovery.

## Migration Plan

Implement only after OpenSpec approval. Retain release gates and distinct publication/production authority. Rollback stops writers and forces simulation before older code. Preserve evidence; no financial reversal.
