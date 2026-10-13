# Spec Delta

Commands run offline from the repository root. New test names are planned checks; passing assertions are required, not empty selections. Private reference evidence stays outside Git.

## MODIFIED Requirements

### Requirement: Flex selection and conversion

The connector SHALL select Trade children, exclude CASH/OPT, aggregate DETAIL dividend/payments-in-lieu/withholding by security/day, and select BASE_SUMMARY cash. Other cash types/levels and AssetSummary SHALL be ignored. Trade type SHALL be BUY for exact BUY, otherwise SELL. Quantities/prices SHALL be absolute; commission/withholding costs become fees, refunds/rebates clamp to zero. Nonpositive payments SHALL skip.

Dividend rates SHALL accept positive finite `<CCY> <rate> PER SHARE` tokens with optional decimals and valid comma thousands grouping. Rate currency SHALL equal payment currency. Malformed, conflicting or unusable tokens SHALL NOT supply quantity evidence.

The connector SHALL distinguish ordinary/bonus distributions from dividend/PIL portions before counting distinct rates. Signed rows SHALL cancel only with unique compatible opposite rows within the same payment type, distribution label, currency and rate. Ambiguous cancellation, partial reversals or conflicting surviving rates SHALL leave quantity unresolved. Cancelled rates SHALL NOT determine replacement quantities. Row order SHALL NOT change unambiguous results. Unlabelled or unmatched portions with multiple possible distributions SHALL remain unresolved.

Each distribution SHALL derive quantity from its combined surviving dividend/PIL amount and usable rate. An unrated PIL SHALL NOT erase a usable rate in its unambiguously associated distribution. Separate ordinary/bonus distributions SHALL retain their common quantity once, only when all independently derived quantities agree after existing rounding: whole shares within strictly 1%, then six decimals. Derived quantity and total-derived price SHALL be positive, finite and representable. Equal rates across separate distributions SHALL NOT collapse them into combined-amount/rate.

Reconciliation SHALL precede fallback. Missing, malformed, partial, ambiguous or incompatible evidence SHALL preserve a new positive payment as quantity 1 and total-derived price, plus a reasoned WARNING and unresolved exception. A reliably derived one-share quantity SHALL NOT create that exception. Gross income, withholding, minor-unit scaling, account/date/currency and stable comment identity SHALL remain preserved. README SHALL describe inferred quantity and provisional fallback.

#### Scenario: Selected records
- **WHEN** Flex rows are parsed/converted
- **THEN** existing selection applies; London GBP price/fee scale together to GBp.

Baseline: README conversion table; `python3 -m pytest -q tests/test_parsing.py tests/test_conversion.py`.

#### Scenario: Complete rate validation
- **WHEN** rates include `1,234`, `12,34`, a mismatched currency, conflicting tokens, a finite rate causing overflow, or a quantity rounded to zero
- **THEN** only usable matching-currency evidence derives quantity; other cases preserve income with an unresolved fallback, without a conversion crash.

Check: `python3 -m pytest -v tests/test_conversion.py -k dividend_rate_format`.

#### Scenario: Distribution portions and common quantities
- **WHEN** dividend 20/0.25 plus unrated PIL 5, ordinary 25/0.25 plus bonus 75/0.75, or ordinary 25/0.25 plus bonus 25/0.25 appear in either order
- **THEN** quantities are respectively 100, 100 and 100; gross incomes are 25, 100 and 50. Independently labelled PIL portions contribute only to their matching distribution; rounded-compatible components agree.

Check: `python3 -m pytest -v tests/test_parsing.py -k dividend_component_quantity`.

#### Scenario: Corrected component and uncertain evidence
- **WHEN** ordinary 25/0.25 is uniquely cancelled by -25/0.25 and replaced by 30/0.30 alongside bonus 75/0.75, or evidence is partial/incompatible/ambiguous
- **THEN** the corrected group has quantity 100 and gross 105 in either row order; uncertain groups retain gross as provisional one-unit payments. Refunds, nonpositive totals and minor units remain preserved; reliable one-share cases have no fallback warning.

