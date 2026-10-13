# Proposal

## Why

The saved Flex report contains 46 positive dividend groups with ten wrong quantities: six dividend/payment-in-lieu pairs, one thousands-formatted rate, and three ordinary/bonus pairs. Gross payments are correct; quantities and per-share prices need correction.

## What Changes

- Retain usable rates; accept correctly grouped comma thousands separators.
- Derive dividend/payment-in-lieu quantity from combined gross payment and its single usable rate.
- Keep the common ordinary/bonus quantity after existing rounding; derive price from total payment.
- Preserve uncertain payments as one unit with a reasoned WARNING, including partially rated ordinary/bonus groups.
- Document these rules in README.

Inventory: saved report, 2025-10-13–2026-10-12; SHA-256 `8a50478e135af8e0ac2deac72d5aab3248c4915807622204e589512461926df4`. XML containers are structural.

| Flex record | Count | Scope |
|---|---:|---|
| CashTransaction: Dividends | 48 | In: quantity evidence |
| CashTransaction: Payment In Lieu Of Dividends | 7 | In: shared-rate payments |
| CashTransaction: Withholding Tax | 50 | In: preserve fee |
| Trade | 135 | Out: unchanged |
| CashReportCurrency | 9 | Out: unchanged |
| AccountInformation | 1 | Out: unchanged |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: replace the dividend rule in “Flex selection and conversion”.

## Impact

Only IBKR parsing/conversion, synthetic tests and README. No new dependency or API field. Ghostfolio request/import/cash helpers remain unchanged.

## Non-goals

Historical repair, activity updates/deletions, mixed-currency regrouping, holdings inference, external rates, live-service runs, sibling changes, and implementation in this proposal session.
