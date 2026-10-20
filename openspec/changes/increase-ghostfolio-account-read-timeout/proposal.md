## Why
Ghostfolio account reads can exceed 30 seconds on a loaded server. The operator requested more time and permits a later replay.

## What Changes
Allow 120 seconds for account list and account detail GET requests. Keep existing write timeouts and failure handling.

## Scope
| Flex records | Scope |
| --- | --- |
| All record types | Out of scope; no Flex parsing or selection change |

## Non-goals
No retry, new configuration, financial behavior change, image replacement or deployment. Preserve the published candidate. A new candidate needs publication and both lab checks before production replay.

## Impact
Ghostfolio account reads and their offline request tests. Shared Ghostfolio helpers require separate downstream propagation; DEGIRO remains pinned.
