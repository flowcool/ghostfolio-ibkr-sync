## MODIFIED Requirements

### Requirement: Simulation

Absent or blank `DRY_RUN` SHALL simulate and emit WARNING `DRY_RUN not set: simulation, nothing written` on every invocation, including configuration failure. After trimming and lowercasing, `1/true/yes/on` SHALL simulate; only `0/false/no/off` SHALL request live writes. Any other value SHALL fail configuration with exit 1 before any HTTP call. After rejection, only the configured Apprise Failure notification SHALL be permitted; no IBKR/Ghostfolio HTTP calls or financial writes SHALL occur. Other safety guards SHALL still apply.

Simulation SHALL run login, reads and the existing preview pipeline without activity, cash or platform writes. Failed simulations SHALL send the configured Failure notification. Successful simulations, token-expiry reminders and previews SHALL send no notification unless corporate-action-detection requires a hold, changed finding or resumption summary. Corporate-action evidence and state SHALL be evaluated in simulation without financial writes. Missing/unwritable corporate-action state or an active hold SHALL exit 1 with the existing consolidated failure path; a clean simulation with valid state retains exit 0. Existing TZ-forced notifications SHALL remain for explicit live mode.

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

#### Scenario: Corporate-action runtime integration
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k runtime_contract` runs the baseline and corporate-action variants for this requirement
- **THEN** baseline behavior remains except for the specified safety holds, persistent-state prerequisites and consolidated corporate-action notification rules; no corporate-action financial request is sent.


### Requirement: Flex selection and conversion

The connector SHALL select Trade children excluding CASH/OPT, DETAIL dividend/PIL/withholding grouped by security/day for historical deduplication, then partitioned by source account and action for new writes, and BASE_SUMMARY cash; ignore other cash types/levels for ordinary import and ignore AssetSummary. Before related BUY/SELL or corrections, CorporateAction rows SHALL follow corporate-action-detection. Require the CorporateActions section: selected-empty means no rows observed in the report window; absent means hold that verified source account's BUY/SELL, without blocking independent cash solely for that absence. Setup documentation SHALL list the required section and observed fields. Do not require OpenPositions or another export format.

Acquire and validate the configured source reports once into a run inventory before review dispatch, including when activity review is disabled. Retain per-source acquisition failures and process independently safe accounts; one missing report SHALL not turn the entire inventory into a success or stop every other account. Preserve existing cross-account reference-replacement and uncertainty fences. Check source account before target lookup or financial action. The inventory changes acquisition timing, not account ownership, existing financial prerequisites or failure isolation. Explicit associated cash evidence SHALL be reported without creating new cash activities or changing dividend conversion. Trades SHALL use BUY for exact BUY and SELL for exact SELL; any other `buySell` value SHALL reject the row (error, run not ok, other trades unaffected); absolute quantity/price; commission/withholding fees with refunds/rebates clamped to zero. Nonpositive payments SHALL skip.

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

Each action SHALL have one payment day, one contract, one currency and one exDate within its source account. Conflicting, incomplete or negative-net action evidence SHALL reject the entire historical group, emit a reason and fail the account result without blocking independent cash or later accounts. Zero-net actions SHALL create no activity. An action seen again with changed financial values SHALL NOT create a correction import. With review disabled, no update is authorized. With review enabled, only the separately approved one-to-one replacement specified in activity-correction-review SHALL update an existing action. Invalid or incomplete action evidence SHALL remain non-actionable. Where saved evidence exposes a conflict, preview SHALL report it for manual review. Withholding-only groups without a positive payment SHALL retain their existing not-payable outcome; report them without inventing a payment or failing solely because tax is present.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.

#### Scenario: Corporate-action runtime integration
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k runtime_contract` runs the baseline and corporate-action variants for this requirement
- **THEN** baseline behavior remains except for the specified safety holds, persistent-state prerequisites and consolidated corporate-action notification rules; no corporate-action financial request is sent.


### Requirement: Position and acceptance guards

Incomplete/redacted/invalid-profile listings SHALL stop startup; assetProfile SHALL override legacy SymbolProfile. Draft/excluded/non-YAHOO records SHALL not back reconciliation. Future candidates SHALL defer. Corporate-action identity and effective-quantity holds SHALL apply before related BUY/SELL dispatch, including optional corrections. Use proven dated native adjustments or already-normalized units exactly once for the position guard. Preserve stored activity values for identities and readback. Do not infer native-adjusted holdings by summing raw activities. Missing proof SHALL hold the bounded scope under corporate-action-detection; all existing acceptance and uncertainty fences SHALL remain. Release SHALL not authorize importing unmatched pre-event raw trades into an already-normalized history. Re-evaluate related conclusions after each confirmed review correction before further dispatch. Unknown effective timing SHALL retain the affected candidate hold. Sales SHALL pass net-quantity and accepted-buy checks; unknown acceptance SHALL block later same-target queries within this run.

#### Scenario: Unusable position evidence
- **WHEN** evidence cannot back sales
- **THEN** candidates are excluded; accepted server symbols determine holdings.

Evidence: `python -m pytest -q tests/test_ghostfolio.py tests/test_orchestration.py -k 'test_count_mismatch_refuses_to_sync or test_current_profile_takes_precedence_over_legacy or test_server_skipped_buy_cannot_authorize_sell_in_same_batch or test_uncertain_import_blocks_further_writes_only_to_same_target or test_canonical_accepted_buy_cannot_back_sale_under_original_ticker'`.

