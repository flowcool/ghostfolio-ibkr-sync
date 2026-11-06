## Why

A dividend group can contain one v2 activity and one legacy activity. The current partial-coverage guard blocks both even when cash and quantity prove one unique allocation.

## What Changes

- Qualify one legacy destination for the single missing action in a two-action group.
- Require exact quantity, gross representation, payment day, currency, account and security, plus complete cash, withholding and accrual evidence.
- Propose the missing identity and reviewed fee together. Preserve destination IDs and other fields.
- Keep the v2 sibling blocked until complete identity coverage is observed.
- Keep all ambiguous groups blocked and retain the additive import guard.

| Flex record type in the saved report | Scope |
| --- | --- |
| AccountInformation | Account validation only |
| CashTransaction: Dividends, Payment In Lieu Of Dividends, Withholding Tax | Action payment and withholding evidence |
| ChangeInDividendAccrual | Structured quantity evidence only |
| Trade | Out of scope; preserve current behavior |
| CashReportCurrency | Out of scope; preserve cash updates |
| ConversionRate | Out of scope |
| CorporateActions | Out of scope; no action records in the observed report |

The table follows the saved complete report used for diagnosis. Regression fixtures use synthetic identifiers and values.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `activity-correction-review`: qualify the unique missing-action correction without weakening other partial groups.

## Non-goals

No production operation, release, new import, deletion, split, merge, maintenance-tool bypass or manual normalization. No general amount tolerance for identity allocation.

## Impact

Change `activity_review.py`, offline review tests and the review/upgrade guides. Reuse the existing PUT, journal, authority and exact-readback mechanisms. No new dependency or API.
