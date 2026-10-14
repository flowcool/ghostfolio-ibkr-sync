## 1. Reject unknown side

- [x] 1.1 In `convert_trade_to_activity`, return `None` unless `buySell` is exact `BUY` or `SELL`; offline tests: unknown values return `None`, BUY/SELL unchanged. Check: `.venv/bin/python -m pytest -q tests -k 'unknown_trade_side_conversion'`.

## 2. Run behavior and docs

- [x] 2.1 Offline `run_sync` test with a synthetic `SELL (Ca.)` beside valid rows: error logged, account not ok, row absent from the holdings gate, valid rows imported. Update the README Trade conversion row. Check: `.venv/bin/python -m pytest -q tests -k 'unknown_trade_side_run'`.
