## Purpose

Detect IBKR corporate actions and explain their effect before related imports. Keep unsafe BUY/SELL on hold while preserving independent work and all existing financial-write boundaries.

## ADDED Requirements

### Requirement: Source-backed corporate-action inventory

Each valid source-account report SHALL inventory every CorporateAction row before affected financial work. Associate rows by verified source account and event evidence. Equal symbols, amounts or dates alone SHALL NOT join events. Retain original row fields, source hashes, effective/report dates, signed quantities, contract IDs, old/new ISINs, ratios and cash fields. Distinguish missing fields from observed zero. Reject nonfinite numbers and conflicting account/event evidence. Row order and repeated identical rows SHALL NOT create extra events. Conflicting repeats SHALL remain visible and unresolved.

The initial qualified shapes SHALL be a forward split with an explicit ratio and a reverse split with linked withdrawal/addition legs and an identity change. Missing legs, unsupported types, revisions and cancellations SHALL remain visible without guessed transformations. A description alone SHALL NOT prove identity continuity, coverage, before/after quantities or cash. No general IBKR actionID stability guarantee is established.

Baseline: README conversion table and existing parsing tests select Trade and dividend records. The saved real reports inspected on 2026-10-24 add four CorporateAction rows for three events. Sanitized fixtures SHALL preserve their structure without private identifiers. Checks below are implementation acceptance commands; they are not current passing evidence.

#### Scenario: Observed shapes and incomplete evidence
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k inventory` replays sanitized forward/reverse shapes, permutations, duplicates, changed IDs, malformed fields, unknown types, missing legs and wrong accounts
- **THEN** three complete events are identified once in the baseline; every counterexample has a bounded unresolved reason; no activity or native split is created.

### Requirement: Separate quantity, identity, history and cash conclusions

Each event finding SHALL show independent conclusions for source completeness, security identity, effective quantity, stored historical cost/dates and event cash. Conclusions SHALL distinguish observed agreement, observed discrepancy and missing proof. No current quantity match SHALL certify acquisition cost, dates or old/new identity. No cost/date difference alone SHALL make a proven identity and effective quantity unsafe.

Compare source units with complete destination activities, relevant profile splits and fresh holdings for the mapped destination account. Identify original trades plus native adjustment, already-normalized activities, or unresolved reconstruction. Apply effective dated ratios exactly once for comparison. Raw BUY minus SELL totals SHALL NOT certify a native-adjusted position. Profile-level events SHALL be checked across all affected destination accounts before their evidence can release any hold. Missing scope SHALL retain a hold.

Cash SHALL be supported by explicit linked source records and complete declared windows. Zero action cash fields with no linked cash row SHALL be reported as no cash component observed in that evidence, never as a universal guarantee. Fractional entitlement, compensation, tax and currency conversion SHALL NOT be invented. Distinct ordinary dividends SHALL retain existing validation and SHALL NOT become split cash by date proximity.

#### Scenario: Independent conclusions
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k conclusions` compares original/native, already-normalized, reconstructed, ISIN-transition, incomplete-window, fractional and explicit-cash fixtures
- **THEN** quantities, identity, cost/dates and cash receive separate reasons; adjustment is not doubled; missing identity and fractional cash remain unresolved; a cost-only discrepancy does not hold proven quantities.

### Requirement: Conservative import holds and evidence-based release

Before dispatch, unresolved corporate-action identity or effective quantity SHALL hold BUY/SELL for every provably affected security, including both old/new aliases. If that set cannot be bounded within the verified source account, hold all BUY/SELL for that account. Do not infer a global account set from an unverified row. Existing source-account validation SHALL stop mismatched reports first. Unsupported evidence SHALL use the same scope rules. Continue unrelated securities, later accounts and independent cash under their existing guards.

Existing activity-review proposals for held BUY/SELL SHALL remain visible and non-actionable. No yes, deleted proposal, acknowledgment or edited state SHALL bypass a corporate-action hold. Known pending correction uncertainty SHALL retain its stronger whole-account financial fence. Corporate-action evidence SHALL not authorize a correction, mapping change or new import.

Release SHALL require fresh, complete identity and effective-quantity evidence for the held scope. A report window that no longer includes the event, a disappeared activity, an absent profile or missing state SHALL NOT prove resolution. Rebuild selection and effective holdings after release. Normal deduplication, acceptance and sale guards SHALL still decide whether an import is safe. Simulated accepted buys SHALL NOT authorize a real sale. Known effective quantities SHALL update only from proven accepted activity results.

