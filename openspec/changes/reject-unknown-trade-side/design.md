## Decisions

- **Fix now.** Cheap guard against a phantom SELL, though no real sample exists (operator, 2026-10-14).
- **Reject in `convert_trade_to_activity`.** Where `activity_type` is chosen, return `None` unless `buySell` equals `BUY` or `SELL`, like the existing invalid quantity/price returns.
- **Reuse the per-row error path.** `run_sync` already logs "cannot be converted safely", counts `skipped_other` and sets `ok = False` for a `None`. `process_account` then reports `account_failed`: failure summary, exit 1. No new branch.
- **Holdings gate unchanged.** `prepared_trades` is built only from converted activities, and `filter_trades_by_holdings` receives their signed quantity. A rejected row never reaches it.
- **Other rows unaffected.** The loop continues; valid trades still import.
- **Additive.** Only the unknown row is ignored; the original trade stays (ADR 0003).
- **Flex query unchanged.**
- **Rollback.** Revert the merge commit.
