# Spec Delta

## MODIFIED Requirements

### Requirement: Current operational limits

The connector SHALL retain documented boundaries: 365-day guidance; daily data; corporate-action detection with evidence-based BUY/SELL holds; manual corporate-action treatment, history and token renewal; additive imports with optional manually approved or explicitly profile-authorized corrections; proximity skips next to manual or legacy rows (INFO when amounts agree, WARNING otherwise, never imported; a distinct payment there needs a manual add); trust principle: a row with a connector comment (`dividend#…`) is ours and trusted by exact identity, and with review disabled a user edit of such a row is out of contract; enabled review SHALL expose differences and manual or profile authority; stored UTC instants with configured-TZ business-date eligibility; unconverted cash/commission currencies; Yahoo quality; net, nonchronological checks; nontransactional buy/sell phases; preview without server acceptance; buffered 10 MiB Flex responses; no general overlap protection. Enabled correction dispatch SHALL require exclusive writes and persistent recovery evidence as specified in activity-correction-review. README SHALL retain the additive-import boundary, manual corporate-action treatment, the 365-day window, persistent-volume requirement, simulation initialization and explicit live opt-in. It SHALL link directly to detailed safety and recovery guidance. Linked user guides SHALL describe the reader floor for notes-bearing references. They SHALL document CORPORATE_ACTION_STATE_FILE, simulation initialization, live BUY/SELL refusal on missing/invalid state, simulation refusal with exit 1 on missing/unwritable state, private retained report bytes, retained events outside later report windows, candidate-specific hold/release evidence, notification frequency and the stable Ghostfolio 3.91.0 minimum for accepting native split evidence. Ordinary acquired reports SHALL rotate automatically after a fixed 30 days from acquisition, without a new ENV setting or quota. Required safety originals SHALL follow corporate-action-detection retention rules. The linked corporate-action guide SHALL explain the exceptions and private copies for longer investigations. Reconciliation supports opt-in bounded automatic corrections and compact decisions without a new job lifecycle. The linked activity-review and configuration guides SHALL describe profiles and limits, fee exclusion from identity, pair rejection, schema-3 migration and private state, uncapped correction execution, the fixed 28-second delay, scheduler duration guidance and downgrade recovery. Correction journals SHALL remain outside rotation. State loss SHALL require a reviewed simulation inventory that reuses surviving evidence and unresolved events; deleting state SHALL not be a resolution method. Available windows cannot certify lifetime history. Document unsupported-event holds, explicit old/new identity mappings, effective-date uncertainty and the unqualified non-admin read gate. Native corporate-action treatment, corporate-action identity remapping and historical repair remain unavailable; legacy comment migration follows activity-reconciliation. Acknowledgment SHALL not release holds. Rollback SHALL stop writers and force simulation before using an older image that lacks these guards; reverting code SHALL not be described as restoring financial data.

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
