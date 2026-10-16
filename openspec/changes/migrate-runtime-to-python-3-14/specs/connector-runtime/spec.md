# Spec Delta

## MODIFIED Requirements

### Requirement: Execution and authentication

The shipped Docker image and every CI or scheduled Python job SHALL use CPython 3.14. Direct Python runs SHALL be documented for Python 3.14 or newer. The connector SHALL NOT reject Python 3.12 explicitly.

The connector SHALL use ENV, Python/Docker one-off runs or Docker CRON, and exactly one credential: GHOST_ACCESS_TOKEN exchanged once per run or unchanged GHOST_TOKEN bearer.

Baseline replaced: README “Prerequisites”, CONTRIBUTING “Tests”, `docs/upstreams.md`, and `tests/test_dockerfile.py` record Python 3.12.

#### Scenario: Configured startup
- **WHEN** startup configuration is evaluated
- **THEN** authentication precedes reads; numeric five-field CRON is validated.

#### Scenario: Repository runtime declarations
- **WHEN** `.venv/bin/python -m pytest -q tests -k python_runtime_baseline` runs
- **THEN** the Docker base, all seven workflow pins, both Renovate ranges, and public direct-run guidance require Python 3.14 as specified.

#### Scenario: Built runtime
- **WHEN** `docker build -t ibkr-python314:check . && bash scripts/check_container_runtime.sh ibkr-python314:check` runs
- **THEN** the isolated one-off and scheduled checks pass, and the container reports CPython 3.14.
