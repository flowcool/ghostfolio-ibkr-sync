# Spec Delta

## MODIFIED Requirements

### Requirement: Unique matching and business dates

Every automatic association SHALL have the same mapped destination account, operation type, resolved security and compatible denomination. A conflicting nonempty ISIN SHALL exclude a candidate. Active YAHOO profiles and existing source validity checks SHALL remain required. A recognized v2 reference to another event SHALL exclude proximity matching. Resolve the security through the existing explicit mapping and supported aliases; a guessed symbol change SHALL NOT establish identity.

The conservative profile SHALL require a recognized unique source reference. Balanced and permissive profiles SHALL also accept unreferenced activities and ambiguous legacy dividend aliases when the complete current candidate set resolves to unique pairs. Fees SHALL NOT exclude, rank or disambiguate candidates. There SHALL be exactly one eligible target per source and one eligible source per target after all profile criteria and valid pair rejections. Never greedily select a candidate by row order, nearest time or smallest amount difference. An exact reference SHALL take precedence over proximity; a conflicting exact candidate SHALL NOT be ignored to obtain a proximity match. Threshold matches SHALL remain labelled `profile match`, not `exact identity`.

Compare dates from the canonical activity value in configured `TZ`, which must equal the Ghostfolio server timezone. Trades use their execution instant. Cash dividends use the written payment calendar day at 00:00 UTC, without converting the posting clock. The same local calendar day SHALL be date-compatible even when intraday instants differ. It SHALL produce no date proposal and SHALL remain eligible for comment-only migration when all other checks pass. Preserve its stored instant. A different local day SHALL be a real date difference and require the existing reviewed correction path. Conservative and balanced corrections SHALL retain the same local calendar day. Permissive corrections SHALL allow inclusive distance of two calendar days for BUY/SELL and three for DIVIDEND. Include weekends; do not infer exchange holidays. Use execution conversion for trades and corporate actions. Use the written calendar day for cash payments and accruals. Stored values and canonical replacement dates do not depend on `TZ`. Keep raw source text, UTC instants, local dates, source zone, configured timezone and actual elapsed difference visible. Missing, unknown or unsupported source timezone evidence SHALL refuse automatic date correction. A corrected date SHALL not change the event-only `IBKR#v2` comment; it SHALL change candidate and migration evidence when the date is part of the matching proof.

#### Scenario: Unique candidates and date boundaries
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k unique_matching` covers EST/EDT, Tokyo, London and New York midnight, DST, inclusive local-date edges, exact references and mapped aliases
- **THEN** only mutually unique supported pairs pass; ambiguity stays visible; profile matches are not labelled exact; corrected UTC instants and configured local days control selection.

#### Scenario: Identity and migration effect
- **WHEN** `python -m pytest -q tests/test_identity_migration.py -k 'timezone or legacy_migration'` replays one event before and after corrected timestamp conversion
- **THEN** `IBKR#v2#<account>:<kind>:<source-id>` remains the same event identity, and a stored date on the same configured local day remains eligible for comment-only migration despite an intraday difference; a different local day excludes comment-only migration and requires reviewed date correction within the active profile limits or manual approval.
