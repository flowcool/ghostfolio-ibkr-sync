# Design

## Context

See proposal.md. Selection skips existing identities before financial comparison. The v2 reader requires a whole-comment match. Migration tools update comments only. Saved Flex inventory SHA-256: `a98b6e9ed5a01e474c233c8d0bbcf945dcc21644318399f8dd22520d25437232`; it does not qualify writes.

## Goals / Non-Goals

Provide reviewed one-to-one replacements. Keep disabled behavior. Reuse no bulk-migration authorization or delete executor.

## Decisions

1. Add a typed functional review module. Reuse `convert_trade_to_activity`, `partition_dividend_actions` and `convert_dividend_actions`. With review enabled, acquire all configured reports once before dispatch. Refuse legacy-global upgrades without sufficient cross-account/historical evidence. Other safe accounts continue.
2. Extend `ghost_get_existing_orders` exact JSON evidence to live review. Compare destination decimals against serialized conversion values without tolerance. Compare full UTC instants; calendar dates control proximity only. Reject unpreservable transport values. Rebuild holdings after confirmed corrections before ordinary selection.
3. Store proposals in `ACTIVITY_REVIEW_FILE`. Reuse package-safe `cleanup_recovery.write_journal` persistence/locking patterns. Derive journal/lock paths. Reject symlinks/input overlap. Compare bytes before dispatch/publication. Preserve literal YAML `yes`. Require editing between runs: advisory locks cannot exclude arbitrary editors.
4. Canonical v2 identity occupies the first line; one blank line separates preserved notes. Extend every reader. Upgrade only exact whole-comment legacy markers. Reject ambiguous markers and aggregates. Retain this reader after disabling review.
5. Adapt `identity_migration.comment_payload` into a full-correction whitelist. Revalidate source, ownership and occupancy. Journal intent before PUT. Dispatch sequentially, verify before advancing, and enforce image-qualified finite run limits/delays. Deferred approvals remain pending.
6. Release a hold when every former candidate belongs to another identified event. Discover new candidates and repeat ordinary selection. Missing/inactive targets remain held.
7. Read immediately, then after waits of 2, 5 and 10 seconds. These provisional bounded waits do not prove settlement. Persist uncertainty. Release only on exact expected-after evidence. Expose no reset, abandon, retry or interactive recovery. Simulation cannot resolve real journals.

## Risks / Trade-offs

No conditional API update: require exclusive destination writes. Qualify preservation, profile/background effects and limits on the exact image. Pinned controller/service/DTO `ef47c0d1b2c48fa4e97fb381561b514e657928cf` support full PUT, not compare-and-swap.

## Migration Plan

Ship disabled. Require isolated acceptance before activation. Halt writers after failure. Disabling retains journals. Reverse only unchanged journal-owned rows under separate authority. Reverting code does not restore financial data.
