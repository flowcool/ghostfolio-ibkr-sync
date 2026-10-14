# Proposal

## Why

A temporary incomplete-statement response currently stops an unattended run at SendRequest (public issue #137). Retrying documented transient Flex responses can recover within the same run without changing financial processing.

## What Changes

- Retry explicitly transient SendRequest codes after 1, 2, 5 and 10 minutes: five attempts, 18 minutes of scheduled waits.
- Fail immediately for permanent, unavailable, missing or unknown error codes.
- Extend GetStatement polling from 10 to 60 attempts at 5 seconds. Preserve its existing Warn/1019 detection and other failure behavior.
- Document waits, exhaustion and permanent failures in README.

Record inventory comes from a saved Flex report; only section/record names were inspected. Retrieval affects the whole XML envelope; no record conversion changes.

| Flex section or record considered | In scope | Out of scope |
| --- | --- | --- |
| AccountInformation | Envelope retrieval | Account interpretation |
| Trades / Trade | Envelope retrieval | Selection and conversion |
| CashTransactions / CashTransaction | Envelope retrieval | Payments, tax and grouping |
| CashReport / CashReportCurrency | Envelope retrieval | Cash updates |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: bounded recovery during Flex retrieval, with unchanged downstream processing.

## Impact

Implementation will touch `fetch_flex_report` in `ibkr_to_ghostfolio.py`, mocked tests in `tests/test_orchestration.py`, and README. No dependency, ENV or Ghostfolio helper change. Failed runs can take longer; HTTP timeouts and existing network retries add to scheduled waits. A stable release will deliver runtime changes separately.

## Non-goals

No runtime changes in this proposal PR. No financial repair, live-service replay, deployment, new retry configuration, transport retry changes, GetStatement code reclassification, or change to imports, cash, exits and notifications.
