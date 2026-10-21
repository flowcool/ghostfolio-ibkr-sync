# connector-runtime Specification

## Purpose
Describe how the connector imports IBKR Flex Web Service activities and cash into Ghostfolio today, and its documented limits.

Commands cite existing offline tests, run from the repository root; expect passing assertions. No production replay.

## Requirements

### Requirement: Execution and authentication

The shipped Docker image and every CI job SHALL use CPython 3.14. Local development and tests from a source checkout SHALL use Python 3.14 or newer when documented. Docker SHALL be the only supported sync execution interface. The package SHALL NOT add an explicit Python 3.12 startup rejection; that compatibility is tested but is not a supported runtime guarantee.

The connector SHALL use ENV, Docker one-off runs or Docker CRON, and exactly one credential: GHOST_ACCESS_TOKEN exchanged once per run or unchanged GHOST_TOKEN bearer. Inside the image, Docker starts the installed package with `python -m ghostfolio_ibkr_sync`.

Baseline replaced: README “Prerequisites”, CONTRIBUTING “Tests”, `docs/upstreams.md`, and `tests/test_dockerfile.py` record Python 3.12.

#### Scenario: Configured startup
- **WHEN** startup configuration is evaluated
- **THEN** authentication precedes reads; numeric five-field CRON is validated.

Evidence: README “Running”; `python -m pytest -q tests/test_auth.py tests/test_entrypoint.py -k 'test_access_mode_authenticates_once_before_any_ghostfolio_or_ibkr_call or test_legacy_mode_never_logs_in_and_uses_the_token_as_bearer or test_valid_cron_is_written_and_tested_before_start or test_invalid_cron_is_rejected_without_echoing_input'`.

#### Scenario: Repository runtime declarations
- **WHEN** `.venv/bin/python -m pytest -q tests -k python_runtime_baseline` runs
- **THEN** the Docker base, all seven workflow pins, both Renovate ranges, and public development guidance require Python 3.14 as specified, while Docker remains the only supported sync execution interface.

#### Scenario: Built runtime
- **WHEN** `docker build -t ibkr-python314:check . && bash scripts/check_container_runtime.sh ibkr-python314:check` runs
- **THEN** the isolated one-off and scheduled checks pass, and the container reports CPython 3.14.

### Requirement: Flex source account gate

Before Ghostfolio target lookup, import, cash update, or other financial write, each fetched report SHALL contain at least one `AccountInformation` row. Every such row SHALL carry the same nonempty `accountId`, and that value SHALL equal the paired `IBKR_ACCOUNT_IDS` entry. Duplicate rows for that one account SHALL be accepted.

Missing, blank, mixed, or mismatched source-account evidence SHALL fail that account without a financial write. Other configured accounts SHALL continue through the existing sequential failure isolation. Logs and notifications SHALL NOT contain the observed report account value.

Baseline: `docs/ibkr-setup.md` requires `ClientAccountID` in Account Information, but `process_account` selected a Ghostfolio target by configured list order without validating it before this requirement was implemented.

#### Scenario: Matching source account

- **WHEN** a synthetic report contains one or more `AccountInformation` rows whose nonempty `accountId` equals the paired configured IBKR account
- **THEN** target lookup and the existing import and cash paths continue unchanged.

#### Scenario: Unsafe source account evidence

- **WHEN** synthetic reports contain no Account Information, a missing or blank `accountId`, more than one account, or one account different from the paired configuration
- **THEN** the affected account fails before target lookup and every financial write, the observed account value is absent from logs and notifications, and later configured accounts still run.

Check: `.venv/bin/python -m pytest -q tests/test_parsing.py tests/test_orchestration.py -k 'source_account'`.

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

The connector SHALL select Trade children excluding CASH/OPT, DETAIL dividend/PIL/withholding grouped by security/day for historical deduplication, then partitioned by source account and action for new writes, and BASE_SUMMARY cash; ignore other cash types/levels and AssetSummary. Trades SHALL use BUY for exact BUY and SELL for exact SELL; any other `buySell` value SHALL reject the row (error, run not ok, other trades unaffected); absolute quantity/price; commission/withholding fees with refunds/rebates clamped to zero. Nonpositive payments SHALL skip.

Cash Transactions SHALL establish payments/gross/withholding. Conversion SHALL preserve account, currency/scaling, cash-day UTC date; comments SHALL use the new v2 identity. Description inference and one-unit fallback SHALL be removed.

Each net-positive action SHALL require identical nonempty `accountId/conid/currency/actionID/exDate`, one unique `Re` with `payDate` matching cash day, and matching `date` OR `reportDate`. Associated quantities SHALL agree as positive finite decimals before numeric conversion, without rounding/tolerance. `Re` alone SHALL NOT establish payment.

