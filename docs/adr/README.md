# Architecture decision records

Records 0001-0007 were recorded on 2026-10-12. These retrospective records describe
existing behavior, not new financial policies or approval to redesign it. The date is the recording
date, not a claim about when the original choice was made. Code and the linked
operational guides remain authoritative; revisit these records when behavior changes. Record 0008 (2026-10-14) documents
the 3.0 prerequisite policy.

| Record | Decision |
| --- | --- |
| [0001](0001-single-file-runtime.md) | Typed modular Python runtime (superseded decision: single file) |
| [0002](0002-comment-and-proximity-deduplication.md) | Comment identities and dividend proximity matching |
| [0003](0003-additive-imports.md) | Additive imports and exact reviewed-update exception |
| [0004](0004-independent-cash-update.md) | Cash updates independent of import success |
| [0005](0005-flex-window-and-corporate-actions.md) | 365-day history and no corporate-action processing |
| [0006](0006-latest-follows-main.md) | Latest image follows stable releases; release-candidate channel |
| [0007](0007-pinned-degiro-core.md) | Reviewed propagation to the pinned DEGIRO core |
| [0008](0008-fail-account-on-missing-flex-prerequisite.md) | Missing Flex prerequisites fail the account; currency is checked after imports |

[Back to development guidance](../../README.md#development).
