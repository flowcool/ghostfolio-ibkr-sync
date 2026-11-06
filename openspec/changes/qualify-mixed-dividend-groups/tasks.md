## 1. Qualify and execute the missing-action correction

- [ ] 1.1 Add strict group qualification and synthetic three-shape regressions. Cover unique allocation, blocked ambiguity, consent invalidation, confirmed dispatch and uncertainty. Files: `ghostfolio_ibkr_sync/activity_review.py`, `tests/test_mixed_dividend_review.py`. Acceptance: `python -m pytest -q tests/test_mixed_dividend_review.py` and `scripts/check.sh`.

## 2. Document the bounded exception

- [ ] 2.1 Explain the qualified exception and retained maintenance limits in `docs/activity-review.md`, `docs/upgrading-to-3.0.md`, `docs/maintenance/identity-migration.md` and `docs/maintenance/missing-dividend-recovery.md`. Acceptance: strict OpenSpec validation and semantic diff review against the requirement.
