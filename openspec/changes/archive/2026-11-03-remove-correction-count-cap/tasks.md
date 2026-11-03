# Tasks

## 1. Execute all eligible corrections

- [x] 1.1 Update the review permit and loop. Cover chains of 1, 5 and 32 corrections, delayed readback, faults at position k, two accounts and restart without resend. Files: `ghostfolio_ibkr_sync/activity_review.py`, `tests/test_activity_review.py`, `tests/test_activity_reconciliation.py`. Requirements: verified correction and safe instructions. Acceptance: `.venv/bin/python -m pytest -q tests/test_activity_review.py tests/test_activity_reconciliation.py`.
- [x] 1.2 Update the required activity-review, release and lab guides and CHANGELOG. Sync the spec delta. Acceptance: `openspec validate --change remove-correction-count-cap --strict` and semantic diff review.
- [x] 1.3 Run the full offline gate and archive this change. Acceptance: `bash scripts/check.sh` and `openspec validate --specs --strict`.
