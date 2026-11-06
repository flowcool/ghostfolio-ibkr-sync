# Proposal

## Why

Manual history contains rounding differences and source-proven replacements.
Explain them without changing existing correction authority.

## What Changes

- Define ordered cause functions in broker-independent helpers. Each returns
  `(label, reason, action)` or no match. First match explains its proven fields.
- Use `information` for proven source views with no more precise authoritative
  replacement. Keep all three information causes and their predicates unchanged.
- Preserve existing corrections by profile or manual `yes` for source-proven
  amount, fee, date, currency and comment replacements. The registry adds no gate.
  Without a named cause, use `correct` with label `source-proven correction`.
- Use `to_check` without a write when exact replacement proof is missing.
  Keep source, identity, quantity, journal and exact-readback guards.
- Require unchanged correction sets on existing profile and manual cases.
- Record three proven rounding shapes and split historical candidates by source proof.
  State each cause's financial risk and required authority.

## Flex Record Scope

Retained Flex XML defines this scope. Private evidence records input hashes.

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
action. Historical candidate differences alone do not prove an exact replacement.
Implementation requires approval of this proposal.
