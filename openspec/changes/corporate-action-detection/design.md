# Design

## Context

See proposal.md. Existing source-account checks and uncertainty fences remain stronger than trade-only holds. Native splits affect profile-wide portfolio calculations; activity GET preserves stored trades.

## Goals / Non-Goals

Separate immutable source evidence, fresh destination evidence and derived findings. Provide safe trade decisions and an inspectable report. No financial executor or automatic repair belongs in this increment.

## Decisions

- Add a typed corporate_actions module. Reuse ibkr parsing/date validation and sync.resolve_symbol. Parse explicit FS/RS evidence conservatively; unsupported or incomplete events retain scoped holds. Symbol-only inference cannot establish identity continuity.
- Reuse ghost_get_existing_orders and exact response parsing from activity_review. Add bounded authenticated profile/holding reads and a restricted export metadata read for version. The observed API returns meta.version; /info does not. Reject unknown/older/prerelease versions only where native proof is needed. Do not require admin tokens.
- Separate effective holdings from stored identity rows in index_existing_activities. Reuse filter_trades_by_holdings, rejected_sell_symbols and accepted-state updates. Apply a proven dated ratio once; never rewrite stored activities. Compare exact decimal evidence without a new tolerance. Current holdings alone cannot settle a historical mismatch.
- In app.run_configured_sync, generalize prepare_review_sources into one validated run inventory before process_review dispatch. Pass its holds into process_account before ordinary selection. Retain visible but non-actionable held corrections. Reuse source-account validation, account isolation and cash paths. An unknown affected set holds all account BUY/SELL. Existing correction uncertainty still blocks every later account financial write.
- Require CORPORATE_ACTION_STATE_FILE on a persistent private mount. Reuse activity_review.safe_path, atomic_yaml and its cooperating-lock pattern without sharing approval state. Simulation can initialize after valid acquisition. Live missing/invalid state holds BUY/SELL. Retain unresolved events outside later report windows and revalidate editable conclusions.
- Extend app.finalize_run and notify's existing single dispatch. Store material finding and confirmed-delivery fingerprints. Active holds repeat each run; unchanged nonblocking findings do not. Notifications contain fixed codes/counts only.

## Risks / Trade-offs

- Missing historical windows: retain explicit unknown coverage; do not certify lifetime completeness.
- Reverse-split per-lot precision residue: retain a hold. No epsilon waiver or automatic conversion.
- Profile changes affect other accounts: require complete affected scope.
- New persistence requirement: document simulation bootstrap and refusal paths before activation.

## Migration Plan

After proposal approval, implement and prove offline behavior. Exact connector release still needs its empty/golden gates and separate publication/production authority. Roll back by stopping writers and forcing simulation before an older image. Retain state and evidence. No financial reversal occurs.
