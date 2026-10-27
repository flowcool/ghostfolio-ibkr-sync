# release-publication Specification

## Purpose

Define stable image publication and verifiable artifact selection without changing connector behavior.

## Requirements

### Requirement: Stable release channel

Stable publication SHALL require a published, non-draft, non-prerelease GitHub Release with an exact `vX.Y.Z` tag without leading zeros, on main. It SHALL publish only `X.Y.Z`; only the current stable release SHALL update `latest`. Main, staging, tag pushes, manual builds and schedules SHALL NOT publish. Weekly security checks SHALL remain; fixes SHALL require maintainer-selected releases, with PATCH for compatibility-neutral security fixes.

#### Scenario: Trigger and channel inspection
- **WHEN** `rg -n 'release:|published|prerelease|latest|schedule|push:' .github/workflows/{release-image,docker-publish}.yml` is run after implementation
- **THEN** only release publication is enabled; scheduled checks have no registry writes; no `X.Y` or staging publication exists.

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

### Requirement: Release-candidate channel

A published, non-draft GitHub prerelease with an exact tag `vX.Y.Z-rc.N` (`N >= 1`, no leading zeros) on main SHALL publish only `X.Y.Z-rc.N`, with the same checks and single-publication guard as stable. It SHALL NOT create or move `latest`, `X.Y.Z` or `X.Y`. Any other prerelease tag, a stable tag flagged prerelease, drafts and tag pushes SHALL publish nothing.

#### Scenario: RC validation offline
- **WHEN** `.venv/bin/python -m pytest -q tests -k 'release_candidate_metadata'` runs synthetic events for `v3.0.0-rc.1` (prerelease true), `v3.0.0-rc.0`, `v3.0.0-rc.01`, `v3.0.0-beta.1` and a draft
- **THEN** only the first prints the tag and version `3.0.0-rc.1`; the others exit with a refusal.

#### Scenario: Latest untouched
- **WHEN** `rg -n 'rc' .github/workflows/release-image.yml` is run
- **THEN** an explicit condition skips promotion for RC tags.

### Requirement: Stable follows the validated RC

When a tag `vX.Y.Z-rc.N` exists, stable `vX.Y.Z` SHALL use the same commit as the highest `N` and SHALL copy that RC image index without rebuilding. The resulting stable and latest digests SHALL equal the qualified RC digest. Missing or mismatched qualification evidence SHALL refuse publication. With no RC for `X.Y.Z`, stable publication SHALL proceed as before. The commit refusal SHALL name both tags.

#### Scenario: Stable commit check
- **WHEN** `.venv/bin/python -m pytest -q tests -k 'release_candidate_stable_commit'` runs the existing source checks
- **THEN** a stable commit different from the highest RC is refused.

#### Scenario: Qualified index inspection
- **WHEN** `gh run view <stable-release-run-id> --log` inspects an authorized stable promotion
- **THEN** the run copies one qualified RC index without a native build and verifies equal RC, stable and latest digests, or refuses before publication when a prerequisite is missing.

### Requirement: RC operator guidance

Guidance SHALL describe cutting an RC, validating it in production as a separate operation, and promoting by tagging stable on the same commit. It SHALL state that an RC never moves `latest` and why a consumer's Renovate does not propose `-rc.` tags, with the documentation link. ADR 0006 SHALL record the channel.

#### Scenario: Guidance present
- **WHEN** `rg -n 'rc\.|release candidate' docs/releasing.md docs/adr/0006-latest-follows-main.md README.md .github/BUILD.md` is run
- **THEN** each file explains its part of the channel.

### Requirement: Qualified promotion evidence

Stable promotion from an RC SHALL require one maintainer-published `lab-qualification.json` asset on that published prerelease. It SHALL bind the repository, source commit, RC tag, index digest, both native manifest digests and successful stopped empty-install and golden-upgrade lab results with SHA-256 evidence hashes. The workflow SHALL verify the RC signature for its release workflow identity and source labels for both native images before publication. Qualification records SHALL contain no credentials or private host paths. They attest maintainer acceptance; they do not replace private runner evidence.

For new images, promotion SHALL verify that runtime version and OCI version equal the target version derived from the selected RC, and that runtime revision and OCI revision equal the qualified full commit. Both architectures SHALL agree. Legacy recovery SHALL accept the original exact RC version metadata of an older qualified image. It SHALL reject mixed, missing or contradictory metadata for either supported identity form. Signature, qualification, source, architecture and digest checks SHALL remain mandatory. Promotion SHALL preserve image bytes and the qualified digest.

#### Scenario: Qualification refusal
- **WHEN** `python3 scripts/promote_release_image.py --plan` reads an otherwise valid stable event whose highest RC lacks the qualification asset
- **THEN** it exits with refusal and creates no registry tag.

