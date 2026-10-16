# connector-runtime Specification

## Purpose
Describe how the connector imports IBKR Flex Web Service activities and cash into Ghostfolio today, and its documented limits.

Commands cite existing offline tests, run from the repository root; expect passing assertions. No production replay.

## Requirements

### Requirement: Execution and authentication

The shipped Docker image and every CI or scheduled Python job SHALL use CPython 3.14. Direct Python runs SHALL be documented for Python 3.14 or newer. The connector SHALL NOT reject Python 3.12 explicitly.

The connector SHALL use ENV, Python/Docker one-off runs or Docker CRON, and exactly one credential: GHOST_ACCESS_TOKEN exchanged once per run or unchanged GHOST_TOKEN bearer.

Baseline replaced: README “Prerequisites”, CONTRIBUTING “Tests”, `docs/upstreams.md`, and `tests/test_dockerfile.py` record Python 3.12.

#### Scenario: Configured startup
- **WHEN** startup configuration is evaluated
- **THEN** authentication precedes reads; numeric five-field CRON is validated.

Evidence: README “Running”; `python -m pytest -q tests/test_auth.py tests/test_entrypoint.py -k 'test_access_mode_authenticates_once_before_any_ghostfolio_or_ibkr_call or test_legacy_mode_never_logs_in_and_uses_the_token_as_bearer or test_valid_cron_is_written_and_tested_before_start or test_invalid_cron_is_rejected_without_echoing_input'`.

#### Scenario: Repository runtime declarations
- **WHEN** `.venv/bin/python -m pytest -q tests -k python_runtime_baseline` runs
- **THEN** the Docker base, all seven workflow pins, both Renovate ranges, and public direct-run guidance require Python 3.14 as specified.

#### Scenario: Built runtime
- **WHEN** `docker build -t ibkr-python314:check . && bash scripts/check_container_runtime.sh ibkr-python314:check` runs
- **THEN** the isolated one-off and scheduled checks pass, and the container reports CPython 3.14.

### Requirement: Simulation

Absent or blank `DRY_RUN` SHALL simulate and emit WARNING `DRY_RUN not set: simulation, nothing written` on every invocation, including configuration failure. After trimming and lowercasing, `1/true/yes/on` SHALL simulate; only `0/false/no/off` SHALL request live writes. Any other value SHALL fail configuration with exit 1 before any HTTP call. After rejection, only the configured Apprise Failure notification SHALL be permitted; no IBKR/Ghostfolio HTTP calls or financial writes SHALL occur. Other safety guards SHALL still apply.

Simulation SHALL run login, reads and the existing preview pipeline without activity, cash or platform writes. Failed simulations SHALL send the configured Failure notification. Successful simulations, token-expiry reminders and previews SHALL send no notification. Existing TZ-forced notifications SHALL remain for explicit live mode.

README configuration, Docker/Compose examples, setup, 3.0 upgrade note and changelog SHALL explain this breaking rc.2 change and explicit false opt-in. Examples SHALL select simulation explicitly; instructions SHALL explain changing to false after review.

Baseline replaced: README configuration; `test_load_config_dry_run_truthy_values`. Commands below target tests to add during implementation; they are not current evidence.

#### Scenario: Live default
- **WHEN** `python3 -m pytest -q tests/test_orchestration.py -k dry_run_default` tests absent, empty and whitespace values across two invocations and invalid configuration
- **THEN** the former live default becomes simulation; each invocation emits exactly one specified WARNING.

#### Scenario: Accepted and invalid values
- **WHEN** `python3 -m pytest -q tests/test_orchestration.py -k dry_run_values` tests all eight values, mixed case, surrounding spaces and invalid input with mocked HTTP and configured/disabled Apprise
- **THEN** only false values request writes; invalid input exits 1 before any HTTP call, makes no IBKR/Ghostfolio calls or financial writes, and then dispatches one Failure notification only when Apprise is configured.

