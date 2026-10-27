# Proposal

## Why

A scheduled production run completed successfully while 68 source events remained held for review. It sent no notification. Scheduler wrapping hid the application log level. Users need clear next steps.

## What Changes

- Every required user action emits at least WARNING and joins one configured Apprise notification, including ntfy, per completed run. This applies in simulation too.
- Repeat reminders while the observed action remains required. Recovered retries and findings that need no action do not trigger these reminders.
- Show the reason, impact, safe next action and applicable file in private logs. Distinguish review approval, missing proof and separately authorized maintenance.
- Report imports, held events, cash outcome and notification outcome separately. Keep existing exit codes.
- Transmit application logs without scheduler wrapping. Route DEBUG/INFO to stdout and WARNING/ERROR to stderr. Preserve the application level and timestamp.
- Replace existing specification exceptions that suppress notifications for required actions.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: action classification, consolidated notifications, final results and clear logs.
- `activity-correction-review`: useful review instructions and reminders without new write authority.
- `corporate-action-detection`: repeated action reminders alongside existing findings and resumption notifications.

## Impact

Update orchestration, outcome records, notification summaries, review reporting, diagnostics, selection reporting, logging setup, entrypoint, offline tests and user documentation. Reuse Apprise and the pinned Supercronic. Add no dependency or mandatory ENV setting. Flag shared-helper changes for separate DEGIRO propagation. Leave siblings unchanged.

### Flex scope

Offline inventory: saved captures A/C from Source identity evidence gates and the existing October 24 archive, including corporate actions. No broker acquisition is needed.

| Observed record | In scope | Out of scope |
|---|---|---|
| AccountInformation | Report prerequisite actions | Ownership changes |
| Trade, including STK/CASH/OPT | Existing decisions and exclusions | Conversion changes |
| CashTransaction: Dividends, Payment In Lieu Of Dividends, Withholding Tax, Deposits/Withdrawals, Broker Interest Paid, Other Fees | Existing action reporting | New imports or cash interpretation |
| ChangeInDividendAccrual | Missing/conflicting evidence guidance | Payment inference |
| CashReportCurrency | Cash result or missing-summary guidance | Balance calculation changes |
| CorporateAction | Existing hold guidance | Financial treatment |
| ConversionRate | None | FX processing |

## Non-goals

No financial repair, bulk approval, production operation, notification retry, success heartbeat, new persistent alert store or automatic host-mount discovery. Preserve import selection, correction qualification, journals and recovery fences.
