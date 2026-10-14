# Tasks

## 1. Timezone prerequisites

- [ ] 1.1 Accept Flex timezone suffixes without changing general UTC conversion; validate IANA `TZ` and relevant cash-row suffixes before account writes; add parser, orchestration, exit, notification, and no-write tests. Verify `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_timezone'`.
- [ ] 1.2 Update README, `docs/ibkr-setup.md`, and configuration examples with required `TZ`, `HHmmss TimeZone`, staged activation, privacy, and rollback. Verify `rg -n 'HHmmss TimeZone|TZ|rollback' README.md docs/ibkr-setup.md`.

## 2. Actionable evidence

- [ ] 2.1 Split six identity checks, implement local-calendar comparison and unavailable/conflicting ISIN states, and add focused tests. Verify `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_actionable'`.
- [ ] 2.2 Render human anomaly blocks, failed-check counts, outside-window values, and non-certifying proximity explanations; test levels and privacy. Run the same actionable check plus `.venv/bin/python -m pytest -q tests/test_finalize.py`.

## 3. Real acceptance

- [ ] 3.1 With operator authorization, run one production-read-only `DRY_RUN`; verify zero writes, explain every formerly compound finding, reconcile both proximity skips, and record bounded evidence in the closing note.
