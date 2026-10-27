# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

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
