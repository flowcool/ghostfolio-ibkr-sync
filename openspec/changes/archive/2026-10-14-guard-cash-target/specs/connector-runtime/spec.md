## ADDED Requirements

### Requirement: Cash target guard

Configuration SHALL refuse a `GHOST_ACCOUNT_NAMES` list where two effective targets, after trimming, are the same; when `GHOST_ACCOUNT_NAMES` is empty the targets are the IBKR account ids. The error SHALL name the duplicated target, and the run SHALL stop with a non-zero exit before any network call or write. Before a cash write, the IBKR base currency (the `AccountInformation` `currency` attribute) SHALL equal the `currency` of the Ghostfolio account returned by the existing account GET. On a difference the connector SHALL log an error naming both currencies, send no cash PUT, and mark the account failed. An absent base currency SHALL log an error naming the missing Flex field, send no cash PUT, and mark the account failed. Matching currencies SHALL behave as before. Under `DRY_RUN` the GET and the check SHALL still run; no PUT is sent.

#### Scenario: Duplicate target refused
- **WHEN** `.venv/bin/python -m pytest -q tests -k 'cash_target_duplicate'` runs with two IBKR accounts naming one Ghostfolio account, and with a repeated IBKR id and no names
- **THEN** configuration fails naming that target; no HTTP call is made.

#### Scenario: Currency mismatch
- **WHEN** `.venv/bin/python -m pytest -q tests -k 'cash_currency_guard'` runs with base currency and account currency different
- **THEN** one error names both currencies, no PUT is sent and the account is failed.

#### Scenario: Currency match
- **WHEN** the same command runs with equal currencies, live and under `DRY_RUN`
- **THEN** live sends the unchanged PUT; `DRY_RUN` logs the same "would set cash balance" value.

#### Scenario: Base currency absent
- **WHEN** `.venv/bin/python -m pytest -q tests -k 'base_currency_parse'` runs on a report without `AccountInformation` currency
- **THEN** none is returned; one error names the missing field, no PUT is sent and the account is failed.

## MODIFIED Requirements

### Requirement: Current operational limits

The connector SHALL retain documented boundaries: 365-day guidance; daily data; manual corporate actions/history/token renewal; additive corrections; proximity false matches; UTC dates; unconverted cash/commission currencies; Yahoo quality; net, nonchronological checks; nontransactional buy/sell phases; preview without server acceptance; buffered 10 MiB Flex responses; no overlap protection.

#### Scenario: Operator checks limits
- **WHEN** limitations are read
- **THEN** these boundaries are visible, and `GHOST_CURRENCY` is not documented as a setting.