#### Scenario: Preview
- **WHEN** `python3 -m pytest -q tests/test_auth.py -k dry_run_modes` exercises default, true and explicit false with mocked HTTP
- **THEN** simulation retains login/reads and preview but sends no financial POST/PUT; false permits activity, cash and platform writes with valid prerequisites.

### Requirement: Flex selection and conversion

The connector SHALL select Trade children excluding CASH/OPT, DETAIL dividend/PIL/withholding grouped by security/day, and BASE_SUMMARY cash; ignore other cash types/levels and AssetSummary. Trades SHALL use BUY for exact BUY and SELL for exact SELL; any other `buySell` value SHALL reject the row (error, run not ok, other trades unaffected); absolute quantity/price; commission/withholding fees with refunds/rebates clamped to zero. Nonpositive payments SHALL skip.

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

#### Scenario: Unknown trade side
- **WHEN** a synthetic Trade has `buySell` `SELL (Ca.)`, empty or lowercase `sell`, beside valid BUY and SELL rows
- **THEN** only the unknown row is rejected with an error, never counted by the holdings gate; valid rows convert unchanged.

Check: `.venv/bin/python -m pytest -q tests -k 'unknown_trade_side'`.

### Requirement: Mapping and duplicate reconciliation

Mapping SHALL prefer ISIN mappings, then IBKR symbols. Trade IDs SHALL suppress reimport. Manual matching SHALL use quantity and ±2 days, including summed fills; nearby mismatches SHALL warn/skip. Dividends SHALL match by account/comment (including the old symbol comment), or, for existing active YAHOO dividends of the same account and symbol whose comment does not start with `dividend#` (manual or legacy rows), at ±3 days. Connector-comment rows (`dividend#…`) SHALL NOT enter the proximity index, so a distinct payment next to an imported one is imported. A proximity skip SHALL stay a skip. The comparison SHALL use the exact source gross and the existing row's quantity × unitPrice, normalized to a common major unit (minor-unit markets as in conversion) and rounded to its minor unit; an unsupported denomination SHALL be "not comparable". Equal amounts SHALL log INFO "amounts agree" with both fee values; equal amounts do not prove the same payment. Otherwise it SHALL log one WARNING naming both dates, both gross values with currencies (or "not comparable"), both fee values, and the operator action: check IBKR and add the payment by hand if it is distinct. It SHALL NOT change exit status or notifications.

#### Scenario: Existing entries
- **WHEN** existing entries match
- **THEN** duplicates are excluded; manual-buy exclusions warn.

Evidence: `python -m pytest -q tests/test_parsing.py tests/test_filters.py tests/test_orchestration.py -k 'test_resolve_symbol_prefers_mapping_then_ibkr_symbol or test_already_imported_trade_is_not_reimported or test_manual_buy_same_day_same_qty_is_not_reimported_and_warns or test_split_fills_summing_to_a_manual_sell_are_matched or test_dividend_match_window_is_exactly_three_days'`.

#### Scenario: Distinct payment next to an imported one
- **WHEN** an active canonical row `dividend#<ISIN>#2026-07-15` (gross 25) exists and the report holds a distinct payment on 2026-07-16 (gross 100)
- **THEN** the 2026-07-16 payment is imported, no proximity log line appears.

Check: `.venv/bin/python -m pytest -q tests -k dividend_proximity_canonical`.

#### Scenario: Manual row near the payment
- **WHEN** a manual row without connector comment lies within ±3 days, once with equal gross and once with different gross
- **THEN** both payments are skipped; equal gross logs INFO "amounts agree", different gross logs one WARNING with both dates, both gross values, fee values and the operator action; exit status is unchanged.

Check: `.venv/bin/python -m pytest -q tests -k dividend_proximity_amount`.

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

Configured notifications SHALL send at most one Failure, legacy-expiry or forced-preview summary per completed run, without affecting exit status. Failure SHALL notify even for default or truthy simulation and invalid `DRY_RUN`. A failure with an expiry reminder or forced preview SHALL use one Failure summary, never a second dispatch. Without configured Apprise, no notification SHALL be sent.

