# connector-runtime Specification

## Purpose
Describe how the connector imports IBKR Flex Web Service activities and cash into Ghostfolio today, and its documented limits.

Commands cite existing offline tests, run from the repository root; expect passing assertions. No production replay.

## Requirements

### Requirement: Execution and authentication

The connector SHALL use ENV, Python/Docker one-off runs or Docker CRON, and exactly one credential: GHOST_ACCESS_TOKEN exchanged once per run or unchanged GHOST_TOKEN bearer.

#### Scenario: Configured startup
- **WHEN** startup configuration is evaluated
- **THEN** authentication precedes reads; numeric five-field CRON is validated.

Evidence: README “Running”; `python -m pytest -q tests/test_auth.py tests/test_entrypoint.py -k 'test_access_mode_authenticates_once_before_any_ghostfolio_or_ibkr_call or test_legacy_mode_never_logs_in_and_uses_the_token_as_bearer or test_valid_cron_is_written_and_tested_before_start or test_invalid_cron_is_rejected_without_echoing_input'`.

### Requirement: Simulation

Truthy DRY_RUN (1/true/yes/on) SHALL preview without financial writes/notifications; access-token login and reads remain. Absent, empty or any other DRY_RUN value SHALL write for real; no Compose file sets a default. Siblings simulate when DRY_RUN is absent.

#### Scenario: Preview
- **WHEN** DRY_RUN is enabled
- **THEN** login/reads occur without financial writes/notifications.

#### Scenario: Live default
- **WHEN** DRY_RUN is empty or not a truthy value
- **THEN** the configuration selects live writes.

Evidence: `python -m pytest -q tests/test_auth.py::test_access_mode_dry_run_logs_in_reads_with_the_bearer_and_writes_nothing tests/test_finalize.py::test_failed_dry_run_sends_nothing tests/test_orchestration.py::test_load_config_dry_run_truthy_values`; README “Configuration” (`DRY_RUN` row).

### Requirement: Flex selection and conversion

The connector SHALL select Trade children excluding CASH/OPT, DETAIL dividend/PIL/withholding grouped by security/day, and BASE_SUMMARY cash; ignore other cash types/levels and AssetSummary. Trades SHALL use BUY for exact BUY, otherwise SELL; absolute quantity/price; commission/withholding fees with refunds/rebates clamped to zero. Nonpositive payments SHALL skip.

Cash Transactions SHALL establish payments/gross/withholding. Conversion SHALL preserve account, currency/scaling, cash-day UTC date/comment. Description inference and one-unit fallback SHALL be removed.

Each net-positive action SHALL require identical nonempty `accountId/conid/currency/actionID/exDate`, one unique `Re` with `payDate` matching cash day, and matching `date` OR `reportDate`. Associated quantities SHALL agree as positive finite decimals before numeric conversion, without rounding/tolerance. `Re` alone SHALL NOT establish payment.

Dividends/PIL and distinct ordinary/bonus actions SHALL use one common quantity, never sum quantities. Zero-net actions SHALL provide no quantity; negative-net actions/mixed currencies/incompatible evidence SHALL reject the group. Results SHALL be row-order independent. Price SHALL be cash gross/quantity, irrespective of accrual money/rate. After numeric conversion/minor-unit scaling, quantity/price SHALL remain positive finite and fee nonnegative finite; overflow/positive underflow SHALL reject the group.

#### Scenario: Selected records
- **WHEN** baseline selection/conversion is replayed with enriched fixtures
- **THEN** selection/gross/fees/scaling/date/identity remain unchanged.

Baseline: README conversion table. Check: `.venv/bin/python -m pytest -q tests/test_parsing.py tests/test_conversion.py`.

#### Scenario: Quantity association
- **WHEN** fixtures cover unrated PIL (3 shares/gross 1.5), quantity 450 versus inferred 451, fractions/one-share, earlier date/late reportDate, wrong keys/dates, multiple Re, missing/invalid/conflicting quantities, Re without cash
- **THEN** supported quantities remain unchanged; unsupported groups reject; Re creates no payment.

