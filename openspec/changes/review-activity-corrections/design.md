# Design

## Context

See proposal.md. The current selector skips existing identities before financial comparison. The v2 reader requires a whole-comment match. Existing migration tools update comments only.

The saved Flex inventory has SHA-256 `a98b6e9ed5a01e474c233c8d0bbcf945dcc21644318399f8dd22520d25437232`. Its structure supports the proposal table. It does not qualify corrected live writes.

## Goals / Non-Goals

Provide reviewed one-to-one replacements. Keep disabled behavior. Do not reuse the bulk migration authorization or delete executor.

## Decisions

1. Add a typed functional review module. Reuse `convert_trade_to_activity`, `partition_dividend_actions` and `convert_dividend_actions`. Build complete source events before deduplication. Do not use rounded report text as write evidence.
2. Extend `ghost_get_existing_orders` exact evidence. Reuse active-account/profile checks. Compare source payloads with original JSON decimals. Use UTC calendar dates for proximity, as current import matching does. Recompute positions after verified corrections before ordinary selection; never add a corrected BUY twice.
3. Store keyed proposals in `ACTIVITY_REVIEW_FILE`. Reuse `cleanup_recovery.write_journal` persistence and locking patterns in package-safe code. Derive journal/lock paths beside the file. Reject symlinks and input overlap. Compare file bytes before publishing to preserve concurrent edits. A standalone `yes` scalar must survive YAML boolean resolution.
4. Keep the canonical v2 identity on the first comment line. Append preserved notes after one blank line. Extend all readers to extract only that first-line identity. Replace exact recognized legacy markers; do not infer references from prose. Earlier strict readers cannot read these extended comments.
5. Adapt `identity_migration.comment_payload` into a separate full-correction whitelist. Reuse authenticated request conventions. Revalidate ownership, source, destination and identity occupancy before PUT. Journal pending intent first. Never echo a GET into PUT or retry an uncertain PUT.
6. Poll reads immediately, then after 2, 5 and 10 seconds. This provisional recovery budget is bounded and testable; it is not proof of server settlement. Preserve unresolved state across runs.

## Risks / Trade-offs

- No conditional API update → local locking plus last-moment readback cannot prevent an external writer race. Require exclusive writes during correction dispatch.
- Profile, draft-tag or background changes → qualify the exact destination image before enablement. The pinned controller/service/DTO at `ef47c0d1b2c48fa4e97fb381561b514e657928cf` support full PUT, not transactional compare-and-swap.

## Migration Plan

Ship disabled. Require isolated acceptance before activation. Halt with simulation after failure. Disabling review stops new corrections but retains journals. Reverse only unchanged journal-owned rows under separate authority. Retain the new reader after notes-bearing references exist; reverting code does not restore data.
