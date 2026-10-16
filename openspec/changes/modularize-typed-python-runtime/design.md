# Design

## Context

See `proposal.md`. Docker is the supported interface. Complete `dividend-proximity-amount-evidence`, then the separate Python 3.12 → 3.14 migration, before task 1.1. This refactor ships in the v3.0.0 RC series; restart the 10-day production soak on its RC.

## Goals / Non-Goals

Small interfaces, strict application types, unchanged financial behavior. No compatibility launcher, PyPI release, Python migration here, or sibling edits.

## Decisions

1. Create `models`, `config`, `ibkr`, `ghostfolio`, `sync`, `diagnostics`, and `app` modules plus `__main__`. `app.run` reuses `run_sync`, `process_account`, and `finalize_run`. Shared immutable models prevent adapter import cycles.
2. `config.load` reuses `load_config` and `load_notification_config` validation. Use frozen dataclasses for settings and financial records; typed dictionaries for external JSON. This preserves explicit validation without Pydantic.
3. `ibkr` reuses `_ibkr_get`, `fetch_flex_report`, and `parse_*`. `ghostfolio` reuses `ghost_*` reads/writes and existing HTTP fakes. `sync` reuses `convert_*`, filtering, deduplication, and account decisions. `diagnostics` reuses `historical_dividend_comparison`, classification, formatting, and logging.
4. Configure Ruff and strict application mypy in `pyproject.toml`. Pin Ruff, mypy, types-requests, and types-PyYAML in `requirements-dev.txt`. Tests retain relaxed typing. Local checks and CI run Ruff, mypy, and pytest through `scripts/check.sh`.
5. Keep the old runtime executable during extraction. Task 4.2 switches Dockerfile and entrypoint.sh, installs with `pip install --no-deps .`, then deletes `ibkr_to_ghostfolio.py` without a launcher. `_notify_worker_argv` returns `[sys.executable, "-I", "-m", "ghostfolio_ibkr_sync", "--notify-worker"]`; remove the `__file__` spawn guard in `send_notification`. Installation makes isolated module lookup work. `cleanup_dividends.py`, `cleanup_duplicates.py`, and `cleanup_recovery.py` import `activity_is_active` from the package.
6. Adapt `scripts/check_container_runtime.sh`: replace old-path ownership and mounted-probe assumptions; retain hardened one-off/scheduled checks. With no network or credentials, spawn the installed worker through its production argv, feed malformed input, and require exit 10. This proves worker dispatch without synchronization or delivery.
7. Task 4.3 updates README, AGENTS.md, CONTRIBUTING.md, OpenSpec context, Python conventions, ADR 0001 (superseded), and upgrading-to-3.0.md. Document `docker exec <container> python -m ghostfolio_ibkr_sync`. Update ADR 0007: DEGIRO retains the last single-file pin; future propagation requires changing its hardcoded `check_core` source_path. No DEGIRO edits.

## Risks / Verification

Behavior drift: every task runs `scripts/check.sh` and its targeted check. Moved tests change only imports and patch targets; assertions stay identical. Add separate tests for changed launch contracts. Validate isolated containers before RC publication. Rollback: prior RC image digest.
