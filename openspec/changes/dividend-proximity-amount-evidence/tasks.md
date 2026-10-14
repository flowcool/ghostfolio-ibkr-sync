Execution order: 1.1, 2.1, 3.1, 4.1, 5.1. Code tasks start only after v3.0.0 stable is published (no code on main during the rc.1 soak, infra-5ex1).

## 1. Exclude connector rows from proximity

- [ ] 1.1 In `ghost_get_existing_orders` skip `dividend#` comments when building `dividend_dates`; in `process_account` drop only the post-import `dividend_dates` append and keep the `existing_dividend_comments.add`, so exact identity still dedups within the run. Offline test: canonical 25 on 07-15 then a distinct 100 on 07-16 gives two imports. Check: `.venv/bin/python -m pytest -q tests -k dividend_proximity_canonical`.

## 2. Visible proximity skip

- [ ] 2.1 Store `(date, gross, currency)` entries, compare with the source gross after minor-unit rounding, log INFO for equal and one WARNING for different or not comparable; exit status unchanged. Tests: manual equal gross, manual different gross, missing currency. Check: `.venv/bin/python -m pytest -q tests -k dividend_proximity_amount`.

## 3. Diagnostic mirror

- [ ] 3.1 In `_historical_proximity` exclude connector-comment rows and show source and candidate gross in the `skipped by proximity` block. Tests: only-canonical neighbour is not proximity-skipped; manual neighbour shows both values; import selection unchanged. Check: `.venv/bin/python -m pytest -q tests -k 'historical_diagnostic_skip_cause'`.

## 4. Docs

- [ ] 4.1 Update `docs/adr/0002` (canonical rows excluded, warning on amount difference), README line 51, the conversion-table Dividend row and the "Additive imports" limit, and `docs/ibkr-setup.md` line 123. Check: `rg -n -i 'proximity|±3 days|within 3 days' README.md docs/`.

## 5. Real validation

- [ ] 5.1 Real DRY_RUN of main after 4.1 against the prod Flex query (operation: needs a Florent-validated Operation plan; Ghostfolio read only, no write). Proof: dividend import selection equals the previous real dry run for the same Flex rows; count of proximity INFO and WARNING lines recorded (this measures the manual/legacy rows named in Non-goals); exit 0, ERROR 0. Check: the run log and the counts noted on the bead.