Successful simulation, including default/blank/truthy `DRY_RUN`, SHALL send no success, expiry-only or preview notification. With explicit false `DRY_RUN`, missing or invalid IANA `TZ` SHALL retain the forced-preview summary even when every account succeeds, and the summary SHALL name the reason. Success/warnings without expiry and interruptions SHALL send nothing.

#### Scenario: Consolidated outcome
- **WHEN** `python3 -m pytest -q tests/test_finalize.py tests/test_token_expiry.py -k 'test_several_failed_accounts_make_one_dispatch_after_every_account_ran or test_summary_carries_no_secret_identifier_host_or_amount or test_notification_problems_keep_exit_code_and_account_processing or test_success_notifies_once_after_both_accounts_and_preserves_exit or test_reminder_is_run_local_and_multiple_runs_can_repeat_it'` runs with explicit live mode
- **THEN** fixed-code summaries omit identifiers, amounts and secrets; delivery does not affect exit status, and reminders can repeat on later runs.

#### Scenario: Forced preview notifies
- **WHEN** `python3 -m pytest -q tests/test_finalize.py -k historical_diagnostic_preflight` runs with absent/invalid `TZ`, valid `TZ`, and default/truthy/explicit-false `DRY_RUN`
- **THEN** explicit false with invalid TZ sends one summary naming the forced-preview reason even on success; successful default/truthy simulations stay silent; failures send Failure once.

#### Scenario: Notification compatibility
- **WHEN** `python3 -m pytest -q tests/test_finalize.py -k dry_run_modes` exercises default, blank, all truthy values, explicit false and invalid input, with success, failure, expiry reminders, previews, TZ forcing, configured/disabled Apprise and delivery failure
- **THEN** failed runs send one Failure notification when configured, including default/truthy simulation and invalid input; successful simulations, expiry-only reminders and previews send nothing; explicit false retains existing notification behavior; delivery never changes exit status.

### Requirement: Current operational limits

The connector SHALL retain documented boundaries: 365-day guidance; daily data; manual corporate actions/history/token renewal; additive corrections; proximity skips next to manual or legacy rows (INFO when amounts agree, WARNING otherwise, never imported; a distinct payment there needs a manual add); trust principle: a row with a connector comment (`dividend#…`) is ours and trusted by exact identity, and a user edit of such a row is out of contract; UTC dates; unconverted cash/commission currencies; Yahoo quality; net, nonchronological checks; nontransactional buy/sell phases; preview without server acceptance; buffered 10 MiB Flex responses; no overlap protection.

#### Scenario: Operator checks limits
- **WHEN** limitations are read
- **THEN** these boundaries are visible, and `GHOST_CURRENCY` is not documented as a setting.

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

The diagnostic SHALL retain original JSON decimal numeric evidence from the existing GET before float decoding; reconstructing evidence from decoded floats SHALL NOT establish exactness. The existing import/position numeric path, read count and failure contract SHALL remain unchanged. The `dividend_dates` index SHALL change: it SHALL exclude rows whose comment starts with `dividend#`, and each entry SHALL carry date, exact gross, currency and fee instead of a bare date. Destination gross SHALL be exact stored quantity × unitPrice, summed only within a complete representation; fees SHALL use the same representation. Source gross SHALL remain exact cash payments; source fee SHALL use the existing max(0,-cash withholding) convention. Raw signed withholding/refund rows and their total SHALL remain separate evidence. Gross/fee deltas SHALL be destination minus source after normalization; a gross or fee delta whose absolute value is below half a minor unit of the source currency SHALL be classified rounding noise and SHALL stay counted in the summary and visible at DEBUG; every other nonzero delta, and every quantity delta, SHALL remain visible without tolerance or display rounding suppression.

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

