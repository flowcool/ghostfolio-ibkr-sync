# Design

## Context

See proposal.md. Baseline: main `8679db1`; reader release `246b890`, rc.5 digest `sha256:32a034c96c2a675329e0aa38a3003a0352db8cec013ea74b6d04ac04cc8a9369`. Release and both lab proofs are complete. Saved destination evidence concerns Ghostfolio 3.86.0; current runtime remains unverified.

## Goals / Non-Goals

**Goals:** Preserve identity across accounts and generations. Preview exact historical replacements before any maintenance write.

**Non-Goals:** No inferred event identity, financial repair or automatic historical update.

## Decisions

1. Reuse `parse_versioned_activity_identity`, `trade_id_decision` and `dividend_dedup_decision`. Add one strict writer using the same grammar. Use the verified source account, never the destination UUID. Reject unsafe identities instead of escaping, hashing or falling back.
2. Keep `parse_cash_dividends` security/day groups for historical precedence and coverage. After deduplication, partition new candidates by action. Reuse `dividend_positive_actions`, `dividend_structured_quantity`, `_dividend_cash_sum`, `minor_unit_conversion` and conversion functions. Dividend/PIL portions share one action; distinct actions produce separate activities. Florent accepted this choice over aggregate comments.
3. Reuse `accepted_import_subset` and import phases. Parse accepted v2 kinds before updating indexes or holdings. The current `IBKR#` branch would incorrectly count v2 dividends as trades. Preview bookkeeping remains simulated.
4. Build a separate maintenance entry point around pure identity/conversion rules and exact saved JSON numbers. Reuse diagnostic currency/local-date evidence; never equate its rounding tolerance or proximity confidence with conversion eligibility. Preview has no network client. Florent requested historical conversion, limited to exact 1→1 comment replacements; aggregate splitting is excluded.
5. Explicit apply/rollback uses a private, hashed manifest and journal. Reuse redirect-safe request conventions, but do not extend the additive import function with updates. Ghostfolio's update DTO requires full financial context; unchanged readback and side-effect proof are blocking gates.

## Risks / Trade-offs

Unknown action lifetime or ambiguous withholding → block the affected dividend group. Invalid source identity → fail its account before writes. Legacy precedence can still hide events → report the limitation. Partial v2 coverage → retain rc.5 refusal, never fill automatically.

## Migration Plan

Approve proposal before tasks. Prove gates offline, publish an immutable writer RC numbered rc.6 or later, then pass both versioned labs. Require separate authorization for production and maintenance. After v2 appears, rc.5 is the minimum reader. Stop writes first; preserve v2 rows and the journal. Only proven comment replacements can be reversed. Detailed gates and acceptance are in the delta spec.
