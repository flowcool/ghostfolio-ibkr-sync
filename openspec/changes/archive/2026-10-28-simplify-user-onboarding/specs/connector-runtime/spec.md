# Connector Runtime Documentation Delta

## MODIFIED Requirements

### Requirement: Simulation

Absent or blank `DRY_RUN` SHALL simulate and emit WARNING `DRY_RUN not set: simulation, nothing written` on every invocation, including configuration failure. After trimming and lowercasing, `1/true/yes/on` SHALL simulate; only `0/false/no/off` SHALL request live writes. Any other value SHALL fail configuration with exit 1 before any HTTP call. After rejection, only the configured Apprise Failure notification SHALL be permitted; no IBKR/Ghostfolio HTTP calls or financial writes SHALL occur. Other safety guards SHALL still apply.

Simulation SHALL run login, reads and the existing preview pipeline without activity, cash or platform writes. Failed simulations SHALL send the configured Failure notification. Successful simulations SHALL notify for required user actions under Notifications, including required token renewal and timezone correction. A deliberate clean preview alone SHALL send no notification. Existing corporate-action findings and resumption notifications remain eligible. Corporate-action evidence and state SHALL be evaluated in simulation without financial writes. Missing/unwritable corporate-action state or an active hold SHALL exit 1 with the existing consolidated failure path; a clean simulation with valid state retains exit 0. Existing TZ-forced notifications SHALL remain for explicit live mode.

README configuration, Docker/Compose examples, setup and the 3.0 upgrade note SHALL explain the breaking rc.2 simulation-default change and explicit false opt-in. The upgrade note SHALL warn that older images can write with absent DRY_RUN and require explicit DRY_RUN=true for rollback previews. CHANGELOG.md SHALL link to GitHub Releases as the release-history authority; it SHALL NOT duplicate current behavior instructions. Examples SHALL select simulation explicitly; instructions SHALL explain changing to false after review.

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

#### Scenario: Current simulation instructions
- **WHEN** `rg -n 'DRY_RUN|simulation|Releases' README.md docs/getting-started.md docs/configuration.md docs/ibkr-setup.md docs/upgrading-to-3.0.md CHANGELOG.md` runs
- **THEN** current setup instructions require deliberate write enablement, and the changelog points to Releases without contradictory runtime instructions.


### Requirement: Current operational limits

The connector SHALL retain documented boundaries: 365-day guidance; daily data; corporate-action detection with evidence-based BUY/SELL holds; manual corporate-action treatment, history and token renewal; additive imports with optional explicitly approved corrections; proximity skips next to manual or legacy rows (INFO when amounts agree, WARNING otherwise, never imported; a distinct payment there needs a manual add); trust principle: a row with a connector comment (`dividend#…`) is ours and trusted by exact identity, and with review disabled a user edit of such a row is out of contract; enabled review SHALL expose validated per-event differences for approval; UTC dates; unconverted cash/commission currencies; Yahoo quality; net, nonchronological checks; nontransactional buy/sell phases; preview without server acceptance; buffered 10 MiB Flex responses; no general overlap protection. Enabled correction dispatch SHALL require exclusive writes and persistent recovery evidence as specified in activity-correction-review. README SHALL retain the additive-import boundary, manual corporate-action treatment, the 365-day window, persistent-volume requirement, simulation initialization and explicit live opt-in. It SHALL link directly to the detailed safety and recovery guidance. Linked user guides SHALL describe the new reader floor for notes-bearing references. They SHALL document CORPORATE_ACTION_STATE_FILE, simulation initialization, live BUY/SELL refusal on missing/invalid state, simulation refusal with exit 1 on missing/unwritable state, private retained report bytes, retained events outside later report windows, candidate-specific hold/release evidence, notification frequency and the stable Ghostfolio 3.91.0 minimum for accepting native split evidence. Ordinary acquired reports SHALL rotate automatically after a fixed 30 days from acquisition, without a new ENV setting or quota. Required safety originals SHALL follow corporate-action-detection retention rules. The linked corporate-action guide SHALL explain the exceptions and private copies for longer investigations. Current reconciliation remains diagnostic logs/proposals plus user action, without a new job lifecycle. Correction journals SHALL remain outside rotation. State loss SHALL require a reviewed simulation inventory that reuses surviving evidence and unresolved events; deleting state SHALL not be a resolution method. Available windows cannot certify lifetime history. Document unsupported-event holds, explicit old/new identity mappings, effective-date uncertainty and the unqualified non-admin read gate. Native treatment, identity remapping and historical repair SHALL remain unavailable in this increment. Acknowledgment SHALL not release holds. Rollback SHALL stop writers and force simulation before using an older image that lacks these guards; reverting code SHALL not be described as restoring financial data.

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

