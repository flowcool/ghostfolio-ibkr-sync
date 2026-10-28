## MODIFIED Requirements

### Requirement: Mapping and duplicate reconciliation

Mapping SHALL prefer ISIN mappings, then IBKR symbols. The existing matching rules below SHALL apply when ACTIVITY_REVIEW_FILE is disabled. When enabled, activity-correction-review SHALL first inspect complete supported source events, including existing identities, and hold events with pending candidates before ordinary selection. No blank approval or deleted review entry SHALL authorize a related import. A valid bound rejection SHALL exclude only its source-target pair from review and ordinary duplicate matching. When every current candidate is rejected and no new candidate exists, repeat ordinary selection with those exclusions. Keep exact-identity, position, corporate-action and uncertainty guards. Active profiles first apply activity-reconciliation; off retains manual review. Rejection never removes a target from matching other events. If all former candidates are proven assigned to other identified events, release the hold and repeat ordinary selection under activity-correction-review. Missing or inactive targets SHALL remain held except an already-rejected pair whose target absence is proven by a complete listing under activity-correction-review. Review SHALL NOT combine trade fills or dividend actions into one correction. Trade IDs SHALL suppress reimport. Manual matching SHALL use quantity and ±2 days, including summed fills. Ambiguous split fills SHALL only be summed within the same parsed calendar day, side, resolved ticker, and ISIN; nearby mismatches SHALL warn/skip. Dividends SHALL match by account/comment (including the old symbol comment), or, for existing active YAHOO dividends of the same account and symbol whose comment does not start with `dividend#` (manual or legacy rows), at ±3 days. Connector-comment rows (`dividend#…`) SHALL NOT enter the proximity index, so a distinct payment next to an imported one is imported. A proximity skip SHALL stay a skip. The comparison SHALL use the exact source gross and the existing row's quantity × unitPrice, normalized to a common major unit (minor-unit markets as in conversion) and rounded to its minor unit; an unsupported denomination SHALL be "not comparable". Equal amounts SHALL log INFO "amounts agree" with both fee values; equal amounts do not prove the same payment. Otherwise it SHALL log one WARNING naming both dates, both gross values with currencies (or "not comparable"), both fee values, and the operator action: check IBKR and add the payment by hand if it is distinct. It SHALL NOT change exit status. Required manual checks SHALL join the consolidated notification under Notifications.

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

### Requirement: Additive imports and independent cash

New imports SHALL remain additive. Existing activities SHALL change only through the optional one-to-one correction flow with literal yes consent or explicit profile authority in activity-correction-review. Disabling review SHALL retain the existing no-update guarantee. No review flow SHALL delete an activity. Unresolved symbols SHALL drop/retry the reduced batch with degradation. Accounts SHALL run sequentially despite failures. Cash SHALL be independent of ordinary import success. A failed or unresolved correction SHALL fence all later financial writes for its account, including cash and platform writes. An uncertain account SHALL resume writes only after exact expected-after readback resolves every unresolved request, without another PUT or an interactive reset/abandon path. Pending proposals alone SHALL NOT block independent cash. Clean/degraded runs SHALL exit 0/1.

#### Scenario: Partial failure
- **WHEN** import fails or sections are absent
- **THEN** import failure permits cash; missing CashTransactions degrades; absent BASE_SUMMARY only warns.

Evidence: README “How it works”; `python -m pytest -q tests/test_orchestration.py tests/test_ghostfolio.py -k 'test_import_failure_fails_the_account_keeps_state_untouched_but_still_updates_cash or test_missing_cash_transactions_section_fails_the_run_but_still_imports_trades or test_report_without_cash_row_is_a_warning_not_a_failure or test_unresolved_symbol_is_dropped_and_batch_retried'`.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.

### Requirement: Current operational limits