#### Scenario: Legacy comment identity
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k coherent_dividend_legacy_identity` runs canonical and legacy symbol comments with passing and failing identity checks
- **THEN** a legacy comment whose account, comment symbol and comment date qualify owns one source block; a later failed destination-row check stays in that block with the check named; no row is reported twice.

#### Scenario: Currency states and declared rate
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k 'coherent_dividend_currency or coherent_dividend_declared_rate'` runs KRW, JPY, missing, conflicting and unknown currency cases plus one-action, multi-action and missing-rate evidence
- **THEN** KRW and JPY compare with one-unit precision; each invalid state has the correct reason; only the one-action matched-Re rate is retained.

### Requirement: Diagnostic execution and visibility

The diagnostic SHALL use existing reads, ENV and logs without persistence or financial writes. INFO SHALL summarize coverage/categories; anomaly/uncertainty details SHALL include reasons, activity IDs and source references with quantities/monetary deltas when supported. The per-account import line SHALL include the same `to check`, `informational` and `noise` counts as the dividend report, so its duplicate count cannot be mistaken for the report result. Logs remain private. Findings SHALL NOT alter exits/notifications; technical failures retain current behavior. Live runs SHALL NOT execute the diagnostic. README SHALL explain one-off Docker DRY_RUN without CRON, categories, limits and unchanged financial state.

#### Scenario: Dry-run report
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic or coherent_dividend_import_summary'` runs mocked dry and live accounts
- **THEN** dry-run details and the import line expose identical report counts without writes; live behavior, exits and notifications remain unchanged.

Baseline: the 2026-10-15 real dry-run import line reported duplicate skips while the report separately reported items to check, without a link between the numbers.

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

Dry-run details SHALL name each failed or unavailable active/id/data-source/symbol/date/ISIN check with expected/observed values. Human blocks SHALL show security, source and destination UTC/local dates, activity IDs, and supported quantity/gross/fee/currency. INFO SHALL count failed checks. Canonically absent sources skipped by import deduplication SHALL remain absent and SHALL name the skip path that import selection takes, with the same predicate and input set (connector-comment rows excluded), in its order: `skipped by historical comment` when the account's old `dividend#<symbol>#<date>` comment is among the existing dividend comments of any activity, active or not; otherwise `skipped by proximity`. Each SHALL show the available weak-candidate values and active status; `skipped by proximity` SHALL also show source and candidate gross. Neither label SHALL certify identity. A finding left uncertain by missing, unsupported or conflicting currency context SHALL keep its reason and SHALL show the observed source and destination currency values and provenance. Outside-window rows SHALL show destination security, date, and values. No finding SHALL repair data or change selection.

Baseline: the v2.5.0 dry run emitted 114 opaque findings. Saved evidence measured missing profile ISIN in 44/44 groups, Paris-midnight dates in 5/44, and no other failed identity checks. The first replay of this change passed identity for 44/44 and compared 39: three unproven component partitions, two unsupported-currency (KRW) groups, and two absent groups skipped by old symbol comments but labeled proximity.

#### Scenario: Separate identity checks and local dates
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_identity'` exercises all six checks, Paris winter/summer dates, absent ISIN, and conflicting ISIN
- **THEN** each check exposes expected/observed values, local calendar matches certify date, missing ISIN permits amount comparison, and conflicting ISIN blocks it.

#### Scenario: Actionable private report
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_actionable'` exercises outside-window rows and proximity skips
- **THEN** private human-readable details and aggregate counts expose the required evidence without certifying weak identity or changing data.

#### Scenario: Skip cause and observed currency
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_skip_cause'` exercises an absent group with an old symbol comment and a proximity candidate, the same with an inactive comment carrier, an absent group with only a proximity candidate, an absent group whose only nearby row is canonical, and unsupported, missing and conflicting source/destination currency context
- **THEN** the first two show `skipped by historical comment`, the third `skipped by proximity` with both gross values, an absent group whose only nearby row has a connector comment is not proximity-skipped, each finding stays absent or uncertain, currency findings keep their reason and show observed source/destination currency and provenance, and import selection is unchanged.