#### Scenario: Safety details remain reachable
- **WHEN** `rg -n 'reader|retention|30 days|3.91.0|state loss|rollback|Rollback|acknowledg' README.md docs/corporate-actions.md docs/activity-review.md docs/upgrading-to-3.0.md` runs
- **THEN** all existing operational boundaries remain documented; README provides direct links, and moved sections retain navigation from their old entry points.


### Requirement: Forward dividend upgrade guidance

Linked setup and upgrade guides SHALL require enrichment before upgrade, explain rejections/removed inference and backup/prior-image-digest rollback without financial restoration. Extra fields SHALL retain prior-runtime compatibility.

#### Scenario: Upgrade inspection
- **WHEN** guidance is inspected
- **THEN** preparation/ENV/mounts and historical boundaries are explicit.

Check: `rg -n -A 35 'structured|enrich|rollback' docs/ibkr-setup.md docs/upgrading-to-3.0.md`.


### Requirement: Diagnostic execution and visibility

Each diagnostic item SHALL declare either a user action with an observable resolution condition or an informational evidence limitation. An evidence limitation remains visible but does not trigger a reminder.

The diagnostic SHALL use existing reads, ENV and logs without persistence or financial writes. INFO SHALL summarize coverage/categories. Items requiring user checks SHALL emit at least WARNING; anomaly/uncertainty details SHALL include reasons, activity IDs and source references with quantities/monetary deltas when supported. The per-account import line SHALL include the same `to check`, `informational` and `noise` counts as the dividend report, so its duplicate count cannot be mistaken for the report result. Logs remain private. Findings SHALL NOT alter exits. Items requiring user action SHALL join Notifications in simulation too. Information and noise alone SHALL not trigger a required-action notification; technical failures retain current behavior. Live runs SHALL NOT execute the diagnostic. The linked configuration guide SHALL explain one-off Docker DRY_RUN without CRON, categories, limits and unchanged financial state.

#### Scenario: Dry-run report
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic or coherent_dividend_import_summary'` runs mocked dry and live accounts
- **THEN** dry-run details and the import line expose identical report counts without writes; live diagnostic selection, financial behavior and exits remain unchanged; required actions join the consolidated notification.

Baseline: the 2026-10-15 real dry-run import line reported duplicate skips while the report separately reported items to check, without a link between the numbers.

#### Scenario: Required-action reporting compatibility
- **WHEN** `python -m pytest -q tests -k operator_action` exercises this requirement with synthetic inputs and mocked HTTP
- **THEN** required actions emit at least WARNING and join one configured notification; financial selection, payloads, account fences and exit codes remain unchanged.


### Requirement: Retry guidance

The linked configuration guide SHALL document the SendRequest retry set, immediate failures, five-attempt schedule, longer GetStatement window and additional transport time. It SHALL explain that exhaustion still fails the run and that no ENV change is required.

#### Scenario: Operator inspects retry policy
- **WHEN** `rg -n -A 22 'Flex retry policy' docs/configuration.md` is run after implementation
- **THEN** the retry codes, 18-minute scheduled SendRequest wait, 300-second GetStatement wait, transport caveat and final failure behavior are visible.


### Requirement: Minimal native lab evidence

The connector SHALL emit only three new evidence kinds through `log.debug`: `window`, `preview` and `cash`. Each message SHALL be `LAB_EVIDENCE ` followed by compact JSON with exactly `kind` and `value`. The normal timestamp and DEBUG logging prefix SHALL precede the message. JSON escaping SHALL keep each message on one physical line. JSON numbers SHALL be finite. Unserializable or nonfinite evidence SHALL be omitted without changing existing operations. The evidence addition SHALL emit no LAB_EVIDENCE at INFO. Operational logging and required-action reporting SHALL govern new framing and summaries; the former global byte-identical INFO constraint SHALL not prohibit those changes. Evidence payloads, financial behavior, guards and requests SHALL remain unchanged. Evidence SHALL NOT dump secrets, URLs, XML, ENV, configuration, headers or response bodies. The maintainer release guide SHALL state that lab acceptance needs `LOG_LEVEL=DEBUG`.

#### Scenario: Framing and INFO compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_run_evidence.py -k 'format or info or nonfinite'` runs with synthetic inputs and mocked HTTP
- **THEN** DEBUG evidence parses on single physical lines, preserves escaped payload text and finite numbers, excludes configuration secrets, and adds no HTTP calls; INFO contains no LAB_EVIDENCE; per-activity preview message content remains unchanged while framing, levels and operational summaries follow the reporting requirements.

