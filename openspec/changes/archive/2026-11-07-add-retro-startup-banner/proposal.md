## Why

Docker startup currently prints only a plain release identity. A compact retro banner gives the connector a visible identity.
Florent approved the fixed pyfiglet slant preview and autonomous delivery on 2026-11-07.

## What Changes

Print fixed ASCII art once from the existing Docker entrypoint, before the release identity.
Generate the art with pyfiglet 1.0.4. Do not add a runtime dependency.

| Flex record types considered | In scope | Out of scope |
| --- | --- | --- |
| None: this change does not read Flex reports | Startup text | All broker records and financial behavior |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `release-publication`: Add a fixed retro banner at Docker startup.

## Impact

Only entrypoint output and its offline tests change. Existing version, commit, scheduler, streams and exit codes stay the same.

## Non-goals

No configurable fonts, color, runtime rendering, broker access or financial change.
