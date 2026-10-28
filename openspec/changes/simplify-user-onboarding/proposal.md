# Proposal

## Why

The first installation requires editing a two-account deployment. Two Docker examples omit persistent safety state. Several guides contradict the current notification contract. A new user cannot reliably follow one complete path.

## What Changes

- Make one account the default Compose example. Retain the existing primary service and ENV names. Provide a separate multi-account example.
- Add a complete first-install guide: obtain files, configure services and mapping, prepare private state, preview, review, then explicitly enable writes and scheduling.
- Correct both autonomous Docker examples and all current notification instructions.
- Keep CHANGELOG.md as a link to GitHub Releases, the existing release-history authority.
- Shorten README and link detailed corporate-action, review and maintenance guides. Preserve old entry points and anchors.
- Keep one Flex field checklist. Separate mandatory setup from legacy authentication, optional platform metadata and advanced maintenance.

## Capabilities

### New Capabilities

- `user-documentation`: Complete installation examples, progressive navigation and consistent current instructions.

### Modified Capabilities

- `connector-runtime`: Permit detailed operational guidance in linked user guides. Link the changelog to Releases; preserve runtime rules.
- `activity-correction-review`: Place review instructions in the directly linked guide.
- `corporate-action-detection`: Place retention instructions in the directly linked guide.

## Flex Record Scope

Retained Flex reports establish the first six record types. Parser tests cover AssetSummary; the current spec covers optional OpenPosition evidence. Neither appears in the inspected reports. No source or parser change is proposed.

| Record type | Documentation scope | Runtime change |
| --- | --- | --- |
| AccountInformation | Required source account and currency | None |
| Trade | Required trade fields; CASH/OPT exclusions | None |
| CashTransaction | Dividend, payment-in-lieu and withholding evidence; other cash excluded | None |
| ChangeInDividendAccrual | Required quantity evidence | None |
| CashReportCurrency | BASE_SUMMARY ending cash | None |
| CorporateAction | Required selected section and safety evidence | None |
| OpenPosition | Optional evidence only | None |
| AssetSummary | Ignored; no setup requirement | None |

## Non-goals

No runtime changes, empty mapping default, automatic mapping suggestions, new diagnostics, removed commands or financial operations. No changes to financial guards, approvals, evidence retention, release qualification or sibling connectors.

## Impact

User Markdown, Compose examples, .env.example and their existing compatibility checks. One implementation branch and PR. No dependency, API, credential or production change. Existing deployments keep their supported configuration.
