# Bound broker history to the Flex window and leave corporate actions manual

Date: 2026-10-12. Status: accepted (existing behavior).

The configured Flex Activity Statement supplies at most 365 days of history;
the sync does not reconstruct older purchases. Existing Ghostfolio history or
manual opening purchases must back older positions. Daily additive runs retain
previously imported history. The holdings guard uses net quantities rather than
chronological reconstruction, so it cannot prove complete historical accounting.

The parser consumes Trades, Cash Transactions and Cash Report, not Corporate
Actions. Splits and mergers require manual reconciliation; split-adjusted market
prices can disagree with unchanged stored transactions. Keep the 365-day query
for recovery instead of narrowing it casually: an omitted purchase can prevent
a later sell from passing the holdings gate.

Sources: [Flex setup](../ibkr-setup.md#2-create-a-flex-query),
[Limitations](../../README.md#limitations), and `parse_trades`,
`parse_cash_dividends`, `parse_cash_report` and `filter_trades_by_holdings` in the
[runtime](../../ibkr_to_ghostfolio.py).
