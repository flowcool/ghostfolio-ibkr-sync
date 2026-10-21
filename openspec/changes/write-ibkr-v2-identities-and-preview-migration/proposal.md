# Proposal

## Why

Legacy comments can collide across source accounts. A security/day dividend can also contain several events. The released rc.5 reader supports v2; writing and conversion need approval.

## What Changes

- Write `IBKR#v2#<source-account>:TRADE:<tradeID>` for BUY/SELL and `IBKR#v2#<source-account>:DIVIDEND:<actionID>` for dividends.
- **BREAKING:** Require candidate Trade accountId to match the verified report account. Emit one dividend per proven action. Combine dividend and PIL portions of that action. Assign withholding from cash evidence, never by amount inference.
- Keep every historical generation readable, with legacy precedence and partial-coverage protection. Require bounded operator recovery after partial acceptance and block detectable action-ID replacement conflicts.
- Add an offline migration preview. Replace comments only for exact historical 1→1 matches. Keep aggregated, ambiguous, changed and unsupported rows untouched. Prove unchanged import selection across the complete configured source-account inventory.
- Extend maintenance tooling outside the runtime image. Specify separate explicit maintenance apply/rollback commands. Preview comes first. Actual conversion requires a reviewed manifest, proven API preservation and a separately authorized operation.
- Require evidence gates for source stability, destination limits, rollback and sibling compatibility before enabling writes.

### Flex scope

Three captures establish this inventory. Hashes are in the delta. Rebuild when inputs change.

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

Later implementation changes runtime helpers and offline tests. Amend ADR 0002, README and upgrade guidance. Flag DEGIRO shared-helper propagation; keep its pin. Bourse Direct targets BD v3; its inspected runtime still uses v1/v2. Retain the common grammar.

## Non-goals

No automatic historical edits, row splitting, financial correction, deletion, account move, cash migration or sibling implementation. This scope authorizes artifacts only. Tasks follow approval. Target an unused rc.6 or later.
