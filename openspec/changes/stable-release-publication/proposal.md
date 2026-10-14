# Proposal

## Why

Operators need a stable release channel and protection against accidental image replacement. The maintainer approved replacing the main-following policy in [ADR 0006](../../../../docs/adr/0006-latest-follows-main.md).

## What Changes

- **BREAKING:** only a published stable GitHub Release produces `X.Y.Z`; only the current stable release updates `latest`. Stop main, staging, tag-push, manual and weekly publication. Freeze existing `X.Y` and staging aliases.
- Keep weekly security checks without publishing. Ship security fixes through maintainer-selected releases; compatibility-neutral fixes increment PATCH.
- Refuse existing version tags and uncertain registry responses. Validate native amd64/arm64 images and their published configuration digests before manifest promotion.
- Switch at the next stable release. Document digest capture, migration and manual recovery of a failed `latest` promotion.

| Considered input | In scope | Out of scope |
|---|---|---|
| Release/workflow metadata | Publication contract | Deployment |
| IBKR Flex record types: none considered | None | All broker records and conversion |

No Flex report is needed: this change consumes only publication metadata.

## Capabilities

### New Capabilities

- `release-publication`: stable publication, artifact verification and upgrade guidance.

### Modified Capabilities

None. `connector-runtime` remains unchanged.

## Impact

Implementation will change `.github/workflows/docker-publish.yml`, add `.github/workflows/release-image.yml` and adapt sibling release helpers under `scripts/`. Update README, `.github/BUILD.md`, `docs/releasing.md` and ADR 0006 together.

### Source comparison

[Current workflow](../../../../.github/workflows/docker-publish.yml) and [build guarantees](../../../../.github/BUILD.md) publish main/latest, staging and full/minor versions; weekly rebuilds can change mutable tags. [DEGIRO workflow](https://github.com/flowcool/ghostfolio-degiro-sync/blob/main/.github/workflows/release-image.yml) and [guarantees](https://github.com/flowcool/ghostfolio-degiro-sync/blob/main/.github/BUILD.md) provide release-triggered native validation, overwrite guards and stable promotion. Retaining the current channel avoids migration; the approved alternative requires explicit security releases. Both use digest rollback.

## Non-goals

No runtime, dependency ownership, financial-service access, deployment, image/tag deletion or GitHub release-immutability activation. Immutability remains separately owned. This PR contains planning artifacts only.
