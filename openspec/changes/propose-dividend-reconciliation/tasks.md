## 1. Rules

- [ ] 1.1 Build the candidate set and strong/weak confidence per IBKR dividend (same security, local day, gross, fee), including coherent twins, offline. Check: `.venv/bin/python -m pytest -v tests -k 'dividend_match_strong'`.
- [ ] 1.2 Add the weak rules (proximity window, quantity gap, one-unit gap), tie-breaks and "no confident match", offline. Check: `.venv/bin/python -m pytest -v tests -k 'dividend_match_weak'`.

## 2. Report text

- [ ] 2.1 Render the "Proposed match" section with labels and action line in every block of the dividend; prove classes, counts and exits are unchanged. Check: `.venv/bin/python -m pytest -v tests -k 'dividend_match_unchanged'`.

## 3. Real validation

- [ ] 3.1 Reuse the operator-validated production DRY_RUN operation plan (no new plan; the work item is an operation) and capture the log privately. Check: `rg -c "Decimal\(|[0-9]E-[0-9]" <log>` prints 0, every item to check shows a proposed match or "no confident match", and the summary counts match the scenario.
