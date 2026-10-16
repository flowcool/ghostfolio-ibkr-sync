# Design

## Context

See `proposal.md`. The runtime exposes Docker/ENV behavior, not a Python library interface. Its existing offline suite characterizes the financial behavior. Python 3.14 and `dividend-proximity-amount-evidence` must reach the RC first.

## Goals / Non-Goals

**Goals:** small module interfaces, strict application types, unchanged observable behavior, and one identical local/CI check.

**Non-Goals:** preserve the internal script path, redesign financial logic, package code for PyPI, or change sibling repositories.

## Decisions

1. Create `ghostfolio_ibkr_sync/` with `models`, `config`, `ibkr`, `ghostfolio`, `sync`, `diagnostics`, and `app` modules plus `__main__`. `app.run` is the outer interface. It reuses `run_sync`, `process_account`, and `finalize_run` behavior.
2. `config.load` returns an immutable `Settings` dataclass, reusing `load_config` and `load_notification_config` validation. Internal financial records use frozen dataclasses. External JSON payloads use typed dictionaries. This avoids Pydantic and preserves explicit validation.
3. `ibkr` owns `_ibkr_get`, `fetch_flex_report`, and all `parse_*` behavior. `ghostfolio` owns the existing `ghost_*` reads and writes. Each exposes a small client interface; tests inject their current HTTP fakes.
4. `sync` owns `convert_*`, filtering, deduplication, and account decisions as functions. `diagnostics` owns `historical_dividend_comparison`, classification, formatting, and logging. Tests move to these interfaces rather than testing temporary forwarding layers.
5. Configure Ruff and mypy in `pyproject.toml`; pin them in `requirements-dev.txt`. Strict mypy covers the application package, while tests use relaxed types. A repository check script runs Ruff, mypy, and pytest; CI calls that script.
6. Move one module at a time. Keep the current runtime executable until `app` owns orchestration, then update Docker, CRON, tests, and documentation to `python -m ghostfolio_ibkr_sync` and delete the old file.

## Risks / Trade-offs

- **Behavior drift during movement** → require focused characterization tests and the full existing suite.
- **Import cycles** → shared immutable models depend on no adapter; `app` alone composes modules.
- **Large review surface** → one module and its tests per task; no mixed financial change.
- **RC regression** → validate the image in DRY_RUN and roll back to the prior image digest.

## Migration Plan

Complete the dividend change, then Python 3.14. Extract modules in dependency order, switch the entry point last, run the common check and container checks, and publish only through the existing RC release path.
