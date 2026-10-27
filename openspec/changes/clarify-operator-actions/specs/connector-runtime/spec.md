## MODIFIED Requirements

### Requirement: Notifications

Configured notifications SHALL send at most one consolidated summary per completed run. Failures, required user actions, existing corporate-action findings/resumptions, legacy-token expiry and forced-preview reasons SHALL share that dispatch. Failure SHALL retain title priority. Every observed required user action SHALL notify on each completed run until current evidence shows that it no longer requires action, including default, blank and truthy simulation. Approval, acknowledgment, previous delivery and unchanged findings SHALL NOT suppress a still-required action. A clean success SHALL send no success heartbeat. Recovered retries and informational findings that need no action SHALL NOT create a required-action notification. Existing corporate-action first/changed nonblocking findings and verified resumptions SHALL retain their own notification rules.

Failure SHALL notify even with invalid DRY_RUN or configuration. Deliberate simulation alone SHALL not notify. Required token renewal or timezone correction SHALL notify in simulation too. Repeated observations of the same event/reason SHALL contribute once to the summary. Separate reasons SHALL remain visible without claiming their counts are disjoint. Required actions SHALL include safe plain-English next steps and fixed reason codes/counts. External summaries SHALL contain no account names/IDs, securities, activity/source IDs, financial values, local paths, hosts, credentials, destination URLs or raw errors. Private logs SHALL provide details and applicable paths.

Without configured Apprise, no send SHALL occur. Each completed run SHALL log a notification result: `not required`, `disabled`, `invalid configuration`, `sent`, `failed`, or `timeout, delivery unconfirmed`. Required action with disabled/invalid delivery SHALL produce at least WARNING and a safe configuration instruction. Failed delivery SHALL also warn. Never claim ntfy received a message merely because notifications are configured. `sent` means the transport reported success, not device receipt. Retain fixed failure reasons without destination values. Do not notify recursively about delivery failure.

Preserve one bounded worker attempt, its credential-isolated environment and its timeout. Never retry within the run after failure or timeout. Delivery outcome SHALL NOT change financial behavior or exit status. Actions still observed next run SHALL remain eligible regardless of delivery outcome. Corporate notification-state locking, revalidation and post-send confirmation SHALL remain. Delivery-state failure SHALL not change financial evidence or release a hold. Interruptions SHALL NOT claim completion or send a completion notification.

Baseline replaced: tests/test_finalize.py success/warning silence and the 2026-10-27 production cycle with 68 review-held source events and no notification. Commands below specify future acceptance, not current passing evidence.

#### Scenario: Repeated required action and resolution
- **WHEN** `python -m pytest -q tests/test_finalize.py -k operator_action_reminders` exercises live and all simulation modes across unchanged, changed and resolved conditions
- **THEN** each completed run with a required action makes one configured dispatch; ordinary deduplication does not hide the action; resolution ends that reminder without a success heartbeat.

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
- **WHEN** `python3 -m pytest -q tests/test_finalize.py tests/test_token_expiry.py -k 'test_several_failed_accounts_make_one_dispatch_after_every_account_ran or test_summary_carries_no_secret_identifier_host_or_amount or test_notification_problems_keep_exit_code_and_account_processing or test_success_notifies_once_after_both_accounts_and_preserves_exit or test_reminder_is_run_local_and_multiple_runs_can_repeat_it'` runs with explicit live mode
- **THEN** fixed-code summaries omit identifiers, amounts and secrets; delivery does not affect exit status, and reminders can repeat on later runs.

#### Scenario: Forced preview notifies
- **WHEN** `python3 -m pytest -q tests/test_finalize.py -k historical_diagnostic_preflight` runs with absent/invalid `TZ`, valid `TZ`, and default/truthy/explicit-false `DRY_RUN`
- **THEN** explicit false with invalid TZ sends one summary naming the forced-preview reason even on success; successful default/truthy simulations without a required-action or corporate-action notification reason stay silent; failures send Failure once.