Dividend/PIL portions of one action SHALL use one common quantity, never sum quantities. Distinct ordinary/bonus actions SHALL produce distinct activities, each with its own proven quantity. Zero-net actions SHALL provide no quantity; negative-net actions/mixed currencies/incompatible evidence SHALL reject the group. Results SHALL be row-order independent. Price SHALL be cash gross/quantity, irrespective of accrual money/rate. After numeric conversion/minor-unit scaling, quantity/price SHALL remain positive finite and fee nonnegative finite; overflow/positive underflow SHALL reject the group.

#### Scenario: Selected records
- **WHEN** baseline selection/conversion is replayed with enriched fixtures
- **THEN** trade selection, scaling and dates remain unchanged; dividend partition and v2 identities follow this delta, with gross and signed withholding conserved before fee clamping.

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
- **THEN** valid actions retain their own quantities and cash totals; invalid groups reject; distinct-action quantities can differ; permutation/accounting/identity assertions pass.

#### Scenario: Unknown trade side
- **WHEN** a synthetic Trade has `buySell` `SELL (Ca.)`, empty or lowercase `sell`, beside valid BUY and SELL rows
- **THEN** only the unknown row is rejected with an error, never counted by the holdings gate; valid rows convert unchanged.

Check: `.venv/bin/python -m pytest -q tests -k 'unknown_trade_side'`.

#### Scenario: Action partition and withholding
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_event_partition` covers split dividend/PIL, two ordinary/bonus actions, unequal action quantities, missing or conflicting tax association, refunds, zero/negative actions and multiple payment days
- **THEN** one activity is proposed per positive action; each tax row belongs to exactly one action; every source cash row is accounted for; ambiguous groups produce no dividend payload and fail that account's result while trades, safe sales, independent cash and later accounts continue.

Withholding SHALL join by nonempty source account, actionID, conid, currency and payment day. Missing tax exDate SHALL be allowed; a nonempty contradictory exDate SHALL reject the group. No amount ratio, description, arbitrary allocation or missing-tax guess SHALL establish ownership. Per-action signed withholding/refunds SHALL be summed before the existing zero-fee clamp. Separate fees can therefore differ from the old group-level clamp when opposite signed tax exists; the preview SHALL expose that difference, never hide it as rounding.

Each action SHALL have one payment day, one contract, one currency and one exDate within its source account. Conflicting, incomplete or negative-net action evidence SHALL reject the entire historical group, emit a reason and fail the account result without blocking independent cash or later accounts. Zero-net actions SHALL create no activity. An action seen again with changed financial values SHALL remain additive: no correction import or update is authorized. Where saved evidence exposes such a conflict, preview SHALL report it for manual review. Automatic sync is not a general financial reconciliation service. Withholding-only groups without a positive payment SHALL retain their existing not-payable outcome; report them without inventing a payment or failing solely because tax is present.

### Requirement: Mapping and duplicate reconciliation

Mapping SHALL prefer ISIN mappings, then IBKR symbols. Trade IDs SHALL suppress reimport. Manual matching SHALL use quantity and ±2 days, including summed fills. Ambiguous split fills SHALL only be summed within the same parsed calendar day, side, resolved ticker, and ISIN; nearby mismatches SHALL warn/skip. Dividends SHALL match by account/comment (including the old symbol comment), or, for existing active YAHOO dividends of the same account and symbol whose comment does not start with `dividend#` (manual or legacy rows), at ±3 days. Connector-comment rows (`dividend#…`) SHALL NOT enter the proximity index, so a distinct payment next to an imported one is imported. A proximity skip SHALL stay a skip. The comparison SHALL use the exact source gross and the existing row's quantity × unitPrice, normalized to a common major unit (minor-unit markets as in conversion) and rounded to its minor unit; an unsupported denomination SHALL be "not comparable". Equal amounts SHALL log INFO "amounts agree" with both fee values; equal amounts do not prove the same payment. Otherwise it SHALL log one WARNING naming both dates, both gross values with currencies (or "not comparable"), both fee values, and the operator action: check IBKR and add the payment by hand if it is distinct. It SHALL NOT change exit status or notifications.

#### Scenario: Existing entries
- **WHEN** existing entries match
- **THEN** duplicates are excluded; manual-buy exclusions warn.

Evidence: `python -m pytest -q tests/test_parsing.py tests/test_filters.py tests/test_orchestration.py -k 'test_resolve_symbol_prefers_mapping_then_ibkr_symbol or test_already_imported_trade_is_not_reimported or test_manual_buy_same_day_same_qty_is_not_reimported_and_warns or test_split_fills_summing_to_a_manual_sell_are_matched or test_dividend_match_window_is_exactly_three_days'`.