#### Scenario: Legacy identity and residual skip causes
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'coherent_dividend_legacy_identity or historical_diagnostic_skip_cause'` exercises a valid old symbol comment, an old comment with a failed identity check, and sources with only non-identity historical or proximity candidates
- **THEN** each row claimed by its old symbol comment appears in one source block even when a destination-row check fails; only comments that fail the account-and-comment claim criteria use residual skip-cause wording; import selection is unchanged.

#### Scenario: Real read-only acceptance
- **WHEN** the operator-authorized `DRY_RUN=1 LOG_LEVEL=DEBUG .venv/bin/python -m ghostfolio_ibkr_sync` runs with the approved real-data ENV and private log capture
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

Each finding SHALL use English plain words, one `Action:` line and the statement that nothing was written. A block SHALL NOT include a second `Proposed action:` line. No report block or summary line SHALL contain a Python representation, including `Decimal(...)`, dict/list syntax, exponent notation or the word `None` as a value. Missing values SHALL read `unavailable`. Category, failed-check and unavailable-check summaries SHALL use deterministic plain `name:count` text, or `none` when empty.

Every monetary value shown in a block, including gross, fee and monetary deltas on both the source and destination sides, SHALL be quantized for display to the common currency minor unit with round-half-away-from-zero. Quantities SHALL retain their exact plain-decimal display. Display rounding SHALL NOT change comparison, category or action.

The classes SHALL remain coherent, information, noise, outside window and to check. `unsupported currency` SHALL appear only when a nonempty code has no explicit minor-unit definition. Missing currency SHALL read `missing currency`; unequal supported codes SHALL read `conflicting currencies`. A source and destination that both use KRW SHALL be comparable, not unsupported.

A complete single legacy activity with equal quantity and fee SHALL be `legacy declared-rate rounding` information when its Ghostfolio gross equals quantity × the matched payment `Re` `grossRate` and the paid cash gross differs by exactly one minor unit. Its reason SHALL state that the legacy row uses the declared rate and IBKR paid a rounded cash amount. Its sole action SHALL read `No action: IBKR rounding accepted.` The block SHALL stay visible at INFO as audit information. It SHALL NOT suggest that IBKR revised the amount after import. A one-minor-unit fee difference, or any one-minor-unit gross difference outside this proven pattern, SHALL remain to check as `minimal difference, cause unknown`. No finding SHALL automatically correct an activity.

After informational findings, one INFO line SHALL read `N to check, N informational, N noise`, followed by each item to check. Findings SHALL NOT change exits or notifications.

#### Scenario: Plain, quantized, single-action report
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py tests/test_check_dividend_report.py -k 'coherent_dividend_format or check_dividend_report'` formats decimals, unavailable values, empty/nonempty summaries and blocks with match proposals
- **THEN** monetary text uses the currency minor unit; quantities stay exact; each block has one action; the checker reports zero violations.

#### Scenario: Classes from synthetic inputs
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k 'dividend_readable_classes or dividend_readable_pairs or coherent_dividend_one_jpy'` runs noise, one-unit, larger, quantity, legacy, split, absent and unsupported cases
- **THEN** existing classes stay stable except the complete declared-rate one-unit pattern, which becomes information with its known reason and no-action audit result.

#### Scenario: Plain report
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py tests/test_check_dividend_report.py -k 'dividend_readable_report or coherent_dividend_format or coherent_dividend_action'` formats source, destination, identity, summary and match text
- **THEN** all values are plain, monetary values are quantized, missing values read `unavailable`, and each block has one action.

#### Scenario: Correct currency reasons
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k coherent_dividend_currency` formats equal KRW, missing currency, conflicting supported codes and an unknown code
- **THEN** only the unknown code reads `unsupported currency`; equal KRW compares; the other states use their distinct reasons.

#### Scenario: One-JPY legacy row
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k coherent_dividend_one_jpy` runs equal quantity and fee, Ghostfolio gross equal to quantity × `grossRate`, paid cash gross one JPY higher or lower, and one-JPY fee or incomplete-pattern boundaries
- **THEN** the proven gross pattern gives one visible information block with the declared-rate rounding reason and `No action: IBKR rounding accepted.`; one-unit fee differences and other cases that fail one condition remain to check as `minimal difference, cause unknown`.