#### Scenario: Notification compatibility
- **WHEN** `python3 -m pytest -q tests/test_finalize.py -k dry_run_modes` exercises default, blank, all truthy values, explicit false and invalid input, with success, failure, expiry reminders, previews, TZ forcing, configured/disabled Apprise and delivery failure
- **THEN** failed runs send one Failure notification when configured, including default/truthy simulation and invalid input; successful simulations without required action or a corporate-action reason send nothing; expiry and preview follow the required-action rule in every mode; delivery never changes exit status.

#### Scenario: Corporate-action runtime integration
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k runtime_contract` runs the baseline and corporate-action variants for this requirement
- **THEN** baseline behavior remains except for the specified safety holds, persistent-state prerequisites and consolidated corporate-action notification rules; no corporate-action financial request is sent.

### Requirement: Simulation

Absent or blank `DRY_RUN` SHALL simulate and emit WARNING `DRY_RUN not set: simulation, nothing written` on every invocation, including configuration failure. After trimming and lowercasing, `1/true/yes/on` SHALL simulate; only `0/false/no/off` SHALL request live writes. Any other value SHALL fail configuration with exit 1 before any HTTP call. After rejection, only the configured Apprise Failure notification SHALL be permitted; no IBKR/Ghostfolio HTTP calls or financial writes SHALL occur. Other safety guards SHALL still apply.

Simulation SHALL run login, reads and the existing preview pipeline without activity, cash or platform writes. Failed simulations SHALL send the configured Failure notification. Successful simulations SHALL notify for required user actions under Notifications, including required token renewal and timezone correction. A deliberate clean preview alone SHALL send no notification. Existing corporate-action findings and resumption notifications remain eligible. Corporate-action evidence and state SHALL be evaluated in simulation without financial writes. Missing/unwritable corporate-action state or an active hold SHALL exit 1 with the existing consolidated failure path; a clean simulation with valid state retains exit 0. Existing TZ-forced notifications SHALL remain for explicit live mode.

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

#### Scenario: Required-action reporting compatibility
- **WHEN** `python -m pytest -q tests -k operator_action` exercises this requirement with synthetic inputs and mocked HTTP
- **THEN** required actions emit at least WARNING and join one configured notification; financial selection, payloads, account fences and exit codes remain unchanged.

### Requirement: Mapping and duplicate reconciliation

Mapping SHALL prefer ISIN mappings, then IBKR symbols. The existing matching rules below SHALL apply when ACTIVITY_REVIEW_FILE is disabled. When enabled, activity-correction-review SHALL first inspect complete supported source events, including existing identities, and hold events with pending candidates before ordinary selection. No blank approval or deleted review entry SHALL authorize a related import. If all former candidates are proven assigned to other identified events, release the hold and repeat ordinary selection under activity-correction-review. Missing or inactive targets SHALL remain held. Review SHALL NOT combine trade fills or dividend actions into one correction. Trade IDs SHALL suppress reimport. Manual matching SHALL use quantity and ±2 days, including summed fills. Ambiguous split fills SHALL only be summed within the same parsed calendar day, side, resolved ticker, and ISIN; nearby mismatches SHALL warn/skip. Dividends SHALL match by account/comment (including the old symbol comment), or, for existing active YAHOO dividends of the same account and symbol whose comment does not start with `dividend#` (manual or legacy rows), at ±3 days. Connector-comment rows (`dividend#…`) SHALL NOT enter the proximity index, so a distinct payment next to an imported one is imported. A proximity skip SHALL stay a skip. The comparison SHALL use the exact source gross and the existing row's quantity × unitPrice, normalized to a common major unit (minor-unit markets as in conversion) and rounded to its minor unit; an unsupported denomination SHALL be "not comparable". Equal amounts SHALL log INFO "amounts agree" with both fee values; equal amounts do not prove the same payment. Otherwise it SHALL log one WARNING naming both dates, both gross values with currencies (or "not comparable"), both fee values, and the operator action: check IBKR and add the payment by hand if it is distinct. It SHALL NOT change exit status. Required manual checks SHALL join the consolidated notification under Notifications.

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

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.

