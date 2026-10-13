# Tasks

Future implementation only; sequential fresh sessions after approval. Synthetic inputs/mocked HTTP only.

## 1. Quantity and components

- [ ] 1.1 Deliver “Selected records”, “Quantity association” and “Components and money” in ibkr_to_ghostfolio.py, tests/test_parsing.py, tests/test_conversion.py and README. Run `python3 -m pytest -v tests -k 'dividend_structured_quantity or dividend_structured_components'` and the baseline command. Document IBKR quantity, cash authority and removed inference.

## 2. Input and integration

- [ ] 2.1 Deliver “Compatibility and isolation” and “Upgrade inspection” in ibkr_to_ghostfolio.py, tests/test_orchestration.py, tests/test_finalize.py, README and docs/ibkr-setup.md. Run `python3 -m pytest -v tests -k dividend_structured_input` and the inspection command. Cover schema, empty/short-window evidence, dedup-before-quantity, local outcomes, retry, migration and rollback.
