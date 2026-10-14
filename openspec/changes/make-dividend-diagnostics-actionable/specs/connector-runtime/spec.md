# Spec Delta

## ADDED Requirements

### Requirement: Timezone-qualified actionable dividend evidence

`TZ` SHALL be a valid IANA zone. Every DETAIL dividend, payment-in-lieu, and withholding `CashTransaction.dateTime` SHALL use observed Flex form `YYYYMMDD;HHmmss TimeZone`. Invalid timezone input SHALL fail that account before any Ghostfolio financial write, including cash, through the normal failure outcome; it SHALL NOT enable `DRY_RUN`. Other cash types remain outside validation.

The source `YYYYMMDD` SHALL remain the IBKR business day. Historical identity SHALL compare it with the destination instant's calendar day in `TZ`; general trade/import UTC conversion SHALL remain unchanged. An absent destination profile ISIN SHALL be unavailable evidence, while a nonempty conflict SHALL fail identity.

Dry-run details SHALL name each failed or unavailable active/id/data-source/symbol/date/ISIN check with expected/observed values. Human blocks SHALL show security, source and destination UTC/local dates, activity IDs, and supported quantity/gross/fee/currency. INFO SHALL count failed checks. Canonically absent sources suppressed by proximity SHALL remain absent but show `skipped by proximity` and weak-candidate values. Outside-window rows SHALL show destination security, date, and values. No finding SHALL repair data or change selection.

Baseline: saved query 1671605 emitted 105 relevant timezone-qualified rows (`EST`/`EDT`); the v2.5.0 dry run emitted 114 opaque findings.

#### Scenario: Timezone preflight and calendar identity
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_timezone'` runs with Paris winter/summer, `EST`/`EDT`, and invalid inputs
- **THEN** local calendar matches certify date, valid imports keep existing UTC conversion, and invalid accounts perform no financial write and fail normally.

#### Scenario: Actionable private report
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_actionable'` exercises six identity checks, outside-window rows, and proximity skips
- **THEN** private human-readable details and aggregate counts expose the required evidence without certifying weak identity or changing data.
