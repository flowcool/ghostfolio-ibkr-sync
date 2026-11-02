# Proposal

## Why

Unchanged held events produce daily notifications. The operator needs a notice when action changes, and a bounded reminder when it does not.

## What Changes

- Group required actions by fixed reason and unique event count.
- Notify on the first group, any count or reason change, and after seven days without a confirmed reminder.
- Keep immediate failure notifications and private per-event evidence.
- Exclude automatic work and budget deferrals from required actions.

## Capabilities

### Modified Capabilities

- `connector-runtime`: required-action notification schedule and classification.
- `corporate-action-detection`: grouped action reminders with immediate failure priority.

## Impact

Notification finalization, private delivery state, review reporting, offline tests and user configuration documentation change. No dependency or financial request changes.

| Sanitized Flex fixture record | In scope | Out of scope |
| --- | --- | --- |
| Trade | Existing action counts | Parsing and imports |
| CashTransaction | Existing action counts | Payment and tax selection |
| CorporateAction | Existing action counts | Holds and evidence |
| CashReportCurrency | Existing missing-cash action | Cash updates |

Record types come from the saved sanitized fixtures in tests and the report builders in `tests/_sync_helpers.py`. No source interpretation changes.

## Non-goals

No release, production deployment, broker access, financial write, new ENV setting or sibling propagation.
