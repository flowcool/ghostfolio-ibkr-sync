# Proposal

## Why

IBKR splits can make ordinary imports unsafe. The candidate detects these events, but retains a full XML for every acquisition without rotation. It also misses an unavailable source when checking shared destination ownership.

## What Changes

- **BREAKING:** require CorporateActions and private persistent state. Hold unsafe BUY/SELL while preserving independent cash and unrelated work.
- Explain source completeness, identity, quantity, history and cash separately. No corporate-action writes.
- Accept operator-verified effective dates bound to official documents. Keep native acceptance disabled until non-admin image qualification passes.
- Rotate ordinary acquired reports automatically after 30 days. Use a fixed duration, with no new ENV setting or storage quota.
- Keep original reports and bindings only while needed for safety. Preserve known events, conflicts and their necessary chains. Remove redundant copies after verification.
- Report maintenance failure without a new trade hold when required evidence remains durable and valid. Missing required proof still holds affected BUY/SELL.
- Hold all shared destination owners when one owner has a known event or unavailable source evidence.
- Keep current reconciliation logs and proposals. The user handles manual cleanup and reruns the analysis. Rotation does not affect correction journals.

## Flex Record Scope

This table retains the real XML scope inspected on 2026-10-24. No new source format is introduced.

| Record | In scope | Out of scope |
|---|---|---|
| CorporateAction | Event evidence, conflicts and safe holds | Native writes or historical conversion |
| Trade | Existing BUY/SELL and quantity chains | New CASH/OPT support |
| AccountInformation | Source-account validation | Ownership inference |
| CashTransaction | Existing dividends/tax and explicit event cash evidence | Guessed compensation |
| CashReportCurrency | Independent BASE_SUMMARY cash | New FX treatment |
| ChangeInDividendAccrual | Existing dividend validation | New dividend behavior |
| ConversionRate | Existing ignored behavior | Historical conversion |
| OpenPosition, when present | Optional source quantity anchor | Mandatory query section |

## Capabilities

### Modified Capabilities

- `corporate-action-detection`: evidence, rotation, holds and notifications.
- `connector-runtime`: preflight, maintenance reporting and user guidance.

## Impact

Corporate evidence storage, orchestration, existing offline tests and README. Reuse existing locks, atomic writes and financial fences. Shared helper changes retain the downstream propagation requirement.

## Non-goals

No new reconciliation job, archive replay command, automatic historical repair, new dependency, broker access, production action or publication. Exact-image release gates remain separate.