Check: `.venv/bin/python -m pytest -v tests -k dividend_structured_quantity`.

#### Scenario: Final numeric limits
- **WHEN** fixtures cover quantity `1e-400`/`1e400`, decimal conflicts collapsing to one numeric value, price overflow/underflow, and GBP→GBp overflow of price/fee alongside normal scaling
- **THEN** unsafe groups reject locally, decimal conflicts before conversion; valid quantity/price/fee/cash totals remain correct.

Check: `.venv/bin/python -m pytest -v tests -k dividend_structured_numeric`.

#### Scenario: Components and money
- **WHEN** fixtures include split PIL, ordinary/bonus at equal/different rates, unequal quantities, signed zero/negative actions, mixed currencies and differing accrual gross/tax/rate
- **THEN** valid groups retain quantity/cash totals; invalid groups reject; permutation/accounting/identity assertions pass.

Check: `.venv/bin/python -m pytest -v tests -k dividend_structured_components`.

### Requirement: Mapping and duplicate reconciliation

Mapping SHALL prefer ISIN mappings, then IBKR symbols. Trade IDs SHALL suppress reimport. Manual matching SHALL use quantity and ±2 days, including summed fills; nearby mismatches SHALL warn/skip. Dividends SHALL match account/comment or account/symbol at ±3 days.

#### Scenario: Existing entries
- **WHEN** existing entries match
- **THEN** duplicates are excluded; manual-buy exclusions warn.

Evidence: `python -m pytest -q tests/test_parsing.py tests/test_filters.py tests/test_orchestration.py -k 'test_resolve_symbol_prefers_mapping_then_ibkr_symbol or test_already_imported_trade_is_not_reimported or test_manual_buy_same_day_same_qty_is_not_reimported_and_warns or test_split_fills_summing_to_a_manual_sell_are_matched or test_dividend_match_window_is_exactly_three_days'`.

### Requirement: Position and acceptance guards

Incomplete/redacted/invalid-profile listings SHALL stop startup; assetProfile SHALL override legacy SymbolProfile. Draft/excluded/non-YAHOO records SHALL not back reconciliation. Future candidates SHALL defer. Sales SHALL pass net-quantity and accepted-buy checks; unknown acceptance SHALL block later same-target queries within this run.

#### Scenario: Unusable position evidence
- **WHEN** evidence cannot back sales
- **THEN** candidates are excluded; accepted server symbols determine holdings.

Evidence: `python -m pytest -q tests/test_ghostfolio.py tests/test_orchestration.py -k 'test_count_mismatch_refuses_to_sync or test_current_profile_takes_precedence_over_legacy or test_server_skipped_buy_cannot_authorize_sell_in_same_batch or test_uncertain_import_blocks_further_writes_only_to_same_target or test_canonical_accepted_buy_cannot_back_sale_under_original_ticker'`.

### Requirement: Additive imports and independent cash

Imports SHALL be additive. Unresolved symbols SHALL drop/retry the reduced batch with degradation. Accounts SHALL run sequentially despite failures. Cash SHALL be independent of import success. Clean/degraded runs SHALL exit 0/1.

#### Scenario: Partial failure
- **WHEN** import fails or sections are absent
- **THEN** import failure permits cash; missing CashTransactions degrades; absent BASE_SUMMARY only warns.

Evidence: README “How it works”; `python -m pytest -q tests/test_orchestration.py tests/test_ghostfolio.py -k 'test_import_failure_fails_the_account_keeps_state_untouched_but_still_updates_cash or test_missing_cash_transactions_section_fails_the_run_but_still_imports_trades or test_report_without_cash_row_is_a_warning_not_a_failure or test_unresolved_symbol_is_dropped_and_batch_retried'`.

### Requirement: Notifications

Configured notifications SHALL send at most one failure/legacy-expiry/forced-preview summary per completed run, without affecting exit status. A run forced into `DRY_RUN` by missing or invalid IANA `TZ` SHALL send that summary even when every account succeeds, and the summary SHALL name the reason. Success/warnings without expiry, operator-chosen simulation and interruptions SHALL send nothing.

