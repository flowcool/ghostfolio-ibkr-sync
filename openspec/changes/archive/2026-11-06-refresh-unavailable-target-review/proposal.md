# Proposal

## Why

A retained proposal can show an obsolete proposed date when its target is unavailable.
The blocked row must show current source values without restoring correction authority.

## What Changes

- Refresh source-derived values when a normal-run target is unavailable.
- Clear comparisons that require a current target.
- Preserve source holds, rejection bindings and journal recovery.
- Cover repeated refresh, compact deletion and restart with synthetic tests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `activity-correction-review`: define the preview for unavailable targets.

## Scope

The existing synthetic Flex report builders cover these record types.
Source conversion does not change.

| Flex record | In scope | Out of scope |
| --- | --- | --- |
| Trade | Retained BUY/SELL preview | Trade conversion |
| CashTransaction | Retained DIVIDEND preview | Payment and withholding conversion |
| ChangeInDividendAccrual | Existing quantity evidence in the preview | Accrual conversion |

## Non-goals

No production action, financial write, release or lab run is part of this preparation.
Do not change rejection semantics or release a hold to hide a proposal.

## Impact

Change `activity_review.py`, offline regression tests and the activity-review guide.
Keep the private-state and journal schemas compatible.
Both shared lab scenarios remain required before merge.
