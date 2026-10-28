# Proposal

## Why

Activity review repeats technical evidence but hides some blocked differences. It also requires manual decisions for simple reference and representation changes. Operators need explicit automation limits and one readable decision file.

## What Changes

- Trust the configured source-to-destination account mapping for historical ownership. Migrate a unique legacy reference without requiring historical cross-account coverage. Preserve all other fields during that operation.
- Add `ACTIVITY_RECONCILIATION=off|conservative|balanced|permissive`, default `off`. Profiles permit bounded one-to-one corrections. Fees do not establish identity; accepted corrections use source fees.
- Require exact BUY/SELL quantities. Support source-proven dividend quantities, GBP/GBp normalization and proven calculation residue. Bound gross differences and local-calendar date distance by profile.
- Require unique matches in both directions. Show unresolved groups without merging or splitting activities.
- Add durable pair rejection. Release a fully rejected event to ordinary import checks without rematching the rejected pairs.
- **BREAKING:** publish compact review schema 3. Keep one operator YAML; retain exact evidence in private internal state. Read schemas 1/2 and clear their approvals once. Keep unresolved journals recoverable.
- Show already-conforming activities separately from proposed corrections. Name each conflicting activity and each observed difference.

## Capabilities

### New Capabilities

- `activity-reconciliation`: Profile rules, mapping responsibility, unique matching, precision and grouped diagnosis.

### Modified Capabilities

- `activity-correction-review`: Compact decisions, rejection, profile authority and retained recovery.
- `connector-runtime`: Reconciliation before selection, rejection-aware duplicate checks and additive-update exception.

## Flex Record Scope

Checked retained reports.

| Record type | Scope | Evidence |
| --- | --- | --- |
| AccountInformation | Source ownership | Observed |
| Trade | One trade event | Observed |
| CashTransaction | Dividend cash and tax | Observed |
| ChangeInDividendAccrual | Dividend quantity | Observed |
| CashReportCurrency | Existing cash path only | Observed |
| CorporateAction | Existing holds only | Observed |
| OpenPosition | No new matching evidence | Existing optional contract; not observed |
| AssetSummary | Excluded | Parser coverage; not observed |

## Non-goals

No deletion, fill aggregation, automatic BUY/SELL quantity change, corporate-action repair, lifetime-history proof, web interface, new broker fields or sibling rollout. Planning grants no financial operation or publication authority.

## Impact

Review, selection, settings, notifications and maintenance adapters; offline tests and user guidance. Reuse the qualified update API and recovery journal. No new runtime dependency. Flag shared-helper propagation; keep DEGIRO pinned. Record the mapping decision in ADR 0009.
