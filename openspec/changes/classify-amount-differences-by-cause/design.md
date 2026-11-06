# Design

## Context

See `proposal.md`. `diagnostics.classify_dividend_findings` accepts declared-rate
rounding. `activity_reconciliation.numeric_evidence` proves converter residue.
`activity_review.process_review` owns every correction and its recovery.
The evidence and financial risks are in the specification deltas.

## Goals / Non-Goals

Use one small ordered registry for explanation and routing. Keep broker evidence
in adapters. Keep request execution in the existing reviewed-update path.

## Decisions

1. Add pure typed functions in `ghostfolio_ibkr_sync/amount_differences.py`.
   A normalized finding carries broker, operation, exact source/target decimals,
   currency provenance, independent association and cause evidence. Each cause
   returns `(label, reason, action)` or `None`. Actions are `correct` and
   `information`. First match wins; no match means `to_check`.
   Fixed order: IBKR declared rate, BD printed gross, DEGIRO execution views,
   source-proven manual entry error. Specific source-view rules precede repair
   to prevent a generic entry-error rule from correcting accepted rounding.
   Keep the entry-error function unregistered until complete real-data proof
   passes the specification gate. A global tolerance would hide causes.
2. Reuse `_historical_minor_unit`, exact decimal arithmetic and denomination
   evidence. Broker adapters supply raw fields, not trusted acceptance flags.
   BD uses `notices.checked_amounts` HALF_UP corroboration; DEGIRO uses
   `sync.execution_cash_matches` identity and signed-gross evidence. Define
   their contracts here; enable sibling adapters only in separately owned work.
3. Reuse `numeric_evidence`, `gross_within_limits`, `automatic_pairs` and
   `refresh_proposals`. A cause does not create identity or increase profile
   authority. `correct` requires a fresh complete source, unique association,
   exact replacement and the existing profile limits or manual approval.
   Unknown discrepancies cannot inherit a known cause from the same group.
4. Reuse `process_review`, `update_payload`, durable intent and `recovery_read`.
   Bind cause evidence to the existing proposal revision and journal eligibility.
   Preserve old pending journals. Evidence changes invalidate cause eligibility;
   they never permit resend. Reporting reads execution outcomes; it never writes.

## Risks / Trade-offs

- Manual history mistaken for proof of each error → require the per-field cause
  predicates and preserve current partial-coverage holds.
- Display noise mistaken for proven rounding → keep exact comparisons separate.
- Stored data changed by rollback → code rollback cannot restore financial data.

## Migration Plan

No automatic history conversion. Revert scoped code to restore prior routing;
retain review files and settle pending journals through exact readback.
ADR 0007 requires separate package-aware DEGIRO adoption. Route BD adoption to
its importer owner. No sibling pin or runtime changes here.
