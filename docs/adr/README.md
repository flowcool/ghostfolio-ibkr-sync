# Architecture decision records

Records 0001-0007 were recorded on 2026-10-12. They describe existing behavior.
They do not approve a new financial policy or redesign.
The recording date does not identify when the original choice was made.
Code and the linked operational guides remain authoritative.
Revisit these records when behavior changes.
Record 0008 (2026-10-14) documents the 3.0 prerequisite policy.
Record 0009 (2026-10-28) documents mapping-owned reconciliation and profile authority.

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
| [0009](0009-mapping-owned-reconciliation.md) | Mapping-owned bounded reconciliation |

[Back to development guidance](../../README.md#development-and-contribution).
