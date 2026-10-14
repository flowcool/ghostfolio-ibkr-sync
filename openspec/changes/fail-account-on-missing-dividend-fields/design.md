## Approach

Add one preflight function next to `flex_provenance_failures`
(`ibkr_to_ghostfolio.py`, called in `process_account` right after that check).
Reuse its row filter: `DIVIDEND_CASH_TYPES`, `WITHHOLDING_CASH_TYPE`, DETAIL level.
Reuse the failure path of the time-zone check: `log.error`, then `return {}, False`.
That path runs before any import, cash or platform write and, in the main run
loop, feeds the existing failure notification.

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

One ERROR per account, listing all gaps at once. Each XML attribute maps to its
IBKR field name through one constant dict. The names come from
`docs/ibkr-setup.md`. The message points to the README, like the time-zone one.

## Kept as is

`dividend_input_compatible` stays as the per-candidate backstop. It still
covers rows that hold the attribute but are incomplete elsewhere.
`DRY_RUN` runs the same preflight and fails the same way, because the
time-zone failure does the same.

## Open question

IBKR field names for `reportDate` and `exDate` in the accrual section are taken
from the setup guide. The task checks them against the real report before
release.
