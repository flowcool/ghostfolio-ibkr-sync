# Design

## Context

See proposal.md. Baseline: `dry_run_requested()` accepts only truthy values; all others permit writes. `finalize_run()` reads this helper even after configuration failure.

## Goals / Non-Goals

Use one ENV interpretation for configuration and notification suppression. Keep Ghostfolio write helpers unchanged.

## Decisions

Reuse `.strip().lower()` and the sibling sync rules:

- DEGIRO `degiro_to_ghostfolio.py:1858-1870`, commit `e8908ad`.
- Bourse Direct `boursedirect_to_ghostfolio.py:4180-4182`, commit `3193086`.

Both default to simulation, accept the same eight values and reject invalid values. Bourse Direct's separate offline application commands accept only `0/1`; they are not sync configuration. Blank simulation is the approved IBKR extension.

Make `dry_run_requested()` safe for finalization: only explicit false returns false. Validate invalid input in `load_config()` before network calls. Emit the absent/blank WARNING once in `main()`, before validation, on every invocation. Do not cache it across runs.

Reuse `finalize_run()` suppression. Preserve TZ-forced notifications when explicit false requested live mode. `entrypoint.sh` needs no change. Compose lives in README; no Compose file exists.

## Risks / Trade-offs

Silent stopped imports → per-run WARNING and upgrade note. Existing live-test fixtures → set false explicitly; retain separate default tests.

## Migration Plan

Ship in v3.0.0-rc.2. Document explicit false before enabling writes. Existing explicit production configuration needs no migration. Gate release completion on real proof under a separately validated operation plan; the live soak sets `DRY_RUN=false`. Rollback: prior image digest, retained ENV/mounts; financial records remain. Reverting the proposal commit restores planning only.
