# Design

## Context

Baseline: main `8679db1`; released reader `246b890`, rc.5 image `sha256:32a034c96c2a675329e0aa38a3003a0352db8cec013ea74b6d04ac04cc8a9369`. Reader release and both labs passed. Ghostfolio evidence concerns 3.86.0; current deployment needs verification.

## Goals / Non-Goals

Preserve account/event identity and historical reads. Preview exact comment replacements. Exclude financial repair, aggregate splitting and automatic historical updates.

## Decisions

1. Reuse strict identity parsing and deduplication. Write verified source-account identities. Reject unsafe segments without transformation. Require matching Trade accountId; document this upgrade prerequisite.
2. Preserve security/day groups for legacy precedence and coverage. Partition new candidates by action. Reuse cash/action helpers; extract per-action quantity validation from the existing group-wide validator. Different actions can have different quantities. Associate tax through explicit cash keys.
3. Parse accepted identity kinds before updating holdings. Keep manual-match bookkeeping source-account scoped. Preserve partial-coverage refusal. Require a separately authorized, versioned recovery path for missing actions after partial acceptance. Block detectable same-account/security/day action replacement conflicts.
4. Keep one maintenance engine outside the runtime image. Reuse pure conversion rules, exact JSON decimals, atomic journal writes and journal locks from existing cleanup tooling. Adapt the explicit update payload; never reuse its delete-pair executor. Preview has no network client. Florent requested conversion of exact unique 1→1 historical comments only.
5. Require complete configured account inventory and unchanged before/after import selection. A converted legacy-global marker must not expose another account's trade. Reject financial differences, including changed fee-clamp results.
6. Qualify full update payload preservation and background effects. Bind apply/rollback to reviewed manifests, exclusive writers and durable journals. Negative readback cannot settle a delayed request; require independent completion/cancellation evidence. Existing cleanup tools remain unavailable on v2 until qualified.

## Risks / Trade-offs

Saved overlap proves bounded repeatability, never lifetime stability. Record missing revision coverage as an explicit gate. Account-scoped identity needs no global-ID uniqueness guarantee. Legacy precedence can hide events. Partial acceptance requires operator recovery; no automatic filling. Same-day conflict refusal can block a legitimate additional event. Changed financial values require manual review.

## Migration Plan

Approve before tasks. Implement and qualify offline. Publish an immutable writer RC numbered rc.6 or later; pass both labs. Require separate production and maintenance GO. After any imported or converted v2 row, rc.5 is the reader floor. Stop writers first; retain rows and journal. Reverse only proven comment replacements. The delta defines remaining gates and acceptance.
