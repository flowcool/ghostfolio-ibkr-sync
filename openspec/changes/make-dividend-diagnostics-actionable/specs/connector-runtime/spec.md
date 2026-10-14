# Spec Delta

## ADDED Requirements

### Requirement: Timezone prerequisites and parser compatibility

Before processing any account, missing or invalid IANA `TZ` SHALL force the entire run into `DRY_RUN`, prevent every Ghostfolio financial write, emit one WARNING line with the reason, and mention the forced preview in the final notification.

Every DETAIL dividend, payment-in-lieu, and withholding `CashTransaction.dateTime` SHALL use observed Flex form `YYYYMMDD;HHmmss TimeZone`. A missing or invalid Flex suffix SHALL fail that account before any Ghostfolio financial write, including cash and platform updates, through the normal failure outcome; this failure SHALL NOT enable `DRY_RUN`. Other cash types remain outside suffix validation. The parser SHALL accept the qualified form without changing current UTC conversion for trades or imports.

Baseline: saved query 1671605 emitted 105 relevant timezone-qualified rows (`EST`/`EDT`); v2.5.0 returns `None` for this format.

#### Scenario: Parse qualified Flex timestamps
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_parser'` runs with qualified and existing unqualified formats
- **THEN** qualified timestamps parse successfully and current UTC conversion remains unchanged.

#### Scenario: Force whole-run preview for invalid TZ
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_preflight'` runs with absent/invalid `TZ` across multiple accounts
- **THEN** no account writes, one WARNING explains forced `DRY_RUN`, and the final notification includes the reason.

#### Scenario: Fail an account for missing Flex provenance
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_preflight'` runs with valid `TZ` and missing/invalid suffixes on each relevant cash type
- **THEN** the affected account fails before any financial write, including cash and platform updates, without enabling `DRY_RUN`.

### Requirement: Actionable historical dividend evidence

The source `YYYYMMDD` SHALL remain the IBKR business day. Historical identity SHALL compare it with the destination instant's calendar day in `TZ`. An absent destination profile ISIN SHALL be unavailable evidence and SHALL NOT block amount comparison; a nonempty conflict SHALL fail identity.

Dry-run details SHALL name each failed or unavailable active/id/data-source/symbol/date/ISIN check with expected/observed values. Human blocks SHALL show security, source and destination UTC/local dates, activity IDs, and supported quantity/gross/fee/currency. INFO SHALL count failed checks. Canonically absent sources suppressed by proximity SHALL remain absent but show `skipped by proximity` and weak-candidate values. Outside-window rows SHALL show destination security, date, and values. No finding SHALL repair data or change selection.

Baseline: the v2.5.0 dry run emitted 114 opaque findings. Saved evidence measured missing profile ISIN in 44/44 groups, Paris-midnight dates in 5/44, and no other failed identity checks.

#### Scenario: Separate identity checks and local dates
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_identity'` exercises all six checks, Paris winter/summer dates, absent ISIN, and conflicting ISIN
- **THEN** each check exposes expected/observed values, local calendar matches certify date, missing ISIN permits amount comparison, and conflicting ISIN blocks it.

#### Scenario: Actionable private report
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_actionable'` exercises outside-window rows and proximity skips
- **THEN** private human-readable details and aggregate counts expose the required evidence without certifying weak identity or changing data.

#### Scenario: Real read-only acceptance
- **WHEN** the operator-authorized `DRY_RUN=1 LOG_LEVEL=DEBUG .venv/bin/python ibkr_to_ghostfolio.py` runs with the approved real-data ENV and private log capture
- **THEN** zero financial writes occur, all 44 previously blocked groups reach amount comparison, every remaining anomaly is explainable from the log, and both proximity skips are reconciled with evidence.
