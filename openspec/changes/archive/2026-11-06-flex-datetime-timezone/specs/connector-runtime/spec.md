# Spec Delta

## MODIFIED Requirements

### Requirement: Timezone prerequisites and parser compatibility

Before processing any account, missing or invalid IANA `TZ` SHALL force the entire run into `DRY_RUN`, prevent every Ghostfolio financial write, emit one WARNING line with the reason, and mention the forced preview in the final notification.

Every DETAIL dividend, payment-in-lieu, and withholding `CashTransaction.dateTime` SHALL use observed Flex form `YYYYMMDD;HHmmss TimeZone`. A missing, invalid, unknown, or ambiguous Flex suffix SHALL fail that account before any Ghostfolio financial write, including cash and platform updates, through the normal failure outcome; this failure SHALL NOT enable `DRY_RUN`. Other cash types retain their exemption from requiring a suffix. Every qualified timestamp on Trade, CashTransaction, ChangeInDividendAccrual, or CorporateAction SHALL accept only EST=-05:00 or EDT=-04:00. These fixed offsets identify the query account timezone, not the exchange timezone. No IANA lookup SHALL interpret a source token. Any other qualified token on any of these four record types SHALL fail the account before any financial write, including cash and platform updates. This failure SHALL use the existing cash preflight outcome and SHALL NOT force `DRY_RUN`. Resolve execution timestamps to UTC before use. Cash payment calendar days follow the separate rule below. New tokens require a new change. The parser SHALL retain compatibility for explicitly unqualified forms that are already supported, but SHALL NOT label a qualified wall time as UTC. The host `TZ` SHALL NOT be used to guess a missing or unknown source zone.

Baseline: the initial change corrected qualified execution instants with fixed EST/EDT offsets. Its cash consumer also converted ledger posting clocks. The calendar-day correction below separates these two uses.

#### Scenario: Parse qualified Flex timestamps
- **WHEN** `.venv/bin/python -m pytest -q tests/test_parsing.py -k 'parse_ibkr_datetime_formats or historical_diagnostic_parser'` runs with `20260113;231127 EST`, `20260713;231127 EDT`, an unqualified legacy value, an unknown abbreviation and an invalid suffix
- **THEN** EST resolves to `2026-01-14T04:11:27+00:00`, EDT resolves to `2026-07-14T03:11:27+00:00`, the legacy value keeps its documented compatibility, and unknown or invalid provenance returns no timestamp.

#### Scenario: Explicit tokens on US switch days
- **WHEN** parser fixtures cover `20260308;015900 EST`, `20260308;030000 EDT`, `20261101;013000 EDT` and `20261101;013000 EST`
- **THEN** the UTC results are respectively `2026-03-08T06:59:00+00:00`, `2026-03-08T07:00:00+00:00`, `2026-11-01T05:30:00+00:00` and `2026-11-01T06:30:00+00:00`; each token gives an unambiguous fixed offset.

#### Scenario: Preserve source and destination date evidence
- **WHEN** `.venv/bin/python -m pytest -q tests -k 'datetime_timezone_chain'` exercises trade, dividend, accrual and corporate-action fixtures at Tokyo, New York and London midnight boundaries
- **THEN** trades and corporate actions receive corrected execution instants, cash payments and accruals retain their written calendar day, the source text and source calendar day remain available for diagnostics, and no consumer silently substitutes the old UTC-labelled wall time.

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

### Requirement: Separate execution instants from payment calendar days

R1: Trade execution timestamps SHALL use the explicit EST/EDT offset and convert
to UTC. R2: `tradeDate` SHALL define the exchange business day. For KRX, TSEJ,
LSE, NASDAQ, NYSE, ARCA, BYX and TSE, compare it with the execution instant in
the known exchange zone. Missing or invalid evidence, or a mismatch, SHALL hold
the trade with a reason before import or review. Unknown venues SHALL remain
unchecked. Never infer a zone from currency or ticker. Exclude CASH/FX and OPT
rows before date use.

R3: Dividends, Payment In Lieu Of Dividends and Withholding Tax SHALL use the
calendar day written in `dateTime`. Validate the full timestamp and token first.
Do not use its posting clock as an execution instant. Anchor the payment day at
00:00 UTC. Use this day for grouping, withholding association, accrual matching,
deduplication, review and identity migration. `reportDate` SHALL NOT replace it.
Qualified accrual dates and date-only accruals SHALL use their written day.

R4: ENV `TZ` SHALL control local-day tolerance, diagnostic display and scheduling.
It SHALL equal the Ghostfolio server timezone. Startup SHALL log the validated
comparison timezone. It SHALL NOT change source values or canonical replacement
timestamps. Same-day suppression and profile eligibility can still depend on TZ.
R5: use Python stdlib `zoneinfo` only. Add no date library.

Ghostfolio 3.96.0 displays dates in the browser timezone and derives portfolio
valuation days in the server timezone. A date-only 00:00Z value can show or value
on the previous day west of UTC. This accepted limit SHALL be documented.
A noon-UTC anchor would avoid the demonstrated western-zone shift. It requires
historical-data conversion and a separate operator GO. This change SHALL NOT
convert stored activities or approve review proposals.

#### Scenario: Ledger clocks do not shift the payment day
- **WHEN** dividend, payment-in-lieu and withholding rows contain 19:00 through 23:59 EST/EDT, including US switch days
- **THEN** they keep the written day at 00:00 UTC, match accruals on that day, and never create a next-day date proposal from the posting clock.

#### Scenario: Exchange business-day mismatch
- **WHEN** an imported trade has a known venue and its execution day in that venue differs from `tradeDate`, or required date evidence is invalid
- **THEN** it is held with an explicit reason and produces no import or correction payload; unknown venues and excluded FX value dates are not guessed.

#### Scenario: Comparison timezone does not reinterpret broker values
- **WHEN** offline acceptance runs with Europe/Paris, Asia/Bangkok, America/Los_Angeles and Asia/Kolkata
- **THEN** converted source values and canonical replacement dates stay identical; local-day evidence and eligibility can differ; a compatible stored instant remains preserved.
