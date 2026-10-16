# Proposal

## Why

The 3,187-line runtime concentrates configuration, external access, financial decisions, reporting, and orchestration in one untyped file. The current release-candidate period is the safest time to replace that obsolete maintenance constraint while DRY_RUN remains the default.

## What Changes

- Replace the runtime with a typed `ghostfolio_ibkr_sync` package containing deep modules for configuration, IBKR input, synchronization decisions, Ghostfolio access, diagnostics, and orchestration.
- Use immutable standard-library dataclasses for internal records. Keep calculations as functions and restrict stateful classes to settings and external adapters.
- Add one local and CI quality command covering Ruff, strict mypy checks for application code, and pytest. Keep pinned `pip` requirements and configure tools in `pyproject.toml`.
- Supersede the single-file/no-types/no-classes policy and retain its ADR as history.
- **BREAKING**: remove the documented `ibkr_to_ghostfolio.py` path. Use `python -m ghostfolio_ibkr_sync`; keep Docker, ENV, CRON, DRY_RUN, logs, exits, notifications, and financial behavior unchanged.
- Apply this change after `dividend-proximity-amount-evidence` and the separate Python 3.14 migration, within the same RC series.

Saved synthetic Flex reports in `tests/test_parsing.py`, `tests/test_orchestration.py`, and `tests/test_auth.py` establish this record inventory:

| IBKR Flex record | In scope / out of scope |
|---|---|
| `Trade` except CASH/OPT | In — move unchanged |
| CASH/OPT `Trade` | Out — remain ignored |
| DETAIL `CashTransaction`: Dividends, Payment In Lieu, Withholding Tax | In — move unchanged |
| Other `CashTransaction` types or levels | Out — remain ignored |
| `ChangeInDividendAccrual` | In — move unchanged |
| `CashReportCurrency` with BASE_SUMMARY | In — move unchanged |
| Other `CashReportCurrency` rows | Out — remain ignored |
| `AccountInformation` | In — move unchanged |
| `AssetSummary` | Out — remain ignored |

## Capabilities

### New Capabilities

None. This change adds no product behavior.

### Modified Capabilities

None. `skip_specs` is set because this is a refactor, tooling, and documentation change.

## Non-goals

- Change import selection, reconciliation, amounts, diagnostics, or writes.
- Migrate Python, package management, or sibling connectors.
- Add Pydantic, an application framework, or a shared connector library.

## Impact

The Python runtime, container layout, tests, CI, development dependencies, contributor guidance, runtime-path documentation, and architecture rules change. The public container contract and existing `connector-runtime` requirements do not change. Rollback is the prior RC image digest.
