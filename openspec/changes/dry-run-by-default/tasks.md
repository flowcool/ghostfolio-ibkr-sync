# Tasks

All tasks implement `connector-runtime` / Simulation. Commands run from the repository root with development dependencies installed.

## 1. Runtime

- [ ] 1.1 (60 min) Change `ibkr_to_ghostfolio.py` parsing, validation and per-invocation warning. Add default/value scenarios in `tests/test_orchestration.py`. Set explicit false in existing live fixtures, including notification tests. Acceptance: `python3 -m pytest -q tests/test_orchestration.py tests/test_finalize.py tests/test_outcome.py tests/test_token_expiry.py` passes.
- [ ] 1.2 (60 min; after 1.1) Add pipeline and notification scenarios in `tests/test_auth.py` and `tests/test_finalize.py`, with synthetic reports and mocked HTTP; repair runtime defects if found. Acceptance: `python3 -m pytest -q tests/test_auth.py tests/test_finalize.py tests/test_ghostfolio.py` passes.

## 2. Upgrade guidance

- [ ] 2.1 (60 min; after 1.2) Update README, its Compose examples, `docs/ibkr-setup.md`, `docs/upgrading-to-3.0.md` and `CHANGELOG.md` (create if absent). Remove instructions to unset DRY_RUN for writes. Explain rc.2 defaults, invalid values, warning, notifications, false opt-in and digest rollback. Acceptance: `rg -n 'DRY_RUN|rc\.2|rollback' README.md docs/ibkr-setup.md docs/upgrading-to-3.0.md CHANGELOG.md` shows consistent guidance in every file. No documentation tests.

## 3. Release

- [ ] 3.1 (60 min active work; after merges) Archive, replay `python3 -m pytest -q` on main, publish rc.2 on operator GO, then stable after separately authorized real proof/soak and GO. Acceptance: `for v in 3.0.0-rc.2 3.0.0; do gh release view "v$v" --json tagName,isPrerelease && docker buildx imagetools inspect "ghcr.io/flowcool/ghostfolio-ibkr-sync:$v" || exit 1; done` proves both releases and pullable images. Stable must use the validated RC commit. Keep the parent open until completion.
