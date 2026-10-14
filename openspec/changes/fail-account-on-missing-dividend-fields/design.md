## Approach

Add one preflight function next to `flex_provenance_failures`
(`ibkr_to_ghostfolio.py`, called in `process_account` right after that check).
Reuse its row filter (`DIVIDEND_CASH_TYPES`, `WITHHOLDING_CASH_TYPE`, DETAIL) and
the time-zone failure path: `log.error`, then `return {}, False`. That path runs
before any write and feeds the existing failure notification.

## Checks, in order

1. Collect the relevant DETAIL cash rows. If there are none, stop: pass.
2. Payment keys: `accountId`, `conid`, `currency`, `actionID`, `exDate`. A key is
   missing when no relevant row carries the attribute. This constant already
   exists as `keys` in `dividend_input_compatible`; hoist it to module level and
   use it in both places.
3. Accrual section: if `ChangeInDividendAccruals` is absent, report it.
4. If the section has at least one row, the keys plus `quantity`, `code`, `date`,
   `payDate`, `reportDate` must each appear on some row. This is the existing
   `required` list, hoisted the same way. A present but empty section has no
   columns to check and stays valid.

## Message

One ERROR per account listing all gaps. One constant dict maps each XML attribute to its IBKR field name. The message points to the README.

## Kept as is

`dividend_input_compatible` stays as the per-candidate backstop.
`DRY_RUN` runs the same preflight and fails the same way.

## Decisions

IBKR field names come from `docs/ibkr-setup.md`; the XML carries no UI labels.

Presence rule, not non-empty. In both saved reports, all 50 Withholding Tax
DETAIL rows carry the five payment keys as attributes, except `conid` in the old
query. `exDate` is present but empty on 50/50 rows in both. The check therefore
tests attribute presence only. Empty values stay local rejections.