#### Scenario: Identity compatibility and refusal
- **WHEN** `.venv/bin/python -m pytest -q tests/test_release_image.py -k release_identity` runs isolated image configuration cases
- **THEN** the complete new identity and original legacy identity pass, mismatched versions or commits and mixed metadata fail, and no registry or release write occurs.

### Requirement: Promotion operator instructions

Release instructions SHALL explain the qualification record, target software version, full source commit, candidate registry tags and signature identity, exact digest readback and tagged-workflow limitation. They SHALL explain that an RC can report its target software version before stable publication. They SHALL explain that older images keep their original RC startup text after promotion. User guidance SHALL show the new startup format and state that version metadata is set automatically at build time. Tooling changes SHALL NOT imply permission to publish stable or deploy.

#### Scenario: Maintainer guidance
- **WHEN** `rg -n 'target software version|APP_VERSION|APP_REVISION|tagged commit|same digest|version .*commit' docs/releasing.md docs/configuration.md README.md .github/BUILD.md` runs
- **THEN** the version meaning, automatic metadata, candidate identity, compatibility limits and required proof are explicit.

### Requirement: Legacy qualified RC publication

A maintainer-authorized recovery dispatch on main SHALL permit publication of an older qualified RC without rebuilding. It SHALL require one prepared stable draft with the highest RC source commit, complete release notes, its exact qualified digest and the expected previous latest digest. Before any tag or release write, it SHALL verify qualification, signature, native identities, main ancestry, version absence and unchanged previous stable identity. Existing stable tags, image versions and newer or equal stable releases SHALL refuse this initial-publication path. Tag and release writes SHALL use the repository GITHUB_TOKEN so the older build workflow does not run. The published release SHALL then pass the existing exact-digest promotion checks. Failures after any write attempt SHALL report possible partial state and stop dependent writes without overwrite. Publication SHALL NOT deploy.

#### Scenario: Authorized legacy publication
- **WHEN** `gh run view <recovery-run-id> --log` inspects a maintainer-authorized recovery dispatch
- **THEN** it proves the checks before publication, the actual release response, and stable/latest digests equal to the accepted RC, with no native build.

#### Scenario: Refusal or uncertain write
- **WHEN** `gh run view <recovery-run-id> --log` inspects a recovery with drifted evidence or a failed write
- **THEN** it shows a pre-publication refusal or the exact possible partial phase and performs no dependent publication.

### Requirement: Automatic target software identity

Every new release image SHALL embed the target software version `X.Y.Z` and the full source commit at build time. An accepted `vX.Y.Z-rc.N` or `vX.Y.Z` release tag SHALL produce the same target version `X.Y.Z`. Candidate registry tags and signature identities SHALL retain their full RC identity. OCI version and revision labels SHALL agree with the runtime version and commit. Both native architectures and both checked and published builds SHALL receive the same identity inputs. Invalid release metadata or a missing source commit SHALL block release image publication.

The target version SHALL describe the intended software version. It SHALL NOT certify stable publication. Published images SHALL require no operator-supplied version setting, network lookup or Docker socket to report their identity.

Baseline replaced: release-image.yml passes the full RC tag into APP_VERSION and the OCI version label. Dockerfile preserves APP_VERSION in the runtime image.

#### Scenario: Release metadata derives the software version
- **WHEN** `.venv/bin/python -m pytest -q tests/test_release_image.py -k 'release_candidate_metadata or release_identity'` runs synthetic release inputs
- **THEN** valid stable and RC inputs derive the same target version while preserving distinct publication tags, and malformed inputs or absent source identity refuse publication.

#### Scenario: Native runtime identity agrees with image labels
- **WHEN** `bash scripts/check_container_runtime.sh "$IMAGE"` runs with IMAGE naming an isolated newly built release image
- **THEN** runtime version and full revision match the OCI labels, the expected startup line is present, and missing or contradictory release identity fails the check without financial writes.

### Requirement: Consistent startup software identity

Container startup and every application cycle SHALL report `ghostfolio-ibkr-sync version X.Y.Z — commit <commit-prefix>` for a new release image. The prefix SHALL contain the first twelve hexadecimal characters of the embedded source commit. One-off and CRON modes SHALL report the same identity. Existing severity, streams, scheduler behavior and exit codes SHALL remain unchanged. Local builds without release metadata SHALL report `dev` and `unknown` as appropriate. Startup SHALL make no external request to determine version or publication status.

Baseline replaced: entrypoint.sh and application main currently emit `ghostfolio-ibkr-sync build <APP_VERSION>`. Existing entrypoint tests cover this line.

#### Scenario: Startup identity in both modes
- **WHEN** `.venv/bin/python -m pytest -q tests/test_entrypoint.py tests/test_logging.py -k 'release_identity or operator_action_logging'` runs isolated synthetic startup cases
- **THEN** one-off and scheduled output show the expected version and commit prefix, local fallback remains usable, and existing log framing and scheduler semantics pass.
