# Proposal

## Why

Manual history contains amount differences. Some are proven broker rounding;
others can require correction when complete source evidence proves an entry error.

## What Changes

- Define ordered cause functions in broker-independent helpers. Each returns
  `(label, reason, action)` or no match. First match wins; default is `to_check`.
- Use `information` for proven source views with no more precise authoritative
  replacement. Use `correct` for a proven entry error with an exact replacement.
- Route corrections through existing profile authority and reviewed updates.
  Keep source, identity, quantity, journal and exact-readback guards.
- Record three proven rounding shapes and the unresolved historical candidates.
  State each cause's financial risk and required authority.

## Flex Record Scope

Based on retained Flex XML and the saved report scope. Private evidence records
input hashes. Other brokers supply their own source evidence.

| Flex record | Scope | Use |
| --- | --- | --- |
| `CashTransaction` dividend/PIL, DETAIL | In | Exact paid gross |
| `CashTransaction` withholding, DETAIL | In | Exact fee |
| `ChangeInDividendAccrual` | In | Quantity and matched declared rate |
| `Trade` | In | Exact price/quantity/commission proof; no conversion change |
| `CorporateAction` | Out | Existing holds stay unchanged |
| Other cash types/levels | Out | No accepted cause added |
| `CashReportCurrency`, `AccountInformation` | Out | No cash/account change |
| `AssetSummary` | Out | No report input |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: Report cause, proposed action and actual outcome consistently.
- `activity-reconciliation`: Define cause actions and existing profile authority.

## Impact

Future implementation connects pure cause functions to the IBKR report and
existing correction selection. No new writer, dependency or ENV setting is
required. DEGIRO needs separate package-aware propagation under ADR 0007.
Bourse Direct adoption is a recommendation for its owning repository.

Private evidence retains all measurements and source hashes. Public artifacts
contain no account, security or activity values.

## Non-goals

No amount tolerance for identity or deduplication. No deletion, grouped update,
new profile threshold, guessed quantity, generic FX cause, release or production
action. Historical candidate differences alone do not prove human error.
Implementation requires approval of this proposal.
