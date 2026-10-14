# Design

## Context

See proposal.md for the approved channel decision. Connector specifications do not govern publication; ADR 0006 currently accepts main-following latest.

## Goals / Non-Goals

Deliver the release contract without touching runtime helpers or financial services. Preserve existing CI security gates, SBOM and provenance. GitHub release immutability and dependency ownership remain separate.

## Decisions

Reuse DEGIRO `release-image.yml`: serialized preflight, native runner matrix, digest publication and manifest verification. Adapt `release_metadata`, `registry_version_absent` and `registry_login` into `scripts/release_image.py`; reject drafts/prereleases rather than supporting sibling prereleases. Keep current main-ancestry and exact-tag checks.

Strip `v` for GHCR `X.Y.Z`; retain `v` in Git.

Adapt DEGIRO `verify` and `native_manifest_digest` into `scripts/verify_release_image.py`. Reuse IBKR `scripts/check_container_runtime.sh` for isolated checks. Retain existing dependency-audit/container gates and weekly no-cache checks in `docker-publish.yml`, removing its publication job. Recheck the current stable GitHub release immediately before latest promotion.

Alternative: retaining main publication preserves automatic refresh but contradicts the approved stable channel. Rebuilding existing versions contradicts single publication. Use a new patch release for compatibility-neutral fixes.

## Risks / Trade-offs

Security refresh waits for a release → keep weekly checks and document maintainer action. Partial publication can leave untagged digests or a version without latest → preserve evidence, refuse rebuilds, document explicit digest promotion. Registry guards prevent workflow overwrites, not administrator writes → continue exact digest selection.

## Migration Plan

Update README, BUILD, releasing guidance and ADR 0006 in the delivery PR. Capture the installed digest; switch publication at the next operator-approved stable release. Keep old aliases untouched. Revert workflow/doc changes through a PR to restore the prior channel; operational rollback selects the saved digest and never restores financial data.
