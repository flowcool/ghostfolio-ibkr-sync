## Why

An accepted RC can predate the workflow that preserves its digest. Its original stable-release workflow would rebuild different bytes. Publish the accepted index through an explicit recovery operation.

## What Changes

Add a maintainer-dispatched executor on main. It verifies a prepared stable draft, the highest RC, existing lab qualification, signature, native identities and the recorded previous latest digest. It creates the stable tag and publishes the draft with the repository GITHUB_TOKEN, then copies the exact qualified RC index. Token-originated tag and release writes do not start the old build workflow.

## Capabilities

### Modified Capabilities
- `release-publication`: controlled publication of an older qualified RC.

## Scope

| Flex records | In scope | Out of scope |
| --- | --- | --- |
| None; release operations consume no Flex records | Stable release and image tags | All broker and financial operations |

## Non-goals

No rebuild, production deployment, new lab run, financial write or credential permission change.

## Impact

One recovery workflow, a small executor, reuse of existing publication checks and required operator instructions. No connector runtime change.
