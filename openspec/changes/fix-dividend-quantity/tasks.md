# Tasks

Implement sequentially after approval, one fresh session per slice. Requirement/scenario names refer to specs/connector-runtime/spec.md. Each slice includes tests and required user documentation. No production financial write is an acceptance command.

## 1. Rate evidence and distribution quantities

- [ ] 1.1 Implement “Flex selection and conversion” rate validation and single-distribution dividend/PIL reconciliation in ibkr_to_ghostfolio.py, tests/test_parsing.py, tests/test_conversion.py and README. Prove row-order independence, currency/token validation, overflow and unrepresentable-quantity fallback with `python3 -m pytest -v tests/test_parsing.py tests/test_conversion.py`; preserve accounting and legitimate one-share handling.
- [ ] 1.2 Implement ordinary/bonus association, equal-rate components, labelled PIL portions and uniquely cancellable corrections in the same files. Prove “Distribution portions and common quantities” and “Corrected component and uncertain evidence” with the same command; retain conservative unresolved results for ambiguous corrections.

## 2. Durable evidence and existing dividends

- [ ] 2.1 Implement “Explicit dividend quantity repair” offline planning only in cleanup_dividends.py and cleanup_recovery.py, with tests/test_cleanup_recovery.py and docs/cleanup.md. Add private keyed YAML evidence, exact ownership/identity, originals/proposals, source hashes and collision protection. Verify with `python3 -m pytest -v tests/test_cleanup_recovery.py -k dividend_quantity_plan`; no apply or live requests.
- [ ] 2.2 Implement “Mapping and duplicate reconciliation” comparison before suppression in ibkr_to_ghostfolio.py and tests/test_orchestration.py; reuse the plan representation, preserve daily additive behavior and update README and ADR 0002/0003 wording. Verify unique canonical matches, unresolved proximity/multiple/redacted cases and refusal of monetary repair with `python3 -m pytest -v tests/test_orchestration.py -k dividend_existing_reconciliation`. Existing work owns monetary-revision delivery; no duplicate task here.
- [ ] 2.3 Implement “Persistent unresolved dividend” lifecycle and ENV-configured private durable storage in ibkr_to_ghostfolio.py, tests/test_orchestration.py and README. Verify repeat runs, persistence failure, later verified resolution, out-of-window retention and dry-run journal preservation with `python3 -m pytest -v tests/test_orchestration.py -k dividend_unresolved_lifecycle`; retain independent valid imports/cash updates.

## 3. Visible degraded outcomes

- [ ] 3.1 Implement “Unresolved reconciliation is visible” in ibkr_to_ghostfolio.py, tests/test_outcome.py, tests/test_finalize.py and README: unresolved exceptions/corrections produce exit 1 and one configured sanitized summary; ordinary warnings stay unchanged. Run `python3 -m pytest -v tests/test_outcome.py tests/test_finalize.py tests/test_token_expiry.py`; prove repeat visibility, delivery failure and dry-run silence.

## 4. Explicit historical maintenance

- [ ] 4.1 Implement “Explicit dividend quantity repair” apply and exact readback in cleanup_dividends.py/cleanup_recovery.py; extend tests/test_cleanup_recovery.py and docs/cleanup.md. Run `python3 -m pytest -v tests/test_cleanup_recovery.py -k dividend_quantity_repair`; prove explicit-only writes, unchanged gross/fee/metadata and repeated apply without another PUT, while preserving duplicate cleanup behavior.
- [ ] 4.2 Implement explicit resume/restore in the same files and docs. Verify “Stale plan, interruption and restore” with `python3 -m pytest -v tests/test_cleanup_recovery.py -k dividend_quantity_recovery`; prove stale ownership/values refusal, timeout readback, conflict refusal and restoration of originals without DELETE or reinjection.

## 5. Integrated reference acceptance

- [ ] 5.1 Run `python3 -m pytest -v tests/test_parsing.py tests/test_conversion.py tests/test_orchestration.py tests/test_outcome.py tests/test_finalize.py tests/test_cleanup.py tests/test_cleanup_recovery.py`, plus the originating item's hash-bound real-report replay. Extend that replay with independent source gross/withholding sums, minor-unit scaling, exact identity/account/date checks and captured WARNING assertions. Expect groups=46, quantity_mismatches=0, multi_rate_groups=3, multi_rate_correct=3, no_rate_groups=1, no_rate_correct=1, all ordinary/bonus quantities=100, accounting_identity_checked=46 and unresolved_no_rate_groups=1. Synthetic saved destination snapshots prove before/after proposals and recovery without service access; they do not claim ten actual stored activities were repaired. Keep unresolved PIL actionable and reliable quantity-one free of fallback warnings. Review projected-helper propagation if those units changed; publish the main spec only through normal archive after delivery.