Check: `python3 -m pytest -v tests/test_parsing.py tests/test_conversion.py -k dividend_reconciliation_accounting`.

### Requirement: Mapping and duplicate reconciliation

Mapping SHALL prefer ISIN mappings, then IBKR symbols. Trade IDs SHALL suppress reimport. Manual matching SHALL use quantity and ±2 days, including summed fills; nearby mismatches SHALL warn/skip. Dividends SHALL retain account/comment or account/symbol-at-±3-days duplicate suppression.

Before suppressing a dividend, the connector SHALL compare source-backed quantity/price against complete existing evidence. Only one active same-account canonical dividend identity, with verified security, currency and date, SHALL support a correction proposal. Legacy/manual/proximity-only matches, multiple candidates or incomplete evidence SHALL remain unresolved; proximity SHALL NOT prove payment identity. Proposals SHALL preserve gross income and fee and show originals, proposed quantity/price and evidence. Monetary/withholding differences SHALL be reported without a quantity-only repair. Already imported provisional quantities SHALL remain unresolved until source evidence and stored values verify resolution.

#### Scenario: Existing entries
- **WHEN** entries match under existing trade/dividend rules
- **THEN** duplicate suppression remains; manual-buy exclusions warn; financial agreement closes reconciliation only with sufficient unique evidence.

Baseline: `python3 -m pytest -q tests/test_filters.py tests/test_orchestration.py -k 'test_dividend_match_window_is_exactly_three_days or test_manual'`.

#### Scenario: Existing dividend needs correction
- **WHEN** source evidence implies quantity 100 and gross 25 while the unique canonical stored activity has quantity 1 and price 25
- **THEN** propose quantity 100 and price 0.25 with unchanged fee, date and identity; send no activity mutation or duplicate import. Multiple, proximity-only, redacted or monetarily different matches remain unresolved without a repair proposal.

Check: `python3 -m pytest -v tests/test_orchestration.py -k dividend_existing_reconciliation`.

### Requirement: Additive imports and independent cash

Imports SHALL be additive. Unresolved symbols SHALL drop/retry the reduced batch with degradation. Accounts SHALL run sequentially despite failures. Cash SHALL be independent of import success. Clean/degraded runs SHALL exit 0/1. Unresolved dividend exceptions or unapplied verified corrections SHALL degrade the run. They SHALL NOT prevent otherwise valid independent imports or cash updates. Failed exception persistence SHALL prevent importing uncertain dividends. Daily synchronization SHALL never apply historical corrections.

#### Scenario: Partial failure
- **WHEN** import fails or sections are absent
- **THEN** import failure permits cash; missing CashTransactions degrades; absent BASE_SUMMARY only warns.

Baseline: README “How it works”; `python3 -m pytest -q tests/test_orchestration.py -k 'test_import_failure_fails_the_account_keeps_state_untouched_but_still_updates_cash or test_report_without_cash_row_is_a_warning_not_a_failure'`.

#### Scenario: Persistent unresolved dividend
- **WHEN** an unrated PIL is newly imported, later deduplicated, or leaves the Flex window while unresolved
- **THEN** retain its private keyed YAML exception and degrade each run until verified resolution; absence is not resolution. Failed storage prevents that uncertain import. Dry runs show planned changes without financial writes or modification of existing exception journals.

Check: `python3 -m pytest -v tests/test_orchestration.py -k dividend_unresolved_lifecycle`.

### Requirement: Notifications

Configured notifications SHALL send at most one failure/legacy-expiry summary per completed run, without affecting exit status. Success/ordinary warnings without expiry, simulation and interruptions SHALL send nothing. Unresolved dividend reconciliation SHALL contribute fixed reason codes and counts to the degraded-run summary; details SHALL remain in private local evidence. Notifications SHALL omit identifiers, hosts, financial values and secrets. Delivery failure SHALL NOT clear exceptions or change reconciliation status.

