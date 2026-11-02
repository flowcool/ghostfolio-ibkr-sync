# Spec Delta

## MODIFIED Requirements

### Requirement: Timezone prerequisites and parser compatibility

Before processing any account, missing or invalid IANA `TZ` SHALL force the entire run into `DRY_RUN`, prevent every Ghostfolio financial write, emit one WARNING line with the reason, and mention the forced preview in the final notification.

Every DETAIL dividend, payment-in-lieu, and withholding `CashTransaction.dateTime` SHALL use observed Flex form `YYYYMMDD;HHmmss TimeZone`. A missing, invalid, unknown, or ambiguous Flex suffix SHALL fail that account before any Ghostfolio financial write, including cash and platform updates, through the normal failure outcome; this failure SHALL NOT enable `DRY_RUN`. Other cash types retain their exemption from requiring a suffix. Every qualified timestamp on Trade, CashTransaction, ChangeInDividendAccrual, or CorporateAction SHALL accept only EST=-05:00 or EDT=-04:00. These fixed offsets identify the query account timezone, not the exchange timezone. No IANA lookup SHALL interpret a source token. Any other qualified token on any of these four record types SHALL fail the account before any financial write, including cash and platform updates. This failure SHALL use the existing cash preflight outcome and SHALL NOT force `DRY_RUN`. Resolve accepted timestamps to UTC before use. New tokens require a new change. The parser SHALL retain compatibility for explicitly unqualified forms that are already supported, but SHALL NOT label a qualified wall time as UTC. The host `TZ` SHALL NOT be used to guess a missing or unknown source zone.

Baseline: saved query 1671605 emitted 105 relevant timezone-qualified rows (`EST`/`EDT`); `tests/test_parsing.py::test_parse_ibkr_datetime_formats` currently asserts the incorrect UTC labelling for qualified rows; `ghostfolio_ibkr_sync/ibkr.py` currently removes the suffix before parsing.

#### Scenario: Parse qualified Flex timestamps
- **WHEN** `.venv/bin/python -m pytest -q tests/test_parsing.py -k 'parse_ibkr_datetime_formats or historical_diagnostic_parser'` runs with `20260113;231127 EST`, `20260713;231127 EDT`, an unqualified legacy value, an unknown abbreviation and an invalid suffix
- **THEN** EST resolves to `2026-01-14T04:11:27+00:00`, EDT resolves to `2026-07-14T03:11:27+00:00`, the legacy value keeps its documented compatibility, and unknown or invalid provenance returns no timestamp.

#### Scenario: Explicit tokens on US switch days
- **WHEN** parser fixtures cover `20260308;015900 EST`, `20260308;030000 EDT`, `20261101;013000 EDT` and `20261101;013000 EST`
- **THEN** the UTC results are respectively `2026-03-08T06:59:00+00:00`, `2026-03-08T07:00:00+00:00`, `2026-11-01T05:30:00+00:00` and `2026-11-01T06:30:00+00:00`; each token gives an unambiguous fixed offset.

#### Scenario: Preserve source and destination date evidence
- **WHEN** `.venv/bin/python -m pytest -q tests -k 'datetime_timezone_chain'` exercises trade, dividend, accrual and corporate-action fixtures at Tokyo, New York and London midnight boundaries
- **THEN** every consumer receives the same corrected instant, the source text and source calendar day remain available for diagnostics, and no consumer silently substitutes the old UTC-labelled wall time.

#### Scenario: Force whole-run preview for invalid TZ
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_preflight'` runs with absent/invalid `TZ` across multiple accounts
- **THEN** no account writes, one WARNING explains forced `DRY_RUN`, and the final notification includes the reason.

#### Scenario: Fail an account for missing Flex provenance
- **WHEN** `.venv/bin/python -m pytest -q tests/test_orchestration.py -k 'historical_diagnostic_preflight'` runs with valid `TZ`, missing or invalid suffixes on each relevant cash type, and an unknown qualified token on each of Trade, CashTransaction, ChangeInDividendAccrual and CorporateAction
- **THEN** the affected account fails before any financial write, including cash and platform updates, without enabling `DRY_RUN`; unrelated cash types retain only their exemption from requiring a suffix.

#### Scenario: Numbered validation gates
- **WHEN** the implementation acceptance record runs gates G1 parser unit tests, G2 all-caller chain tests, G3 identity and migration replay, G4 empty and golden Ghostfolio labs with midnight fixtures, G5 exact readback plus review output, and G6 tradeDate cross-check on every saved Flex XML `Trade` row that the connector imports
- **THEN** every gate passes on one immutable candidate; G6 requires an absolute distance of at most one calendar day between the converted UTC date and `tradeDate`; `CASH` and `OPT` rows are excluded because the import and review paths skip them before any date use, and FX `tradeDate` is a value date that can move across a weekend; any violation in an imported category blocks G6 and invalidates the token assumption; a failed gate blocks release and no stored date is rewritten. The retained replay has 776 rows (STK 686, CASH 86, OPT 4), with violations STK 0, CASH 12, OPT 0; the scoped result passes for all 686 imported rows.

## ADDED Requirements

### Requirement: Corporate-action security filtering before date use

Corporate-action Trade readers SHALL match the event security by ISIN and contract before parsing its date. CASH/FX rows without an ISIN SHALL NOT feed corporate-action dates, even when their UTC date differs from tradeDate by more than one day. G6 remains limited to imported asset categories.

#### Scenario: Excluded CASH dates do not feed corporate actions
- **WHEN** a retained CASH/FX Trade has no ISIN and its converted UTC date differs from tradeDate by more than one day
- **THEN** corporate-action source_chain, decide and history_conclusion exclude that row before date parsing; the event dates stay unchanged and G6 still applies only to imported categories.
