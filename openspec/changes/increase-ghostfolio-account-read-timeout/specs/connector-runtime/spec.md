## ADDED Requirements

### Requirement: Account read timeout

Ghostfolio account list and account detail GET requests SHALL use a 120-second socket inactivity timeout. Cash PUT SHALL retain its 30-second timeout. Authentication, activity reads, redirect rejection, simulation and retry behavior SHALL remain unchanged.

Baseline: ghost_get_accounts and ghost_update_cash_balance use timeout=30. Existing redirect tests assert that value.

#### Scenario: Account reads with more time
- **WHEN** mocked account lookup and cash preflight requests complete successfully
- **THEN** both GET requests use timeout=120 and the cash PUT uses timeout=30.

#### Scenario: Read timeout before cash write
- **WHEN** a mocked cash preflight GET raises ReadTimeout in simulation or live mode
- **THEN** the exception propagates after one GET and no PUT occurs.

Check: `.venv/bin/python -m pytest -q tests/test_ghostfolio.py -k 'account_read_timeout or accounts_reject_redirect or cash_balance_get_rejects_redirect'`.
