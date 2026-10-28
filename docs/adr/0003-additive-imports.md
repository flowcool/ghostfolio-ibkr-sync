# Only add activities during synchronization

Date: 2026-10-12. Status: accepted (existing behavior).

Synchronization imports new activities and never deletes existing Ghostfolio
activities. Optional activity review is the exact reviewed-update exception.
With review disabled, stable identities prevent repeats but do not reconcile
later trade corrections, dividend revisions or reversals against stored records.
A non-off reconciliation profile can authorize a bounded one-to-one correction.
Manual decisions remain available. See [ADR 0009](0009-mapping-owned-reconciliation.md).

The guarantee concerns activities, not all writes: the sync updates account cash
and may fill a missing platform ID. The separate
[cleanup tool](../cleanup.md) can modify/delete activities only under its own
operator-authorized maintenance workflow; it is not invoked by the sync.
Sources: `ghost_import_activities` and `ghost_update_cash_balance` in the
[`ghostfolio` module](../../ghostfolio_ibkr_sync/ghostfolio.py), and
[How it works](../../README.md#how-it-works).

An existing activity can be replaced only through the optional persistent review
with unchanged literal `decision: yes` or bounded profile authority, qualified
finite execution limits,
fresh ownership/occupancy checks, durable before/after intent and exact readback.
Preserve ID, account, owner, tags and notes. No fill aggregation, deletion or
repair outside this authority is authorized. Correction failure fences later account writes,
including cash/platform writes. Simulation consumes no approval and resolves no
real journal. See the [workflow](../activity-review.md).
