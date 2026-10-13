# Spec Delta

## Purpose

Record existing connector behavior and limits from README/offline tests. No runtime change.

Commands cite existing offline tests, run from the repository root; expect passing assertions. No production replay.

## ADDED Requirements

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

The connector SHALL select Trade children, exclude CASH/OPT, aggregate DETAIL dividend/payments-in-lieu/withholding by security/day, and select BASE_SUMMARY cash. Other cash types/levels and AssetSummary SHALL be ignored. Trade type SHALL be BUY for exact BUY, otherwise SELL. Quantities/prices SHALL be absolute; commission/withholding costs become fees, refunds/rebates clamp to zero. Dividends SHALL use the `<CCY> <rate> PER SHARE` rate of the last positive payment row of the group, else book the amount as one unit; nonpositive payments SHALL skip (README “How activities are converted”).

#### Scenario: Selected records
- **WHEN** Flex rows are parsed/converted
- **THEN** selection/aggregation applies; London GBP price/fee scale together to GBp.

Evidence: `python -m pytest -q tests/test_parsing.py tests/test_conversion.py -k 'test_parse_trades_keeps_only_trade_elements or test_dividend_and_withholding_are_summed_per_isin_and_day or test_summary_rows_are_ignored_when_detail_rows_exist or test_other_cash_types_are_ignored or test_cash_and_options_are_skipped or test_pence_market_scales_price_and_fee_together'`.

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

Configured notifications SHALL send at most one failure/legacy-expiry summary per completed run, without affecting exit status. Success/warnings without expiry, simulation and interruptions SHALL send nothing.

#### Scenario: Consolidated outcome
- **WHEN** accounts finish with failure/expiry
- **THEN** fixed-code summaries omit identifiers/amounts/secrets; reminders can repeat.

Evidence: `python -m pytest -q tests/test_finalize.py tests/test_token_expiry.py -k 'test_several_failed_accounts_make_one_dispatch_after_every_account_ran or test_summary_carries_no_secret_identifier_host_or_amount or test_notification_problems_keep_exit_code_and_account_processing or test_success_notifies_once_after_both_accounts_and_preserves_exit or test_reminder_is_run_local_and_multiple_runs_can_repeat_it'`.

### Requirement: Current operational limits

The connector SHALL retain documented boundaries: 365-day guidance; daily data; manual corporate actions/history/token renewal; additive corrections; proximity false matches; UTC dates; unconverted cash/commission currencies; unused GHOST_CURRENCY; Yahoo quality; net, nonchronological checks; nontransactional buy/sell phases; preview without server acceptance; buffered 10 MiB Flex responses; no overlap protection.

#### Scenario: Operator checks limits
- **WHEN** limitations are read
- **THEN** these boundaries are visible.

Evidence: README “Limitations”; `sed -n '/^## Limitations/,/^## Inspecting/p' README.md`.
