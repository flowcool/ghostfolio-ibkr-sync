# Proposal

## Why

Additive imports leave historical dividends unverified. Captures show coherent components, repetition and discrepancies.

## What Changes

- Add historical comparison to every truthy `DRY_RUN`, including one-off Docker runs without `CRON`.
- Log summary/details, uncertainty and exact destination-minus-source monetary differences.
- Define activity/profile currency precedence with provenance and exact major/minor-unit normalization.
- Separate complete single/component representations from coherence; report competing complete representations as probable repetition even with discrepancies. Require globally unique destination assignment.
- Retain JSON decimal evidence before float decoding; preserve cash tax/refund evidence and the existing fee convention.
- Specify one acceptance command per slice, including reader compatibility and final outcome regressions across `tests/`.
- Reuse quantity/cash rules; no financial changes.

Saved enriched Flex XML inventory:

| Record type | Rows | Scope |
|---|---:|---|
| CashTransaction: Dividends | 48 | In: payments |
| CashTransaction: Payment In Lieu Of Dividends | 7 | In: payments |
| CashTransaction: Withholding Tax | 50 | In: fees |
| ChangeInDividendAccrual: Po/Re | 154 | In: quantities |
| CashTransaction: Other Fees | 97 | Out |
| CashTransaction: Deposits/Withdrawals | 1 | Out |
| CashTransaction: Broker Interest Paid | 36 | Out |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: dry-run historical comparison and visibility.

## Impact

Future runtime/tests/README changes. ENV/mounts/dependencies unchanged. Shared-reader changes require downstream propagation review.

## Non-goals

No maintenance, monetary-revision delivery, deduplication changes, planning service calls, implementation, main-spec sync or archive. Captures stay private.
