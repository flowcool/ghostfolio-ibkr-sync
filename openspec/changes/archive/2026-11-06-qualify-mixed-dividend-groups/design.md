## Context

`refresh_proposals` blocks a group when some expected v2 identities exist and others do not. `source_events` already validates and converts cash actions separately. The three observed shapes differ in action order and accrual revisions. Each has one legacy row with exact quantity and gross representation; its fee needs review.

## Decisions

Add a pure qualification helper in `activity_review.py`. Limit this path to two source actions, exactly one covered action and exactly one missing action. Require one valid covered destination in the mapped account. Validate the whole relevant destination inventory before choosing the legacy row. Reject duplicate identities, extra candidates, manual overlaps and malformed context.

Use `values_of`, `effective_currency`, `numeric_evidence` and `date_eligible`. Require exact quantity and currency, the same payment day, and either exact source gross or the converter's proven numeric representation. Require explicit withholding and associated accrual evidence. Do not use profile amount tolerance for allocation.

Only the missing action's proven legacy pair bypasses partial coverage. Its proposal changes comment and reviewed fee. Preserve the stored quantity, unit price, timestamp and destination ID. Other proposals remain blocked until fresh readback proves full coverage. Bind consent to the full group evidence and destination inventory. Revalidate before dispatch through the existing refresh. Keep manual/profile authority, durable intent, exact readback, pacing and uncertainty handling unchanged.

## Acceptance and rollback

Run synthetic regressions for the three shapes and ambiguous variants. Run the full offline gate and strict OpenSpec validation. Require CI and Pullfrog head review. Before merge, run the exact PR image in the empty and golden labs when reservations allow it. Retain proof and stop owned labs. If priority users hold the labs, hand off the ready PR within the stated wait limit.

Revert the scoped commit before release. A later deployment can retain its previous pinned digest. Code rollback never reverses financial writes.

## Risks and limits

Exact gross alone cannot identify an action. All independent keys and the absence of alternatives are mandatory. Groups with missing withholding, missing accruals or more than two actions remain blocked. Historical migration and recovery submission retain their stricter separate contracts.
