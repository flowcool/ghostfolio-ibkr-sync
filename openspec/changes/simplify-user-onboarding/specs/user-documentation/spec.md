# User Documentation Delta

## Purpose

Provide one complete installation path and reachable operational guidance that agrees with the existing connector safety and reporting contracts.

## ADDED Requirements

### Requirement: Complete single-account installation

The primary installation path SHALL use one account without removing another service or supplying another account's variables. It SHALL explain obtaining the deployment files, choosing a reachable Ghostfolio network and URL, authentication, target account and currency, required Flex fields, mapping review, private writable state, simulation, result review, backup, explicit live opt-in and scheduling. The existing primary service and account ENV names SHALL remain supported. A root-level compose.multi-account.yaml SHALL retain separate state directories and staggered schedules. Existing multi-account installations SHALL receive explicit file-selection migration guidance preserving Compose project identity, ENV, service names and state; no automatic service removal SHALL be recommended. Shared DRY_RUN behavior SHALL be explained. Compose SHALL select an existing network through GHOST_DOCKER_NETWORK, default ghostfolio. Instructions SHALL derive GHOST_HOST from a service name or alias on that network and explain that a newly created network alone does not connect Ghostfolio; manual attachment can disappear on recreation. File acquisition SHALL identify the source checkout and its supported image version; examples from the documentation checkout retain stable 3.3+ compatibility. Examples SHALL select simulation and keep existing container hardening. Commands that resolve Compose SHALL use synthetic values and `--env-file /dev/null` during acceptance.

Baseline: README Quick start, compose.yaml, .env.example and tests/test_compose_example.py currently require two configured services.

#### Scenario: One account resolves without another account
- **WHEN** `env IBKR_TOKEN=synthetic IBKR_ACCOUNT_IDS_INDIVIDUAL=SOURCE IBKR_QUERY_IDS_INDIVIDUAL=1 GHOST_ACCESS_TOKEN=synthetic GHOST_ACCOUNT_NAME_INDIVIDUAL=Example docker compose --env-file /dev/null config --quiet` runs
- **THEN** it exits 0 without joint-account values, starting containers or contacting financial services.

#### Scenario: Deployment examples retain isolation and hardening
- **WHEN** `.venv/bin/python -m pytest -q tests/test_compose_example.py` runs after its existing checks are adapted to both examples
- **THEN** one-account and multi-account models retain simulation, private separate state mounts, ENV credentials and existing hardening.

### Requirement: Complete autonomous examples

Every Docker command presented as a complete sync or diagnostic invocation SHALL configure and mount persistent corporate-action state. Its instructions SHALL give directory ownership, permissions and simulation initialization. Both autonomous Docker commands SHALL use a private .env.run with container variable names and unquoted values, mode 0600, without CRON. They SHALL explicitly select DRY_RUN and mount the existing per-account ./state/individual directory at /state. Instructions SHALL forbid overlap with a scheduled run and distinguish local evidence maintenance from financial writes. Docker command examples SHALL NOT put token values in shell history. The Compose .env SHALL NOT be presented as a Docker run ENV file. Both commands SHALL use the same documented safety prerequisites as Compose. Financial writes SHALL remain disabled until explicit review and opt-in.

Baseline: both autonomous Docker commands in docs/configuration.md currently mount only mapping.yaml.

#### Scenario: Inspect complete Docker commands
- **WHEN** `rg -n -A 22 'docker run' docs/configuration.md` runs
- **THEN** each complete invocation provides state configuration and a persistent mount; adjacent instructions state permissions and simulation prerequisites.

### Requirement: Consistent current behavior and release history

Before replacing CHANGELOG.md, every migration and rollback fact SHALL remain available in a linked guide or release. The 3.0 guide SHALL retain the historical breaking default and explicit DRY_RUN=true before rollback to older images. Current user guides SHALL agree with the existing Simulation, Notifications, Required user actions and Final operational result contracts. They SHALL distinguish clean success, required action, failure, interruption and notification delivery. Successful simulation SHALL NOT be described as always silent. Historical upgrade guides SHALL distinguish old behavior from current instructions. CHANGELOG.md SHALL remain a working entry point to GitHub Releases. Maintainer procedures SHALL be reached from contribution guidance; README SHALL keep a Releases link. Any investigation retained as historical material SHALL be labelled accordingly and SHALL point to current release instructions.

Baseline: conflicting text in docs/ibkr-setup.md, docs/troubleshooting.md and CHANGELOG.md; historical process description in docs/release-notes-automation.md.

#### Scenario: Inspect notification and history instructions
- **WHEN** `rg -n -i 'notif|expiry|simulation|release|historical' README.md docs/getting-started.md docs/configuration.md docs/ibkr-setup.md docs/troubleshooting.md docs/upgrading-to-3.0.md CHANGELOG.md docs/release-notes-automation.md` runs
- **THEN** current statements agree with the runtime contracts and historical statements cannot be mistaken for current setup instructions.

### Requirement: Progressive guidance without lost safety content

README SHALL present purpose, essential limits, prerequisites and one installation entry point. Detailed corporate-action guidance SHALL live in docs/corporate-actions.md. Activity review SHALL provide clear sections for use, proposal review, approval, execution, recovery and safety limits. docs/maintenance.md SHALL index distinct maintenance operations. Each mutating procedure SHALL state its prerequisites, authorization, stop conditions and recovery before its commands. Every restructured guide SHALL preserve old anchors or provide same-anchor links to moved content. docs/cleanup.md SHALL retain its old anchors and link to the moved procedures. Recovery entry points SHALL state the v2 restrictions on unqualified pair cleanup tools. Review snippets SHALL use ibkr-sync-individual and mount /review separately from corporate state at /state. Mapping SHALL be edited before restrictive ownership changes. Relative links in moved text SHALL remain valid. One checklist in docs/ibkr-setup.md SHALL own required Flex sections and fields. Unknown current vendor UI order SHALL NOT be asserted. Legacy authentication and optional platform metadata SHALL remain outside the mandatory first-install path. Existing mapping examples and fallback rules SHALL remain unchanged.

Baseline: README has 2778 words; docs/cleanup.md combines several operations; docs/activity-review.md has only one subsection. README safety details are currently required by connector-runtime.

#### Scenario: Inspect guide entry points
- **WHEN** `rg -n '^#{1,4} |corporate-actions.md|getting-started.md|maintenance.md' README.md docs/getting-started.md docs/corporate-actions.md docs/activity-review.md docs/maintenance.md docs/cleanup.md` runs
- **THEN** installation, financial exceptions, review and each maintenance operation have distinct entry points; old navigation remains available.

#### Scenario: Existing navigation checks
- **WHEN** `.venv/bin/python -m pytest -q tests/test_documentation.py` runs after the existing DOCUMENTS collection and navigation expectations include every changed/new guide
- **THEN** existing checked links and anchors resolve; no test depends on exact prose. A bounded one-off link and anchor check covers new and moved guides without adding a test framework.

#### Scenario: Resolved network and mounts
- **WHEN** `env IBKR_TOKEN=synthetic IBKR_ACCOUNT_IDS_INDIVIDUAL=SOURCE IBKR_QUERY_IDS_INDIVIDUAL=1 GHOST_ACCESS_TOKEN=synthetic GHOST_ACCOUNT_NAME_INDIVIDUAL=Example GHOST_DOCKER_NETWORK=example-network docker compose --env-file /dev/null config --format json` runs
- **THEN** the model selects example-network, mapping and state bind sources resolve under the installation directory, simulation remains enabled and no service starts. The corresponding multi-account check uses distinct source/target values and staggered CRON values.
