# Architecture decision records

Recorded on 2026-10-12. These retrospective records describe existing behavior,
not new financial policies or approval to redesign it. The date is the recording
date, not a claim about when the original choice was made. Code and the linked
operational guides remain authoritative; revisit these records when behavior changes.

| Record | Existing decision |
| --- | --- |
| [0001](0001-single-file-runtime.md) | Single-file Python runtime |
| [0002](0002-comment-and-proximity-deduplication.md) | Comment identities and dividend proximity matching |
| [0003](0003-additive-imports.md) | Additive activity imports only |
| [0004](0004-independent-cash-update.md) | Cash updates independent of import success |
| [0005](0005-flex-window-and-corporate-actions.md) | 365-day history and no corporate-action processing |
| [0006](0006-latest-follows-main.md) | Latest image follows stable releases; release-candidate channel |
| [0007](0007-pinned-degiro-core.md) | Reviewed propagation to the pinned DEGIRO core |

[Back to development guidance](../../README.md#development).
