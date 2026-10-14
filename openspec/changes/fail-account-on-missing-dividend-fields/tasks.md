## 1. Upfront dividend field check

- [x] 1.1 Add the preflight, hoist the key lists, wire it after the time-zone check, with offline tests for the three scenarios in `specs/connector-runtime/spec.md`. Check: `.venv/bin/python -m pytest -v tests -k 'dividend_field_prerequisites or dividend_structured_input or historical_diagnostic_preflight'`.
  Also replay the private captures once, locally and uncommitted, with a one-off `python -c` that calls the new function on `tmp/sidecar-real-dryrun-20261014/flex.xml` (expect one ERROR naming only `conid`) and on `tmp/sidecar-diagnostic-dryrun-20261014/flex.xml` (expect none). Quote the output in the closing note; add no repository test for it.

## 2. Setup guide

- [ ] 2.1 In `docs/ibkr-setup.md`, replace the last paragraph (blocks new dividends with a warning) with the account-failure rule and the field-name list. Check: `rg -n -A6 'Required payment keys' docs/ibkr-setup.md`.
