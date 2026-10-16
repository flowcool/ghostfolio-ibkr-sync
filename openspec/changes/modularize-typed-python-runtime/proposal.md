# Proposal

## Why

The 3,187-line runtime combines configuration, external access, financial decisions, reporting, and orchestration. A typed package removes this maintenance constraint.

## What Changes

- Create `ghostfolio_ibkr_sync` modules for configuration, IBKR input, synchronization, Ghostfolio access, diagnostics, and orchestration. Use immutable dataclasses for internal records. Keep calculations as functions; restrict stateful classes to settings and adapters.
- Pin Ruff, mypy, types-requests, and types-PyYAML in `requirements-dev.txt`. Configure strict application typing in `pyproject.toml`; run Ruff, mypy, and pytest through `scripts/check.sh` locally and in CI.
- **BREAKING**: Docker only. Delete `ibkr_to_ghostfolio.py` without a compatibility launcher. Document `docker exec <container> python -m ghostfolio_ibkr_sync`.
- Install the package in the image with `pip install --no-deps .`. Start notifications with `[sys.executable, "-I", "-m", "ghostfolio_ibkr_sync", "--notify-worker"]`; prove worker startup in an isolated container. Adapt `scripts/check_container_runtime.sh`.
- Migrate `cleanup_dividends.py`, `cleanup_duplicates.py`, and `cleanup_recovery.py` to import `activity_is_active` from the package.
- Supersede the single-file/no-types/no-classes policy. Update user documentation, architecture rules, and ADR 0007. DEGIRO stays pinned to the last single-file commit. Future propagation requires a DEGIRO change because its `check_core` hardcodes `source_path`. Do not modify that repository.
- Apply after `dividend-proximity-amount-evidence`, then the separate Python 3.12 → 3.14 migration, before task 1.1. Stay in the v3.0.0 RC series. Restart the 10-day production soak on the resulting RC.

Saved synthetic Flex reports in `tests/test_parsing.py`, `tests/test_orchestration.py`, and `tests/test_auth.py` establish this inventory:

| IBKR Flex record | In scope / out of scope |
|---|---|
| `Trade` except CASH/OPT | In: move unchanged |
| CASH/OPT `Trade` | Out: remain ignored |
| DETAIL `CashTransaction`: Dividends, Payment In Lieu, Withholding Tax | In: move unchanged |
| Other `CashTransaction` types or levels | Out: remain ignored |
| `ChangeInDividendAccrual` | In: move unchanged |
| `CashReportCurrency` with BASE_SUMMARY | In: move unchanged |
| Other `CashReportCurrency` rows | Out: remain ignored |
| `AccountInformation` | In: move unchanged |
| `AssetSummary` | Out: remain ignored |

## Capabilities

No new capability. Modified `connector-runtime`: the "Real read-only acceptance" scenario names the removed launcher; its command becomes `python -m ghostfolio_ibkr_sync`, with every other word unchanged (operator decision 2026-10-16).

## Non-goals

Change financial behavior, ENV, CRON, DRY_RUN, logs, exits, or notifications; migrate Python here; publish to PyPI; change siblings.

## Impact

Runtime, tests, image, CI, and documentation change. Each task requires `scripts/check.sh` plus its targeted check. Moved tests change only imports and patch targets; assertions remain identical. Rollback: prior RC image digest.
