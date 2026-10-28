# Design

## Context

See proposal.md. The runtime already reports required actions and cycle results. Existing requirements fix content locations in README and CHANGELOG.md. Their complete deltas preserve runtime semantics while permitting linked guides.

## Goals / Non-Goals

**Goals:** One complete first-install path and one source for each operational explanation.

**Non-Goals:** Runtime, broker queries, mapping defaults, financial writes, release automation and sibling changes.

## Decisions

1. Reuse `ibkr-sync-individual` and its ENV names in compose.yaml. Put the existing two-account model in examples/compose.multi-account.yaml. Use `--project-directory .` when invoking that file so mounts still resolve from the installation directory. Renaming variables would add migration cost without user benefit.
2. Reuse `.env.example`, `mapping.yaml.example` and the existing `open_store` directory checks. Correct both Docker commands. Prefer the private ENV file to inline credentials. Explain obtaining files and attaching the connector to the actual Ghostfolio network. Keep hardening and private per-account state.
3. Reuse the current `finalize_run`, `_finalize_notification` and outcome contracts as documentation authorities. Add no preflight mode or summary generator. Keep GitHub Releases authoritative and turn CHANGELOG.md into a stable pointer.
4. Add getting-started, corporate-actions and maintenance guides. Split cleanup into operation guides under docs/maintenance/: cleanup, missing-dividend recovery and identity migration. Keep cleanup.md as an index with every previous anchor. Preserve moved README anchors as short linked sections. Retain essential safety warnings near first-run commands. Link maintainer material from CONTRIBUTING.md. Label the old release-note investigation as historical and link current releasing.md.
5. Adapt existing Compose and navigation checks. Use one-off link validation for moved guides. Add no prose tests or contributor tooling. No full runtime suite is needed for this scope.

## Risks / Trade-offs

- Hidden safety detail → Keep mandatory state, preview, backup and explicit live opt-in in the main path.
- Broken issue/release links → Preserve old anchors and check relative links.
- Misleading first-run success → Explain existing cycle results and that a preview cannot prove server acceptance.
- Unverified IBKR interface order → Reuse observed field names; do not claim current UI order without evidence.

## Migration Plan

Existing deployments need no migration. Validate offline with synthetic ENV, review semantic diffs and preserve line endings. Roll back with a scoped Git revert. No image, data or service rollback is involved. Deliver one PR after approval; no runtime release is required.
