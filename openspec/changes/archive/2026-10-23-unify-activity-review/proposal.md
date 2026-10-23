## Why

Historical identity conversion and activity review can propose the same activity. Users need one approval file and a clear distinction between a reference change and a financial correction. External review found that the proof for a full historical batch cannot authorize an arbitrary approved subset.

## What Changes

- Use schema 2 with `reference_updates` and `activity_corrections` in one private file.
- Show `exact`, `probable` or `blocked` as the evidence level for the association. This level does not approve a financial value.
- Execute only literal `approve: yes`. Skip all other choices. Store no rejection or correspondence table.
- Prepare historical reference changes in that same file. Keep their separately authorized maintenance executor. Recompute eligibility and complete import selection for the exact approved subset.
- Compare preserved business fields exactly. Ignore only named server metadata and derived values. Retain raw evidence hashes.
- Document the normal-run and historical-maintenance paths with examples and recovery limits.

| Saved Flex record type | Scope |
|---|---|
| Trade | Supported BUY/SELL identities and review |
| CashTransaction | Supported dividend actions and withholding evidence |
| ChangeInDividendAccrual | Existing dividend quantity evidence |
| AccountInformation | Source-account ownership |
| CashReportCurrency | Existing cash behavior only |
| ConversionRate | Existing conversion behavior only |
| CorporateAction | Out of scope; no rows in the retained inventory |

The table follows the saved report inventory used for the historical preview.

## Non-goals

No automatic historical conversion in normal sync. No new financial policy, rejection store, activity deletion or aggregate split. No production writes, release activation or qualification claim. No weaker historical cross-account proof.
