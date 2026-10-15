# Design

## Context

See proposal.md. Baseline: `dry_run_requested()` accepts only truthy values; all others permit writes. `finalize_run()` reads this helper even after configuration failure.

## Goals / Non-Goals

Use one ENV interpretation for configuration and successful-notification suppression. Keep Ghostfolio write helpers unchanged.

## Decisions

Reuse `.strip().lower()` and the sibling sync rules:

- DEGIRO `degiro_to_ghostfolio.py:1858-1870`, commit `e8908ad`.
- Bourse Direct `boursedirect_to_ghostfolio.py:4180-4182`, commit `3193086`.

Both default to simulation, accept the same eight values and reject invalid values. Bourse Direct's separate offline application commands accept only `0/1`; they are not sync configuration. Blank simulation is the approved IBKR extension.

Make `dry_run_requested()` safe for finalization: only explicit false returns false. Reject invalid input in `load_config()` before any HTTP call. Record configuration failure; only Apprise delivery can follow rejection, with no IBKR/Ghostfolio calls or financial writes. Emit the absent/blank WARNING once in `main()`, before validation, on every invocation. Do not cache it across runs.

Change `finalize_run()` to notify Failure on a failed run, including default, true and invalid `DRY_RUN`. Reuse `load_notification_config()`, `build_failure_summary()` and `send_notification()`; delivery cannot change exit status. Suppress successful simulation, expiry-only and preview notifications. Preserve TZ-forced notifications when explicit false requested live mode. This replaces the raw-value suppression at `ibkr_to_ghostfolio.py:2978` and the Simulation/Notifications requirements. `entrypoint.sh` needs no change. Compose lives in README; no Compose file exists.

## Risks / Trade-offs

Silent stopped imports → per-run WARNING and upgrade note. Existing live-test fixtures → set false explicitly; retain separate default tests.

## Migration Plan

The existing single project release owns archive, main replay, RC publication, authorized real proof/soak and stable publication. No separate release task is needed here. Ship in v3.0.0-rc.2. Document explicit false before enabling writes. Existing explicit production configuration needs no migration. Gate release completion on real proof under a separately validated operation plan; the live soak sets `DRY_RUN=false`. Rollback: prior image digest, retained ENV/mounts; financial records remain. Reverting the proposal commit restores planning only.
