## Why

Manual reconciliation groups ambiguous split fills with `dateTime[:8]`. This is a full day for compact timestamps, but only `YYYY-MM-` for dashed timestamps. Two fills on different days of one month can therefore sum to one manual trade and be suppressed incorrectly. The global v3.0.0 RC review found this latent defect. Synthetic offline tests provide the acceptance proof.

## What changes

- Build the split-fill grouping day from the existing parsed IBKR timestamp.
- Keep side, resolved ticker, and ISIN as grouping dimensions.
- Add synthetic coverage for same-day and different-day dashed timestamps.

## Record types considered

Source: the existing sanitized `Trade` fixtures in `tests/test_filters.py`. The Flex source fields do not change.

| Flex record | Decision |
|---|---|
| Trade with a supported `dateTime` | In scope: group ambiguous fills by parsed calendar day |
| Trade with a missing or invalid `dateTime` | Unchanged: it cannot match a manual row |
| CashTransaction | Out of scope |
| CashReportCurrency | Out of scope |
| AssetSummary and other Flex records | Out of scope |

## Non-goals

- Change the ±2-day manual-match window.
- Change quantity tolerance, ticker resolution, or holdings checks.
- Import ambiguous fills automatically.
- Change timestamp parsing or timezone interpretation.
