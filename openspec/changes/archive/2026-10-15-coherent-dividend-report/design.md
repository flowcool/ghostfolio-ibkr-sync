# Design

## Context

See `proposal.md`. The report is read-only. Import selection and cash-based dividend conversion stay unchanged.

## Goals / Non-Goals

**Goals:** One block per identity; consistent reasons, labels, actions and counts.

**Non-Goals:** Identity v2, proximity amount evidence, stored-data changes and historical duplicate cleanup. Reversible maintenance remains a separate idea.

## Decisions for approval

1. **Claim legacy identity.** `historical_dividend_comparison` preserves canonical ISIN-comment criteria. A legacy symbol comment claims a group by account, resolved comment symbol and source date. `_historical_identity_checks` then checks active/id/data-source/symbol/date/ISIN row fields. Failed checks stay uncertain or to check in that one block. Amount equality cannot establish identity.

2. **Separate currency and display.** `_historical_currency` and `_historical_minor_unit` share explicit definitions, including zero-decimal JPY/KRW ([SIX](https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml)). Missing, conflicting and unsupported codes stay distinct. Exact `Decimal` evidence drives classification; `quantize(..., ROUND_HALF_UP)` drives display. Plain summary helpers replace dict output and `None`.

3. **Recognize proven rounding.** `dividend_structured_quantity` exposes finite `grossRate` from the unique matched payment `Re` for one net-positive action. `classify_dividend_findings` requires equal quantity/fee, destination gross = quantity × rate, and exactly one minor-unit cash difference. Visible INFO audit information reads `legacy declared-rate rounding`, states the declared-rate cause and `No action: IBKR rounding accepted.` Other one-unit differences remain `minimal difference, cause unknown`. Do not infer a later IBKR revision.

4. **Keep the action on the compared row.** `format_historical_dividend_finding` owns the sole `Action:`. `_propose_match` and `_match_action` preserve the row compared by the reason, shown as `Ghostfolio: activity ...`; they never target another candidate. `_match_is_strong` keeps security/day/gross/fee criteria. `_format_match` labels a selected strong row with unequal quantity `Keep, quantity differs`. Historical split rows remain `Differs`. `check_action` in `scripts/check_dividend_report.py` rejects a different target. No `Proposed action:` is emitted.

5. **Link counts.** `log_historical_dividend_comparison` returns report counts to `process_account` for DRY_RUN only.

6. **Defer generic reconciliation.** Retain the first proven cause without a generic policy; [EU settlement tolerance](https://eur-lex.europa.eu/eli/reg_del/2018/1229/oj) does not establish a dividend rule.

## Risks / Trade-offs

- Wrong legacy row fields → retain failed checks.
- Absent currency definition → never guess decimals.
- Display hides a delta → keep exact classification.
- Equal gross hides quantity differences → explicit label and compared-row action.

## Migration and Rollback

No data migration. Revert the implementation commit to restore the old report.
