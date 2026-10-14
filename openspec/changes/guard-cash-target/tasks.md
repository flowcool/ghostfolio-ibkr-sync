## 1. Remove the unused setting

- [x] 1.1 Remove `GHOST_CURRENCY` from `load_config`, README and its test. Check: `.venv/bin/python -m pytest -q tests -k 'load_config'`.

## 2. Duplicate target

- [x] 2.1 Refuse a duplicated effective target in `load_config` (names, or IBKR ids when names are empty), naming the target; offline tests cover duplicate names, a repeated id without names, and distinct targets. Check: `.venv/bin/python -m pytest -q tests -k 'cash_target_duplicate'`.

## 3. Currency guard

- [x] 3.1 Add `parse_base_currency` (`AccountInformation` `currency`) and extend the `report()` fixture. Check: `.venv/bin/python -m pytest -q tests -k 'base_currency_parse'`.
- [ ] 3.2 Compare currencies in `ghost_update_cash_balance` (error naming both, no PUT, account failed, GET kept under `DRY_RUN`, absent currency: error, no PUT, account failed); update the README. Check: `.venv/bin/python -m pytest -q tests -k 'cash_currency_guard'`.
