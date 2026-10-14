## 1. Classification

- [x] 1.1 Wait for task 1.1 of `fail-account-on-missing-dividend-fields` to merge. Then classify gross/fee deltas (noise, minimal difference for every currency including a 0.01 EUR or USD case, other) and quantity deltas, with offline tests. Check: `.venv/bin/python -m pytest -v tests -k 'dividend_readable_classes'`.
- [ ] 1.2 Add probable-duplicate, equal-total split and absent/outside-coverage pair detection, with offline tests. Check: `.venv/bin/python -m pytest -v tests -k 'dividend_readable_pairs'`.

## 2. Report text

- [ ] 2.1 Rewrite the finding blocks (plain reason, values, action line, no-write statement, no Python text) and the summary line. Check: `.venv/bin/python -m pytest -v tests -k 'dividend_readable_report'`.

## 3. Real validation

- [ ] 3.1 Reuse the operator-validated production DRY_RUN operation plan (no new plan; the work item is an operation) and capture the log privately. Check: `rg -c "Decimal\(|[0-9]E-[0-9]" <log>` prints 0, and the summary counts match the scenario.