#### Scenario: Consolidated outcome
- **WHEN** accounts finish with failure/expiry
- **THEN** fixed-code summaries omit identifiers/amounts/secrets; reminders can repeat.

Baseline: `python3 -m pytest -q tests/test_finalize.py tests/test_token_expiry.py`.

#### Scenario: Unresolved reconciliation is visible
- **WHEN** several accounts retain dividend exceptions
- **THEN** one configured summary reports fixed codes/counts, exit is 1, and unresolved cases remain visible on subsequent runs. Without configured delivery, local evidence and exit 1 remain. Dry runs never notify; other warnings retain their behavior.

Check: `python3 -m pytest -v tests/test_finalize.py tests/test_outcome.py -k dividend_reconciliation_summary`.

### Requirement: Current operational limits

The connector SHALL retain documented boundaries: 365-day guidance; daily data; manual corporate actions/history/token renewal; additive corrections; proximity false matches; UTC dates; unconverted cash/commission currencies; unused GHOST_CURRENCY; Yahoo quality; net, nonchronological checks; nontransactional buy/sell phases; preview without server acceptance; buffered 10 MiB Flex responses; no overlap protection. README SHALL distinguish read-only dividend reconciliation from explicit historical repair and require durable private exception storage. Quantity outside available evidence SHALL remain unresolved; current holdings SHALL NOT establish historical dividend entitlement.

#### Scenario: Operator checks limits
- **WHEN** limitations are read
- **THEN** existing boundaries, report retention and explicit maintenance authorization are visible.

Check: `sed -n '/^## Limitations/,/^## Inspecting/p' README.md`.

## ADDED Requirements

### Requirement: Explicit dividend quantity repair

Maintenance SHALL prepare a private keyed YAML plan from saved Flex and Ghostfolio evidence without activity writes. It SHALL preserve source files, bind the plan to source hashes, target owner/account and exact activity identity, and record originals, proposed values and unresolved reasons. Input/output collisions, changed evidence, ambiguous ownership or unsupported financial values SHALL be refused. Quantity repair SHALL only change quantity/unitPrice, preserving gross income, fee, date, currency, identity and metadata. Daily runs SHALL never invoke apply. Details of unresolved entitlement SHALL identify missing evidence rather than recommend a guessed quantity.

An explicit operator apply SHALL require reviewed proposals, verified backup and quiet portfolio writers. It SHALL revalidate fresh ownership and unchanged originals, persist recovery evidence before each PUT and verify exact readback. Missing/changed records or unknown outcomes SHALL stop further repair. Correction journals SHALL be distinguished from duplicate-cleanup journals and SHALL NOT enter deletion paths. Explicit resume SHALL distinguish unchanged, already-corrected and unknown records without duplicate mutations. Explicit restore SHALL use recorded originals only when the current activity still matches the verified correction; it SHALL preserve unrelated fields. No automatic DELETE, reinjection, compensation or financial-value repair SHALL occur.

#### Scenario: Offline plan and explicit apply
- **WHEN** a quantity-only discrepancy is planned, applied and inspected again using mocked HTTP
- **THEN** planning performs no activity writes; apply verifies preserved income and exact readback; repeated apply performs no additional PUT. Preview does not overwrite source evidence or an existing plan.

Check: `python3 -m pytest -v tests/test_cleanup_recovery.py -k dividend_quantity_repair`.

#### Scenario: Stale plan, interruption and restore
- **WHEN** a record changes after planning, a PUT times out, or an applied correction is explicitly restored
- **THEN** stale state is refused; fresh readback determines whether the correction committed; unresolved outcomes stop; restore preserves unrelated edits or refuses conflicts.

Check: `python3 -m pytest -v tests/test_cleanup_recovery.py -k dividend_quantity_recovery`.