#### Scenario: Consolidated outcome
- **WHEN** accounts finish with failure/expiry
- **THEN** fixed-code summaries omit identifiers/amounts/secrets; reminders can repeat.

#### Scenario: Forced preview notifies
- **WHEN** `.venv/bin/python -m pytest -q tests/test_finalize.py -k 'historical_diagnostic_preflight'` runs with absent/invalid `TZ`, valid `TZ`, and operator-set `DRY_RUN`
- **THEN** the forced preview sends one summary naming the reason even on success; a live run without failure and an operator-chosen `DRY_RUN` send nothing.

Evidence: `python -m pytest -q tests/test_finalize.py tests/test_token_expiry.py -k 'test_several_failed_accounts_make_one_dispatch_after_every_account_ran or test_summary_carries_no_secret_identifier_host_or_amount or test_notification_problems_keep_exit_code_and_account_processing or test_success_notifies_once_after_both_accounts_and_preserves_exit or test_reminder_is_run_local_and_multiple_runs_can_repeat_it or historical_diagnostic_preflight'`.

### Requirement: Current operational limits

The connector SHALL retain documented boundaries: 365-day guidance; daily data; manual corporate actions/history/token renewal; additive corrections; proximity false matches; UTC dates; unconverted cash/commission currencies; unused GHOST_CURRENCY; Yahoo quality; net, nonchronological checks; nontransactional buy/sell phases; preview without server acceptance; buffered 10 MiB Flex responses; no overlap protection.

#### Scenario: Operator checks limits
- **WHEN** limitations are read
- **THEN** these boundaries are visible.

Evidence: README “Limitations”; `sed -n '/^## Limitations/,/^## Inspecting/p' README.md`.

### Requirement: Enriched dividend input and local rejection

Processing SHALL extract cash identity without quantity checks, deduplicate by account/comment/proximity, then validate new candidates; existing activities remain untouched and unverified by import selection. A separate dry-run diagnostic SHALL compare historical evidence without changing that selection.

ChangeInDividendAccruals SHALL be mandatory. Required attributes SHALL cover candidate payment/relevant accrual keys, plus `quantity/code/date/payDate/reportDate` on relevant accruals. Nonempty key mismatches SHALL exclude unrelated accruals; missing keys SHALL NOT prove irrelevance. Unrelated rows SHALL NOT block candidates. Withholding SHALL retain cash grouping without accrual-schema requirements. Missing section/relevant attributes SHALL block account dividends; present-but-empty evidence SHALL reject affected groups. Empty sections without payments SHALL be valid.

Rejections SHALL log distinct incompatibility/missing/contradiction reasons, never mark rejected payments imported, leave trades/cash operating, and SHALL NOT change success/exit/notifications. Other failures SHALL retain existing behavior.

#### Scenario: Compatibility and isolation
- **WHEN** old/empty/short-window exports, malformed unrelated rows beside valid candidates, relevant missing attributes versus empty values, and existing dividends with invalid/conflicting quantities are processed
- **THEN** identity→dedup→quantity order, rejection scopes/logs/retries, unrelated-row isolation and unchanged outcomes are asserted.

Check: `.venv/bin/python -m pytest -v tests -k dividend_structured_input`.

### Requirement: Forward dividend upgrade guidance

README/setup SHALL require enrichment before upgrade, explain rejections/removed inference and backup/prior-image-digest rollback without financial restoration. Extra fields SHALL retain prior-runtime compatibility.

#### Scenario: Upgrade inspection
- **WHEN** guidance is inspected
- **THEN** preparation/ENV/mounts and historical boundaries are explicit.

Check: `rg -n -A 35 'structured|enrich|rollback' README.md docs/ibkr-setup.md`.

### Requirement: Historical dividend comparison

Every truthy DRY_RUN SHALL compare cash distributions with existing target-account dividend sets, before deduplication hides them. Cash establishes gross/withholding; current exact accrual association establishes quantity. Missing/conflicting evidence SHALL remain uncertain. Comparisons SHALL use common currency units and exact decimal values and never sum component quantities.

