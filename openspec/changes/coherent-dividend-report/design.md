# Design

## Context

See `proposal.md`. The report is read-only. Import selection and current cash-based dividend conversion stay unchanged.

## Goals / Non-Goals

**Goals:** Produce one complete block per dividend identity. Make every reason, amount and action accurate. Link import counts to report counts.

**Non-Goals:** Do not add identity v2. Do not implement proximity amount evidence. Do not update existing activities.

## Decisions for approval

1. **Use the old symbol comment as alternate identity.** `historical_dividend_comparison` will claim either the ISIN comment or `dividend#<resolved-symbol>#<date>`. It will then reuse `_historical_identity_checks`. This gives one block and keeps failed checks visible. Amount matching stays rejected because it can invent identity.

2. **Use explicit currency minor units.** `_historical_currency` and `_historical_minor_unit` will share one currency definition. JPY and KRW use zero decimals, as listed by [SIX ISO 4217](https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml). Missing, conflicting and unknown codes stay distinct. Monetary display will reuse exact `Decimal` evidence and `quantize(..., ROUND_HALF_UP)`. Classification keeps unrounded values.

3. **Recognize the proven one-unit legacy pattern.** For a source group with one net-positive action, the existing association in `dividend_structured_quantity` will expose the finite `grossRate` of its unique matched payment `Re`. `classify_dividend_findings` will select `legacy declared-rate rounding` only when quantity and fee agree, Ghostfolio gross equals quantity × rate, and cash differs by one minor unit. The reason will say: `Legacy row uses the declared rate; IBKR paid a rounded cash amount.` The one action will offer an optional unit-price correction to the paid gross, or keeping the row. The alternative “IBKR revised after import” is rejected because five of six observed revisions predate payment.

4. **Render one action.** `format_historical_dividend_finding` will own the only `Action:` line. `_format_match` will show evidence and labels without `Proposed action:`. Plain summary helpers will replace dict output and `None`.

5. **Link summaries by counts.** `log_historical_dividend_comparison` will return report counts. `process_account` will include them in the dividend import line during DRY_RUN. Live output stays unchanged.

## Risks / Trade-offs

- **A legacy comment has a wrong symbol or date.** → Identity checks keep one uncertain block.
- **A currency definition is absent.** → Report `unsupported currency`; never guess decimals.
- **Display rounding hides a sub-unit delta.** → The class still uses exact values and names noise.

## Migration and Rollback

No data migration applies. Revert the implementation commit to restore the old report. Existing Ghostfolio data is unchanged.
