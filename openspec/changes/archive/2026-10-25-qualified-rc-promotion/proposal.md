## Why

Stable publication currently rebuilds the RC source with a different version label. The stable digest therefore differs from the image accepted in both labs. Preserve the accepted bytes.

## What Changes

Stable releases with an RC copy the highest RC image index. They require a maintainer-published qualification record, matching source and architectures, and the RC workflow signature. Stable publication without an RC and RC builds keep their existing checks.

## Capabilities

### Modified Capabilities
- `release-publication`: exact digest promotion with fail-closed qualification checks.

## Scope

| Flex records | In scope | Out of scope |
| --- | --- | --- |
| None; release tooling consumes no Flex reports | Image publication | All broker records and financial writes |

## Non-goals

No stable publication, production deployment, broker access, new lab run or runtime behavior change in this implementation.

## Impact

Release workflow, publication helpers and existing release instructions. The related endurance test uses the installed C YAML codec inside that test only, preserving its full scenarios and durable writes. Promotion retains the RC application version and image labels. Existing release tags cannot receive a new workflow retroactively.
