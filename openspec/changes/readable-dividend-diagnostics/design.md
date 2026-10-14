## Decisions

- **Reuse the existing pipeline.** Classification runs on the findings that `format_historical_dividend_finding` and `log_historical_dividend_comparison` already receive. No new read, no new state.
- **Noise rule.** Compare each gross/fee delta with half the minor unit of the source currency, taken from the existing currency-exponent helper (JPY 0.5, GBP/USD/EUR 0.005). Quantity deltas are never noise. Real evidence: one sub-cent GBP row and one float residue; no other currency measured.
- **One-unit bucket.** For every currency. Equal quantity and a gross or fee delta of exactly one minor unit. Evidence: 6 JPY rows; a 2-decimal rounding of the unit price explains only 2 of 6, so the cause stays unknown (open question; the Ghostfolio write path was not read).
- **Probable duplicate.** A legacy-comment destination row with the same security and local day as a compared group. In the real log all 10 have a twin, and the sibling amounts sum to the source. Not verified as active duplicates in Ghostfolio, so the wording says "probable".
- **Catch-all.** Any finding outside coherent, outside window, information and noise is "to check" with its reason.
- **Split text.** Sum destination rows of one uncertain partition; if gross and fee equal the source, print "total equal". The spec rule that amount equality does not prove completeness stays; only the text changes.
- **Absent/outside-coverage pair.** An absent source skipped by historical comment and a destination row outside proven coverage with the same security, day, gross and fee print as one information line (2 dividends, 4 findings today).
- **Decimal printing.** Print plain decimals (`format(value, "f")`), never `repr`. This removes the 39 `Decimal('0')` lines and the exponent form.
- **Language.** Log text stays English, like the rest of the product. French is used only in operator conversation.
- **Levels.** To-check and information findings log at INFO. Coherent and outside-window findings stay at DEBUG. The summary is one INFO line followed by the to-check detail.
- **Rollback.** Revert the implementation PRs. Diagnostics run only under DRY_RUN and write nothing.

## Open questions

- Why four of the six one-yen gaps exist (other import path, IBKR revision, or rounding).
- Whether USD, EUR or KRW rows ever show noise: not measured.
