# Design

## Context

`process_review` currently unpacks `QUALIFIED_EXECUTION` as `(5, 28.0)`.
The count check retains otherwise valid approvals after five PUTs.
`recovery_read` already verifies each request before the next PUT.

## Goals / Non-Goals

Apply every eligible correction in one run. Keep sequential dispatch and D=28 s.
Do not change profile limits, source parsing, financial readback or journal v3.

## Decisions

Represent `QUALIFIED_EXECUTION` as delay seconds or `None` for unavailable
qualification. Remove the count check. Keep oldest-first selection, fresh
context checks, `recovery_read`, durable intent and the financial run-stop flag.
Simulation previews every eligible correction without consuming approval.
Queue position remains an ordering hint. Remaining eligible runs is one for
currently eligible work; it cannot predict recovery after an uncertain request.

No ENV setting controls the delay or a count. Add no run duration bound.
Existing process/request timeouts remain. Large backlogs therefore take longer.
Operators must allow at least `(corrections - 1) * 28` seconds plus source,
request and readback time. Existing exclusive-writer rules still apply.

Reuse the delayed `ReviewServer` for chains of 1, 5 and 32 corrections. Inject
failure at the first, middle and last position. Test restart recovery without
resend and global stop across two accounts.

## Risks / Trade-offs

A long run can overlap an external schedule. Keep the existing exclusive-writer
requirement; do not introduce a hidden count or time cutoff.

Rollback stops writers, preserves review/state/journal, forces simulation and
restores the prior qualified image. Code rollback does not reverse writes.
The RC gate must prove both labs on the exact digest, at least 30 corrections
per chain, request gaps at least 28 s, background completion within 28/1.5 s,
exact readback and stop without resend. Floating Ghostfolio metadata is recorded.