The diagnostic SHALL retain original JSON decimal numeric evidence from the existing GET before float decoding; reconstructing evidence from decoded floats SHALL NOT establish exactness. The existing import/position numeric path, return shape, indexes, read count and failure contract SHALL remain unchanged. Destination gross SHALL be exact stored quantity × unitPrice, summed only within a complete representation; fees SHALL use the same representation. Source gross SHALL remain exact cash payments; source fee SHALL use the existing max(0,-cash withholding) convention. Raw signed withholding/refund rows and their total SHALL remain separate evidence. Gross/fee deltas SHALL be destination minus source after normalization; a gross or fee delta whose absolute value is below half a minor unit of the source currency SHALL be classified rounding noise and SHALL stay counted in the summary and visible at DEBUG; every other nonzero delta, and every quantity delta, SHALL remain visible without tolerance or display rounding suppression.

A nonempty activity currency SHALL determine the denomination of its price and fee. Only null activity currency SHALL permit fallback to a supported profile currency, with explicit provenance. Missing/invalid/unsupported context SHALL remain uncertain. Major/minor units SHALL be normalized exactly without overwriting activity denomination; a GBP activity with a GBp profile SHALL NOT be rescaled as though its activity values were GBp.

The report SHALL distinguish coherent single/component sets, probable repeated representations, quantity/monetary differences, absent destination records, uncertain identity and outside-report-window history. Findings can overlap. Canonical account/comment identity SHALL require consistent security/date evidence; proximity, legacy-symbol or timezone explanations alone SHALL remain uncertain. Inactive/unsupported records SHALL NOT certify matches. Every source group and unmatched target dividend SHALL be accounted for; no finding authorizes repair.

A complete representation SHALL cover one whole source payment group as a single activity or cover every independently identified source component exactly once as a component set. Only identity/coverage-proven partitions SHALL be evaluated; amount equality SHALL NOT establish completeness and arbitrary subset search SHALL NOT be used. A complete representation with quantity/gross/fee disagreement SHALL retain its discrepancies; coherent SHALL require exact agreement on all supported quantities, gross and fee. Two or more distinct complete representations of the same source group SHALL be probable repetition even with discrepancies; incomplete or unproven partitions SHALL remain uncertain. Assignment SHALL be globally unique across source groups: no destination activity SHALL certify two groups. Contested ownership SHALL leave all affected comparisons uncertain, independent of processing order.

#### Scenario: Payment representations
- **WHEN** synthetic inputs cover ordinary/bonus, split PIL, whole-payment versus component sets, repeated sets with monetary discrepancies, incomplete partitions, disputed cross-group ownership, fractional quantities, sub-float decimal differences, signed tax/refunds, null activity currency, GBP/GBp denomination differences and unsupported currency context
- **THEN** components remain distinct from repetition; complete-but-discrepant representations are not coherent; disputed ownership stays uncertain in either processing order; currency provenance, quantity differences, signed exact monetary deltas and raw tax/refund evidence are reported independently.

Check: `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k representations`.

#### Scenario: Incomplete identity
- **WHEN** fixtures include missing/conflicting accruals, absent destination rows, legacy comments, timezone shifts, inactive rows and older history
- **THEN** coverage and uncertainty are explicit; no weak match is certified.

Check: `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k evidence`.

### Requirement: Diagnostic execution and visibility

The diagnostic SHALL use existing reads, ENV and logs without persistence or financial writes. INFO SHALL summarize coverage/categories; anomaly/uncertainty details SHALL include reasons, activity IDs and source references with quantities/monetary deltas when supported. Logs remain private. Findings SHALL NOT alter exits/notifications; technical failures retain current behavior. Live runs SHALL NOT execute the diagnostic. README SHALL explain one-off Docker DRY_RUN without CRON, categories, limits and unchanged financial state.

#### Scenario: Dry-run report
- **WHEN** mocked runs exercise dry/live modes, anomalies and read failures
- **THEN** dry-run logs contain summary/details without financial writes/notifications; anomalies preserve success; technical failures retain failure; live behavior remains unchanged.

