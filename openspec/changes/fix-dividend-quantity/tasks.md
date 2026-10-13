# Tasks

Future implementation only; sequential fresh sessions after approval. Commands require passing assertions. Synthetic inputs and mocked HTTP only.

## 1. Rates and portions

- [ ] 1.1 Deliver “Rates and portions” and preserve “Selected records”: update ibkr_to_ghostfolio.py, tests/test_parsing.py, tests/test_conversion.py and README. Prove token/currency validation, dividend/PIL row-order independence, numerical limits and reasoned fallback with `python3 -m pytest -v tests/test_parsing.py tests/test_conversion.py -k dividend_forward_rates`.

## 2. Components and compatibility

- [ ] 2.1 Deliver “Components and uncertainty” and “Upgrade inspection” in the same files. Cover equal-rate/labelled-PIL components, unique correction, partial/incompatible/ambiguous evidence, mixed currencies, legitimate one-share and accounting preservation. Run `python3 -m pytest -v tests/test_parsing.py tests/test_conversion.py` and the README inspection command; update inference, compatibility and recovery guidance. No historical repair is claimed.
