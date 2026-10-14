# Tasks

Each task is one vertical slice of about one hour. Run offline checks with synthetic inputs and mocked HTTP. Real acceptance needs operator authorization and private logs.

## 1. Parser with timezone suffix

- [x] 1.1 Make `parse_ibkr_datetime()` accept `YYYYMMDD;HHmmss TimeZone`, including observed EST/EDT, without changing current UTC conversion; add compatibility tests. Verify `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_parser'`.

## 2. Prerequisites before writes

- [x] 2.1 Force whole-run `DRY_RUN` for missing/invalid IANA `TZ` before any account runs, with one WARNING and a final-notification mention. Keep Flex suffixes mandatory for dividends, PIL, and withholding: missing/invalid suffix fails the affected account before import, cash, or platform writes without enabling `DRY_RUN`. Test multiple accounts, no writes, failure outcomes, and notifications. Verify `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_preflight'`.

## 3. Separate identity evidence

- [x] 3.1 Split active/id/data-source/symbol/date/ISIN checks with expected/observed values; compare dates in local IANA `TZ`; treat absent profile ISIN as unavailable and permit amount comparison, while a nonempty conflict blocks identity. Cover six checks and Paris winter/summer dates. Verify `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_identity'`.

## 4. Readable findings and counts

- [x] 4.1 Render security/date/value anomaly blocks, failed-check counts, outside-window values, and non-certifying `skipped by proximity` explanations for both absent groups (label corrected by 4.2). Test levels, privacy, and notification compatibility. Verify `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_actionable'` and `.venv/bin/python -m pytest -q tests/test_finalize.py`.

- [x] 4.2 Pass the unmutated `existing_dividend_comments` set to `historical_dividend_comparison()`. Name the absent-group skip path in import-selection order: `(account_id, f"dividend#{symbol}#{date}") in existing_dividend_comments` yields `skipped by historical comment` with the carrying evidence rows and active status, else a proximity match yields `skipped by proximity`. For missing, unsupported or conflicting currency context, keep the reason and add a `currency context: source=… destination=… provenance=…` line. Do not change import selection or the supported currency list. Align the label text in README and `docs/ibkr-setup.md`, and state near the README supported-denomination list that the log shows the observed currency. Files: `ibkr_to_ghostfolio.py`, `tests/test_dividend_diagnostics.py`, `README.md`, `docs/ibkr-setup.md`. Verify `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_skip_cause or historical_diagnostic or representations or evidence'` and `.venv/bin/python -m pytest -q tests/test_finalize.py`.

## 5. README and user docs

- [x] 5.1 Update README, `docs/ibkr-setup.md`, and configuration examples with `TZ` forced-preview behavior, WARNING/final notification, mandatory `HHmmss TimeZone` and account failure, staged activation, privacy, and rollback. Verify `rg -n 'HHmmss TimeZone|TZ|DRY_RUN|WARNING|notification|rollback' README.md docs/ibkr-setup.md`.

## 6. Real dry-run acceptance

- [x] 6.1 With operator authorization and approved real-data ENV, run `DRY_RUN=1 LOG_LEVEL=DEBUG .venv/bin/python ibkr_to_ghostfolio.py` with private log capture. Verify zero financial writes; all 44 previously blocked groups passing active/id/data-source/symbol/local-date (ISIN pass or unavailable), then reaching exact amount comparison or staying uncertain only with `component partition identity not proven` or a currency-context finding showing the observed currency (no component assignment from amounts), matching the 39/3/2 replay baseline (any other cause or count fails and is reported); explain remaining anomalies; both absent groups logging `skipped by historical comment`, reconciled with their evidence rows; both unsupported-currency groups showing a `currency context:` line that names KRW; and record the command and bounded observed evidence in the closing note.
