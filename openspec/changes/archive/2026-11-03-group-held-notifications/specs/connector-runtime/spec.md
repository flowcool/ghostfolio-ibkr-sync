## MODIFIED Requirements

### Requirement: Notifications

Configured notifications SHALL send at most one consolidated summary per completed run. Failure SHALL retain title priority and notify immediately on every failed run. Required user actions SHALL form groups by fixed reason and unique private event count. The stable grouped fingerprint SHALL depend only on sorted reason/count pairs. The first group, a new reason, any count increase or decrease, or a cleared reason SHALL notify. An unchanged group SHALL notify only when seven days (168 hours) have passed since its last confirmed summary delivery. Seven days is the validated fixed default; no ENV override SHALL change it. A same-count event replacement within a reason SHALL retain the fingerprint. A cleared reason SHALL appear with count zero, including when the last group clears. A clean success without a previous action group SHALL send no heartbeat. Approval and previous delivery SHALL NOT imply resolution. Current evidence SHALL decide whether action remains required. Automatic processing, approved work awaiting qualification and per-run budget deferrals SHALL NOT create a required action or notification by themselves. Existing corporate-action first/changed nonblocking findings and verified resumptions SHALL retain their own rules and share the dispatch.

Private persistent delivery state SHALL retain schema, context binding, grouped fingerprint, counts and last confirmed delivery time. It SHALL contain no credentials, approval or per-event evidence. Store it beside the configured corporate-action state in the existing private mount. Missing, corrupt, unsafe or unwritable state SHALL leave actions eligible and log a fixed warning. A clock before the recorded delivery SHALL leave actions eligible. Failed cycles SHALL NOT replace the successful action snapshot or certify cleared reasons from incomplete acquisition. Full per-event evidence SHALL remain in the private log/report on every run, even when delivery is suppressed.

Failure SHALL notify even with invalid DRY_RUN or configuration. Deliberate simulation alone SHALL not notify. Required token renewal or timezone correction SHALL notify in simulation too. Repeated observations of the same event/reason SHALL contribute once to the summary. Separate reasons SHALL remain visible without claiming their counts are disjoint. Required actions SHALL include safe plain-English next steps and fixed reason codes/counts. External summaries SHALL contain no account names/IDs, securities, activity/source IDs, financial values, local paths, hosts, credentials, destination URLs or raw errors. Private logs SHALL provide details and applicable paths.

Without configured Apprise, no send SHALL occur. Each completed run SHALL log a notification result: `not required`, `disabled`, `invalid configuration`, `sent`, `failed`, or `timeout, delivery unconfirmed`. Required action with disabled/invalid delivery SHALL produce at least WARNING and a safe configuration instruction. Failed delivery SHALL also warn. Never claim ntfy received a message merely because notifications are configured. `sent` means the transport reported success, not device receipt. Retain fixed failure reasons without destination values. Do not notify recursively about delivery failure.

Preserve one bounded worker attempt, its credential-isolated environment and its timeout. Never retry within the run after failure or timeout. Delivery outcome SHALL NOT change financial behavior or exit status. Only confirmed delivery SHALL advance the grouped snapshot and reminder clock. Failed or unconfirmed delivery SHALL leave actions eligible next run. Revalidate the delivery-state generation under a separate lock before atomic confirmation; concurrent changes SHALL NOT be overwritten. Corporate notification-state locking, revalidation and post-send confirmation SHALL remain. Delivery-state failure SHALL not change financial evidence or release a hold. Interruptions SHALL NOT claim completion or send a completion notification.

Baseline replaced: tests/test_finalize.py success/warning silence and the 2026-10-27 production cycle with 68 review-held source events and no notification. Commands below specify future acceptance, not current passing evidence.

#### Scenario: Repeated required action and resolution
- **WHEN** `python -m pytest -q tests/test_finalize.py -k operator_action_reminders` exercises live and all simulation modes across unchanged, changed and resolved conditions
- **THEN** the first grouped action dispatches once; the unchanged next run stays silent; group changes and cleared reasons dispatch once; an unchanged group dispatches at exactly seven days; private evidence remains visible.

#### Scenario: One private summary across all reasons
- **WHEN** `python -m pytest -q tests/test_finalize.py -k operator_action_summary` combines several accounts, failures, review, diagnostics, mapping, token expiry, forced preview and corporate-action reasons with secret and financial canaries
- **THEN** one redacted dispatch includes safe instructions and fixed reason counts; failure retains priority; repeated observations do not inflate the same event/reason count.

#### Scenario: Explicit delivery result
- **WHEN** `python -m pytest -q tests/test_finalize.py tests/test_notify.py -k operator_action_delivery` exercises clean silence, absent/empty/invalid configuration, success, worker failure, timeout and interruption
- **THEN** completed runs log the correct result; required action with disabled delivery warns; no destination leaks, resend or recursion occurs; interruption never claims completion.

#### Scenario: Existing transport and financial contracts
- **WHEN** `python -m pytest -q tests/test_finalize.py tests/test_notify.py tests/test_token_expiry.py tests/test_corporate_actions.py` runs offline with synthetic inputs and mocked HTTP
- **THEN** worker isolation, bounded delivery, corporate state and financial fences remain valid with the explicitly changed action and simulation notification rules.

#### Scenario: Consolidated outcome
- **WHEN** `python3 -m pytest -q tests/test_finalize.py tests/test_token_expiry.py -k 'test_several_failed_accounts_make_one_dispatch_after_every_account_ran or test_summary_carries_no_secret_identifier_host_or_amount or test_notification_problems_keep_exit_code_and_account_processing or test_success_notifies_once_after_both_accounts_and_preserves_exit or test_reminder_is_grouped_and_unchanged_runs_stay_silent'` runs with explicit live mode
- **THEN** fixed-code summaries omit identifiers, amounts and secrets; delivery does not affect exit status, and unchanged reminders follow the fixed seven-day schedule.