#### Scenario: Required-action reporting compatibility
- **WHEN** `python -m pytest -q tests -k operator_action` exercises this requirement with synthetic inputs and mocked HTTP
- **THEN** required actions emit at least WARNING and join one configured notification; financial selection, payloads, account fences and exit codes remain unchanged.

### Requirement: Enriched dividend input and local rejection

With review disabled, processing SHALL extract cash identity without quantity checks, deduplicate by account/comment/proximity, then validate candidates. Automatic sync SHALL leave existing activities untouched and unverified in that mode. With review enabled, complete supported action evidence SHALL be validated before proposing a correction, including an already stored identity. Only explicit yes approval SHALL authorize the reviewed one-to-one update. The separate bulk maintenance conversion SHALL retain its stricter contract. The dry-run diagnostic itself SHALL not change selection or authorize a correction.

ChangeInDividendAccruals SHALL be mandatory. Required attributes SHALL cover candidate payment/relevant accrual keys and `quantity/code/date/payDate/reportDate`. Nonempty key mismatches SHALL exclude unrelated accruals; missing keys SHALL NOT prove irrelevance. Unrelated rows SHALL NOT block candidates. Withholding SHALL retain cash evidence without accrual-schema requirements; new action writes SHALL require the explicit tax association in Flex selection and conversion. Missing section/relevant attributes SHALL block account dividends; present-but-empty evidence SHALL reject affected groups. Empty sections without payments SHALL be valid.

Rejections SHALL log distinct reasons, never mark rejected payments imported, and leave trades/cash operating. Partial v2 coverage, action-context conflicts and the new action-partition failures specified in Flex selection and conversion SHALL fail the account result; other existing local rejections SHALL NOT change success or exit. A rejected payable event requiring investigation SHALL emit at least WARNING and join the required-action notification. Other failures SHALL retain current behavior.

#### Scenario: Compatibility and isolation
- **WHEN** `.venv/bin/python -m pytest -q tests -k dividend_structured_input` runs old, empty, short-window, unrelated, missing, conflicting and partial-v2 cases
- **THEN** identity→dedup→quantity order, scopes, logs, retries and isolation remain; partial v2 and new action-partition failures change the account outcome as specified; other local rejections preserve their outcomes.

#### Scenario: Partition failure isolation
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_partition_isolation` covers a missing tax association and conflicting source actions beside valid trades, safe sales, cash and a later account
- **THEN** the affected group emits no dividend, the account result fails, existing rows remain untouched, and independent work continues.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.

#### Scenario: Required-action reporting compatibility
- **WHEN** `python -m pytest -q tests -k operator_action` exercises this requirement with synthetic inputs and mocked HTTP
- **THEN** required actions emit at least WARNING and join one configured notification; financial selection, payloads, account fences and exit codes remain unchanged.

### Requirement: Diagnostic execution and visibility

Each diagnostic item SHALL declare either a user action with an observable resolution condition or an informational evidence limitation. An evidence limitation remains visible but does not trigger a reminder.

The diagnostic SHALL use existing reads, ENV and logs without persistence or financial writes. INFO SHALL summarize coverage/categories. Items requiring user checks SHALL emit at least WARNING; anomaly/uncertainty details SHALL include reasons, activity IDs and source references with quantities/monetary deltas when supported. The per-account import line SHALL include the same `to check`, `informational` and `noise` counts as the dividend report, so its duplicate count cannot be mistaken for the report result. Logs remain private. Findings SHALL NOT alter exits. Items requiring user action SHALL join Notifications in simulation too. Information and noise alone SHALL not trigger a required-action notification; technical failures retain current behavior. Live runs SHALL NOT execute the diagnostic. README SHALL explain one-off Docker DRY_RUN without CRON, categories, limits and unchanged financial state.

#### Scenario: Dry-run report
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic or coherent_dividend_import_summary'` runs mocked dry and live accounts
- **THEN** dry-run details and the import line expose identical report counts without writes; live diagnostic selection, financial behavior and exits remain unchanged; required actions join the consolidated notification.