#### Scenario: Split-fill calendar-day boundary
- **WHEN** two ambiguous fills use supported dashed timestamps on different days of the same month and their combined quantity equals one nearby manual trade
- **THEN** the fills remain separate ambiguous groups and do not consume the manual trade; same-day dashed fills still reconcile by their sum.

Check: `.venv/bin/python -m pytest -q tests/test_filters.py -k 'split_fills'`.

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

Processing SHALL extract cash identity without quantity checks, deduplicate by account/comment/proximity, then validate candidates. Automatic sync SHALL leave existing activities untouched and unverified. Only the separately invoked maintenance conversion can replace a proven historical comment under its stricter contract. A separate dry-run diagnostic SHALL not change selection.

ChangeInDividendAccruals SHALL be mandatory. Required attributes SHALL cover candidate payment/relevant accrual keys and `quantity/code/date/payDate/reportDate`. Nonempty key mismatches SHALL exclude unrelated accruals; missing keys SHALL NOT prove irrelevance. Unrelated rows SHALL NOT block candidates. Withholding SHALL retain cash evidence without accrual-schema requirements; new action writes SHALL require the explicit tax association in Flex selection and conversion. Missing section/relevant attributes SHALL block account dividends; present-but-empty evidence SHALL reject affected groups. Empty sections without payments SHALL be valid.

Rejections SHALL log distinct reasons, never mark rejected payments imported, and leave trades/cash operating. Partial v2 coverage, action-context conflicts and the new action-partition failures specified in Flex selection and conversion SHALL fail the account result; other existing local rejections SHALL NOT change success, exit, or notifications. Other failures SHALL retain current behavior.

#### Scenario: Compatibility and isolation
- **WHEN** `.venv/bin/python -m pytest -q tests -k dividend_structured_input` runs old, empty, short-window, unrelated, missing, conflicting and partial-v2 cases
- **THEN** identity→dedup→quantity order, scopes, logs, retries and isolation remain; partial v2 and new action-partition failures change the account outcome as specified; other local rejections preserve their outcomes.

#### Scenario: Partition failure isolation
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_partition_isolation` covers a missing tax association and conflicting source actions beside valid trades, safe sales, cash and a later account
- **THEN** the affected group emits no dividend, the account result fails, existing rows remain untouched, and independent work continues.

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

### Requirement: Versioned activity identity reader

Exact lowercase `IBKR#v` SHALL reserve versioned identities. Other `IBKR#<rest>` SHALL remain legacy. Accepted forms are:

- `IBKR#v2#<source-account>:TRADE:<tradeID>`
- `IBKR#v2#<source-account>:DIVIDEND:<actionID>`

The common grammar SHALL be `<BROKER>#v<N>#<source-account>:<KIND>:<source-id>`. `N` SHALL match `[1-9][0-9]*`; segments SHALL match `[A-Za-z0-9._-]+`. V2 SHALL map `TRADE` only to BUY/SELL and `DIVIDEND` only to DIVIDEND. Any other reserved identity SHALL return `invalid_identity` and stop before writes. Notifications SHALL omit identities. New eligible activities SHALL write exactly these v2 forms. No new legacy identity SHALL be generated.

The reader SHALL globally index v2 by source account and comment, not Ghostfolio account. For mapping, dividend v2 SHALL be connector-owned and excluded from proximity and historical diagnostics.

Baseline: ADR 0002/tests prove legacy behavior; two reports repeat 49 conflict-free action IDs.

#### Scenario: Strict dual reader
- **WHEN** `.venv/bin/python -m pytest -q tests -k versioned_identity_reader` covers legacy, valid and invalid comments
- **THEN** legacy and v2 load; invalid reserved identities stop before writes with `invalid_identity`.

#### Scenario: Write account-scoped identities
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_identity_writer` covers two source accounts with equal tradeID/actionID, BUY/SELL, dividend/PIL and different destination names/UUIDs
- **THEN** source-account/event identities differ across source accounts and remain byte-identical across destination remapping; financial conversion follows its existing rules except for the specified dividend partition.

Source row accountId SHALL equal the verified report account for every candidate. Missing, unsafe or conflicting source-account/event segments, or a generated comment over 2000 ASCII characters, SHALL fail the affected account before any financial write. IDs SHALL NOT be trimmed, escaped, hashed, truncated, case-folded or replaced by fallback legacy IDs. A future destination version SHALL require renewed limit validation before use.

Accepted v2 BUY/SELL SHALL update holdings and the global v2 index. Accepted v2 DIVIDEND SHALL update only that index, never holdings or the legacy-global trade-ID set. Manual proximity matches SHALL remain ephemeral and scoped to the verified source account; they SHALL NOT populate the legacy-global trade-ID set or suppress another account. Manual-tag advice SHALL show the exact proposed v2 identity, never recommend a newly written legacy marker. Only proven accepted rows SHALL update real-run state. Simulated rows SHALL update simulation state only.

#### Scenario: Same-run accepted state
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_accepted_state` covers multiple accounts, repeated queries, dividends, accepted subsets and omitted buys before sells
- **THEN** each v2 kind updates only its proper index/holdings; no second source account is suppressed by another account's v2 trade ID; omitted rows do not become existing or authorize a sale; equal tradeIDs manually matched in one source account do not suppress another account and advice uses the v2 grammar.