#### Scenario: Real read-only acceptance
- **WHEN** the operator-authorized real dry-run log is passed to `python3 scripts/check_dividend_report.py <private-log>` and every emitted dividend block is then read
- **THEN** the checker exits 0 with zero violations, and the closing evidence reports the reading verdict for every block without exposing private amounts or identifiers.

Baseline: `scripts/check_dividend_report.py` currently detects Python representations, float noise, contradictory actions, duplicate rows and false unsupported-currency reasons in the saved 2026-10-15 report.

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

### Requirement: Proposed dividend match

Under DRY_RUN, every dividend item to check that has a candidate SHALL carry one `Proposed match` section. The section SHALL show the IBKR dividend and candidate Ghostfolio rows side by side, each row labelled `Keep`, `Keep, quantity differs`, `Duplicate` or `Differs`. Confidence SHALL be strong for the same security, local day, gross and fee, or weak for a candidate without equal gross and fee. A strong row selected to keep whose quantity differs from IBKR SHALL read `Keep, quantity differs`, never plain `Keep`. Quantity SHALL have no tolerance. With no candidate the section SHALL read `no confident match`. Weak proposals SHALL label no row `Keep` or `Keep, quantity differs`.

The proposed-match section SHALL NOT contain an action line. The enclosing block's single `Action:` line SHALL name the row and operation, or state that no action is needed. When the reason compares a Ghostfolio activity, the Action SHALL name that same activity, shown on the block's `Ghostfolio: activity ...` line, never another candidate. A quantity-difference reason SHALL request a manual quantity comparison for that activity and SHALL NOT state that no action is needed. `scripts/check_dividend_report.py` SHALL report a violation if the Action targets another candidate instead of the compared activity. Historical rows that split the same gross SHALL remain visible as `Differs`; their cleanup is out of scope and remains a separate reversible-maintenance idea. A legacy symbol-comment row that owns the source group SHALL appear once as the compared row; it SHALL NOT receive a second legacy-twin block. The proposal SHALL NOT write, repair or change import selection, classes, categories, summary counts, exits or notifications. Text SHALL follow the report's plain and quantized display rules.

#### Scenario: Strong match with a legacy twin
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k 'dividend_match_strong or coherent_dividend_action'` formats a canonical row with a separate free-text legacy twin
- **THEN** labels and confidence remain correct; the block has one `Action:` line and no `Proposed action:` line.

#### Scenario: Strong quantity difference with historical splits
- **WHEN** `.venv/bin/python -m pytest -q tests/test_dividend_diagnostics.py::test_coherent_dividend_action_targets_compared_row_with_legacy_splits tests/test_check_dividend_report.py::test_action_target_differs_from_compared_row tests/test_check_dividend_report.py::test_action_target_matches_compared_row` runs synthetic same-security, same-local-day rows: a compared connector activity with quantity 1, gross 1000 JPY and fee 0 against IBKR quantity 100 with the same gross and fee, plus two historical activities with gross 400 and 600 JPY
- **THEN** confidence stays strong; the connector row reads `Keep, quantity differs`; both historical rows remain visible as `Differs`; the sole Action names the connector activity and requests manual quantity comparison; the checker accepts this target and rejects an Action that names either historical row instead.

#### Scenario: Weak and absent
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k 'dividend_match_weak or coherent_dividend_action'` runs one-unit, quantity, proximity and no-candidate cases
- **THEN** weak proposals keep no row; absent stays no confident match; every block has one action.

#### Scenario: Display only
- **WHEN** `.venv/bin/python -m pytest -v tests/test_dividend_diagnostics.py -k 'dividend_match_unchanged or coherent_dividend_format'` compares findings before and after formatting
- **THEN** classes, categories, summary counts, exits and notifications are unchanged; displayed amounts are quantized and plain.

