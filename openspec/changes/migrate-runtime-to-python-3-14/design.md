# Design

## Context

See `proposal.md`. The current Docker tag, seven workflow pins, two Renovate ranges, and public guidance name Python 3.12. The 3.14 image remains Debian Trixie. Current dependency pins resolve binary artifacts for Python 3.14 on amd64 and arm64.

## Goals / Non-Goals

**Goals:** Make Python 3.14 the proven image and CI runtime before `modularize-typed-python-runtime` starts.

**Non-Goals:** Change connector logic, dependency versions, Python 3.12 behavior, release publication, or deployment.

## Decisions

1. Keep the existing `python:<minor>-slim@sha256:<digest>` mechanism. Change the minor to 3.14 and resolve the current multi-architecture digest during implementation. An exact patch tag would prevent the existing Renovate digest-update path from carrying patch releases.
2. Change every `actions/setup-python` pin in `docker-publish.yml`, `release-image.yml`, `dependency-release-watch.yml`, and `upstream-release-watch.yml`. A dual-version matrix is excluded because only 3.14 is supported by CI after this migration.
3. Reuse both `renovate.json` `allowedVersions` rules. Move their bounds to 3.14 and retain manual review, release age, and digest pinning.
4. Keep `requirements.txt` and `requirements-dev.txt` unchanged. PyPI metadata and cross-platform binary resolution already cover 3.14, so dependency updates would hide the cause of a regression.
5. Extend `test_python_base_keeps_tag_and_pins_digest` and add focused assertions for workflows, Renovate, and guidance. Reuse `scripts/check_container_runtime.sh` to assert `sys.version_info[:2] == (3, 14)` inside the built image.
6. Reuse the existing native amd64/arm64 workflow jobs, offline pytest suite, dependency audit, image scans, and isolated runtime checks. Update README, CONTRIBUTING, and `docs/upstreams.md` where they state the current version.

## Risks / Trade-offs

- A valid tag with the wrong digest could run another Python version. The in-image assertion detects it.
- Package metadata proves installation, not behavior. The full offline suite and native container checks provide behavioral evidence.

## Migration Plan

Ship this change in the v3.0.0 RC series before the modular refactor. Roll back by restoring the prior image digest and configuration.
