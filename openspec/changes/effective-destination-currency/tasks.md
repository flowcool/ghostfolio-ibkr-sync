# Tasks

Claude approved decisions 1–4 with the amendments below. Implement these tasks
in order. Retain current profile limits and dividend representation rules.
Residual counts require evidence. No fixed residual hold count is required.

All spec paths below are relative to this change. Runtime checks use Python 3.14
from the development environment, synthetic inputs and mocked HTTP. The private
replay input stays read-only. No production or broker access is needed.

## 1. Resolve currency without changing raw evidence

- [ ] 1.1 Implement the shared pure resolver and use it for existing dividend amounts and historical diagnostics. Files: `ghostfolio_ibkr_sync/ghostfolio.py`, `ghostfolio_ibkr_sync/diagnostics.py`, `tests/test_ghostfolio.py`, `tests/test_dividend_diagnostics.py`. Requirement: `specs/connector-runtime/spec.md` — Proven effective destination currency. Scenarios: explicit override/proven fallback and exact scaling. Verify: `python -m pytest -q tests/test_ghostfolio.py tests/test_dividend_diagnostics.py -k effective_currency_resolution`.
- [ ] 1.2 Apply resolved currency to exact accepted import subsets without changing submitted payloads, accepted identities or account fences. Files: `ghostfolio_ibkr_sync/ghostfolio.py`, `tests/test_ghostfolio.py`, `tests/test_orchestration.py`. Requirement: `specs/connector-runtime/spec.md` — Exact acceptance with nullable currency evidence. Scenario: accepted subsets and subsequent holdings. Verify: `python -m pytest -q tests/test_ghostfolio.py tests/test_orchestration.py -k effective_currency_acceptance`.

## 2. Compare review operations and diagnose remaining holds

- [ ] 2.1 Make review field comparison use effective currency while preserving raw snapshots and comment-only operation fields. Remove only proven conforming currency-only proposals. Update `docs/activity-review.md` with raw/effective currency, unknown-proof holds and unchanged authority limits. Files: `ghostfolio_ibkr_sync/activity_review.py`, `tests/test_activity_review.py`, `tests/test_activity_reconciliation.py`, `docs/activity-review.md`. Requirement: `specs/activity-correction-review/spec.md` — Currency representation does not create a correction. Scenario: conformity and retained real differences. Verify: `python -m pytest -q tests/test_activity_review.py tests/test_activity_reconciliation.py -k effective_currency_comparison`; inspect the guide with `rg -n 'currency|profile|journal' docs/activity-review.md`.
- [ ] 2.2 Apply the same resolver to manual candidates, automatic pairs, exact numeric evidence and groups. Give precise currency/source/amount/identity reasons. Preserve current financial limits and distinct legacy trade/dividend authority. Files: `ghostfolio_ibkr_sync/activity_review.py`, `ghostfolio_ibkr_sync/activity_reconciliation.py`, `ghostfolio_ibkr_sync/diagnostics.py`, `tests/test_activity_reconciliation.py`, `tests/test_dividend_diagnostics.py`, `tests/test_conversion.py`. Requirements: `specs/activity-reconciliation/spec.md` — Effective currency in association and financial evidence; Precise currency and eligibility diagnosis. Scenarios: independent legacy gates, distinct reasons and grouping, scaling. Verify: `python -m pytest -q tests/test_activity_reconciliation.py tests/test_dividend_diagnostics.py tests/test_conversion.py -k 'effective_currency_legacy or effective_currency_diagnosis or effective_currency_scaling'`.

## 3. Confirm exact writes and retain recovery contracts

- [ ] 3.1 Add new-policy currency comparison and bound actual raw readback evidence to the existing exact request/recovery path. Keep all other financial and preserved-field checks exact. Files: `ghostfolio_ibkr_sync/activity_review.py`, `ghostfolio_ibkr_sync/activity_preservation.py` only if a currency-specific comparison adapter is needed, `tests/test_activity_review.py`. Requirement: `specs/activity-correction-review/spec.md` — Currency evidence survives refresh and exact recovery. Scenario: positive readback with exact preservation. Verify: `python -m pytest -q tests/test_activity_review.py -k effective_currency_readback`.
- [ ] 3.2 Implement the reviewed comparison-policy compatibility choice. Run the real code at tag `v4.0.0` against a pending new-policy journal and prove it fails closed. If that proof fails, use a new explicit journal version and classify the release as minor. Retain legacy pending contracts, immutable journal evidence, consent invalidation, rejection bindings and safe downgrade behavior. Update `docs/activity-review.md` with the reader limit and recovery steps. Files: `ghostfolio_ibkr_sync/activity_review.py`, `tests/test_activity_review.py`, `docs/activity-review.md`. Same requirement. Scenario: upgrade and downgrade evidence. Verify: `python -m pytest -q tests/test_activity_review.py -k effective_currency_persistence`; inspect the updated downgrade guidance with `rg -n 'journal|downgrade|rollback' docs/activity-review.md`.

## 4. Keep historical identity tools consistent and stricter

- [ ] 4.1 Use effective currency in historical identity preview without relaxing exact financial/day/coverage or selection-replay checks. Files: `identity_migration.py`, `tests/test_identity_migration.py`. Requirement: `specs/connector-runtime/spec.md` — Exact acceptance with nullable currency evidence. Scenario: historical preview remains exact. Verify: `python -m pytest -q tests/test_identity_migration.py -k effective_currency`.
- [ ] 4.2 Use effective currency in recovery accepted-payload and positive readback comparisons. Permit a legitimate explicit override while retaining independent existing-row, identity and settlement guards. Files: `identity_recovery.py`, `tests/test_identity_recovery.py`. Same requirement. Scenario: recovery remains exact. Verify: `python -m pytest -q tests/test_identity_recovery.py -k effective_currency`.

## 5. Verify the complete offline behavior

- [ ] 5.1 Implement the G2 test using the private hash-bound review input. Report observed baseline separately from synthetic profile/source supplementation. Cover all named residual rows, 7272.T, missing-proof controls, the 108-to-zero class, the conditional 66-candidate projection and the 25 currency checks. Preserve input bytes, disable network/credentials and require zero financial requests. Files: `tests/test_activity_reconciliation.py` and existing test helpers only as needed. Requirement: `specs/activity-reconciliation/spec.md` — Replay expectations respect evidence and current limits. Scenario: hash-bound simulation and count limits. Verify: `python -m pytest -q -s tests/test_activity_reconciliation.py -k effective_currency_replay` with `EFFECTIVE_CURRENCY_REPLAY_INPUT` set to the private input.

Complete G1 with `bash scripts/check.sh` after the integrated changes pass.
G3/G4 remain acceptance gates on the one immutable candidate in both labs.
They are not implementation tasks or proof delivered by this proposal. Reuse
the owning execution item for their operation plan and evidence. Route a missing
Infra runner capability to Infra. The future IBKR PR must flag ADR 0007 downstream
propagation; this work does not update the DEGIRO pin. Archive only after the
approved implementation and required qualification, under the project workflow.