### Requirement: Dividend action coverage

The positive action set SHALL contain each distinct `(accountId, actionID)` with exact Decimal net above zero, exclude zero, and reject missing, conflicting, or negative evidence.

Legacy exact comments SHALL win. Otherwise, complete v2 coverage SHALL mark the group existing. Partial coverage SHALL reject it, fail its account, and prevent legacy import. Before the no-coverage path, existing v2 dividend context SHALL be checked for the same source account, security and payment day. An unexpected actionID or context that cannot exclude an overlapping stored event SHALL block that group for manual review and fail its account result without blocking independent work. This is an exact-context safety check, not proximity matching or financial equivalence. No coverage without such conflict SHALL retain the existing proximity check, then partition eligible new groups into v2 action activities. Trades, safe sales, cash and later accounts SHALL continue. Partial v2 coverage SHALL retain the rc.5 failure outcome. New action-partition failures SHALL also fail the account result as specified above; other pre-existing local rejections SHALL retain their outcomes.

#### Scenario: Complete, partial and absent coverage
- **WHEN** `.venv/bin/python -m pytest -q tests -k "versioned_identity_reader or v2_generation_dedup"` covers complete, partial and absent multi-action sets plus zero-net and invalid actions
- **THEN** complete coverage skips, partial coverage fails only the account without import, absent coverage follows proximity then v2 selection, and invalid new action partitions fail as specified without emitting dividend rows.

#### Scenario: Historical generations and conservative precedence
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_generation_dedup` covers `IBKR#<tradeID>`, resolved-symbol/raw-symbol/ISIN `dividend#<key>#<date>`, mixed v2 rows, inactive markers, destination moves and overlapping windows
- **THEN** legacy-global trade IDs still suppress matching IDs globally; account-local exact historical dividend comments win before action coverage; full v2 coverage skips globally by source account; partial coverage blocks the whole group; v2 dividends never enter proximity or historical diagnostics.

Legacy precedence SHALL NOT certify event completeness. It can still suppress a later distinct event in the same historical security/day group. Preview SHALL report this limitation; no automatic backfill, repair, filling of partial coverage or ownership inference from equal amounts is authorized.

#### Scenario: Replaced identity or additional same-day event
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_action_conflict` covers replaced actionIDs, unrelated source accounts, changed financial values, unknown stored security context and legitimate additional same-day actions
- **THEN** detectable overlapping conflicts block without a new payout; ambiguous additional events require manual review; unrelated accounts continue. No claim is made that this guard detects revisions which also change day or security.

All candidates in a group SHALL pass validation before dispatch. One import batch SHALL NOT be treated as an atomic transaction: Ghostfolio can accept a subset. Partial acceptance SHALL preserve proven accepted identities and fail the account. Later imports SHALL retain partial-coverage refusal; no automatic filling or legacy fallback is allowed. Repeated failures can recur throughout the configured report window; logs and upgrade guidance SHALL expose the recovery requirement.

#### Scenario: Bounded recovery after partial acceptance
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_partial_recovery` covers partial server acceptance, uncertain requests and changed source evidence
- **THEN** normal reruns refuse incomplete coverage. A recovery preview identifies only exact missing action payloads from complete source evidence and a fresh destination snapshot. It preserves accepted rows and financial values. Uncertainty or changed evidence blocks dispatch.

Recovery SHALL require stopped competing writers, settled outstanding requests, complete source/action and destination evidence, a reviewed manifest of exact missing identities and financial fields, and a separately approved operation plan. A versioned, tested recovery command SHALL submit only those missing payloads, prove full coverage by readback, then prove zero reinsertions on normal simulation. Recovery is a distinct explicit import operation, not migration conversion or automatic retry. Missing recovery tooling blocks writer enablement; no temporary live script is an alternative.

### Requirement: Exact short import acceptance

A valid 2xx response SHALL map each returned row to one submitted `(accountId, comment)` and verify financial fields. A shorter known set SHALL retain proven creations, warn with omitted comments and an instruction to inspect Ghostfolio before rerun, avoid retry, and fail the account. Sales SHALL use only accepted buys. Cash and later accounts SHALL continue. Unknown-outcome fencing and identifier-free notifications SHALL remain.

