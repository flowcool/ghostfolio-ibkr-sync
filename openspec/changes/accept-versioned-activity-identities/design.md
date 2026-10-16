# Design

## Context

`ghost_get_existing_orders` reads legacy identities. `accepted_import_subset` proves creations, but `ghost_import_activities` treats a proven short response as clean.

## Goals / Non-Goals

**Goals:** Add a strict dual reader, shared ADR, exact acceptance and safe rollback.

**Non-Goals:** Generate v2 comments, migrate activities, split dividend actions, change financial values, or edit sibling repositories.

## Decisions

1. Add pure parsing beside `ghost_get_existing_orders`. Accept legacy and exact v2 forms; reserved malformed/future prefixes fail closed. The ADR cites DEGIRO's `broker_identity` validation and Bourse Direct's versioned marker without sharing broker code.
2. Keep both conversion functions unchanged. `dividend_dedup_decision` compares source actions with v2 rows: complete coverage skips; partial coverage rejects. Thus rc.4 cannot create a mixed legacy row after rc.5.
3. Reuse `accepted_import_subset` for submitted-minus-created identities. `ghost_import_activities` warns and returns `ok=False`, without retry or an unknown-outcome fence. Holdings, sequencing, cash independence and notifications remain.

## Risks / Trade-offs

- **One-account evidence** → Account remains in every key; cross-account action uniqueness is unnecessary.
- **Unexpected characters** → Reject them; observed comments are 36 characters or fewer versus Ghostfolio's 2,000 limit.
- **Rollback** → Release rc.4 before the separate rc.5 writer/migration change.

## Migration Plan

Release rc.4 after offline checks and separate GO. Restore rc.3 if needed. After rc.5 writes, use rc.4 or newer.