#### Scenario: Forced preview notifies
- **WHEN** `python3 -m pytest -q tests/test_finalize.py -k historical_diagnostic_preflight` runs with absent/invalid `TZ`, valid `TZ`, and default/truthy/explicit-false `DRY_RUN`
- **THEN** explicit false with invalid TZ sends one summary naming the forced-preview reason even on success; successful default/truthy simulations without a required-action or corporate-action notification reason stay silent; failures send Failure once.

#### Scenario: Notification compatibility
- **WHEN** `python3 -m pytest -q tests/test_finalize.py -k dry_run_modes` exercises default, blank, all truthy values, explicit false and invalid input, with success, failure, expiry reminders, previews, TZ forcing, configured/disabled Apprise and delivery failure
- **THEN** failed runs send one Failure notification when configured, including default/truthy simulation and invalid input; successful simulations without required action or a corporate-action reason send nothing; expiry and preview follow the required-action rule in every mode; delivery never changes exit status.

#### Scenario: Corporate-action runtime integration
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k runtime_contract` runs the baseline and corporate-action variants for this requirement
- **THEN** baseline behavior remains except for the specified safety holds, persistent-state prerequisites and consolidated corporate-action notification rules; no corporate-action financial request is sent.

#### Scenario: Grouped reminder state and deferred work
- **WHEN** `python -m pytest -q tests/test_grouped_notifications.py` runs unchanged groups, new reasons, changed counts, all-clear, seven-day boundary, failed delivery, corrupt state, clock rollback and approved budget deferrals
- **THEN** only material changes, due reminders or actual failures dispatch; no private event data enters external text; automatic deferrals never request approval or notify.

### Requirement: Required user actions

Every condition requiring user intervention SHALL emit a private log at WARNING or above and enter the run's required-action summary. Classification SHALL follow the decision and evidence, not log-text matching or WARNING count. Each action SHALL identify its reason, affected scope, impact, safe next step and applicable configured file or setting. If there is no relevant file, name the service or UI to inspect. Retain existing credential and source-account redaction rules. Reporting SHALL NOT add a financial request, source request, approval, retry or permission.

The following inventory SHALL be covered without reporting itself changing conversion, import selection or exits; reconciliation changes follow activity-reconciliation:

| Condition | Required action |
|---|---|
| Review needing a choice, invalid approval, stale choice | Inspect the proposal and execution path; choose yes or reject only for the intended bound operation; profile authority is separate |
| Missing/conflicting review evidence, unqualified correction, historical maintenance | Obtain the stated proof or follow separately authorized maintenance; yes alone cannot release it |
| Uncertain financial request | Inspect preserved journal and destination proof; do not resend, delete or edit the journal |
| Corporate-action hold or required evidence/state missing | Inspect conclusions and recover proof; acknowledgment is not release |
| Unverified symbol fallback or different-symbol holding conflict | Verify the destination security or correct the configured mapping |
| Manual-trade proximity needing verification or reference repair | Compare source and destination before any manual edit |
| Dividend proximity discrepancy or diagnostic item to check | Inspect the comparison; amount agreement does not authorize cleanup |
| Signed tax or reversal with zero-net/negative evidence, orphan withholding, or rejected payable event | Inspect the preserved source and destination evidence; do not invent or resend a transaction |
| Evidence-limited diagnostic representation | Read the named report limitation and its impact; no user correction is requested until a concrete source or destination action exists |
| Nonblocking corporate evidence-maintenance finding | Inspect or restore the named evidence/state file; automatic retry remains distinct from a user intervention |
| Payable source event omitted for missing, invalid or conflicting evidence | Inspect the rejection and required source fields; never invent payment or quantity |
| Missing BASE_SUMMARY | Inspect report cash configuration; disclose that cash was not updated |
| Invalid configuration, authentication, source acquisition or unsuccessful financial processing | Inspect the stated reason and configuration/service; preserve recovery fences |
| Required token renewal or timezone correction | Correct the named setting before affected live processing |
| Required notification cannot be sent | Configure or repair Apprise; use the local log without recursive notification |

Approved work awaiting a later qualified cycle SHALL be reported as deferred automatic work, not a new approval request. Future-dated events, normal exclusions, accepted rounding information, deliberate simulation and recovered retries SHALL not create a required action by themselves. Representation limits SHALL explain their impact without asking for an impossible correction. An informational limitation SHALL not enter the required-action summary unless the implementation names a concrete user action and an observable resolution condition. A required action SHALL name the evidence that proves resolution; a repeated diagnostic limitation SHALL remain visible as information when no such action exists.

Re-evaluate relevant action evidence from the acquired reports and existing destination/review state, including events already skipped as duplicates. An unresolved mapping or review action SHALL not vanish merely because an import completed earlier. Add no broker request. Only the grouped notification delivery state under Notifications is permitted. Missing current evidence SHALL NOT be described as resolution. Retained review/state findings SHALL keep their visibility. State coverage limits without certifying unobserved lifetime history.

Baseline: app.py, sync.py, activity_review.py and diagnostics.py already emit operator instructions; tests/test_finalize.py treats ordinary successful warnings as silent. Commands specify future acceptance.

#### Scenario: Decision inventory and unchanged financial behavior
- **WHEN** `python -m pytest -q tests -k operator_action_inventory` exercises the listed conditions, duplicate observations, two accounts, later deduplicated runs, recovered retries and deferred approved work
- **THEN** every required action has a reason and safe instruction at WARNING or above; only actual required actions enter repeated reminders; coverage limits remain explicit; original requests, payloads, approvals, fences and exits remain unchanged.
