## ADDED Requirements

### Requirement: Dividend field prerequisites

Before any Ghostfolio financial write, including cash and platform updates, each account's Flex report SHALL be checked for the dividend attributes the connector requires. A report with no relevant DETAIL cash rows (`Dividends`, `Payment In Lieu Of Dividends`, `Withholding Tax`) SHALL pass without this check, in `DRY_RUN` as in live runs.

An attribute SHALL be missing when no row of its section carries it. Required `CashTransaction` attributes on those rows SHALL be `accountId`, `conid`, `currency`, `actionID` and `exDate`. `ChangeInDividendAccruals` SHALL be mandatory once relevant cash rows exist. When that section has rows, its attributes SHALL cover the cash keys plus `quantity`, `code`, `date`, `payDate` and `reportDate`. A present but empty section SHALL stay valid.

A missing attribute or section SHALL fail the account through the normal failure outcome with one ERROR line. The line SHALL name every missing XML attribute with the IBKR field to select, and SHALL NOT enable `DRY_RUN`. A single empty or malformed value SHALL keep the local rejection of "Enriched dividend input and local rejection".

#### Scenario: Cash field not ticked
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'dividend_field_prerequisites'` runs a report with dividend rows but no `conid`, and no new dividend
- **THEN** the account fails before any write with one ERROR naming `conid` and its IBKR field, and `DRY_RUN` stays unchanged.

#### Scenario: Complete or empty report
- **WHEN** the same command runs a complete report, a report without relevant cash rows, and a present empty accrual section
- **THEN** no prerequisite error is logged and outcomes are unchanged.

#### Scenario: Isolated bad row
- **WHEN** the same command runs a report where one row has an empty `conid` and the attribute exists elsewhere
- **THEN** the account does not fail on prerequisites and the row keeps its local rejection.
