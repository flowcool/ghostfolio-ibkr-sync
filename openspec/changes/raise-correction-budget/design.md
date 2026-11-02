# Design

## Runtime contract

Keep `activity_review.QUALIFIED_EXECUTION` as the active image-bound RC permit:
`(destination_image, limit, delay_seconds)`, currently `(image, 5, 15.0)`. Do
not read a budget from ENV. A future lower-only setting may reduce the count,
but it must never increase the count or reduce the qualified delay. Stable
promotion requires the empty and golden burst gate PASS on the exact RC digest.
If that gate measures a longer background chain, revise the permit in a new RC.

The existing `recovery_read` remains the request completion gate. It performs
bounded exact reads and records the raw observed result in the v3 journal. The
next PUT starts only after the current entry is confirmed. The delay starts
between confirmed corrections, before the next fresh evidence check.

When a dispatched correction remains unresolved after bounded recovery, set a
run-stop marker, retain the pending entry and proposal, and break the correction
loop. The application returns failure before ordinary account imports or cash
writes. The account fence remains in `_review_blocked_accounts`. Later approved
proposals retain their approval and hold for a later recovery run. A confirmed
first correction remains confirmed.

The existing outcome path records `correction_uncertain`; finalization sends the
single redacted failure notification. Ordinary budget deferral remains silent.

## Offline destination mock

Extend the synthetic review server with a delayed background queue. A PUT can
hold its derived row update until a configured number of later GETs. Tests then
prove that exact readback settles the first correction before the second PUT.
The mock does not claim Ghostfolio qualification.

## Compatibility and rollback

Journal version 3 and all existing recovery rules remain unchanged. Rollback
stops writers, preserves the review file, state and journal, forces simulation,
and restores the previous qualified image. A code rollback does not reverse a
financial write. An unresolved v3 entry needs a compatible reader and exact
expected-after evidence; no resend is allowed.

## Acceptance evidence

- Five corrections dispatch under one shared budget.
- A delayed background mock proves delay and exact readback ordering.
- The first failed correction sends one PUT, leaves the remaining approvals
  deferred and stops the whole financial run.
- A pending v3 journal recovers mid-burst without resending its first PUT.
- Two configured accounts consume one shared budget.
- Full pytest and `scripts/check.sh` pass.