#### Scenario: Required-action reporting compatibility
- **WHEN** `python -m pytest -q tests -k operator_action` exercises this requirement with synthetic inputs and mocked HTTP
- **THEN** required actions emit at least WARNING and join one configured notification; financial selection, payloads, account fences and exit codes remain unchanged.


### Requirement: Writer release order and sibling compatibility

The released reader floor SHALL remain rc.5, commit `246b890d8cf2b6a58e99bbbf0169aa5f846c23bc`, image `sha256:32a034c96c2a675329e0aa38a3003a0352db8cec013ea74b6d04ac04cc8a9369`. Existing delivery evidence records 72 reader/acceptance tests, 1701 total tests, immutable publication, eight successful native lab invocations, empty first-install 142 creations, golden upgrade zero creations, zero idempotence creations and both instances stopped. This session inspected that evidence and local Git ancestry; it performed no new runtime replay.

Order SHALL be: proposal approval; implementation-task creation; offline implementation/qualification and review; archive and main replay; separate GO for an unused immutable writer RC numbered rc.6 or later; publish digest; both versioned empty/golden lab scenarios PASS on that same digest; separately authorized production activation; separately authorized comment conversion after reviewed migration preview; stable promotion only under a new GO. No soak duration or daily-cycle count SHALL gate release. Reuse valid candidate evidence when its artifact, inputs and relevant environment are unchanged. A failed digest SHALL be superseded, never promoted. Lab tests SHALL include new v2 creates, repeat runs, mixed history, short/partial acceptance, bounded recovery, maintenance and rollback on isolated synthetic rows. Expected sets and counts SHALL derive from each fixed report/snapshot pair; earlier reader counts SHALL NOT be extrapolated to the writer partition. Lab credentials SHALL remain separate from production. Stop both instances after runs.

Before any newly imported or converted v2 row exists, the previous validated rollback procedure remains applicable. After a reviewed correction writes a notes-bearing reference, rollback SHALL retain a qualified reader that supports that extended comment. Bare-v2 rc.5 support alone SHALL NOT qualify it. Afterwards, safe halt SHALL stop writers and force simulation, then restore rc.5 or a newer qualified dual reader for bare v2 history, or the new notes-compatible reader when such comments exist. Pre-rc.5 code SHALL NOT run against mixed history. Reader rollback preserves rows, does not repair data, and can still refuse partial dividend coverage. Re-enable writes only after exact mixed-generation preview and a separate GO. G6 SHALL prove this behavior using the actual rc.5 image, including complete and partial action sets, before production writing.

The common grammar SHALL remain broker-specific in generation: IBKR v2 and the Bourse Direct BD v3 target contract. The inspected Bourse Direct checkout at `3193086cd0223b0bfb18a388c53f1e0c65327dce` defines v3 in its proposed notice-import spec, but its runtime still contains v1/v2 writers; no delivered v3 writer is asserted. DEGIRO at `e8908adabd5453c9b57cb2dd687dc92a81ce15b2` writes unversioned account-scoped comments. Its authoritative CORE_PROVENANCE pins the IBKR single-file source at `5749146ff297133a6a85d9006bba60b65d9f7cde`; package adoption remains separate. DEGIRO remains pinned pending its separately owned generation decision. No sibling writer changes are implied. G7 SHALL compare sibling readers and request helpers at pinned revisions. Every changed broker-agnostic import/cash/request helper SHALL flag DEGIRO propagation under ADR 0007 and require a separate downstream change. ADR 0002 and linked configuration and upgrade guides SHALL document exact formats, required matching Trade accountId, historical limits, comment cap, recovery prerequisites, preview/maintenance separation and the rc.5 rollback floor. Existing cleanup tools SHALL NOT run against v2 history until separately qualified; document that restriction and their outside-image boundary; add no new ADR.

#### Scenario: Mixed-history rollback and downstream boundary
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_release_compatibility` runs a compatibility matrix for old/new comments, complete/partial sets, sibling namespaces and proposed maintenance changes
- **THEN** the matrix preserves reading of all historical generations, excludes pre-rc.5 rollback after v2, records pending image-backed proofs, and leaves sibling generations and pins unchanged.

All G1–G7 evidence, current destination runtime/image confirmation, a complete saved migration-input replay and image-backed import/maintenance/rollback results remain necessary. None is certified by strict OpenSpec validation. Material counterexamples SHALL stop the affected work and return the proposal for approval; they SHALL NOT become implicit implementation assumptions.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.
