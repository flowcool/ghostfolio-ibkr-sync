# Tasks

These tasks require operator approval of this change. Acceptance commands below target new tests. They are not passing evidence yet. Each slice includes its own tests and required README text. Existing release gates remain outside this implementation checklist.

## 1. Read source events and explain evidence

- [ ] 1.1 Add the typed corporate-action inventory and sanitized real-shape fixtures. Cover source-account validation, the two forward events, linked reverse legs, row-order independence, repeats and unsupported/conflicting records. Touch corporate_actions.py, ibkr.py, types.py, tests/test_corporate_actions.py and synthetic fixture files. Verify: `python -m pytest -q tests/test_corporate_actions.py -k inventory`.
- [ ] 1.2 Add independent identity, quantity, history and cash conclusions. Preserve observed zero versus unavailable evidence. Document source-window and cash limits in README. Touch corporate_actions.py, tests/test_corporate_actions.py and README.md. Verify: `python -m pytest -q tests/test_corporate_actions.py -k conclusions`.

## 2. Prove destination units before import

- [ ] 2.1 Add authenticated bounded reads for native profile/holding evidence and filtered export version metadata. Require stable 3.91.0 minimum only for native evidence; retain exact response decimals and existing redirect/credential rules. Document the floor in README. Touch ghostfolio.py, corporate_actions.py, tests/test_corporate_actions.py, tests/test_ghostfolio.py and README.md. Verify: `python -m pytest -q tests/test_corporate_actions.py -k native_evidence`. Flag the shared helper change for separate downstream propagation.
- [ ] 2.2 Separate stored identity rows from effective dated holdings. Cover original/native, already-normalized and unresolved histories; no double adjustment, tolerance or inferred ISIN continuity. Preserve accepted-buy and sale guards. Touch ghostfolio.py, sync.py, app.py and tests/test_corporate_actions.py. Verify: `python -m pytest -q tests/test_corporate_actions.py -k 'conclusions or native_evidence or effective_holdings'`.

## 3. Retain findings and apply scoped holds

- [ ] 3.1 Add CORPORATE_ACTION_STATE_FILE configuration, private keyed YAML, simulation bootstrap, locking and atomic publication. Preserve unresolved events across shorter windows; reject missing live state, unsafe paths and edited conclusions. Document the persistent mount and initialization in README. Touch config.py, corporate_actions.py, types.py, tests/test_corporate_actions.py and README.md. Verify: `python -m pytest -q tests/test_corporate_actions.py -k persistence`.
- [ ] 3.2 Generalize the validated run source inventory before review dispatch. Enforce affected-security or account BUY/SELL holds in review and ordinary imports. Rebuild selection only after evidence-based release. Preserve independent cash, later accounts and stronger pending-write fences. Touch app.py, activity_review.py, corporate_actions.py and tests/test_corporate_actions.py. Verify: `python -m pytest -q tests/test_corporate_actions.py -k holds`.

## 4. Report outcomes and preserve the runtime contract

- [ ] 4.1 Publish detailed findings each run and coalesce redacted notification reasons into the existing single dispatch. Cover first/changed nonblocking findings, repeated holds, resumption, simulation and failed delivery. Document notification frequency and manual resolution limits in README. Touch app.py, outcome.py, notify.py, corporate_actions.py, tests/test_corporate_actions.py, tests/test_finalize.py and README.md. Verify: `python -m pytest -q tests/test_corporate_actions.py -k notifications`.
- [ ] 4.2 Integrate all slices with baseline source/identity/review/cash gates. Prove no corporate-action financial request, no automatic repair and no weakening of unknown-write fences. Complete README rollback guidance and the native-versus-normalized examples. Touch tests/test_corporate_actions.py, affected runtime modules and README.md. Verify: `python -m pytest -q tests/test_corporate_actions.py -k runtime_contract`, then `bash scripts/check.sh`. Record the exact candidate and remaining image-backed release gates; do not present offline checks as runtime qualification.
