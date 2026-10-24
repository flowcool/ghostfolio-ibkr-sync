# Proposal

## Why

Real IBKR records establish two forward splits and one reverse split with an ISIN change. Current imports ignore these events. Stored activities can already use adjusted units, so applying a native ratio can duplicate an adjustment.

## What Changes

- Detect, explain and propose handling for corporate actions. Keep all corporate-action writes unavailable.
- **BREAKING:** hold BUY/SELL for affected securities when identity or effective quantity is unproven. Hold all account BUY/SELL when the affected set cannot be bounded. Continue independent cash and unrelated work under existing guards.
- **BREAKING:** require CorporateActions in Flex and private persistent state initialized in simulation. A missing source section holds account BUY/SELL.
- Release holds from fresh financial evidence, never acknowledgment. Cost/date differences alone do not require a quantity hold.
- Report each run. Notify active holds each run, other findings on first appearance or change, and verified resumption.
- Require observed stable Ghostfolio 3.91.0 minimum before accepting native split evidence. Version alone does not prove a case.

## Flex Record Scope

This table comes from the saved real XML reports inspected on 2026-10-24. An empty CorporateActions section differs from a missing section.

| Record | In scope | Out of scope |
|---|---|---|
| CorporateAction | Forward/reverse event evidence; unknown-event reporting and safe holds | Native writes and automatic historical conversion |
| Trade | Existing supported BUY/SELL; corporate-action safety gate | New CASH/OPT support |
| AccountInformation | Existing source-account validation | Ownership inference |
| CashTransaction | Existing dividends/tax; explicit event cash evidence in reports | New cash activities or guessed compensation |
| CashReportCurrency | Existing independent BASE_SUMMARY cash | Currency conversion |
| ChangeInDividendAccrual | Existing dividend validation | New dividend behavior |
| ConversionRate | Inventory only; retain current ignored behavior | Historical conversion |

## Capabilities

### New Capabilities

- `corporate-action-detection`: event evidence, durable findings, quantity/identity decisions and notifications.

### Modified Capabilities

- `connector-runtime`: corporate-action preflight, import holds and notification rules.

## Impact

Typed parsing, orchestration, effective holdings, retained source evidence, private YAML state, authenticated reads and setup guidance. Reuse current identity, cash and write-uncertainty guards. Shared Ghostfolio helper changes require a separate downstream propagation decision.

## Non-goals

No split registration, activity repair, identifier remapping, historical conversion, additional export format, mandatory OpenPositions, production action or sibling implementation. Proposal approval authorizes implementation planning only. Existing activity-review approvals cannot authorize corporate-action treatment or bypass its holds.
