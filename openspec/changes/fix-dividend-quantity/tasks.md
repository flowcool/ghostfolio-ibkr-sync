# Tasks

Future implementation after approval; sequential fresh sessions, synthetic inputs/mocked HTTP.

## 1. Quantity and components

- [x] 1.1 Deliver selection/association/components/numeric scenarios in ibkr_to_ghostfolio.py, tests/test_parsing.py, tests/test_conversion.py and README. Run `.venv/bin/python -m pytest -v tests -k 'dividend_structured_quantity or dividend_structured_components or dividend_structured_numeric'` and baseline. Cover decimal conflicts/overflow/underflow/GBP→GBp/cash authority.

## 2. Input and integration

- [x] 2.1 Deliver compatibility/isolation/upgrade scenarios in ibkr_to_ghostfolio.py, tests/test_orchestration.py, tests/test_finalize.py, README and docs/ibkr-setup.md. Run `.venv/bin/python -m pytest -v tests -k dividend_structured_input` and inspection. Cover identity→dedup→quantity/relevant schema/unrelated rows/empty/short windows/local outcomes/retry/migration/rollback.
