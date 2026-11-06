# Tasks

## 1. Unavailable-target preview

- [x] 1.1 Refresh source-derived preview values in `ghostfolio_ibkr_sync/activity_review.py`. Add synthetic repeated-cycle, compact-deletion and restart tests in `tests/test_activity_review.py`. Document last-observed target evidence in `docs/activity-review.md`. Verify the current-source-preview requirement and both scenarios with `python -m pytest -q tests/test_activity_review.py -k unavailable_target`.

## 2. Integration

- [x] 2.1 Verify the complete offline contract with `scripts/check.sh`. Validate the change with `openspec validate refresh-unavailable-target-review --strict`. Keep the lab gate pending before merge.
