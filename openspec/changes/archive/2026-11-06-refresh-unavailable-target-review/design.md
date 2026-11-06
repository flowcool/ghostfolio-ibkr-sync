# Design

## Context

`refresh_proposals` retains old payloads when discovery cannot use a former target.
`decode_compact` restores deleted entries from private state with blank consent.
See proposal.md for the display defect and scope.

## Goals / Non-Goals

Keep the stable candidate key and the existing hold rules.
Do not change source conversion, historical maintenance or journal recovery.

## Decisions

Use current `source_events` values for the unavailable-target preview.
Filter them through the existing `REPLACED` field set.
Retain `current values` as target evidence from the earlier proposal.
Clear numeric, date and diagnostic comparisons because they require a current target.
Retain the explicit unavailable status and clear consent and automatic authority.
Bind the refreshed preview to current source evidence and a missing-target marker.
Change the review revision when that binding changes.
Fresh discovery must rebuild target-specific notes, fields and authority on return.

Keeping the old preview would preserve the defect.
Hiding the row would conceal the held source.
A schema change is unnecessary: existing compact fields can show this state.
`encode_review` and `decode_compact` remain unchanged to preserve older generation validation.
Retain rejection bindings, rejected-pair absence rules and all journal evidence.

## Risks / Trade-offs

- A source-only preview cannot prove a safe target update. Keep it non-actionable.
- Last-observed target values can be old. Explain their meaning in the guide.
- Compact deletion can restore evidence. Test deletion before and after publication and restart.

## Validation and rollback

Use synthetic DIVIDEND and trade regressions with no network access.
Check missing source, target return, satisfied and reassigned targets.
Run `scripts/check.sh` and strict OpenSpec validation.
Before merge, qualify the exact PR image in both shared labs.
This preparation stops before that gate.
Rollback: revert the code change. Keep review state and journals intact.
