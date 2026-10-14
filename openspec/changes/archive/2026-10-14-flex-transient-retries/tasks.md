# Tasks

Implementation starts only after operator review. Each task is a separate work item and fresh session. Commands below use synthetic responses and mocked HTTP; no live portfolio replay.

## 1. SendRequest recovery

- [x] 1.1 Implement the `connector-runtime` delta's "Bounded SendRequest recovery" in `fetch_flex_report`, preserving `_ibkr_get`, per-response size checks, redaction and URL validation. Add recovery, exhaustion and full code-classification scenarios to `tests/test_orchestration.py`; update README's "Flex retry policy" with retry codes, immediate failures, schedule and transport caveat. Files: `ibkr_to_ghostfolio.py`, `tests/test_orchestration.py`, `README.md`. Verify `.venv/bin/python -m pytest -v tests/test_orchestration.py tests/test_parsing.py -k 'flex_transient_send or flex_fetch or fetch_flex_report or ibkr_get'` (all selected cases pass; patched sleeps assert `[60, 120, 300, 600]`, permanent codes make one request) and `rg -n -A 22 'Flex retry policy' README.md` (18-minute scheduled wait and final failure visible).

## 2. Extended GetStatement window

- [x] 2.1 Implement the delta's "Extended statement polling and preserved guards": default sixty attempts at five seconds, unchanged Warn/1019 detection, overrides, timeout and other-error failures. Add late-success/default-exhaustion coverage in `tests/test_orchestration.py` with patched sleeps; complete README's "Retry guidance" with the 300-second polling window and no ENV change. Files: `ibkr_to_ghostfolio.py`, `tests/test_orchestration.py`, `README.md`. Verify `.venv/bin/python -m pytest -v tests/test_orchestration.py tests/test_parsing.py -k 'flex_fetch or fetch_flex_report or flex_transient or ibkr_get'` (late success, sixty-request exhaustion and existing guards pass) and `rg -n -A 22 'Flex retry policy' README.md` (both budgets and exhaustion behavior visible).

## 3. Stable release

- [x] 3.1 After all implementation items merge, archive the change before the release item, replay acceptance on main, then publish a semver stable release only on the operator's go under `release-publication`. No deployment or financial write. Verify `.venv/bin/python -m pytest -v tests/test_orchestration.py tests/test_parsing.py -k 'flex_fetch or fetch_flex_report or flex_transient or ibkr_get'` on main, `gh run view <release-run-id> --log` (stable publication and native checks pass), and `docker buildx imagetools inspect ghcr.io/flowcool/ghostfolio-ibkr-sync:<X.Y.Z>` (pullable amd64/arm64 image). Record installed/prior digest recovery guidance; close the parent bug and public issue only after runtime delivery. Owned by infra-0npr.7 (single release, Florent 2026-10-14).
