## MODIFIED Requirements

### Requirement: Stable release channel

Stable publication SHALL require a published, non-draft, non-prerelease GitHub Release with an exact `vX.Y.Z` tag without leading zeros, on main. It SHALL publish only `X.Y.Z`; only the current stable release SHALL update `latest`. Main, staging, tag pushes, manual builds and schedules SHALL NOT publish. Weekly security checks SHALL remain; fixes SHALL require maintainer-selected releases, with PATCH for compatibility-neutral security fixes.

#### Scenario: Trigger and channel inspection
- **WHEN** `rg -n 'release:|published|prerelease|latest|schedule|push:' .github/workflows/{release-image,docker-publish}.yml` is run after implementation
- **THEN** only release publication is enabled; scheduled checks have no registry writes; no `X.Y` or staging publication exists.

## ADDED Requirements

### Requirement: Release-candidate channel

A published, non-draft GitHub prerelease with an exact tag `vX.Y.Z-rc.N` (`N >= 1`, no leading zeros) on main SHALL publish only `X.Y.Z-rc.N`, with the same checks and single-publication guard as stable. It SHALL NOT create or move `latest`, `X.Y.Z` or `X.Y`. Any other prerelease tag, a stable tag flagged prerelease, drafts and tag pushes SHALL publish nothing.

#### Scenario: RC validation offline
- **WHEN** `.venv/bin/python -m pytest -q tests -k 'release_candidate_metadata'` runs synthetic events for `v3.0.0-rc.1` (prerelease true), `v3.0.0-rc.0`, `v3.0.0-rc.01`, `v3.0.0-beta.1` and a draft
- **THEN** only the first prints the tag and version `3.0.0-rc.1`; the others exit with a refusal.

#### Scenario: Latest untouched
- **WHEN** `rg -n 'rc' .github/workflows/release-image.yml` is run
- **THEN** an explicit condition skips promotion for RC tags.

### Requirement: Stable follows the validated RC

When a tag `vX.Y.Z-rc.N` exists, the stable tag `vX.Y.Z` SHALL be refused unless it points to the same commit as the highest `N`. With no RC for `X.Y.Z`, stable publication SHALL proceed as before. The refusal SHALL name both tags.

#### Scenario: Stable commit check
- **WHEN** `.venv/bin/python -m pytest -q tests -k 'release_candidate_stable_commit'` runs the check with tags `v3.0.0-rc.1` and `v3.0.0-rc.2` and a stable `v3.0.0` on a later commit, then on the `rc.2` commit
- **THEN** the first run fails naming `v3.0.0-rc.2`; the second succeeds.

### Requirement: RC operator guidance

Guidance SHALL describe cutting an RC, validating it in production as a separate operation, and promoting by tagging stable on the same commit. It SHALL state that an RC never moves `latest` and why a consumer's Renovate does not propose `-rc.` tags, with the documentation link. ADR 0006 SHALL record the channel.

#### Scenario: Guidance present
- **WHEN** `rg -n 'rc\.|release candidate' docs/releasing.md docs/adr/0006-latest-follows-main.md README.md .github/BUILD.md` is run
- **THEN** each file explains its part of the channel.
