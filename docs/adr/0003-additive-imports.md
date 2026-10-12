# Only add activities during synchronization

Date: 2026-10-12. Status: accepted (existing behavior).

Synchronization imports new activities; it never edits or deletes existing
Ghostfolio activities. Stable identities prevent repeats but do not reconcile
later trade corrections, dividend revisions or reversals against stored records.
This keeps automatic synchronization from rewriting the operator's history;
corrections need explicit manual review rather than an automatic repair policy.

The guarantee concerns activities, not all writes: the sync updates account cash
and may fill a missing platform ID. The separate
[cleanup tool](../cleanup.md) can modify/delete activities only under its own
operator-authorized maintenance workflow; it is not invoked by the sync.
Sources: `ghost_import_activities` and `ghost_update_cash_balance` in the
[runtime](../../ibkr_to_ghostfolio.py), and
[How it works](../../README.md#how-it-works).
