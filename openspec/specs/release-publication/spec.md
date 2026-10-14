# release-publication Specification

## Purpose

Define stable image publication and verifiable artifact selection without changing connector behavior.

## Requirements

### Requirement: Stable release channel

Publication SHALL require a published, non-draft, non-prerelease GitHub Release with an exact `vX.Y.Z` tag without leading zeros, on main. It SHALL publish only `X.Y.Z`; only the current stable release SHALL update `latest`. Main, staging, tag pushes, manual builds and schedules SHALL NOT publish. Weekly security checks SHALL remain; fixes SHALL require maintainer-selected releases, with PATCH for compatibility-neutral security fixes.

#### Scenario: Trigger and channel inspection
- **WHEN** `rg -n 'release:|published|prerelease|latest|schedule|push:' .github/workflows/{release-image,docker-publish}.yml` is run after implementation
- **THEN** only stable release publication is enabled; scheduled checks have no registry writes; no `X.Y` or staging publication exists.

### Requirement: Single publication and verified architectures

Publication SHALL serialize across releases, reject existing `X.Y.Z` manifests and ambiguous registry errors, and recheck absence before creating the manifest. Native amd64/arm64 builds SHALL pass existing security and isolated runtime checks. Published configuration digests SHALL match checked images; the final manifest SHALL contain both architectures before latest promotion. A rerun SHALL refuse an existing version, including partial promotion failures.

#### Scenario: Publication evidence
- **WHEN** `gh run view <release-run-id> --log` inspects an operator-authorized release or rerun
- **THEN** logs prove version absence, both native checks and configuration matches before promotion, or a blocking rejection without overwrite.

### Requirement: Migration and digest recovery

Guidance SHALL announce the next-stable-release cutover, freeze existing minor/staging tags without deleting them, and require recording the installed digest. Failed latest promotion SHALL permit explicit manual promotion of that verified digest only for the current stable release. Digest rollback SHALL preserve configuration and explain that financial records remain. Publication SHALL NOT deploy.

Baseline: README “Docker image” already documents digest rollback and main-following latest; the latter is deliberately replaced.

#### Scenario: Operator guidance
- **WHEN** `rg -n 'stable|digest|frozen|financial|deploy' README.md .github/BUILD.md docs/releasing.md docs/adr/0006-latest-follows-main.md` is run
- **THEN** cutover, frozen aliases, recovery, rollback and deployment boundaries are explicit.
