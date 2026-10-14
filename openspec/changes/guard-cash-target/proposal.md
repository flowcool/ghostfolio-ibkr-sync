## Why

The cash stage writes IBKR's ending cash into the Ghostfolio account as-is. Two setups give a wrong balance silently: two IBKR accounts mapped to one Ghostfolio account (the last write wins), and a Ghostfolio account whose currency differs from the IBKR base currency (the amount is stored in the wrong currency). The product rule is one IBKR account per Ghostfolio account; nothing enforces it. ADR 0004 says the currencies "must match" but does not enforce it.

## What changes

- Startup refuses a `GHOST_ACCOUNT_NAMES` list that names one Ghostfolio account twice, before any network call or write.
- Before the cash write, the IBKR base currency is compared with the Ghostfolio account currency. On a difference the account fails with an error naming both currencies. No cash is written. No conversion is added.
- The unused `GHOST_CURRENCY` setting is removed; a value still set is ignored, as today.
- Matching currencies behave as before.

## Record types considered

Source: one saved real Flex report.

| Flex record | Decision |
|---|---|
| AccountInformation `currency` | In scope: the base currency code |
| CashReportCurrency `BASE_SUMMARY` | In scope: amount only, it carries no currency code |
| Other CashReportCurrency rows, Trades, CashTransactions | Out of scope |

## Non-goals

- Summing cash from several sources into one target.
- Currency conversion or a new FX dependency.
- Real-data reproduction: none exists, accepted by the operator. Proof is offline synthetic tests.
