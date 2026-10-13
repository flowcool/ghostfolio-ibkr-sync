# Proposal

## Why

The saved Flex report contains 46 positive dividend groups with ten incorrect inferred quantities. Deduplication can hide these errors, and log-only fallback loses per-share information without an alert. Reconciliation must recover supported quantities and keep unresolved cases actionable.

## What Changes

- Retain signed component evidence, validate complete rate tokens and reconcile before fallback.
- Preserve uncertain new payments as one unit with a persistent exception and degraded result, rather than treating their quantity as verified.
- Compare supported quantities with existing activities before deduplication; retain current duplicate suppression.
- Store private keyed YAML exceptions and before/after correction proposals. Unresolved cases trigger the configured failure summary.
- Provide explicit operator maintenance for verified historical quantity/price corrections, with recovery and readback. Daily synchronization remains additive.
- Document persistence, notifications and maintenance in README and docs/cleanup.md.

Inventory: saved report, 2025-10-13–2026-10-12; SHA-256 `8a50478e135af8e0ac2deac72d5aab3248c4915807622204e589512461926df4`. XML containers are structural.

| Flex record | Count | Scope |
|---|---:|---|
| CashTransaction: Dividends | 48 | In: quantity/component evidence |
| CashTransaction: Payment In Lieu Of Dividends | 7 | In: component portions |
| CashTransaction: Withholding Tax | 50 | In: preserve fee |
| Trade | 135 | Out: unchanged |
| CashReportCurrency | 9 | Out: unchanged |
| AccountInformation | 1 | Out: unchanged |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: conversion, existing-dividend comparison, unresolved outcomes, notifications, operational limits and explicit historical maintenance.

## Impact

IBKR runtime, existing dividend maintenance/recovery tools, synthetic tests and user documentation. Reuse ENV configuration, Apprise and YAML; no new dependency or daily financial-write endpoint. Recheck DEGIRO propagation if projected Ghostfolio helpers change. Configure durable private storage before deployment.

## Non-goals

Automatic historical updates/deletions, monetary or withholding repair, mixed-currency regrouping, current-holdings inference, external rates, live-service runs, sibling changes and implementation during planning. Missing historical entitlement evidence remains unresolved; this report cannot prove it. Existing monetary-revision work retains its scope.
