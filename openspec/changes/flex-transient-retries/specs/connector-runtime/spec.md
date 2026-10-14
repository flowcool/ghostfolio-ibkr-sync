# Spec Delta

## ADDED Requirements

### Requirement: Bounded SendRequest recovery

The connector SHALL retry a non-Success SendRequest response only for ErrorCode `1001`, `1004`, `1005`, `1006`, `1007`, `1008`, `1009`, `1018`, `1019` or `1021`. It SHALL make at most five SendRequest attempts, with waits of 60, 120, 300 and 600 seconds before subsequent attempts. These scheduled waits total 18 minutes; transport timeouts and network retries are additional.

Codes `1003`, `1010`–`1017`, `1020`, missing codes and unknown codes SHALL fail without application-level retry. Classification SHALL use ErrorCode, never message matching. Exhaustion SHALL fail with the final IBKR message, retaining credential redaction. Recovery SHALL use the successful response's reference and validated statement URL without changing financial processing.

Source: [IBKR Version 3 error table](https://www.ibkrguides.com/clientportal/performanceandstatements/flex3error.htm), checked 2026-10-14. The retry set follows descriptions that explicitly advise retrying; `1003` supplies no such advice. This is connector policy, not a guarantee of IBKR recovery.

#### Scenario: Transient error recovers
- **WHEN** mocked responses provide `1004` followed by Success and a ready statement
- **THEN** one 60-second wait occurs, the successful reference is used, and retrieval succeeds.

Check after implementation: `.venv/bin/python -m pytest -v tests/test_orchestration.py -k flex_transient_send_recovery`.

#### Scenario: Transient errors exhaust the budget
- **WHEN** every SendRequest attempt returns a retryable code
- **THEN** exactly five attempts and waits `[60, 120, 300, 600]` occur; the last message is reported without credentials and GetStatement is never called.

Check after implementation: `.venv/bin/python -m pytest -v tests/test_orchestration.py -k flex_transient_send_exhaustion`.

#### Scenario: Permanent and unclassified errors stop
- **WHEN** fixtures cover every retryable code and every immediate-failure code, including expired/invalid tokens `1012`/`1015`, a missing code, an unknown code and misleading messages
- **THEN** only the explicit retry set schedules another attempt; immediate failures make one request and preserve redacted error context.

Check after implementation: `.venv/bin/python -m pytest -v tests/test_orchestration.py -k flex_transient_send_classification`.

### Requirement: Extended statement polling and preserved guards

Default GetStatement polling SHALL allow 60 attempts at 5-second intervals, replacing 10 attempts. The existing Warn-or-1019 pending condition, explicit polling overrides, ready-response handling, timeout failure and immediate failure for other codes SHALL remain. Sixty consecutive pending responses SHALL retain the existing sleep-after-each-pending-response behavior: 300 seconds of scheduled waits followed by failure. Existing network retries, XML size limits, statement-host validation, ENV, financial-write guards, account outcomes and notifications SHALL remain unchanged.

Baseline: `tests/test_orchestration.py` Flex-fetch tests cover Warn, code-only 1019, explicit overrides, timeout, 1018 rejection and foreign hosts. `tests/test_parsing.py` covers response size guards.

#### Scenario: Longer generation recovers or expires
- **WHEN** mocked polling needs more than ten attempts or remains pending for all sixty attempts
- **THEN** a later ready statement succeeds, or polling fails after sixty attempts and 300 seconds of scheduled waits; explicit overrides and existing guards still pass.

Check after implementation: `.venv/bin/python -m pytest -v tests/test_orchestration.py tests/test_parsing.py -k 'flex_fetch or fetch_flex_report or flex_transient'`.

### Requirement: Retry guidance

README SHALL document the SendRequest retry set, immediate failures, five-attempt schedule, longer GetStatement window and additional transport time. It SHALL explain that exhaustion still fails the run and that no ENV change is required.

#### Scenario: Operator inspects retry policy
- **WHEN** `rg -n -A 22 'Flex retry policy' README.md` is run after implementation
- **THEN** the retry codes, 18-minute scheduled SendRequest wait, 300-second GetStatement wait, transport caveat and final failure behavior are visible.