The connector SHALL retain documented boundaries: 365-day guidance; daily data; corporate-action detection with evidence-based BUY/SELL holds; manual corporate-action treatment, history and token renewal; additive imports with optional manually approved or explicitly profile-authorized corrections; proximity skips next to manual or legacy rows (INFO when amounts agree, WARNING otherwise, never imported; a distinct payment there needs a manual add); trust principle: a row with a connector comment (`dividend#…`) is ours and trusted by exact identity, and with review disabled a user edit of such a row is out of contract; enabled review SHALL expose differences and manual or profile authority; stored UTC instants with configured-TZ business-date eligibility; unconverted cash/commission currencies; Yahoo quality; net, nonchronological checks; nontransactional buy/sell phases; preview without server acceptance; buffered 10 MiB Flex responses; no general overlap protection. Enabled correction dispatch SHALL require exclusive writes and persistent recovery evidence as specified in activity-correction-review. README SHALL describe the new reader floor for notes-bearing references and the persistent-volume requirement. It SHALL document CORPORATE_ACTION_STATE_FILE, simulation initialization, live BUY/SELL refusal on missing/invalid state, simulation refusal with exit 1 on missing/unwritable state, private retained report bytes, retained events outside later report windows, candidate-specific hold/release evidence, notification frequency and the stable Ghostfolio 3.91.0 minimum for accepting native split evidence. Ordinary acquired reports SHALL rotate automatically after a fixed 30 days from acquisition, without a new ENV setting or quota. Required safety originals SHALL follow corporate-action-detection retention rules. README SHALL explain the exceptions and private copies for longer investigations. Reconciliation supports opt-in bounded automatic corrections and compact decisions without a new job lifecycle. README SHALL describe profiles and limits, fee exclusion from identity, pair rejection, schema-3 migration and private state, the shared execution budget and downgrade recovery. Correction journals SHALL remain outside rotation. State loss SHALL require a reviewed simulation inventory that reuses surviving evidence and unresolved events; deleting state SHALL not be a resolution method. Available windows cannot certify lifetime history. Document unsupported-event holds, explicit old/new identity mappings, effective-date uncertainty and the unqualified non-admin read gate. Native corporate-action treatment, corporate-action identity remapping and historical repair remain unavailable; legacy comment migration follows activity-reconciliation. Acknowledgment SHALL not release holds. Rollback SHALL stop writers and force simulation before using an older image that lacks these guards; reverting code SHALL not be described as restoring financial data.

#### Scenario: Operator checks limits
- **WHEN** limitations are read
- **THEN** these boundaries are visible, and `GHOST_CURRENCY` is not documented as a setting.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.

#### Scenario: Corporate-action runtime integration
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k runtime_contract` runs the baseline and corporate-action variants for this requirement
- **THEN** baseline behavior remains except for the specified safety holds, persistent-state prerequisites and consolidated corporate-action notification rules; no corporate-action financial request is sent.

#### Scenario: Rotation runtime integration
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k retention_reporting` covers ordinary report expiry and maintenance outcomes with simulation, manual review, cash, later accounts and configured or disabled notifications
- **THEN** the fixed 30-day policy is reported accurately, manual reconciliation and correction journals retain their contract, maintenance warnings use the existing dispatch, and required-proof failures retain the existing financial fences.

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

Enabled review classifies conforming unique v2 rows and relevant conflicts under activity-reconciliation. It SHALL NOT fabricate cash/accrual evidence, complete partial actions or enable automatic backfill. Ordinary imports retain the coverage rules above.

#### Scenario: Relevant review context
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k conformity` exercises unrelated context and incomplete partitions
- **THEN** unrelated context alone does not block conformity, actual conflicts name their counterparts, and incomplete partitions stay held.

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

Trade qualification SHALL likewise check overlapping-report stability, repeated/conflicting IDs, source-account equality and corrections. A changed trade under an already stored identity requires manual review unless an explicit active profile authorizes its one-to-one correction under activity-reconciliation. Source stability, partition and provenance qualification remain mandatory. Profiles SHALL NOT override repeated or conflicting source identities.

#### Scenario: Source qualification remains bounded
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_source_qualification` replays qualified saved-input summaries and synthetic revision, reuse, multi-day, missing-account, incomplete-window and cross-account counterexamples
- **THEN** each evidence claim has an explicit status and scope; a failed or missing gate prevents the corresponding write capability; no fixture result is reported as a vendor guarantee.

