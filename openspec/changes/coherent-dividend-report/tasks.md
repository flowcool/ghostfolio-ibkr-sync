# Tasks

## 1. One report identity and linked summary

- [ ] 1.1 In `ibkr_to_ghostfolio.py`, make canonical ISIN and legacy symbol dividend comments claim the same source group before identity checks, account for each destination row once, and include the report counts in the DRY_RUN dividend import line. Add focused cases to `tests/test_dividend_diagnostics.py` and `tests/test_orchestration.py`. Verify with `.venv/bin/python -m pytest -q tests/test_dividend_diagnostics.py tests/test_orchestration.py -k 'coherent_dividend_legacy_identity or coherent_dividend_import_summary'`.

## 2. Coherent plain report

- [ ] 2.1 In `ibkr_to_ghostfolio.py`, define explicit currency minor units including zero-decimal JPY and KRW, separate missing/conflicting/unsupported currency reasons, quantize every displayed monetary value with round-half-away-from-zero, render deterministic plain summaries and `unavailable`, and emit exactly one `Action:` line per block with no `Proposed action:` line. Update `tests/test_dividend_diagnostics.py` and `tests/test_check_dividend_report.py`. Verify with `.venv/bin/python -m pytest -q tests/test_dividend_diagnostics.py tests/test_check_dividend_report.py -k 'coherent_dividend_currency or coherent_dividend_format or coherent_dividend_action or check_dividend_report'`.

## 3. Proven one-unit legacy rounding

- [ ] 3.1 In `ibkr_to_ghostfolio.py`, retain the finite `grossRate` from the unique matched payment `Re` only for a source group with one net-positive action, and classify only the complete equal-quantity/equal-fee pattern whose Ghostfolio gross equals quantity × rate and whose IBKR paid gross differs by one minor unit. Render `legacy declared-rate rounding`, the known cause, and the optional manual unit-price correction. Add positive JPY cases in both directions and missing-rate, multi-action and other negative boundary cases to `tests/test_dividend_diagnostics.py`. Verify with `.venv/bin/python -m pytest -q tests/test_dividend_diagnostics.py -k 'coherent_dividend_declared_rate or coherent_dividend_one_jpy'`.

## 4. Real report acceptance

- [ ] 4.1 After tasks 1-3 are merged, run one Florent-authorized real DRY_RUN from the fixed `main` under a validated operation plan. Prove zero financial writes. Run `python3 scripts/check_dividend_report.py <private-log>` and require exit 0 with zero violations. Read every dividend block. Report one verdict per block to Florent without private amounts or identifiers. Verify that the operation note contains the pinned commit, dry-run proof, checker output, block count and complete reading verdict.
