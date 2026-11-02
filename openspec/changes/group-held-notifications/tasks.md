# Tasks

## 1. Grouped delivery

- [ ] 1.1 Implement connector-runtime Notifications with private grouped state and single dispatch in action_notifications.py and app.py. Add tests/test_grouped_notifications.py and update tests/test_finalize.py and tests/test_token_expiry.py. Document the interval and state in docs/configuration.md. Verify unchanged, changed, cleared, due, failure and unsafe-state scenarios with pytest.

## 2. Held-event classification

- [ ] 2.1 Implement connector-runtime required-action inventory and corporate-action grouped scheduling in activity_review.py and app.py. Update tests/test_activity_review.py and add budget/qualification finalization tests. Preserve approval, uncertainty and maintenance boundaries. Verify focused pytest and update notification documentation and CHANGELOG.md.

## 3. Integration

- [ ] 3.1 Run bash scripts/check.sh with the full offline suite. Validate and archive this change with both spec deltas synchronized. Review the diff and merge through one PR after CI and Pullfrog acceptance.
