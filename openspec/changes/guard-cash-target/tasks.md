## 1. Remove the unused setting

- [ ] 1.1 Remove `GHOST_CURRENCY` from `load_config`, README and its test. Check: `.venv/bin/python -m pytest -q tests -k 'load_config'`.

## 2. Duplicate target

- [ ] 2.1 Refuse a duplicated Ghostfolio name in `load_config`, naming the target; offline tests cover duplicate and distinct names. Check: `.venv/bin/python -m pytest -q tests -k 'cash_target_duplicate'`.

## 3. Currency guard

- [ ] 3.1 Add `parse_base_currency` (`AccountInformation` `currency`) and extend the `report()` fixture. Check: `.venv/bin/python -m pytest -q tests -k 'base_currency_parse'`.
- [ ] 3.2 Compare currencies in `ghost_update_cash_balance` (error naming both, no PUT, account failed, GET kept under `DRY_RUN`, absent currency warns and skips); update the README "How it works", Create accounts and Limitations text. Check: `.venv/bin/python -m pytest -q tests -k 'cash_currency_guard'`.
