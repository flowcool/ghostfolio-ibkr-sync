# Proposal

## Why

An omitted `DRY_RUN` currently permits financial writes. Make simulation the default in v3.0.0, starting with rc.2, so a missing setting cannot enable writes.

## What Changes

- **BREAKING:** absent or blank `DRY_RUN` selects simulation and logs a WARNING on every run.
- Require an explicit false value for live writes. Invalid values fail before any HTTP call; only the configured Apprise Failure notification can follow rejection. No financial writes occur.
- Notify Failure for failed simulations when Apprise is configured. Successful simulations, token-expiry reminders and previews stay silent.
- Update README, Compose examples, upgrade guidance and changelog before rc.2. The existing single project release owns publication; no separate release flow is added.

### Flex scope

Source: saved sanitized XML inputs in `tests/test_parsing.py` and `tests/test_orchestration.py`. Rebuild this table if those inputs change. The mode applies to all writes; conversion stays unchanged.

| Records considered | Scope |
|---|---|
| Trade, including CASH/OPT; AssetSummary | In: write guard; selection unchanged |
| CashTransaction: Dividends, Payment In Lieu Of Dividends, Withholding Tax, other types/levels | In: write guard; selection unchanged |
| CashReportCurrency: BASE_SUMMARY, other currencies | In: cash write guard; selection unchanged |
| AccountInformation; ChangeInDividendAccrual | In: existing validation only |
| CorporateAction; Transfer; OpenPosition; ConversionRate | Out: no new support |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: Simulation, failure notifications and user guidance.

## Impact

Change configuration and startup in `ibkr_to_ghostfolio.py`, offline tests and user documentation. No dependency or API changes. Existing installations with explicit `DRY_RUN` need no operational migration. The live soak must set `DRY_RUN=false`.

## Non-goals

No financial conversion changes, sibling changes, deployment or real-service run in this proposal.
