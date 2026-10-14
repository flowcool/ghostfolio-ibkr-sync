# Tasks

Each task is one vertical slice of about one hour. Run offline checks with synthetic inputs and mocked HTTP. Real acceptance needs operator authorization and private logs.

## 1. Parser with timezone suffix

- [ ] 1.1 Make `parse_ibkr_datetime()` accept `YYYYMMDD;HHmmss TimeZone`, including observed EST/EDT, without changing current UTC conversion; add compatibility tests. Verify `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_parser'`.

## 2. Prerequisites before writes

- [ ] 2.1 Force whole-run `DRY_RUN` for missing/invalid IANA `TZ` before any account runs, with one WARNING and a final-notification mention. Keep Flex suffixes mandatory for dividends, PIL, and withholding: missing/invalid suffix fails the affected account before import, cash, or platform writes without enabling `DRY_RUN`. Test multiple accounts, no writes, failure outcomes, and notifications. Verify `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_preflight'`.

## 3. Separate identity evidence

- [ ] 3.1 Split active/id/data-source/symbol/date/ISIN checks with expected/observed values; compare dates in local IANA `TZ`; treat absent profile ISIN as unavailable and permit amount comparison, while a nonempty conflict blocks identity. Cover six checks and Paris winter/summer dates. Verify `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_identity'`.

## 4. Readable findings and counts

- [ ] 4.1 Render security/date/value anomaly blocks, failed-check counts, outside-window values, and non-certifying `skipped by proximity` explanations for both absent groups. Test levels, privacy, and notification compatibility. Verify `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_actionable'` and `.venv/bin/python -m pytest -q tests/test_finalize.py`.

## 5. README and user docs

- [ ] 5.1 Update README, `docs/ibkr-setup.md`, and configuration examples with `TZ` forced-preview behavior, WARNING/final notification, mandatory `HHmmss TimeZone` and account failure, staged activation, privacy, and rollback. Verify `rg -n 'HHmmss TimeZone|TZ|DRY_RUN|WARNING|notification|rollback' README.md docs/ibkr-setup.md`.

## 6. Real dry-run acceptance

- [ ] 6.1 With operator authorization and approved real-data ENV, run `DRY_RUN=1 LOG_LEVEL=DEBUG .venv/bin/python ibkr_to_ghostfolio.py` with private log capture. Verify zero financial writes and all 44 previously blocked groups reaching amount comparison; explain remaining anomalies, reconcile both proximity skips, and record the command and bounded observed evidence in the closing note.
