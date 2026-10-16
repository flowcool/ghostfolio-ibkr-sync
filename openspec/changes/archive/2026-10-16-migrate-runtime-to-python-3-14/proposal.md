# Proposal

## Why

The shipped image and CI still use Python 3.12. Move them to Python 3.14 before the typed modular refactor so that the refactor starts from the required runtime baseline.

## What Changes

- Change the pinned Docker base from `python:3.12-slim` to `python:3.14-slim` with the current multi-architecture digest.
- Change all seven Python pins in the four CI and scheduled workflows to 3.14.
- Change both Renovate interpreter ranges from 3.12 to 3.14 while retaining reviewed digest and patch updates.
- Keep all runtime and development dependency versions unchanged. Their PyPI metadata and binary resolution support Python 3.14 on amd64 and arm64.
- Document Python 3.14+ for direct runs. Do not add a runtime block for Python 3.12.
- Make the isolated container check prove that the built image runs CPython 3.14.

Saved synthetic Flex reports in `tests/test_parsing.py`, `tests/test_orchestration.py`, and `tests/test_auth.py` establish this inventory:

| IBKR Flex record | Scope |
|---|---|
| `Trade` except CASH/OPT | Out: behavior unchanged |
| CASH/OPT `Trade` | Out: remains ignored |
| DETAIL dividend, payment-in-lieu, and withholding `CashTransaction` | Out: behavior unchanged |
| Other `CashTransaction` types or levels | Out: remain ignored |
| `ChangeInDividendAccrual` | Out: behavior unchanged |
| BASE_SUMMARY `CashReportCurrency` | Out: behavior unchanged |
| Other `CashReportCurrency` rows | Out: remain ignored |
| `AccountInformation` | Out: behavior unchanged |
| `AssetSummary` | Out: remains ignored |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: require Python 3.14 for the shipped image and CI, and document Python 3.14+ for direct runs.

## Non-goals

Change financial behavior, dependencies, ENV, authentication, schedules, logs, exits, notifications, publication, deployment, or sibling repositories. Do not claim that Python 3.12 fails.

## Impact

Dockerfile, four workflows, Renovate policy, container checks, tests, README, CONTRIBUTING, and upstream documentation change. The change precedes `modularize-typed-python-runtime` in the v3.0.0 RC series. Rollback uses the prior image digest.