Baseline: the current short-count test is clean; the pinned lab returned HTTP 201 without creation for a duplicate.

#### Scenario: Proven short response
- **WHEN** `.venv/bin/python -m pytest -q tests -k short_import_acceptance` runs full, short and unknown responses
- **THEN** only full acceptance is clean; short acceptance preserves the exact returned subset without retry; unknown outcomes retain their write fence.

### Requirement: Account read timeout

Ghostfolio account list and account detail GET requests SHALL use a 120-second socket inactivity timeout. Cash PUT SHALL retain its 30-second timeout. Authentication, activity reads, redirect rejection, simulation and retry behavior SHALL remain unchanged.

Baseline: ghost_get_accounts and ghost_update_cash_balance use timeout=30. Existing redirect tests assert that value.

#### Scenario: Account reads with more time
- **WHEN** mocked account lookup and cash preflight requests complete successfully
- **THEN** both GET requests use timeout=120 and the cash PUT uses timeout=30.

#### Scenario: Read timeout before cash write
- **WHEN** a mocked cash preflight GET raises ReadTimeout in simulation or live mode
- **THEN** the exception propagates after one GET and no PUT occurs.

Check: `.venv/bin/python -m pytest -q tests/test_ghostfolio.py -k 'account_read_timeout or accounts_reject_redirect or cash_balance_get_rejects_redirect'`.

### Requirement: Source identity evidence gates

Before enabling the writer, source qualification SHALL record capture hashes, report/query fields, account count, overlap window, event counts, revision/reversal coverage and conflicting associations. Evidence SHALL distinguish observations from vendor guarantees. Missing proof for a required qualification case SHALL block the affected writer capability; synthetic tests alone SHALL NOT prove IBKR stability.

Observed on 2026-10-21 by offline XML inspection:

| Capture | SHA-256 | Bounded observation |
|---|---|---|
| A, baseline | `8a50478e135af8e0ac2deac72d5aab3248c4915807622204e589512461926df4` | 135 trades with safe nonempty tradeID/accountId; 118 STK, 16 CASH, 1 OPT; one AccountInformation; nine cash-report currency rows |
| B, enriched | `30a04860bea149ed55b3308c326997446940ee8d7f2859e534e84284de33e539` | One source account; 55 payment rows, 50 withholding rows, 46 security/day groups, 49 positive actions, 154 accrual rows |
| C, timezone-enriched | `a8864f5d40ceccffac677d76cab97c2ffda37e06d0a6493f000ef4f50b0fd134` | Same action set and normalized payment evidence as B; timezone suffix differs |

Three groups contain two actions. All 50 withholding rows match payment account/action/contract/currency/day. All 50 lack exDate. No fee-clamp total difference was observed between action and historical grouping in these captures; this does not prove future refund cases. Payment evidence normalized here means contract, currency, exDate, calendar day, payment type and amount, grouped by account/action. These captures establish repeatability over two nearby acquisitions of one account. They do not establish lifetime stability, future revisions, complete short windows or cross-account uniqueness. B and C are diagnostic section captures, not complete runnable reports with AccountInformation.