#### Scenario: Bounded holds and release
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k holds` exercises two accounts, aliases, unknown scope, old events outside the next window, manual acknowledgment, existing yes approvals, uncertain corrections and later complete evidence
- **THEN** only the justified BUY/SELL scope is held, independent cash continues unless a stronger existing fence applies, and only fresh financial proof releases the hold before normal selection.

### Requirement: Native evidence requires a qualified destination

Accept native split evidence only after an authenticated read establishes a stable Ghostfolio version of at least 3.91.0. Unknown, malformed, prerelease and older versions SHALL NOT certify native treatment. Do not require administrator credentials. Version read failure SHALL hold only work whose proof depends on native treatment; ordinary unaffected imports SHALL retain their existing requirements.

Version and ratio existence are necessary evidence, not acceptance of all event shapes. Require exact effective-quantity agreement and complete identity scope. No epsilon, rounding or integer coercion SHALL turn a native quantity discrepancy into agreement. A failed native case SHALL remain unresolved. The initial increment SHALL send no native split request, activity repair, cash-component creation, identifier remapping or historical conversion.

Observed limits: the isolated frozen latest image on 2026-10-24 reported 3.92.0. Original forward-split cases reached exact quantities and zero after closing sales. The original four-lot reverse-split case returned 100.00000000000001 instead of 100 and did not reach its repeat/closing-sale checks. This does not certify every forward split or reject every reverse split. GET /api/v1/export with a restrictive activityIds filter returned meta.version without administrator authority in that lab. Exact 3.91.0 source also contains that metadata; 3.91.0 runtime replay remains unobserved.

#### Scenario: Version and numerical evidence
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k native_evidence` mocks filtered version reads, stable boundary versions, prereleases, denied reads, exact native agreement and the observed reverse-split residue
- **THEN** only observed stable versions at or above 3.91.0 support native evidence, exact mismatch stays held, and no corporate-action financial request is dispatched.

### Requirement: Private persistent findings and notification state

CORPORATE_ACTION_STATE_FILE SHALL name a private regular keyed YAML file in a persistent mounted directory. It SHALL contain schema version, account/event bindings, retained evidence fingerprints, conclusions, held scope and notification fingerprints. It SHALL contain no credentials or financial approval control. Do not reuse the activity-review approval file or create a deduplication correspondence table. Fresh source/destination evidence SHALL remain authoritative.

A valid simulation SHALL initialize a missing file after input validation and publish its observed inventory. A live run with unset path, missing state, invalid schema, unsafe path, unsafe permissions or unavailable lock SHALL hold all BUY/SELL using that state and report the failure. It SHALL NOT create blank state and resume trading. Independent cash SHALL retain its existing guards. An unavailable path SHALL not prevent a safe identifier-free failure notification. Require atomic synced replacement, a cooperating-writer lock, private directory/file permissions and input-path collision checks. Existing state SHALL not be overwritten on failure or concurrent change. State loss requires simulation and review of the available history; it cannot establish coverage before the inspected windows.

Retain known unresolved events across shorter report windows. Reconcile current evidence instead of trusting editable conclusions. Publish the detailed report every run, including unchanged findings. If persistence fails, keep the affected BUY/SELL held. Report state and source limits explicitly; this feature does not establish a complete lifetime corporate-action inventory.

#### Scenario: Persistence and loss of evidence
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k persistence` exercises simulation initialization, live missing files, restarts, shorter windows, edited conclusions, symlinks, permissions, locks, failed replacement and changed input hashes
- **THEN** durable findings remain private and inspectable, no stale conclusion releases a hold, invalid state cannot authorize BUY/SELL, and financial inputs remain unchanged.

### Requirement: Consolidated corporate-action reporting

With Apprise configured, active corporate-action holds SHALL notify once in each completed run. Nonblocking findings SHALL notify on first appearance and material change. A previously held scope SHALL notify when fresh evidence permits resumption. Acknowledgment SHALL not suppress active holds. Simulation SHALL report these same observed conditions without claiming a financial execution. Coalesce these reasons with existing failure/expiry/forced-preview reasons into at most one dispatch per run. Unchanged nonblocking findings SHALL remain in the detailed report without another notification.

Notification bodies SHALL contain only safe fixed reason codes and counts. No account, security, activity ID, amount, host or credential SHALL appear. Notification failure SHALL not change financial decisions or exit status. Record successful notification fingerprints only after confirmed delivery. Failed delivery SHALL remain eligible next run. Active holds and state failures SHALL degrade the run; nonblocking historical discrepancies alone SHALL not.

#### Scenario: Repeated notifications and resumption
- **WHEN** `python -m pytest -q tests/test_corporate_actions.py -k notifications` runs first, unchanged, changed, held, resolved, simulated, failed-delivery and Apprise-disabled cases alongside other run failures
- **THEN** one redacted summary follows the specified schedule, detailed findings appear every run, and notification delivery neither releases a hold nor changes the run outcome.
