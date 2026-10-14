## Why

A Flex `Trade` row whose `buySell` is not exactly `BUY` or `SELL` (for example a cancellation) is imported as a SELL. That can create a phantom sale. Real reports hold only `BUY` and `SELL`, so the defect is latent. No real cancellation sample exists (operator accepted); proof is offline synthetic tests.

## What changes

- A `Trade` with any `buySell` other than exact `BUY` or `SELL` is not converted. The existing per-row error path applies: error logged, account run not ok, failure notification.
- The holdings gate needs no change: it only sees converted trades.
- README conversion row updated.

## Record types considered

Source: two saved real Flex reports (`buySell` counts: BUY and SELL only).

| Flex record | Decision |
|---|---|
| Trade `buySell` BUY / SELL | In scope, unchanged |
| Trade other `buySell` value | In scope: rejected per row |
| Other Trade attributes, CashTransactions, CashReportCurrency | Out of scope |

## Non-goals

- Cancellation handling: the original trade stays imported (additive imports, ADR 0003).
- New Flex query fields.
- A warning-only skip branch.
