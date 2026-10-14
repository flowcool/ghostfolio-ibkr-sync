## Why

If the IBKR Flex query lacks a field the connector needs for dividends, the run
stays silent. A real DRY_RUN on a query without the contract ID (`conid`) in Cash
Transactions exited 0 with no ERROR and no WARNING. The next new dividend would be
refused with only a warning. The time-zone check already fails the account at the
start with an actionable error. Dividend fields get no such check.

## What changes

- Before any write, the connector checks which required dividend fields the report
  contains, even when there is no new dividend.
- If a required field is not in the report at all, the account fails with one
  ERROR. It names the missing XML attributes and the IBKR field names to tick.
- The failure uses the existing failure outcome and notification. It does not
  enable DRY_RUN, the same as the time-zone rule.
- A single empty or malformed row keeps today's local rejection.

## Record types considered

Source: saved real reports (old production query, tested query) and the README.

| Flex record | Decision |
|---|---|
| CashTransaction, Dividends | In scope |
| CashTransaction, Payment In Lieu Of Dividends | In scope |
| CashTransaction, Withholding Tax | In scope |
| CashTransaction, Broker Interest Paid, Deposits/Withdrawals, Other Fees | Out of scope |
| ChangeInDividendAccrual | In scope (required once relevant cash rows exist) |
| Trades, Cash Report, Account Information | Out of scope, unchanged |

## Non-goals

- No change to which dividends are imported, rejected or compared.
- No new required field. The list stays as the code requires today.
- No check of `dividendType` or `transactionID`.
- No check when the report has no relevant cash rows.
- No automatic repair of the IBKR query.

## Impact

Operators with an incomplete query see their account fail at the next run, with
the fix named. Accounts with a complete query see no change.