Baseline: the 2026-10-15 real dry-run import line reported duplicate skips while the report separately reported items to check, without a link between the numbers.

#### Scenario: Required-action reporting compatibility
- **WHEN** `python -m pytest -q tests -k operator_action` exercises this requirement with synthetic inputs and mocked HTTP
- **THEN** required actions emit at least WARNING and join one configured notification; financial selection, payloads, account fences and exit codes remain unchanged.

### Requirement: Readable dividend report

Each finding SHALL use English plain words, one `Action:` line and the statement that nothing was written. A block SHALL NOT include a second `Proposed action:` line. No report block or summary line SHALL contain a Python representation, including `Decimal(...)`, dict/list syntax, exponent notation or the word `None` as a value. Missing values SHALL read `unavailable`. Category, failed-check and unavailable-check summaries SHALL use deterministic plain `name:count` text, or `none` when empty.

Every monetary value shown in a block, including gross, fee and monetary deltas on both the source and destination sides, SHALL be quantized for display to the common currency minor unit with round-half-away-from-zero. Quantities SHALL retain their exact plain-decimal display. Display rounding SHALL NOT change comparison, category or action.

The classes SHALL remain coherent, information, noise, outside window and to check. `unsupported currency` SHALL appear only when a nonempty code has no explicit minor-unit definition. Missing currency SHALL read `missing currency`; unequal supported codes SHALL read `conflicting currencies`. A source and destination that both use KRW SHALL be comparable, not unsupported.

A complete single legacy activity with equal quantity and fee SHALL be `legacy declared-rate rounding` information when its Ghostfolio gross equals quantity × the matched payment `Re` `grossRate` and the paid cash gross differs by exactly one minor unit. Its reason SHALL state that the legacy row uses the declared rate and IBKR paid a rounded cash amount. Its sole action SHALL read `No action: IBKR rounding accepted.` The block SHALL stay visible at INFO as audit information. It SHALL NOT suggest that IBKR revised the amount after import. A one-minor-unit fee difference, or any one-minor-unit gross difference outside this proven pattern, SHALL remain to check as `minimal difference, cause unknown`. No finding SHALL automatically correct an activity.

After informational findings, one INFO line SHALL read `N to check, N informational, N noise`, followed by each item to check at WARNING or above. Findings SHALL NOT change exits. Items to check SHALL join the required-action notification. Information and noise alone SHALL not trigger it.

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

#### Scenario: Required-action reporting compatibility
- **WHEN** `python -m pytest -q tests -k operator_action` exercises this requirement with synthetic inputs and mocked HTTP
- **THEN** required actions emit at least WARNING and join one configured notification; financial selection, payloads, account fences and exit codes remain unchanged.

### Requirement: Proposed dividend match

Under DRY_RUN, every dividend item to check that has a candidate SHALL carry one `Proposed match` section. The section SHALL show the IBKR dividend and candidate Ghostfolio rows side by side, each row labelled `Keep`, `Keep, quantity differs`, `Duplicate` or `Differs`. Confidence SHALL be strong for the same security, local day, gross and fee, or weak for a candidate without equal gross and fee. A strong row selected to keep whose quantity differs from IBKR SHALL read `Keep, quantity differs`, never plain `Keep`. Quantity SHALL have no tolerance. With no candidate the section SHALL read `no confident match`. Weak proposals SHALL label no row `Keep` or `Keep, quantity differs`.

The proposed-match section SHALL NOT contain an action line. The enclosing block's single `Action:` line SHALL name the row and operation, or state that no action is needed. When the reason compares a Ghostfolio activity, the Action SHALL name that same activity, shown on the block's `Ghostfolio: activity ...` line, never another candidate. A quantity-difference reason SHALL request a manual quantity comparison for that activity and SHALL NOT state that no action is needed. `scripts/check_dividend_report.py` SHALL report a violation if the Action targets another candidate instead of the compared activity. Historical rows that split the same gross SHALL remain visible as `Differs`; their cleanup is out of scope and remains a separate reversible-maintenance idea. A legacy symbol-comment row that owns the source group SHALL appear once as the compared row; it SHALL NOT receive a second legacy-twin block. The proposal SHALL NOT write, repair or change import selection, classes, categories, summary counts or exits. Its items to check SHALL join the required-action notification. Text SHALL follow the report's plain and quantized display rules.

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
- **THEN** classes, categories, summary counts and exits are unchanged; displayed amounts are quantized and plain; formatting SHALL not add a notification for an already counted action.

