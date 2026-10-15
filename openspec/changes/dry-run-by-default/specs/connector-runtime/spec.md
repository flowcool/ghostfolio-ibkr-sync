## MODIFIED Requirements

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

### Requirement: Notifications

Configured notifications SHALL send at most one Failure, legacy-expiry or forced-preview summary per completed run, without affecting exit status. Failure SHALL notify even for default or truthy simulation and invalid `DRY_RUN`. A failure with an expiry reminder or forced preview SHALL use one Failure summary, never a second dispatch. Without configured Apprise, no notification SHALL be sent.

Successful simulation, including default/blank/truthy `DRY_RUN`, SHALL send no success, expiry-only or preview notification. With explicit false `DRY_RUN`, missing or invalid IANA `TZ` SHALL retain the forced-preview summary even when every account succeeds, and the summary SHALL name the reason. Success/warnings without expiry and interruptions SHALL send nothing.

Baseline modified: `openspec/specs/connector-runtime/spec.md`, Simulation says "SHALL preview without financial writes/notifications"; Notifications says "operator-chosen simulation and interruptions SHALL send nothing." The current `finalize_run()` docstring at `ibkr_to_ghostfolio.py:2978` says "Dry runs (DRY_RUN read raw, even when configuration is invalid) never notify." This delta replaces the simulation suppression for failures. Commands here target tests to add or update, not current evidence.

#### Scenario: Consolidated outcome
- **WHEN** `python3 -m pytest -q tests/test_finalize.py tests/test_token_expiry.py -k 'test_several_failed_accounts_make_one_dispatch_after_every_account_ran or test_summary_carries_no_secret_identifier_host_or_amount or test_notification_problems_keep_exit_code_and_account_processing or test_success_notifies_once_after_both_accounts_and_preserves_exit or test_reminder_is_run_local_and_multiple_runs_can_repeat_it'` runs with explicit live mode
- **THEN** fixed-code summaries omit identifiers, amounts and secrets; delivery does not affect exit status, and reminders can repeat on later runs.

#### Scenario: Forced preview notifies
- **WHEN** `python3 -m pytest -q tests/test_finalize.py -k historical_diagnostic_preflight` runs with absent/invalid `TZ`, valid `TZ`, and default/truthy/explicit-false `DRY_RUN`
- **THEN** explicit false with invalid TZ sends one summary naming the forced-preview reason even on success; successful default/truthy simulations stay silent; failures send Failure once.

#### Scenario: Notification compatibility
- **WHEN** `python3 -m pytest -q tests/test_finalize.py -k dry_run_modes` exercises default, blank, all truthy values, explicit false and invalid input, with success, failure, expiry reminders, previews, TZ forcing, configured/disabled Apprise and delivery failure
- **THEN** failed runs send one Failure notification when configured, including default/truthy simulation and invalid input; successful simulations, expiry-only reminders and previews send nothing; explicit false retains existing notification behavior; delivery never changes exit status.
