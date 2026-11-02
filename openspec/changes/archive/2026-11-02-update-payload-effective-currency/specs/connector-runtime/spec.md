# Connector runtime delta

## ADDED Requirements

### Requirement: Valid currency at activity update boundaries

The optional correction and identity-maintenance PUT paths SHALL send a valid
effective activity currency on every update payload. Cleanup comment PUTs SHALL validate their explicit currency before HTTP and
retain their existing refusal of null-currency rows. A null, empty or unresolved
payload currency SHALL block the update before HTTP. Additive imports and
independent cash updates retain their existing behavior.

#### Scenario: Offline DTO enforcement

- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k http_double_rejects_invalid_currency` submits a null, empty or non-ISO currency
- **THEN** the mock Ghostfolio endpoint rejects it before applying any row
  change, matching the deployed DTO contract.