Check: `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic or representations or evidence or dividend_structured_input or ghostfolio or finalize'`; this also selects existing compatibility/outcome regressions, including both dividend rejection/failure cases in `tests/test_finalize.py`.

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

Dry-run details SHALL name each failed or unavailable active/id/data-source/symbol/date/ISIN check with expected/observed values. Human blocks SHALL show security, source and destination UTC/local dates, activity IDs, and supported quantity/gross/fee/currency. INFO SHALL count failed checks. Canonically absent sources skipped by import deduplication SHALL remain absent and SHALL name the skip path that import selection takes, with the same predicate and input set, in its order: `skipped by historical comment` when the account's old `dividend#<symbol>#<date>` comment is among the existing dividend comments of any activity, active or not; otherwise `skipped by proximity`. Each SHALL show the available weak-candidate values and active status. Neither label SHALL certify identity. A finding left uncertain by missing, unsupported or conflicting currency context SHALL keep its reason and SHALL show the observed source and destination currency values and provenance. Outside-window rows SHALL show destination security, date, and values. No finding SHALL repair data or change selection.

Baseline: the v2.5.0 dry run emitted 114 opaque findings. Saved evidence measured missing profile ISIN in 44/44 groups, Paris-midnight dates in 5/44, and no other failed identity checks. The first replay of this change passed identity for 44/44 and compared 39: three unproven component partitions, two unsupported-currency (KRW) groups, and two absent groups skipped by old symbol comments but labeled proximity.

#### Scenario: Separate identity checks and local dates
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_identity'` exercises all six checks, Paris winter/summer dates, absent ISIN, and conflicting ISIN
- **THEN** each check exposes expected/observed values, local calendar matches certify date, missing ISIN permits amount comparison, and conflicting ISIN blocks it.

#### Scenario: Actionable private report
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_actionable'` exercises outside-window rows and proximity skips
- **THEN** private human-readable details and aggregate counts expose the required evidence without certifying weak identity or changing data.

#### Scenario: Skip cause and observed currency
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_skip_cause'` exercises an absent group with an old symbol comment and a proximity candidate, the same with an inactive comment carrier, an absent group with only a proximity candidate, and unsupported, missing and conflicting source/destination currency context
- **THEN** the first two show `skipped by historical comment`, the third `skipped by proximity`, each finding stays absent or uncertain, currency findings keep their reason and show observed source/destination currency and provenance, and import selection is unchanged.

#### Scenario: Real read-only acceptance
- **WHEN** the operator-authorized `DRY_RUN=1 LOG_LEVEL=DEBUG .venv/bin/python ibkr_to_ghostfolio.py` runs with the approved real-data ENV and private log capture
- **THEN** zero financial writes occur; all 44 previously blocked groups pass the active, id, data-source, symbol and local-date checks, with ISIN pass or unavailable; each reaches exact amount comparison or stays uncertain only with `component partition identity not proven` or a currency-context finding that shows the observed currency, never a component assignment inferred from amounts; the outcome matches the replay baseline of 39 compared, 3 unproven partitions and 2 unsupported currency, and any other cause or count fails acceptance and is reported; every remaining anomaly is explainable from the log; both absent groups log `skipped by historical comment`, reconciled with their evidence rows; and both unsupported-currency groups show a `currency context:` line naming KRW.

### Requirement: Bounded SendRequest recovery

The connector SHALL retry a non-Success SendRequest response only for ErrorCode `1001`, `1004`, `1005`, `1006`, `1007`, `1008`, `1009`, `1018`, `1019` or `1021`. It SHALL make at most five SendRequest attempts, with waits of 60, 120, 300 and 600 seconds before subsequent attempts. These scheduled waits total 18 minutes; transport timeouts and network retries are additional.

Codes `1003`, `1010`–`1017`, `1020`, missing codes and unknown codes SHALL fail without application-level retry. Classification SHALL use ErrorCode, never message matching. Exhaustion SHALL fail with the final IBKR message, retaining credential redaction. Recovery SHALL use the successful response's reference and validated statement URL without changing financial processing.

