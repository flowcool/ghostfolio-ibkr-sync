# Proposal

## Why

Stable promotion preserves the qualified candidate image. That image currently reports its RC tag after promotion to `latest`. Operators need an automatic software version and source commit that remain correct through promotion.

## What Changes

- Derive the target software version `X.Y.Z` from the validated release tag at build time.
- Embed that version and the exact source commit in each native image. Show them in one-off and scheduled startup logs.
- Keep `X.Y.Z-rc.N` as the candidate registry tag and signature identity. A target software version does not certify stable publication.
- Verify the embedded identity before publication and promotion. Preserve the qualified digest without rebuilding.
- Preserve recovery of older qualified images with their original RC metadata.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `release-publication`: automatic image identity, startup reporting, promotion verification and compatibility guidance.

## Impact

Dockerfile, entrypoint, application startup, release metadata and promotion scripts, native image workflow, existing runtime checks and release/user documentation. No dependency or required operator setting is added. Shared financial helpers remain unchanged.

## Flex Record Scope

The saved baseline XML inventory was checked again. The saved October 24 inventory in the archived corporate-action proposal supplies the additional record types. This change reads no report content.

| Record | In scope | Out of scope |
|---|---|---|
| AccountInformation | None | All parsing and processing |
| Trade, including STK/CASH/OPT | None | All parsing and processing |
| CashTransaction | None | All parsing and processing |
| ChangeInDividendAccrual | None | All parsing and processing |
| CashReportCurrency | None | All parsing and processing |
| CorporateAction | None | All parsing and processing |
| ConversionRate | None | All parsing and processing |
| OpenPosition, when present | None | All parsing and processing |

## Non-goals

No runtime registry or GitHub lookup, mutable channel detection, manual version override requirement, financial change, sibling propagation, rewrite of published images, publication or production deployment. The next image still requires its own exact-digest qualification and publication authority.