#### Scenario: Real read-only acceptance
- **WHEN** the operator-authorized real dry-run log is read after `python3 scripts/check_dividend_report.py <private-log>` exits 0
- **THEN** each to-check block has a proposal or no confident match, exactly one action targeting the activity compared by its reason, an explicit `Keep, quantity differs` label when applicable, and no duplicate legacy-identity block.

Baseline: current proposed-match tests preserve classification. The saved 2026-10-15 report also shows a compared connector row with quantity 1 versus IBKR 100, equal gross/fee and two historical rows splitting that gross: the proposal labels the connector row `Keep`, while the Action targets a historical `Differs` row. This is the gap addressed by task 3.2.

#### Scenario: Required-action reporting compatibility
- **WHEN** `python -m pytest -q tests -k operator_action` exercises this requirement with synthetic inputs and mocked HTTP
- **THEN** required actions emit at least WARNING and join one configured notification; financial selection, payloads, account fences and exit codes remain unchanged.

### Requirement: Minimal native lab evidence

The connector SHALL emit only three new evidence kinds through `log.debug`: `window`, `preview` and `cash`. Each message SHALL be `LAB_EVIDENCE ` followed by compact JSON with exactly `kind` and `value`. The normal timestamp and DEBUG logging prefix SHALL precede the message. JSON escaping SHALL keep each message on one physical line. JSON numbers SHALL be finite. Unserializable or nonfinite evidence SHALL be omitted without changing existing operations. The evidence addition SHALL emit no LAB_EVIDENCE at INFO. Operational logging and required-action reporting SHALL govern new framing and summaries; the former global byte-identical INFO constraint SHALL not prohibit those changes. Evidence payloads, financial behavior, guards and requests SHALL remain unchanged. Evidence SHALL NOT dump secrets, URLs, XML, ENV, configuration, headers or response bodies. README SHALL state that lab acceptance needs `LOG_LEVEL=DEBUG`.

#### Scenario: Framing and INFO compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_run_evidence.py -k 'format or info or nonfinite'` runs with synthetic inputs and mocked HTTP
- **THEN** DEBUG evidence parses on single physical lines, preserves escaped payload text and finite numbers, excludes configuration secrets, and adds no HTTP calls; INFO contains no LAB_EVIDENCE; per-activity preview message content remains unchanged while framing, levels and operational summaries follow the reporting requirements.

#### Scenario: Required-action reporting compatibility
- **WHEN** `python -m pytest -q tests -k operator_action` exercises this requirement with synthetic inputs and mocked HTTP
- **THEN** required actions emit at least WARNING and join one configured notification; financial selection, payloads, account fences and exit codes remain unchanged.

## ADDED Requirements

### Requirement: Required user actions

Every condition requiring user intervention SHALL emit a private log at WARNING or above and enter the run's required-action summary. Classification SHALL follow the decision and evidence, not log-text matching or WARNING count. Each action SHALL identify its reason, affected scope, impact, safe next step and applicable configured file or setting. If there is no relevant file, name the service or UI to inspect. Retain existing credential and source-account redaction rules. Reporting SHALL NOT add a financial request, source request, approval, retry or permission.

The following inventory SHALL be covered without changing conversion, diagnostic categories, import selection or exits:

| Condition | Required action |
|---|---|
| Review needing a choice, invalid approval, stale choice | Inspect the proposal and execution path; approve only if eligible and intended |
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

Re-evaluate relevant action evidence from the acquired reports and existing destination/review state, including events already skipped as duplicates. An unresolved mapping or review action SHALL not vanish merely because an import completed earlier. Add no persistent alert store or broker request. Missing current evidence SHALL NOT be described as resolution. Retained review/state findings SHALL keep their visibility. State coverage limits without certifying unobserved lifetime history.

