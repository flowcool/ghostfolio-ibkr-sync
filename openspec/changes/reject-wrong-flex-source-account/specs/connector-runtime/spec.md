# Spec Delta

## ADDED Requirements

### Requirement: Flex source account gate

Before Ghostfolio target lookup, import, cash update, or other financial write, each fetched report SHALL contain at least one `AccountInformation` row. Every such row SHALL carry the same nonempty `accountId`, and that value SHALL equal the paired `IBKR_ACCOUNT_IDS` entry. Duplicate rows for that one account SHALL be accepted.

Missing, blank, mixed, or mismatched source-account evidence SHALL fail that account without a financial write. Other configured accounts SHALL continue through the existing sequential failure isolation. Logs and notifications SHALL NOT contain the observed report account value.

Baseline: `docs/ibkr-setup.md` requires `ClientAccountID` in Account Information, but `process_account` currently selects a Ghostfolio target by configured list order without validating it.

#### Scenario: Matching source account

- **WHEN** a synthetic report contains one or more `AccountInformation` rows whose nonempty `accountId` equals the paired configured IBKR account
- **THEN** target lookup and the existing import and cash paths continue unchanged.

#### Scenario: Unsafe source account evidence

- **WHEN** synthetic reports contain no Account Information, a missing or blank `accountId`, more than one account, or one account different from the paired configuration
- **THEN** the affected account fails before target lookup and every financial write, the observed account value is absent from logs and notifications, and later configured accounts still run.

Check: `.venv/bin/python -m pytest -q tests/test_parsing.py tests/test_orchestration.py -k 'source_account'`.
