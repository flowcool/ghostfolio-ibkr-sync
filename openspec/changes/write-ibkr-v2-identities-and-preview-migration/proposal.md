# Proposal

## Why

Legacy comments can collide across source accounts. A security/day dividend can also contain several events. The released rc.5 reader supports v2; writing and historical conversion need a separate approved contract.

## What Changes

- Write `IBKR#v2#<source-account>:TRADE:<tradeID>` for BUY/SELL and `IBKR#v2#<source-account>:DIVIDEND:<actionID>` for dividends.
- **BREAKING:** Emit one dividend per proven action. Combine dividend and PIL portions of that action. Assign withholding from cash evidence, never by amount inference.
- Keep every historical generation readable, with existing legacy precedence and partial-coverage protection.
- Add an offline migration preview. Propose comment replacement only for exact, unique historical 1→1 matches. Keep aggregated, ambiguous, changed and unsupported rows untouched.
- Specify separate explicit maintenance apply/rollback commands. Preview comes first. Actual conversion requires a reviewed manifest, proven API preservation and a separately authorized operation.
- Require evidence gates for source stability, destination limits, rollback and sibling compatibility before enabling writes.

### Flex scope

Counts come from three saved captures; the delta spec identifies their hashes. Rebuild this inventory if inputs change.

| Record / subtype | Observed rows | Scope |
|---|---:|---|
| Trade / STK | 118 | v2 writes and 1→1 preview |
| Trade / CASH, OPT | 16, 1 | Excluded as today |
| CashTransaction / Dividends, PIL, Withholding Tax DETAIL | 48, 7, 50 | Action partition and preview |
| CashTransaction / other DETAIL | 134 | Out |
| ChangeInDividendAccrual | 154 | Quantity evidence only |
| AccountInformation | 1 in baseline | Source-account proof |
| CashReportCurrency / BASE_SUMMARY, other | 1, 8 | Unchanged; no migration writes |
| AssetSummary, CorporateAction, Transfer, OpenPosition, ConversionRate | 0 | Unobserved; out |

## Capabilities

### Modified Capabilities

- `connector-runtime`: v2 writes, event partition, historical reads and explicit identity maintenance.

## Impact

Change `ibkr.py`, `sync.py`, `app.py`, identity/request helpers and offline tests during later implementation. Amend ADR 0002, README and upgrade guidance. Flag DEGIRO shared-helper propagation; keep its pin. Bourse Direct targets BD v3; its inspected runtime still uses v1/v2. No new common grammar or ADR is needed.

## Non-goals

No automatic historical edits, row splitting, financial correction, deletion, account move, cash migration or sibling implementation. This proposal authorizes no runtime change, service call, migration, release or deployment. Implementation tasks await proposal approval. Writer release numbering is rc.6 or later, subject to availability.
