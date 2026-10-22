# Proposal

## Why

The connector skips probable duplicates. Corrections remain manual. The operator will approve exact replacements for the next run through a file.

## What Changes

- Add optional `ACTIVITY_REVIEW_FILE`, on a persistent writable volume.
- Compare BUY, SELL and DIVIDEND events with existing activities. Use exact references or bounded date proximity. Present candidates and proposed values in keyed YAML.
- Read approvals on every run. Only `approve: yes` permits the displayed correction. Blank approvals remain pending and prevent the related new import.
- Update one existing activity per source event. Preserve its ID, account, tags and user notes. Replace recognized old references with the current IBKR reference.
- Remove confirmed corrections. Release an import hold when all former candidates belong to other identified events. Retain missing-target, failed and source-unavailable proposals. Reset approval when reviewed values change.
- Journal before/after values. Confirm updates by exact readback. After uncertainty, block account writes until expected values appear. No reset, retry or interactive recovery.
- Let simulation refresh the file without financial writes or consuming valid approvals.

### Record scope

Offline inventory of a saved complete Flex report: 132 trades, 239 cash transactions and 154 accrual rows.

| Flex record | Scope |
|---|---|
| AccountInformation | Verify source account |
| Trade, supported (STK observed) | BUY/SELL candidates |
| Trade, CASH/OPT | Excluded |
| CashTransaction, Dividends/PIL | Payment evidence; one positive action per candidate |
| CashTransaction, Withholding Tax | Fees for its proven payment action |
| CashTransaction, Other Fees/Deposits/Withdrawals/Broker Interest Paid | Excluded |
| ChangeInDividendAccrual | Quantity evidence, never a payment |
| CashReportCurrency | Existing cash path; no review correction |
| ConversionRate | No new FX conversion |
| CorporateActions, empty in capture | Excluded |
| FlexQueryResponse/FlexStatements/FlexStatement and section containers | Existing parsing and window context |

Rebuild the inventory if source sections or record types change.

## Capabilities

### New Capabilities

- `activity-correction-review`: persistent proposals, approval, verified updates and recovery.

### Modified Capabilities

- `connector-runtime`: optional correction integration, pending-import exclusion and references with preserved user notes.

## Impact

Changes will affect configuration, activity indexing, conversion orchestration, update requests and user guidance. Disabled behavior stays intact. No new dependency. Shared-helper changes require a downstream propagation assessment; sibling connectors remain unchanged.

## Non-goals

No implementation. No many-to-one merge, deletion, rejection choice, automatic approval, bulk historical migration, corporate-action support, production activation or publication.