### Requirement: Historical maintenance from the shared approval file

Historical reference-only maintenance SHALL use the same compact schema-3 decision file and bound private state as normal activity review. The offline `identity_migration.py review` command SHALL stage only exact eligible comment replacements with preserved dates, financial fields, IDs, accounts, tags and notes. It SHALL name the historical maintenance execution path. Normal sync SHALL NOT dispatch those staged maintenance approvals. Both commands SHALL refuse staging or preparation when the shared journal contains a pending request. The operator SHALL stop cooperating review writers before staging, editing or preparing a historical selection.

`identity_migration.py prepare` SHALL select only literal yes decision entries for historical reference-only maintenance. It SHALL rebuild each selected proposal from saved source and destination evidence. Changed evidence, bindings or proposal content SHALL refuse preparation. Unselected entries SHALL produce no correspondence or rejection state. It SHALL re-run complete import selection for the exact selected subset, including full payloads and holdings decisions. Equality for a larger set SHALL NOT replace that proof. Refused selections SHALL not produce an apply manifest. The manifest SHALL bind the approval-file bytes and selected keys. Preparation and apply SHALL hold the shared review lock. Apply SHALL require that file and SHALL refuse plain preview manifests. Successful apply SHALL remove confirmed selections from the file. The maintenance journal SHALL retain their consent keys and revisions. Re-staging SHALL remove stale historical proposals and clear historical approvals, including after rollback; consumed consent SHALL never be resurrected. Apply SHALL revalidate this same file and rebuild the selected manifest before any request. This file consent SHALL NOT replace separate operation authorization, preservation qualification, writer exclusion, settlement or pacing evidence. Existing inspection and journal-owned rollback SHALL remain available.

Community documentation SHALL describe the two sections, evidence levels, skip behavior, both execution paths, exact commands, schema compatibility and recovery. Examples SHALL use synthetic identifiers and SHALL distinguish preparation from production permission.

#### Scenario: Exact approved subset and community commands
- **WHEN** `python -m pytest -q tests/test_identity_migration.py -k shared_review` stages historical proposals, changes approval choices and prepares a subset using mocked saved evidence
- **THEN** only exact yes entries reach the selected manifest, the exact subset passes its own selection replay, changed evidence is refused, no network request occurs, and documented command arguments match the CLI.

Profiles SHALL NOT authorize historical-maintenance dispatch. Rejected historical entries remain unselected and SHALL NOT release normal imports. Runtime and historical proposals SHALL use execution-path-qualified keys. Refresh SHALL preserve staged historical proposals without rewriting their path. The combined selection SHALL retain one-source/one-target conflict checks across both paths; staging SHALL NOT overwrite runtime decisions. An identical source-target pair SHALL occupy only one path; staging refuses a pair with a current runtime proposal, and runtime refresh retains an already-staged historical pair without creating another operation. Stage, prepare and apply SHALL validate state/view generations and preserve schema-1/2 migration and unresolved journal recovery.

#### Scenario: Shared compact maintenance adapter
- **WHEN** `python -m pytest -q tests/test_identity_migration.py -k shared_review` exercises schema migration, profiles, rejection and partial selections
- **THEN** only unchanged manual yes maintenance decisions prepare, selected-subset replay remains mandatory, and profiles cannot reach apply.

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

Separately report conforming identities, confirmed manual/profile corrections, comment migrations, profile deferrals and rejected associations. Count unique events and corrected targets separately from pairs. A rejected pair SHALL NOT count as an import or accepted identity. Simulation reports would-correct counts only.

#### Scenario: Profile result counts
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k profile_execution` exercises mixed outcomes
- **THEN** counts and authority match observed outcomes without false disjoint totals or simulated completion.