Baseline: app.py, sync.py, activity_review.py and diagnostics.py already emit operator instructions; tests/test_finalize.py treats ordinary successful warnings as silent. Commands specify future acceptance.

#### Scenario: Decision inventory and unchanged financial behavior
- **WHEN** `python -m pytest -q tests -k operator_action_inventory` exercises the listed conditions, duplicate observations, two accounts, later deduplicated runs, recovered retries and deferred approved work
- **THEN** every required action has a reason and safe instruction at WARNING or above; only actual required actions enter repeated reminders; coverage limits remain explicit; original requests, payloads, approvals, fences and exits remain unchanged.

### Requirement: Final operational result

Every completed cycle SHALL distinguish `success`, `success with user action required`, and `failure`, independently of the unchanged exit code. A cycle with only automatic deferred work or an evidence limitation that has no user-resolvable action SHALL remain `success` and SHALL report that fact separately. Failure SHALL take priority and retain its action details. The result SHALL use ERROR for failure, WARNING for action-only success and INFO for clean success. Separately report proven accepted imports or simulated proposals, duplicate skips, unique review-held source events, other justified holds, deferred automatic work and cash outcomes per account. Unknown counts SHALL read `unavailable`, never zero. Label overlapping decisions; do not add them into a false reconciliation total. Proposal count SHALL not stand for held-event count.

Cash outcomes SHALL distinguish simulated, request reported successful, not updated and uncertain/failed outcomes, using existing evidence. A successful request SHALL NOT be described as independent balance readback. No new financial readback is introduced. Cash success SHALL not imply held activities were imported. Show notification outcome alongside the cycle result without claiming device delivery. Early failures SHALL report unavailable fields honestly. Exits and financial processing SHALL remain unchanged.

Baseline replaced: app.py emits `Sync complete` for pending-review holds. The 2026-10-27 production log separately reports 68 held events, zero new imports and cash success.

#### Scenario: Held activities with independent cash
- **WHEN** `python -m pytest -q tests/test_orchestration.py tests/test_finalize.py -k operator_action_result` exercises review holds with successful cash, simulation, missing cash, uncertain writes and early configuration failure
- **THEN** status and independent outcomes match the evidence, never claim readback or complete import, include delivery status, and preserve exits and financial requests.

### Requirement: Clear application log framing

One-off and scheduled application logs SHALL use the same readable application timestamp, level and message. Scheduled output SHALL NOT be embedded in a scheduler message with another timestamp, level or channel. Application DEBUG/INFO SHALL use stdout; WARNING and above SHALL use stderr. No record SHALL appear on both streams. Scheduler startup, cycle start/success/failure and shutdown records SHALL remain available and distinguishable. Preserve numeric cron validation, child exit handling, signal handling, LOG_LEVEL filtering and secret suppression. A transport stream SHALL not be presented as application severity.

Preserve LAB_EVIDENCE kind/value JSON, one-line escaping and DEBUG visibility. Logging changes SHALL NOT change financial requests or expose broker query tokens. Add no logger dependency, mandatory ENV or Docker socket access.

#### Scenario: Direct and scheduled application levels
- **WHEN** `python -m pytest -q tests/test_entrypoint.py tests/test_run_evidence.py tests/test_logging.py -k operator_action_logging` runs isolated synthetic entrypoint and subprocess cases at each level and checks the scheduler invocation
- **THEN** records retain their level and intended stream without nested framing or duplicates; cron and lifecycle semantics remain; LAB_EVIDENCE parses unchanged.

#### Scenario: User can locate and act on a finding
- **WHEN** `rg -n -A 12 'User action required|Notification result|container path' docs/configuration.md docs/activity-review.md README.md` runs after implementation
- **THEN** examples explain action-only success, repeats and clean silence, severity/streams, delivery states, volume resolution, safe review distinctions and unchanged financial authority, without private deployment paths.
