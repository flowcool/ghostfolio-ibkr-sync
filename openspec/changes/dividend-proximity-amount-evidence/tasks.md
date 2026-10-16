Order: 1.1, 2.1, 3.1, 4.1, 5.1. Code starts only after v3.0.0 stable (rc.1 soak freeze, infra-5ex1).

## 1. Exclude connector rows from proximity

- [x] 1.1 In `ghost_get_existing_orders` skip `dividend#` comments when building `dividend_dates`; in `process_account` drop only the post-import `dividend_dates` append and keep the `existing_dividend_comments.add`, so exact identity still dedups within the run. Offline test: the mocked Ghostfolio GET returns a canonical row (25, 07-15); a distinct payment (100, 07-16) is imported; a rerun with the same GET plus that new row imports nothing. Check: `.venv/bin/python -m pytest -q tests -k dividend_proximity_canonical`.

## 2. Visible proximity skip

- [x] 2.1 Store `(date, gross, currency, fee)` entries. Update every consumer of the matcher return, including the readable report. Compare the exact source gross (`div["gross"]`) after minor-unit normalization; log INFO "amounts agree" with fee values for equal, one WARNING naming the operator action for different or not comparable (unsupported denomination); exit status unchanged. Tests: equal gross, different gross, GBp row vs GBP source, unsupported currency, equal numbers in different currencies (not comparable: one WARNING, still skipped), manual ordinary 25 + PIL 100 next day -> skipped with WARNING, readable report shows no raw tuple. Check: `.venv/bin/python -m pytest -q tests -k dividend_proximity_amount`.

## 3. Diagnostic mirror

- [x] 3.1 In `_historical_proximity` exclude connector-comment rows and show source and candidate gross in the `skipped by proximity` block. Mirror of 2.1, no new consumer work. Tests: only-canonical neighbour is not proximity-skipped; manual neighbour shows both values; import selection unchanged. Check: `.venv/bin/python -m pytest -q tests -k 'historical_diagnostic_skip_cause'`.

## 4. Docs

- [ ] 4.1 Update `docs/adr/0002` (canonical rows excluded, warning on amount difference, trust principle: a connector-comment row is ours, trusted by exact identity; a user edit of it is out of contract), README line 51, the conversion-table Dividend row and the "Additive imports" limit, and `docs/ibkr-setup.md` line 123. Check: `rg -n -i 'proximity|±3 days|within 3 days' README.md docs/`.

## 5. Real validation

- [ ] 5.1 Operation (needs a Florent-validated Operation plan; read only). On the same day, against the same Flex query, run the old main image and the new code with `DRY_RUN=1`; diff the dividend selections. Acceptance: the diff file exists and every difference is explained, both noted on the bead; INFO and WARNING counts recorded; exit 0, ERROR 0. Check: `diff <old-selection> <new-selection>`.
