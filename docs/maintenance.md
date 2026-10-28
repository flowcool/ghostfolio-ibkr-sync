# Maintenance

Normal sync is additive. These historical procedures have their own authority;
a simulation, matching amount or review approval alone never permits cleanup.
Use versioned checkout tools. They are outside the connector image.

| Need | Procedure | Write boundary |
| --- | --- | --- |
| Inspect or resume interrupted pair cleanup | [Pair cleanup](maintenance/cleanup.md) | Separate operation; not qualified for v2 history |
| Preview and submit missing dividend actions after partial acceptance | [Dividend recovery](maintenance/missing-dividend-recovery.md) | Offline preview first; separately approved submission |
| Convert exact historical references or reverse journal-owned changes | [Identity migration](maintenance/identity-migration.md) | Shared-file approval, exact subset proof and separate operation |
| Review one-to-one financial corrections | [Activity review](activity-review.md) | Exact-image qualification and explicit approval |
| Recover corporate evidence or understand a trade hold | [Corporate actions](corporate-actions.md) | Evidence recovery does not authorize financial treatment |

Before a mutating operation, verify its exact target, backup, qualified inputs,
writer exclusion, expected readback, stop conditions and recovery path. Keep
private evidence and journals. An uncertain write can complete later; old or
absent data alone does not prove that it is safe to resend.

On failure, stop dependent writes and follow that operation's recovery procedure.
Do not delete journals, reset state or rerun with a new journal to bypass a fence.
Runtime rollback does not undo financial data. Pair cleanup remains unavailable
for v2 activity history until separately qualified.

[Older cleanup links](cleanup.md) still lead to their operation sections.
