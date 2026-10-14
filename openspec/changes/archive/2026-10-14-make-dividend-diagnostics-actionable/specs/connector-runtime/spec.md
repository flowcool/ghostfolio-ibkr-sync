# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Notifications

Configured notifications SHALL send at most one failure/legacy-expiry/forced-preview summary per completed run, without affecting exit status. A run forced into `DRY_RUN` by missing or invalid IANA `TZ` SHALL send that summary even when every account succeeds, and the summary SHALL name the reason. Success/warnings without expiry, operator-chosen simulation and interruptions SHALL send nothing.

#### Scenario: Consolidated outcome
- **WHEN** accounts finish with failure/expiry
- **THEN** fixed-code summaries omit identifiers/amounts/secrets; reminders can repeat.

#### Scenario: Forced preview notifies
- **WHEN** `.venv/bin/python -m pytest -q tests/test_finalize.py -k 'historical_diagnostic_preflight'` runs with absent/invalid `TZ`, valid `TZ`, and operator-set `DRY_RUN`
- **THEN** the forced preview sends one summary naming the reason even on success; a live run without failure and an operator-chosen `DRY_RUN` send nothing.

Evidence: `python -m pytest -q tests/test_finalize.py tests/test_token_expiry.py -k 'test_several_failed_accounts_make_one_dispatch_after_every_account_ran or test_summary_carries_no_secret_identifier_host_or_amount or test_notification_problems_keep_exit_code_and_account_processing or test_success_notifies_once_after_both_accounts_and_preserves_exit or test_reminder_is_run_local_and_multiple_runs_can_repeat_it or historical_diagnostic_preflight'`.
