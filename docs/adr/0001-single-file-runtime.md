# Keep the sync runtime in one Python file

Date: 2026-10-12. Status: superseded.

The typed modular runtime of the v3.0.0 release candidates replaces this decision.

## Original decision

The synchronization pipeline and its Ghostfolio helpers lived in one file,
`ibkr_to_ghostfolio.py`, in a functional style without a package. This kept the
runtime small and gave [DEGIRO's core projection](0007-pinned-degiro-core.md) an
identifiable source boundary. A broad extraction was to be reviewed explicitly,
including downstream propagation.

## Why it is superseded

The reviewed extraction happened as a pure refactor with unchanged financial
behavior. The runtime is now the installed package
[`ghostfolio_ibkr_sync`](../../ghostfolio_ibkr_sync/__main__.py):

- One module per concern: `models`, `config`, `ibkr`, `ghostfolio`, `sync`,
  `diagnostics`, `outcome`, `notify` and `app`, plus `__main__`.
- Strict application typing (Ruff and mypy, run by `scripts/check.sh`). Tests keep
  relaxed typing.
- Still functional Python; frozen dataclasses model settings and financial records.
- Docker is the only supported interface. The image installs the package and runs
  `python -m ghostfolio_ibkr_sync`. The old `ibkr_to_ghostfolio.py` file is deleted
  and no compatibility launcher exists.
- The runtime dependencies stay `requests` and `pyyaml`. Apprise is still imported
  only by the notification worker, now started as
  `python -I -m ghostfolio_ibkr_sync --notify-worker`.
- Operator cleanup tools stay separate scripts that import from the package.

## Consequences

DEGIRO keeps its pin on the last single-file source. See
[0007](0007-pinned-degiro-core.md) for the propagation rule. See
[Development](../../README.md#development).
