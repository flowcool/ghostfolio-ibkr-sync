## 1. Clear approval file

- [x] 1.1 Add schema-2 sections, evidence levels, literal-yes skipping and schema-1 compatibility. Preserve pending journals and stale-approval checks. Files: activity_review.py, tests/test_activity_review.py. Acceptance: `python -m pytest -q tests/test_activity_review.py`.

## 2. Selected historical maintenance

- [x] 2.1 Stage reference-only historical proposals in the same file and prepare the exact approved subset through existing migration proof. Rebuild it at apply. Files: identity_migration.py, tests/test_identity_migration.py. Acceptance: `python -m pytest -q tests/test_identity_migration.py`.

## 3. Exact preservation

- [x] 3.1 Distinguish named metadata churn from business or unknown-field drift in migration and review. Preserve raw tamper evidence and recovery compatibility. Files: package preservation helper, activity_review.py, identity_migration.py, migration/review tests. Acceptance: `python -m pytest -q tests/test_identity_migration.py tests/test_activity_review.py`.

## 4. Community guidance

- [x] 4.1 Document both execution paths, evidence levels, only-yes behavior, examples, compatibility and recovery. Files: README.md, docs/cleanup.md. Acceptance: `openspec validate --all --strict` and command examples checked against CLI help and offline tests.
