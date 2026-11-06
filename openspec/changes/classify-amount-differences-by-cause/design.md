# Design

## Context

See `proposal.md`. `diagnostics.classify_dividend_findings` accepts declared-rate
rounding. `activity_reconciliation.numeric_evidence` proves converter residue.
`activity_review.process_review` owns every correction and its recovery.

## Goals / Non-Goals

Explain and route findings. Keep broker evidence in adapters and the existing writer.

## Decisions

1. Add functions in `ghostfolio_ibkr_sync/amount_differences.py`.
   Findings carry exact values, currency, association and broker evidence. Each cause
   returns `(label, reason, action)` or `None`. Actions are `correct` and
   `information`. First match explains only its proven fields.
   Fixed order: IBKR declared rate, BD printed gross, DEGIRO execution views,
   then the candidate omitted-withholding cause. Retain its gate.
   No named match leaves existing correction selection unchanged. Exact source
   replacements use `correct`, labelled `source-proven correction`. This fallback
   is existing authority, not a newly registered cause. Only missing exact
   replacement proof yields `to_check` without a write.
2. Reuse `_historical_minor_unit`, exact decimal arithmetic and denomination
   evidence. Broker adapters supply raw fields, not trusted acceptance flags.
   BD uses `notices.checked_amounts` HALF_UP corroboration; DEGIRO uses
   `sync.execution_cash_matches` identity and signed-gross evidence. Define
   their contracts here; enable sibling adapters only in separately owned work.
3. Reuse `numeric_evidence`, `gross_within_limits`, `automatic_pairs` and
   `refresh_proposals`. A cause does not create identity or increase profile
   authority. `correct` requires a fresh complete source, unique association,
   exact replacement and the existing profile limits or manual approval.
   Missing causes never block profiles or manual `yes`. Information
   covers only proven fields where the source is not more exact. Evaluate other
   fields independently. Preserve amount, fee, date, currency and comment rules.
4. Reuse `process_review`, `update_payload`, durable intent and `recovery_read`.
   Optional explanation changes must not revoke consent or eligibility.
   Changed source, target or authority retains existing invalidation. Preserve pending journals and no
   resend. Reporting reads outcomes; it never writes.
5. Compare correction sets with and without explanations on existing
   profile and manual fixtures. Require identical eligibility, payloads, consent,
   queue order and recovery. Reuse existing reconciliation coverage.

## Risks / Trade-offs

- Explanation mistaken for authority → retain exact source and association guards.
- New cause gate removes valid corrections → require correction-set equivalence.
- Display noise mistaken for proven rounding → keep exact comparisons separate.
- Stored data changed by rollback → code rollback cannot restore financial data.

## Migration Plan

No automatic history conversion. Revert scoped code to restore prior routing;
retain review files and settle pending journals through exact readback.
ADR 0007 requires separate package-aware DEGIRO adoption. Route BD adoption to
its importer owner. No sibling pin or runtime changes here.