#### Scenario: Real read-only acceptance
- **WHEN** the operator-authorized real dry-run log is read after `python3 scripts/check_dividend_report.py <private-log>` exits 0
- **THEN** each to-check block has a proposal or no confident match, exactly one action targeting the activity compared by its reason, an explicit `Keep, quantity differs` label when applicable, and no duplicate legacy-identity block.

Baseline: current proposed-match tests preserve classification. The saved 2026-10-15 report also shows a compared connector row with quantity 1 versus IBKR 100, equal gross/fee and two historical rows splitting that gross: the proposal labels the connector row `Keep`, while the Action targets a historical `Differs` row. This is the gap addressed by task 3.2.

### Requirement: Minimal native lab evidence

The connector SHALL emit only three new evidence kinds through `log.debug`: `window`, `preview` and `cash`. Each message SHALL be `LAB_EVIDENCE ` followed by compact JSON with exactly `kind` and `value`. The normal timestamp and DEBUG logging prefix SHALL precede the message. JSON escaping SHALL keep each message on one physical line. JSON numbers SHALL be finite. Unserializable or nonfinite evidence SHALL be omitted without changing existing operations. At INFO, output SHALL be byte-identical to the pre-change implementation. Existing behavior, guards, requests and notifications SHALL remain unchanged. Evidence SHALL NOT dump secrets, URLs, XML, ENV, configuration, headers or response bodies. README SHALL state that lab acceptance needs `LOG_LEVEL=DEBUG`.

#### Scenario: Framing and INFO compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_run_evidence.py -k 'format or info or nonfinite'` runs with synthetic inputs and mocked HTTP
- **THEN** DEBUG evidence parses on single physical lines, preserves escaped payload text and finite numbers, excludes configuration secrets, and adds no HTTP calls; formatted INFO bytes equal the pre-change output, including the per-activity preview list.

### Requirement: Flex window evidence

For each successfully fetched report, the connector SHALL emit one `window` value from `historical_dividend_report_window`. A proven value SHALL be a two-element JSON list such as `["2025-10-16","2026-10-15"]`. Unavailable bounds SHALL be null. No new bound or import guard SHALL be added.

#### Scenario: Fetched report periods
- **WHEN** `.venv/bin/python -m pytest -q tests/test_run_evidence.py -k window` fetches synthetic reports with valid, repeated, missing, invalid, reversed and conflicting bounds through mocked HTTP
- **THEN** each successful fetch emits one matching list or null; retries and existing results stay unchanged.

### Requirement: Complete dry-run preview evidence

For each `ghost_import_activities` call in dry run, the connector SHALL emit one `preview` value containing the complete activity list, including an empty list. Every payload field SHALL remain exact, including timezone-qualified `date`, `dataSource` and `accountId`. Real imports SHALL emit no preview evidence. Existing readable preview lines SHALL remain unchanged.

#### Scenario: Exact payload preview
- **WHEN** `.venv/bin/python -m pytest -q tests/test_run_evidence.py -k preview` exercises empty lists, BUY, SELL and DIVIDEND payloads with fractional numbers and escaped comments in both modes
- **THEN** preview JSON equals the full payload list, no dry-run POST occurs, and real import requests and results stay unchanged.

### Requirement: Exact cash target evidence

After existing cash currency guards pass, `ghost_update_cash_balance` SHALL emit one `cash` value with exactly `accountId`, `balance` and `currency`. Balance SHALL retain its unrounded numeric value in dry run and real run. The evidence SHALL describe the target, not certify a successful PUT or stored state. Failed guards SHALL retain their existing outcome.

#### Scenario: Cash targets and guards
- **WHEN** `.venv/bin/python -m pytest -q tests/test_run_evidence.py -k cash` exercises zero, negative and sub-cent balances, both modes, currency guards and failed PUTs with mocked HTTP
- **THEN** valid target values match the request without rounding, dry run sends no PUT, and existing guard and failure results stay unchanged.
