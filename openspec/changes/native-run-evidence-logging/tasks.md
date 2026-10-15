# Tasks

## 1. Minimal native lab evidence

- [x] 1.1 Add `window`, `preview` and `cash` DEBUG evidence in `ibkr_to_ghostfolio.py`; add synthetic mocked-HTTP tests in `tests/test_run_evidence.py`; add the README line that lab acceptance needs `LOG_LEVEL=DEBUG`. Spec: `specs/connector-runtime/spec.md`, all requirements and scenarios. Verify `.venv/bin/python -m pytest -q tests/test_run_evidence.py` and `.venv/bin/python -m pytest -q`: exact consumer shapes, complete payloads, finite JSON, unchanged guards and byte-identical INFO. Flag downstream shared-helper propagation in the PR. Rollback: revert the implementation commit. Do not archive or release.
