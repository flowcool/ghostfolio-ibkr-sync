## Decisions

- **Read-only, log only.** The proposal is built inside `classify_dividend_findings` from data it already holds and rendered by `format_historical_dividend_finding`. No new read, state or write. ADR 0003 is unchanged: nothing acts on the proposal; the operator deletes by hand.
- **Candidates.** For one IBKR dividend: its compared Ghostfolio rows, the legacy-comment twins already paired by `classify_dividend_findings`, and the rows of the existing proximity window (`finding["proximity"]`). Coherent groups with a twin are included.
- **Confidence.** Strong: a row with the same security, local day, gross and fee (via `_readable_values`). Weak: same security and local day only, or dates inside the proximity window. Quantity is shown, never scored. Evidence: twins differ in quantity while gross and fee agree.
- **One best candidate.** Strong beats weak. Several equal rows: Keep goes to the row with a canonical comment, else the compared row, else the lowest activity id (deterministic). Other equal rows are Duplicate; unequal rows are Differs. A weak proposal has no Keep: every row is Differs and the action line asks for a manual comparison. No candidate: "no confident match". Never guess beyond this.
- **Action line.** Names one row: the first Duplicate, else the first Differs. Wording follows `READABLE_ACTIONS`.
- **Display only.** `readable["class"]`, labels, counts (summary line) and exits are untouched. A test compares them before and after.
- **Dates.** Print local day and UTC date; match on the local day, as `classify_dividend_findings` does.
- **Printing.** English; plain decimals via `_plain`.
- **Rollback.** Revert the PR.

## Open questions

- Whether a Duplicate is active in Ghostfolio: wording stays "proposed".
- Rows whose totals equal IBKR (split): shown as Differs.