#### Scenario: Corporate-action runtime integration
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k runtime_contract` runs the baseline and corporate-action variants for this requirement
- **THEN** baseline behavior remains except for the specified safety holds, persistent-state prerequisites and consolidated corporate-action notification rules; no corporate-action financial request is sent.


### Requirement: Notifications

Configured notifications SHALL send at most one consolidated Failure, corporate-action, legacy-expiry or forced-preview summary per completed run, without affecting exit status. Failure SHALL notify even for default or truthy simulation and invalid `DRY_RUN`. A failure with an expiry reminder or forced preview SHALL use one Failure summary, never a second dispatch. Without configured Apprise, no notification SHALL be sent.

Successful simulation, including default/blank/truthy `DRY_RUN`, SHALL send no success, expiry-only or preview notification. Corporate-action-detection SHALL add active holds each run, nonblocking first/changed findings and verified resumption to that same dispatch, including simulation. Corporate-action summaries SHALL retain the existing identifier/amount/secret redaction. Failed or unconfirmed delivery SHALL leave its finding eligible next run. Record delivery through separately locked, revalidated companion notification state after send; its failure SHALL not change financial decisions or exit status. With explicit false `DRY_RUN`, missing or invalid IANA `TZ` SHALL retain the forced-preview summary even when every account succeeds, and the summary SHALL name the reason. Success/warnings without expiry or a corporate-action notification reason, and interruptions, SHALL send nothing.

#### Scenario: Consolidated outcome
- **WHEN** `python3 -m pytest -q tests/test_finalize.py tests/test_token_expiry.py -k 'test_several_failed_accounts_make_one_dispatch_after_every_account_ran or test_summary_carries_no_secret_identifier_host_or_amount or test_notification_problems_keep_exit_code_and_account_processing or test_success_notifies_once_after_both_accounts_and_preserves_exit or test_reminder_is_run_local_and_multiple_runs_can_repeat_it'` runs with explicit live mode
- **THEN** fixed-code summaries omit identifiers, amounts and secrets; delivery does not affect exit status, and reminders can repeat on later runs.

#### Scenario: Forced preview notifies
- **WHEN** `python3 -m pytest -q tests/test_finalize.py -k historical_diagnostic_preflight` runs with absent/invalid `TZ`, valid `TZ`, and default/truthy/explicit-false `DRY_RUN`
- **THEN** explicit false with invalid TZ sends one summary naming the forced-preview reason even on success; successful default/truthy simulations without a corporate-action notification reason stay silent; failures send Failure once.

#### Scenario: Notification compatibility
- **WHEN** `python3 -m pytest -q tests/test_finalize.py -k dry_run_modes` exercises default, blank, all truthy values, explicit false and invalid input, with success, failure, expiry reminders, previews, TZ forcing, configured/disabled Apprise and delivery failure
- **THEN** failed runs send one Failure notification when configured, including default/truthy simulation and invalid input; successful simulations, expiry-only reminders and previews without a corporate-action notification reason send nothing; explicit false retains existing notification behavior; delivery never changes exit status.

#### Scenario: Corporate-action runtime integration
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k runtime_contract` runs the baseline and corporate-action variants for this requirement
- **THEN** baseline behavior remains except for the specified safety holds, persistent-state prerequisites and consolidated corporate-action notification rules; no corporate-action financial request is sent.


### Requirement: Current operational limits

The connector SHALL retain documented boundaries: 365-day guidance; daily data; corporate-action detection with evidence-based BUY/SELL holds; manual corporate-action treatment, history and token renewal; additive imports with optional explicitly approved corrections; proximity skips next to manual or legacy rows (INFO when amounts agree, WARNING otherwise, never imported; a distinct payment there needs a manual add); trust principle: a row with a connector comment (`dividend#…`) is ours and trusted by exact identity, and with review disabled a user edit of such a row is out of contract; enabled review SHALL expose validated per-event differences for approval; UTC dates; unconverted cash/commission currencies; Yahoo quality; net, nonchronological checks; nontransactional buy/sell phases; preview without server acceptance; buffered 10 MiB Flex responses; no general overlap protection. Enabled correction dispatch SHALL require exclusive writes and persistent recovery evidence as specified in activity-correction-review. README SHALL describe the new reader floor for notes-bearing references and the persistent-volume requirement. It SHALL document CORPORATE_ACTION_STATE_FILE, simulation initialization, live BUY/SELL refusal on missing/invalid state, simulation refusal with exit 1 on missing/unwritable state, private retained report bytes, retained events outside later report windows, candidate-specific hold/release evidence, notification frequency and the stable Ghostfolio 3.91.0 minimum for accepting native split evidence. State loss SHALL require a reviewed simulation inventory that reuses surviving evidence and unresolved events; deleting state SHALL not be a resolution method. Available windows cannot certify lifetime history. Document unsupported-event holds, explicit old/new identity mappings, effective-date uncertainty and the unqualified non-admin read gate. Native treatment, identity remapping and historical repair SHALL remain unavailable in this increment. Acknowledgment SHALL not release holds. Rollback SHALL stop writers and force simulation before using an older image that lacks these guards; reverting code SHALL not be described as restoring financial data.

#### Scenario: Operator checks limits
- **WHEN** limitations are read
- **THEN** these boundaries are visible, and `GHOST_CURRENCY` is not documented as a setting.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.

#### Scenario: Corporate-action runtime integration
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k runtime_contract` runs the baseline and corporate-action variants for this requirement
- **THEN** baseline behavior remains except for the specified safety holds, persistent-state prerequisites and consolidated corporate-action notification rules; no corporate-action financial request is sent.
