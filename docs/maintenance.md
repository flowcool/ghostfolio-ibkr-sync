# Maintenance

Use these tools for historical maintenance. They are outside the connector image.
Cleanup needs separate authorization.
Simulation, matching amounts and review approval do not authorize it.

| Need | Procedure | Write boundary |
| --- | --- | --- |
| Inspect or resume interrupted pair cleanup | [Pair cleanup](maintenance/cleanup.md) | Separate operation; not qualified for v2 history |
| Preview and submit missing dividend actions after partial acceptance | [Dividend recovery](maintenance/missing-dividend-recovery.md) | Offline preview first; separately approved submission |
| Convert exact historical references or reverse journal-owned changes | [Identity migration](maintenance/identity-migration.md) | Shared-file approval, exact subset proof and separate operation |
| Review one-to-one financial corrections | [Activity review](activity-review.md) | Exact-image qualification and explicit approval |
| Recover corporate evidence or understand a trade hold | [Corporate actions](corporate-actions.md) | Evidence recovery does not authorize financial treatment |

Before any write, verify the target, backup, qualified inputs and exclusive access.
Define the expected readback, stop conditions and recovery path.
Keep evidence and journals private.
An uncertain write can complete later. Old or absent data does not prove that resending is safe.

On failure, stop dependent writes. Follow the operation's recovery procedure.
Do not bypass a block by deleting journals, resetting state or starting a new journal.
Image rollback does not undo financial writes.
Pair cleanup is not qualified for v2 history.

[Older cleanup links](cleanup.md) still lead to their operation sections.
