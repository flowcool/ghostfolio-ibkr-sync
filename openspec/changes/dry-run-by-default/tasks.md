# Tasks

All tasks implement the `connector-runtime` delta: Simulation and Notifications. Commands run from the repository root with development dependencies installed.

## 1. Runtime

- [ ] 1.1 (60 min) Change `ibkr_to_ghostfolio.py` parsing, validation and per-invocation warning. Let `finalize_run()` send Failure for invalid configuration after rejection. Add default/value scenarios in `tests/test_orchestration.py`, including configured/disabled Apprise and HTTP ordering: rejection precedes every HTTP call; only Apprise may follow. Assert exit 1 and no financial writes. Set explicit false in existing live fixtures, including notification tests. Acceptance: `python3 -m pytest -q tests/test_orchestration.py tests/test_finalize.py tests/test_outcome.py tests/test_token_expiry.py` passes.
- [ ] 1.2 (60 min; after 1.1) Change `ibkr_to_ghostfolio.py` finalization and add pipeline/notification scenarios in `tests/test_auth.py`, `tests/test_finalize.py` and `tests/test_token_expiry.py`, with synthetic reports and mocked HTTP. Cover Failure for default/blank/truthy/invalid modes, silent successful simulations/expiry-only reminders/previews, disabled Apprise, single dispatch, unchanged exit on delivery failure, and explicit-live TZ behavior. Update former failed-dry-run silence assertions. Acceptance: `python3 -m pytest -q tests/test_auth.py tests/test_finalize.py tests/test_token_expiry.py tests/test_ghostfolio.py` passes.

## 2. Upgrade guidance

- [ ] 2.1 (60 min; after 1.2) Update README, its Compose examples, `docs/ibkr-setup.md`, `docs/upgrading-to-3.0.md` and `CHANGELOG.md` (create if absent). Remove instructions to unset DRY_RUN for writes. Explain rc.2 defaults, invalid-value rejection before HTTP followed only by configured Failure delivery, warning, failed-simulation Failure notifications, silent successful simulations/expiry-only reminders/previews, false opt-in and digest rollback. Acceptance: `rg -n 'DRY_RUN|rc\.2|rollback' README.md docs/ibkr-setup.md docs/upgrading-to-3.0.md CHANGELOG.md` shows consistent guidance in every file. No documentation tests.

Release ownership: task 3.1 is removed. The existing single project release item outside this repository owns archive after task completion, main replay, rc.2 publication, separately authorized real proof/soak and stable publication. No separate release flow or release work item is created here.
