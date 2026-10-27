# Design

## Context

See proposal.md for motivation. `release_metadata()` already validates release tags. The workflow builds and checks each native image, then verifies published configuration digests. `promote()` copies the qualified index. It currently requires the full RC tag in OCI version labels. `recover_release_image.py` reuses that verifier.

## Goals / Non-Goals

Provide immutable software identity through build, startup and promotion. Preserve the existing publication and financial boundaries. Do not infer a mutable publication channel inside the container.

## Decisions

1. Extend validated release metadata with a separate target-version output. Preserve the existing registry-version output. Use the release tag parser to derive `X.Y.Z`; reject missing or malformed source commits before building. This avoids manual version files and runtime API dependencies.
2. Pass target version and full commit as `APP_VERSION` and `APP_REVISION` build arguments. Persist both in Dockerfile. Use the same values for OCI labels and both workflow build calls. Retain RC registry tags and cosign identities.
3. Update entrypoint and application startup together. Use the existing shell output and application logger. Display twelve commit characters; retain the full value in image configuration. Keep `dev`/`unknown` fallbacks for local images.
4. Reuse `check_container_runtime.sh` and native configuration verification to reject inconsistent release images. Reuse `promote()` for normal promotion and recovery. Accept two complete forms: target version plus exact runtime/OCI revision, or original legacy RC version metadata without the new revision field. Verify the legacy APP_VERSION and OCI label against the selected exact RC. Reject mixed forms. Retain qualification, signature and digest checks before every write.

## Risks / Trade-offs

- An RC reports the target version → document registry tags as the publication channel; startup makes no stable claim.
- Legacy recovery could weaken identity checks → permit only the exact selected RC legacy form, with existing signed digest and qualification requirements.
- Build metadata can differ between check and publication → use identical inputs and retain configuration-digest comparison.
- Metadata changes alter digests → publish a new candidate and qualify that digest; never rewrite an existing image.

## Migration Plan

After approval, implement and verify offline and isolated native behavior. Use the existing release procedure for a new version and both lab gates. Stable publication requires its own recorded GO. Roll back source with an atomic revert before publication. Published versions remain immutable; deployment rollback uses a recorded previous digest and preserves financial data.