Source: [IBKR Version 3 error table](https://www.ibkrguides.com/clientportal/performanceandstatements/flex3error.htm), checked 2026-10-14. The retry set follows descriptions that explicitly advise retrying; `1003` supplies no such advice. This is connector policy, not a guarantee of IBKR recovery.

#### Scenario: Transient error recovers
- **WHEN** mocked responses provide `1004` followed by Success and a ready statement
- **THEN** one 60-second wait occurs, the successful reference is used, and retrieval succeeds.

Check after implementation: `.venv/bin/python -m pytest -v tests/test_orchestration.py -k flex_transient_send_recovery`.

#### Scenario: Transient errors exhaust the budget
- **WHEN** every SendRequest attempt returns a retryable code
- **THEN** exactly five attempts and waits `[60, 120, 300, 600]` occur; the last message is reported without credentials and GetStatement is never called.

Check after implementation: `.venv/bin/python -m pytest -v tests/test_orchestration.py -k flex_transient_send_exhaustion`.

#### Scenario: Permanent and unclassified errors stop
- **WHEN** fixtures cover every retryable code and every immediate-failure code, including expired/invalid tokens `1012`/`1015`, a missing code, an unknown code and misleading messages
- **THEN** only the explicit retry set schedules another attempt; immediate failures make one request and preserve redacted error context.

Check after implementation: `.venv/bin/python -m pytest -v tests/test_orchestration.py -k flex_transient_send_classification`.

### Requirement: Extended statement polling and preserved guards

Default GetStatement polling SHALL allow 60 attempts at 5-second intervals, replacing 10 attempts. The existing Warn-or-1019 pending condition, explicit polling overrides, ready-response handling, timeout failure and immediate failure for other codes SHALL remain. Sixty consecutive pending responses SHALL retain the existing sleep-after-each-pending-response behavior: 300 seconds of scheduled waits followed by failure. Existing network retries, XML size limits, statement-host validation, ENV, financial-write guards, account outcomes and notifications SHALL remain unchanged.

Baseline: `tests/test_orchestration.py` Flex-fetch tests cover Warn, code-only 1019, explicit overrides, timeout, 1018 rejection and foreign hosts. `tests/test_parsing.py` covers response size guards.

#### Scenario: Longer generation recovers or expires
- **WHEN** mocked polling needs more than ten attempts or remains pending for all sixty attempts
- **THEN** a later ready statement succeeds, or polling fails after sixty attempts and 300 seconds of scheduled waits; explicit overrides and existing guards still pass.

Check after implementation: `.venv/bin/python -m pytest -v tests/test_orchestration.py tests/test_parsing.py -k 'flex_fetch or fetch_flex_report or flex_transient'`.

### Requirement: Retry guidance

README SHALL document the SendRequest retry set, immediate failures, five-attempt schedule, longer GetStatement window and additional transport time. It SHALL explain that exhaustion still fails the run and that no ENV change is required.

#### Scenario: Operator inspects retry policy
- **WHEN** `rg -n -A 22 'Flex retry policy' README.md` is run after implementation
- **THEN** the retry codes, 18-minute scheduled SendRequest wait, 300-second GetStatement wait, transport caveat and final failure behavior are visible.

### Requirement: Dividend field prerequisites

Before any Ghostfolio financial write, including cash and platform updates, each account's Flex report SHALL be checked for the dividend attributes the connector requires. A report with no relevant DETAIL cash rows (`Dividends`, `Payment In Lieu Of Dividends`, `Withholding Tax`) SHALL pass without this check, in `DRY_RUN` as in live runs.

An attribute SHALL be missing when no row of its section carries it. Required `CashTransaction` attributes on those rows SHALL be `accountId`, `conid`, `currency`, `actionID` and `exDate`. `ChangeInDividendAccruals` SHALL be mandatory once relevant cash rows exist. When that section has rows, its attributes SHALL cover the cash keys plus `quantity`, `code`, `date`, `payDate` and `reportDate`. A present but empty section SHALL stay valid.

A missing attribute or section SHALL fail the account through the normal failure outcome with one ERROR line. The line SHALL name every missing XML attribute with the IBKR field to select, and SHALL NOT enable `DRY_RUN`. For an attribute or section absent from every relevant row, this requirement SHALL take precedence over "Missing section/relevant attributes SHALL block account dividends" in "Enriched dividend input and local rejection": the account fails before any write instead of a dividends-only block. A single empty or malformed value SHALL keep the local rejection of "Enriched dividend input and local rejection".

#### Scenario: Cash field not ticked
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'dividend_field_prerequisites'` runs a report with dividend rows but no `conid`, and no new dividend
- **THEN** the account fails before any write with one ERROR naming `conid` and its IBKR field, and `DRY_RUN` stays unchanged.

#### Scenario: Complete or empty report
- **WHEN** the same command runs a complete report, a report without relevant cash rows, and a present empty accrual section
- **THEN** no prerequisite error is logged and outcomes are unchanged.

#### Scenario: Isolated bad row
- **WHEN** the same command runs a report where one row has an empty `conid` and the attribute exists elsewhere
- **THEN** the account does not fail on prerequisites and the row keeps its local rejection.

### Requirement: Readable dividend report

Findings that need an operator check or give information SHALL be logged at INFO in English plain words, with the reason, the source and destination values, one action line, and the statement that nothing was written. No finding line SHALL contain a Python representation (`Decimal(...)`, list brackets, exponent notation); decimals SHALL print in plain form. Findings in the coherent and outside-window classes SHALL log at DEBUG only.

The classes SHALL be: to check (quantity difference; gross or fee difference of exactly one minor unit with equal quantity, named "minimal difference, cause unknown"; legacy-comment destination row with the same security and local day as a compared group, named "probable duplicate"; any other amount difference), information (outside window; unsupported currency; exact split; an absent source skipped by historical comment together with a destination row outside proven coverage that has the same security, day, gross and fee, reported as one line) and noise. Every finding that is not coherent, outside window, information or noise SHALL be "to check" and SHALL show its reason; this covers an absent source without an outside-coverage twin (a dividend possibly missing in Ghostfolio), contested ownership, missing currency context and any other uncertain reason. A probable duplicate and an exact split SHALL keep their category uncertain. A destination partition whose rows sum exactly to the source gross and fee SHALL read "total equal to IBKR, split over N rows" and SHALL NOT be called a proven split.

After the findings, one INFO line SHALL read "N to check, N informational, N noise", followed by the detail of each item to check. Findings SHALL NOT change exits or notifications. Detecting amounts revised by IBKR after first import is out of scope; a revised amount appears as an amount difference.

Baseline: the DRY_RUN of 2026-10-14 on query 1492040 gave 114 findings: 28 coherent, 56 outside window, 11 differences (4 quantity, 6 one-yen, 1 sub-cent), 17 uncertain (10 legacy, 3 splits, 2 KRW, 2 outside coverage), 2 absent.

#### Scenario: Classes from synthetic inputs
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'dividend_readable_classes or dividend_readable_pairs'` runs sub-half-unit, one-unit (JPY 1 and EUR or USD 0.01 with equal quantity) and larger deltas, quantity deltas, legacy twins, equal-total splits, absent/outside-coverage pairs and an unpaired absent source
- **THEN** each lands in its class, an unpaired absent source lands in to check, noise stays counted, and uncertain categories are unchanged.

#### Scenario: Plain report
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'dividend_readable_report'` formats a quantity difference with two legacy twins
- **THEN** the block shows both sides, the probable-duplicate sentence, an action line and "Nothing was written", and contains no `Decimal(` or exponent text.

#### Scenario: Real read-only acceptance
- **WHEN** the operator-authorized DRY_RUN on the production query runs with a private log
- **THEN** zero writes occur, `rg -c "Decimal\(|[0-9]E-[0-9]" <log>` prints 0, and the summary reads 20 to check, the information and noise counts, matching the baseline.
