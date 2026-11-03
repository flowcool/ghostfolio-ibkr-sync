# Proposal

## Why

A five-correction cap delays an approved backlog across many scheduled runs.
Apply every eligible approved correction in the current run. Keep the fixed
28-second delay and exact readback protections.

## What Changes

Remove the per-run correction count from the execution permit. Process manual,
profile-authorized and comment-only corrections across all configured accounts.
Stop the whole financial run at the first unresolved correction. Keep journal v3,
unchanged later approvals, one redacted failure notification and no resend.
No ENV setting can lower the delay or add a count cap. Add no run duration limit.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `activity-correction-review`: apply all eligible corrections with fixed pacing.
- `connector-runtime`: document uncapped correction execution.

## Impact

Change the review loop, offline tests, required user guides and CHANGELOG.
Use the existing synthetic Trade fixtures. Broker parsing stays unchanged.

| Flex record type | Scope |
| --- | --- |
| Trade | Existing source events; correction-chain fixtures |
| CashTransaction | Existing dividends; unchanged parsing |
| ChangeInDividendAccrual | Existing dividend evidence; unchanged parsing |
| CorporateAction | Existing holds; unchanged parsing |
| CashReport | Existing cash gate; unchanged parsing |
| AccountInformation | Existing source currency; unchanged parsing |

## Non-goals

No stable publication, production deployment, broker access, new ENV setting,
historical repair or financial tolerance change belongs to this change.
