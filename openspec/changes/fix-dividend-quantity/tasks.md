# Tasks

Both slices implement “Flex selection and conversion” in `specs/connector-runtime/spec.md`; each takes one fresh session after approval.

## 1. Single-rate payments

- [ ] 1.1 Update `ibkr_to_ghostfolio.py`, `tests/test_parsing.py`, `tests/test_conversion.py` and README: strict rate formats, dividend/PIL order independence, missing-rate WARNING and legitimate one-share handling. Prove synthetic scenarios plus accounting/correction regressions with `python3 -m pytest -v tests/test_parsing.py tests/test_conversion.py`.

## 2. Ordinary and bonus components

- [ ] 2.1 In the same files, implement rounded common quantities, partial/incompatible fallback and component netting; update README. Run the same pytest command and the existing hash-bound offline replay recorded with the originating work item. Expected: groups=46, quantity_mismatches=0, multi_rate_groups=3, multi_rate_correct=3, no_rate_groups=1, no_rate_correct=1; all three ordinary/bonus quantities=100, with gross income, fees and identity preserved.