The inspected [IBKR cash reference](https://www.ibkrguides.com/reportingreference/reportguide/cash%20transactionsfq.htm) and [accrual reference](https://www.ibkrguides.com/reportingreference/reportguide/change%20in%20dividend%20accrualsfq.htm) do not establish actionID lifetime or uniqueness. No such guarantee is assumed.

| Gate | Required proof before enabled writes |
|---|---|
| G1: bounded event stability | Define qualified report windows and required revision/reversal/repayment cases before enablement. Saved overlaps SHALL match events independently of actionID and record whether it is retained, replaced or reused. Record case counts and missing coverage explicitly; nearby captures alone leave revision qualification pending. Finite observations SHALL NOT certify lifetime stability. Reuse for independent payable events blocks this grammar. Replacement conflicts require the conservative guard and operator review; unhandled cases require a revised proposal. |
| G2: account scope | Record authoritative or saved multi-account observations when available; label absent evidence unknown. Global uniqueness is informational, not an enablement prerequisite: always retain the account segment. Equal synthetic tradeIDs/actionIDs in two source accounts MUST prove independent identities and deduplication. |
| G3: complete partition | Prove payment, PIL, tax/refund and accrual association, cancellation handling, and complete windows for the qualified cases. Cash totals must conserve exactly before clamping. No stable identity proof can turn an incomplete event window into a complete financial record. |

Trade qualification SHALL likewise check overlapping-report stability, repeated/conflicting IDs, source-account equality and corrections. A changed trade under an already stored identity SHALL require manual review, never an automatic correction.

#### Scenario: Source qualification remains bounded
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_source_qualification` replays qualified saved-input summaries and synthetic revision, reuse, multi-day, missing-account, incomplete-window and cross-account counterexamples
- **THEN** each evidence claim has an explicit status and scope; a failed or missing gate prevents the corresponding write capability; no fixture result is reported as a vendor guarantee.

### Requirement: Destination comment compatibility gates

The destination qualification reference SHALL be Ghostfolio 3.86.0, source commit `ef47c0d1b2c48fa4e97fb381561b514e657928cf`. Existing local lab documentation binds it to image digest `sha256:929a54a1972c48f3cfb30af2db6f9f2aaeb610a9cc5f53264f1df1629eb43078`. This is saved deployment evidence, not a current runtime observation. Production desired configuration uses mutable `latest`; version drift SHALL require renewed qualification.

Pinned source observations:

- [Config](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/libs/common/src/lib/config.ts) sets `COMMENT_MAXIMUM_LENGTH` to 2000.
- [Create DTO](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/libs/common/src/lib/dtos/create-order.dto.ts) and [update DTO](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/libs/common/src/lib/dtos/update-order.dto.ts) validate an optional string, trim its ends and enforce that maximum. No comment character filter appears there. [Order schema](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/prisma/schema.prisma) has nullable String with no narrower declared column limit.
- [Import service](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/apps/api/src/app/import/import.service.ts) compares comment and financial fields without accountId; a changed comment can defeat server deduplication.
- [API setup](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/apps/api/src/main.ts) transforms and whitelists DTO fields and limits JSON bodies to 10mb. That request-size bound is separate from comment length.

The writer SHALL use only ASCII `[A-Za-z0-9._-]+` in account and source-ID segments. `#` and `:` SHALL appear only as grammar separators. Full length SHALL be at most 2000 characters: `15 + len(account) + len(tradeID)` for TRADE, `18 + len(account) + len(actionID)` for DIVIDEND. Valid inputs need no trimming or Unicode length interpretation. Existing historical reader acceptance SHALL NOT acquire the writer's new length restriction.

G4 SHALL verify the image/source binding, realistic identity lengths, permitted punctuation and two-account otherwise identical payloads by exact byte-for-byte import/readback in an isolated synthetic lab. Local boundary tests SHALL cover 1999/2000/2001 against the source-backed 2000-character maximum; a lower arbitrary writer cap SHALL NOT replace that contract. Unicode, whitespace and reserved characters SHALL reject locally. Source inspection does not replace this pending round-trip gate.

#### Scenario: Comment boundaries
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_comment_limits` runs both identity kinds at 1999/2000/2001 characters with invalid separators, whitespace, Unicode and punctuation
- **THEN** only valid ASCII identities of at most 2000 characters become payloads; no transformation or legacy fallback occurs; invalid existing reserved comments still stop globally.

### Requirement: Offline historical identity migration preview

An explicit maintenance tool SHALL produce an offline preview before any conversion. The automatic importer SHALL remain additive. Interface: `python identity_migration.py preview --inputs <inputs.yaml> --output <new-directory>`, from the versioned checkout, outside the runtime image like existing cleanup tools. Preview, apply and rollback SHALL use one maintenance engine and shared pure conversion rules. The tool provides `preview`, `apply`, `inspect` and `rollback` subcommands. Offline tests are in `tests/test_identity_migration.py`.

The keyed YAML input SHALL reference saved Flex reports, a complete exact Ghostfolio activity snapshot with count/version evidence, the complete declared inventory of every configured source account able to import into the portfolio, explicit source-account to destination-account mapping, symbol mapping and IANA TZ. Reports SHALL cover each affected window for all such accounts. Missing accounts or incomplete windows SHALL make affected trade conversions non-actionable; an operator declaration alone SHALL NOT prove report completeness. Files SHALL be opened read-only. The preview SHALL NOT load credentials, authenticate, fetch reports, issue HTTP, update cash/platforms, send notifications or write back to input locations. An existing output path, any input/output overlap or symlink redirection SHALL fail before output. Outputs SHALL be private: directory 0700, files 0600. All mutations SHALL be disabled even when inherited `DRY_RUN=false`.

Only exact and unique 1→1 matches SHALL be eligible for comment conversion:

- Trades: an owned legacy `IBKR#<tradeID>` row and exactly one proven source account/trade event.
- Dividends: an owned historical resolved-symbol, raw-symbol or ISIN `dividend#<key>#<date>` row covering exactly one positive action. Multiple payment/PIL portions of that one action are allowed. Several actions represented by one row are excluded.
- Both: unique source and destination ownership; same destination account, active YAHOO context, side/type, resolved security, supported denomination, source calendar day under the proven historical date policy, exact quantity, gross and fee. Retain the stored UTC instant. Compare original JSON numbers as decimals, not reconstructed floats. Both historical group-level and proposed action-level fee clamps SHALL equal the stored fee; any difference blocks conversion. Any rounding or amount tolerance from the diagnostic report SHALL NOT grant migration eligibility. Missing or conflicting evidence SHALL block conversion.

Preview SHALL list each source event and each in-scope historical row once, with activity ID, source reference, old/new comment, association cardinality, existing fields, expected financial fields, exact differences, evidence status and reason. Counts SHALL distinguish eligible replacement, already v2, absent/new candidate, aggregate, ambiguous, conflicting, partial coverage, unsupported and outside-window. The manifest SHALL bind schema/version, input hashes, source/destination scope, window/TZ, mapping hash, tool commit, destination image/version, planned ordered replacements and before/after row fingerprints. Equal input bytes SHALL give equal ordered decisions and manifest hash; timestamps SHALL stay outside the hashed plan.

The preview SHALL replay the complete import selection with the declared configuration against the original snapshot and a copy with only planned comments replaced. The full selected event/payload set and holdings decisions SHALL be identical, not merely counts. In particular, removing a legacy-global trade marker SHALL NOT expose a previously suppressed trade in another source account. Any difference blocks the affected conversion. Bind this proof to the inventory, windows, mappings, tool and snapshot hashes; changed configuration invalidates it. This bounded proof makes no guarantee about undeclared future accounts.

No alias activity, replacement financial activity, deletion or split SHALL be proposed. Keep manual, inactive, excluded, non-YAHOO, unsupported and unproven rows unchanged. Keep outside-window history visible and unchanged. An already occupied v2 identity, several old rows claiming one event, a legacy trade ID claimed by several accounts, or a partial v2 group SHALL block every affected replacement. Exact historical import deduplication remains more permissive than migration eligibility; preview SHALL explain this difference.

#### Scenario: Exact migration preview
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_migration_preview` exercises exact trade/dividend matches, oldest symbols, one-action split PIL, multi-action aggregates, duplicated ownership, manual/inactive rows, rounding differences, absent sources, short windows, mixed generations, opposite-signed tax clamps and a legacy-global trade marker suppressing another configured account
- **THEN** only unique exact 1→1 rows with unchanged before/after selection are eligible; every other row has one visible exclusion reason; source gross and signed tax totals reconcile; no source or destination input changes.

#### Scenario: Offline and deterministic boundary
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_migration_offline` runs repeated previews with all network access denied, inherited false DRY_RUN, exact JSON decimals, invalid snapshots, changed mappings and output/input overlaps
- **THEN** previews use no network or credentials, write only a new private output directory, reject incomplete/redacted inputs, preserve every input hash, and produce identical decisions for identical inputs.

### Requirement: Explicit maintenance conversion and rollback boundary

Historical conversion SHALL be a separate explicit maintenance action, never a sync option or an effect of `DRY_RUN=false`. The `apply` and `rollback` subcommands SHALL require the approved manifest hash and a private journal. Neither subcommand is authorized by proposal approval. A versioned, tested operation plan and separate Florent GO SHALL bind exact targets, commands, evidence, write count, batch sizes, pacing, stop rules and rollback. Batch and pacing limits SHALL come from qualification of update/background effects, not an assumed safe default. Reuse `cleanup_recovery.py` atomic YAML journal persistence and locking; adapt `cleanup_duplicates.py` explicit PUT construction only after preservation qualification. Its pair validation and delete executor SHALL NOT be reused for this comment-only operation.

Apply SHALL stop every competing writer, obtain a recoverable backup, re-read complete unredacted state and compare every planned row and identity occupancy with its manifest before the first write. Stale input, version/mapping drift, incomplete evidence or unavailable writer exclusion SHALL stop. Only the comment of listed eligible activities SHALL change; IDs, ownership, quantity, price, gross, fee, currency, date, tags and profiles SHALL remain unchanged. No insert/delete, cash/platform update or aggregate conversion is allowed.

The pinned [activity update controller](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/apps/api/src/app/activities/activities.controller.ts) exposes PUT by activity ID. Its update DTO requires financial fields; a comment-only body is insufficient. Its service can enqueue market-data gathering. G5 SHALL prove the exact whitelisted full request, scope/ownership checks, numeric/date/tag/profile preservation, background effects and reverse request on the qualified image. No raw GET object SHALL be echoed into PUT. If preservation cannot be proved, apply remains unavailable and a revised proposal is required.

Before dispatch, the journal SHALL durably record each row's original comment/full fingerprint, target comment and pending request. Readback SHALL prove each conversion before advancing. A timeout, unknown result, server normalization, changed context or failed readback SHALL stop with the pending state retained; no automatic retry. Known completed subsets SHALL remain explicit. A later run SHALL require independent evidence that the pending request has completed or cannot still take effect before retry or reversal. Request-bound evidence is preferred where available; deployment-specific cancellation/quiescence proof requires its own authorized operation. An old-comment or absent-row readback alone SHALL NOT settle a delayed request. If no such proof is available, retain uncertainty and stop.

Rollback SHALL restore only journal-owned converted comments after complete readback proves the recorded v2 comment and unchanged financial/ownership context. Drift SHALL block reversal. Retain all newly imported v2 rows: this migration rollback cannot remove them. A global database restore is not the normal rollback and requires its own operation and reconciliation of intervening writes.

#### Scenario: Guarded conversion and reverse conversion
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_migration_apply_rollback` mocks exact successful updates, stale manifests, concurrent writers, profile effects, numeric normalization, partial completion, timeouts and post-conversion edits
- **THEN** only approved comments change; full readback proves preservation; uncertain requests are not retried; rollback restores only unchanged journal-owned comments and preserves newly imported v2 activities.

### Requirement: Writer release order and sibling compatibility

The released reader floor SHALL remain rc.5, commit `246b890d8cf2b6a58e99bbbf0169aa5f846c23bc`, image `sha256:32a034c96c2a675329e0aa38a3003a0352db8cec013ea74b6d04ac04cc8a9369`. Existing delivery evidence records 72 reader/acceptance tests, 1701 total tests, immutable publication, eight successful native lab invocations, empty first-install 142 creations, golden upgrade zero creations, zero idempotence creations and both instances stopped. This session inspected that evidence and local Git ancestry; it performed no new runtime replay.

Order SHALL be: proposal approval; implementation-task creation; offline implementation/qualification and review; archive and main replay; separate GO for an unused immutable writer RC numbered rc.6 or later; publish digest; both versioned empty/golden lab scenarios PASS on that same digest; separately authorized production preview/soak; separately authorized comment conversion after reviewed migration preview; stable promotion only under a new GO. A failed digest SHALL be superseded, never promoted. Lab tests SHALL include new v2 creates, repeat runs, mixed history, short/partial acceptance, bounded recovery, maintenance and rollback on isolated synthetic rows. Expected sets and counts SHALL derive from each fixed report/snapshot pair; earlier reader counts SHALL NOT be extrapolated to the writer partition. Lab credentials SHALL remain separate from production. Stop both instances after runs.

Before any newly imported or converted v2 row exists, the previous validated rollback procedure remains applicable. Afterwards, safe halt SHALL stop writers and force simulation, then restore rc.5 or a newer qualified dual reader. Pre-rc.5 code SHALL NOT run against mixed history. Reader rollback preserves rows, does not repair data, and can still refuse partial dividend coverage. Re-enable writes only after exact mixed-generation preview and a separate GO. G6 SHALL prove this behavior using the actual rc.5 image, including complete and partial action sets, before production writing.

The common grammar SHALL remain broker-specific in generation: IBKR v2 and the Bourse Direct BD v3 target contract. The inspected Bourse Direct checkout at `3193086cd0223b0bfb18a388c53f1e0c65327dce` defines v3 in its proposed notice-import spec, but its runtime still contains v1/v2 writers; no delivered v3 writer is asserted. DEGIRO at `e8908adabd5453c9b57cb2dd687dc92a81ce15b2` writes unversioned account-scoped comments. Its authoritative CORE_PROVENANCE pins the IBKR single-file source at `5749146ff297133a6a85d9006bba60b65d9f7cde`; package adoption remains separate. DEGIRO remains pinned pending its separately owned generation decision. No sibling writer changes are implied. G7 SHALL compare sibling readers and request helpers at pinned revisions. Every changed broker-agnostic import/cash/request helper SHALL flag DEGIRO propagation under ADR 0007 and require a separate downstream change. Amend ADR 0002, README and upgrade instructions with exact formats, required matching Trade accountId, historical limits, comment cap, recovery prerequisites, preview/maintenance separation and the rc.5 rollback floor. Existing cleanup tools SHALL NOT run against v2 history until separately qualified; document that restriction and their outside-image boundary; add no new ADR.

#### Scenario: Mixed-history rollback and downstream boundary
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_release_compatibility` runs a compatibility matrix for old/new comments, complete/partial sets, sibling namespaces and proposed maintenance changes
- **THEN** the matrix preserves reading of all historical generations, excludes pre-rc.5 rollback after v2, records pending image-backed proofs, and leaves sibling generations and pins unchanged.

All G1–G7 evidence, current destination runtime/image confirmation, a complete saved migration-input replay and image-backed import/maintenance/rollback results remain necessary. None is certified by strict OpenSpec validation. Material counterexamples SHALL stop the affected work and return the proposal for approval; they SHALL NOT become implicit implementation assumptions.
