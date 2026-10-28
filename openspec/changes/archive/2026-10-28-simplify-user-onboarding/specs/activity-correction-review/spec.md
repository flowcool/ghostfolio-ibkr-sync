# Documentation Location Delta

## MODIFIED Requirements

### Requirement: Simulation and activation qualification

Simulation SHALL create and refresh proposals, validate approvals and display exact intended replacements. It SHALL send no financial POST/PUT/DELETE and create no applied journal result. Valid approvals SHALL remain unconsumed. Stale approvals SHALL be cleared using the same rules as live runs. Simulated correction effects SHALL remain isolated from real state. Simulation may display that an unresolved journal now matches expected-after, but SHALL NOT resolve that journal, consume its yes, remove its proposal or release its real account fence. A later live run SHALL revalidate and record observed completion without another PUT.

README SHALL link directly to the activity-review guide. That guide SHALL document the ENV opt-in, persistent-volume permissions, YAML example, sole yes choice, import holds, manual false-match handling, stale/unavailable status, logs, recovery journal and disabling procedure. Activation SHALL require exact-image isolated qualification of full updates, notes and tags, profile/background effects, duplicate references, restart recovery and no repeat writes. Existing empty/golden release acceptance remains required under its own authority; no new mandatory duration gate is introduced. Source inspection and mocks SHALL NOT be presented as image qualification. A failed preservation case SHALL keep affected corrections unavailable.

#### Scenario: Review without financial writes
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_simulation` exercises blank/yes/stale proposals, forced preview and unresolved journals
- **THEN** the YAML is updated, valid yes remains, no financial mutation occurs and neither real accepted-state indexes nor journal results claim a simulated correction.

#### Scenario: Operator guidance and isolated qualification
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_qualification` replays the compatibility contract offline, and the separately authorized exact-image empty/golden acceptance is later evaluated
- **THEN** offline results and actual image evidence are distinguished; missing preservation, recovery or reader-rollback proof blocks real enablement rather than weakening the approved contract.

All test commands above name acceptance tests to implement. They are not evidence of existing feature delivery. Baseline evidence is the README, existing filter/index tests and the pinned update controller/service/DTO cited in connector-runtime.
