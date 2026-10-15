# Design

## Context

See `proposal.md`. The report is read-only. Import selection and current cash-based dividend conversion stay unchanged.

## Goals / Non-Goals

**Goals:** Produce one complete block per dividend identity. Make every reason, amount and action accurate. Link import counts to report counts.

**Non-Goals:** Do not add identity v2. Do not implement proximity amount evidence. Do not update existing activities.

## Decisions for approval

1. **Use the old symbol comment as alternate identity.** The canonical ISIN comment keeps its existing claim criteria. `historical_dividend_comparison` will claim a legacy `dividend#<symbol>#<date>` comment when the account agrees, the comment symbol resolves to the source-group security and the comment date equals the source date. These claim values come from the comment, not the destination row fields. It will then reuse `_historical_identity_checks` for the active/id/data-source/symbol/date/ISIN row fields. A failed row-field check stays uncertain or to check in that one claimed source block, with the check named; it does not create an absent or unmatched block. Amount matching stays rejected because it can invent identity.

2. **Use explicit currency minor units.** `_historical_currency` and `_historical_minor_unit` will share one currency definition. JPY and KRW use zero decimals, as listed by [SIX ISO 4217](https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml). Missing, conflicting and unknown codes stay distinct. Monetary display will reuse exact `Decimal` evidence and `quantize(..., ROUND_HALF_UP)`. Classification keeps unrounded values.

3. **Recognize the proven one-unit legacy pattern.** For a source group with one net-positive action, the existing association in `dividend_structured_quantity` will expose the finite `grossRate` of its unique matched payment `Re`. `classify_dividend_findings` will select `legacy declared-rate rounding` only when quantity and fee agree, Ghostfolio gross equals quantity × rate, and cash differs by one minor unit. The reason will say: `Legacy row uses the declared rate; IBKR paid a rounded cash amount.` The sole action will say: `No action: IBKR rounding accepted.` The information block will stay visible at INFO as audit evidence. A one-minor-unit fee difference, or any one-minor-unit gross difference outside the proven pattern, will stay to check as `minimal difference, cause unknown`. The alternative “IBKR revised after import” is rejected because five of six observed revisions predate payment.

4. **Render one action.** `format_historical_dividend_finding` will own the only `Action:` line. `_format_match` will show evidence and labels without `Proposed action:`. Plain summary helpers will replace dict output and `None`.

5. **Link summaries by counts.** `log_historical_dividend_comparison` will return report counts. `process_account` will include them in the dividend import line during DRY_RUN. Live output stays unchanged.

6. **Defer the cause-based reconciliation policy.** IBKR declared-rate rounding is the first explained cause for a future cause-based reconciliation policy; that policy is out of scope here. Research found no financial consensus for dividend reconciliation; the only standard found uses an absolute tolerance for EU settlement matching under [Commission Delegated Regulation (EU) 2018/1229](https://eur-lex.europa.eu/eli/reg_del/2018/1229/oj).

## Risks / Trade-offs

- **A claimed legacy row has a wrong symbol or date field.** → The destination-row identity checks keep one uncertain block and name the failed check.
- **A currency definition is absent.** → Report `unsupported currency`; never guess decimals.
- **Display rounding hides a sub-unit delta.** → The class still uses exact values and names noise.

## Migration and Rollback

No data migration applies. Revert the implementation commit to restore the old report. Existing Ghostfolio data is unchanged.
