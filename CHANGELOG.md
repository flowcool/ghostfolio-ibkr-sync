# Changelog

## Unreleased — v3.0.0-rc.2

- **Breaking:** absent or blank `DRY_RUN` now simulates. Every such invocation
  logs WARNING `DRY_RUN not set: simulation, nothing written`, including
  configuration failures. After trimming spaces and ignoring case,
  `1/true/yes/on` simulates; only `0/false/no/off` requests live writes.
- Invalid `DRY_RUN` exits 1 before any HTTP call. Only configured Apprise
  Failure delivery may follow rejection. No IBKR/Ghostfolio HTTP calls or
  financial writes occur.
- Simulation keeps login, reads and preview, without activity, cash or platform
  writes. Failed simulations send one configured Failure notification.
  Successful default/blank/truthy simulations send nothing, including expiry-only
  reminders and previews. Failure with an expiry reminder or forced preview
  uses one summary. Without configured Apprise, nothing is sent. Delivery does
  not change exit status. Explicit false `DRY_RUN` retains TZ-forced preview
  notifications, even on success.
- Docker and Compose examples select simulation explicitly. Review the preview,
  then set `DRY_RUN=false` to permit writes. Keep valid `TZ` and all other safety
  guards. Removing `DRY_RUN` no longer enables writes.
- For rollback, restore the recorded image digest with retained ENV and mounts.
  This restores runtime only; it does not undo activities, cash or platform
  writes. Older images can write with absent `DRY_RUN`; use `DRY_RUN=true` for
  rollback previews. See [the 3.0 upgrade guide](docs/upgrading-to-3.0.md).
