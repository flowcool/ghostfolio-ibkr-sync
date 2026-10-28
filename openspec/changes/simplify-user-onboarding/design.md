# Design

## Context

See proposal.md. Reuse existing runtime contracts. Change documentation locations only.

## Goals / Non-Goals

**Goals:** Complete installation and safe documentation migration.

**Non-Goals:** Runtime, broker queries, mapping defaults, financial operations, release automation and siblings.

## Decisions

1. Keep `ibkr-sync-individual` and its ENV names. Put two-account configuration in root-level compose.multi-account.yaml. Relative mounts remain identical. Existing multi-account users select this file and retain Compose project identity, ENV, state and service names before recreating services. Explain orphan containers; never recommend blind orphan removal.
2. Select an existing shared network through Compose-only `GHOST_DOCKER_NETWORK`, default `ghostfolio`. Set `GHOST_HOST` to an actual service name/alias on that network. Reuse a network managed by Ghostfolio's deployment; manual network attachment may disappear on recreation. Verify resolved network and bind sources with synthetic `config --format json`.
3. Both autonomous examples use a private `.env.run` with container variable names, unquoted values, no CRON and mode 0600. Mount `./state/individual:/state`, matching Compose. State the no-concurrent-run rule. Set DRY_RUN explicitly on commands. Reuse `open_store` permissions and initialization. Simulation can update local evidence; it never writes financially. Edit mapping before changing ownership.
4. Reuse `finalize_run`, `_finalize_notification` and outcome contracts for notification wording. Keep Releases authoritative. Before replacing CHANGELOG, preserve all migration facts in linked guides, including the old live default and explicit simulation for rollback.
5. Add getting-started, corporate-actions and maintenance guides. Preserve old anchors in every restructured guide. Keep required setup warnings beside commands. Map every cleanup section to an operation guide (tasks.md). Link maintainer material from CONTRIBUTING. Keep the investigation historical.
6. Adapt existing Compose and navigation checks, including all changed/new guides. Add no permanent tooling or prose tests. Fetch installation files from the documented checkout; state compatibility with stable 3.3+ rather than claiming that unreleased documentation already exists in an old tag.

## Risks / Trade-offs

- Hidden safety detail → Retain essential warnings and direct links.
- Unsafe maintenance → Keep v2 restrictions beside every recovery entry point.
- Path/service conflicts → Review uses `/review`, never replaces `/state`.
- Unverified vendor interface → Keep observed field names; do not invent UI order.

## Migration Plan

Multi-account users need the explicit file-selection migration above. Git revert restores documentation/examples; it cannot undo container operations or financial data. No services run during this work. One local implementation branch; publication remains separate.
