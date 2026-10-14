## Why

Operators cannot test a release in production before `:latest` moves. `release-image.yml` rejects every prerelease (`scripts/release_image.py:16-19`), so the first public image of a major version is also the stable one.

## What changes

- A published GitHub prerelease tagged `vX.Y.Z-rc.N` publishes only `:X.Y.Z-rc.N`, multi-arch, with the same checks as stable. It never moves `:latest`, `:X.Y.Z` or `:X.Y`.
- A stable `vX.Y.Z` is refused unless it points to the same commit as the highest existing `vX.Y.Z-rc.N`.
- Docs: ADR 0006, releasing guide, README and BUILD notes describe the channel.

## Scope

| Item | Decision |
|---|---|
| Release workflow and its preflight script | In scope |
| ADR 0006, releasing guide, README, BUILD notes | In scope |
| Flex record types, import, cash, Ghostfolio calls | Out of scope: no connector change |

## Non-goals

- Deploying an RC to production: a separate operation with its own validated plan.
- Sibling connector repositories: follow-up items in their own projects.
