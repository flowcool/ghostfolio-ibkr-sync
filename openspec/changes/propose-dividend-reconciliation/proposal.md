## Why

The operator still pairs dividend rows by hand. The latest real DRY_RUN gave 20 items to check: 10 compared dividends and 10 legacy-comment rows. Each legacy row only names another activity id, and a matching coherent row is not shown at all.

## What changes

- Each item to check with a candidate gets one "Proposed match" section: the IBKR dividend and the Ghostfolio rows side by side, each labelled Keep, Duplicate or Differs, plus one action line naming the row to act on.
- The section states a confidence (strong or weak), or reads "no confident match".
- It appears in every block of the same dividend, so a legacy-comment row shows the IBKR side too.
- Display only: classes, counts, exits and notifications do not change.

## Record types considered

Source: saved real Flex report, DRY_RUN log 2026-10-14.

| Flex record | Decision |
|---|---|
| CashTransaction Dividends, Payment In Lieu, Withholding Tax | In scope (compared, unchanged) |
| ChangeInDividendAccrual | In scope (quantity evidence, unchanged) |
| Other cash types, Trades, Cash Report | Out of scope |

## Non-goals

- No write, no automatic action, no change to import selection (ADR 0003 stays).
- No identity proof: a proposal is a reading aid.
- No matching beyond the stated rules.
