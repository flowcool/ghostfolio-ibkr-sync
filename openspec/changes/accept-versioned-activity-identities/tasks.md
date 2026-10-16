# Tasks

## 1. Versioned identity reader

- [ ] 1.1 Add the shared identity ADR and a pure legacy/v2 parser beside `ghost_get_existing_orders`. Reject malformed or future IBKR markers. Prove grammar, legacy and complete v2 behavior with `.venv/bin/python -m pytest -q tests -k versioned_identity_reader`.
- [ ] 1.2 Add action-aware coverage to `dividend_dedup_decision`. Prove that complete v2 coverage skips and partial coverage rejects without a legacy import, using the same command.

## 2. Exact import acceptance

- [ ] 2.1 Make `ghost_import_activities` fail a known short 2xx response while retaining proven creations, continuing cash and later accounts, and preserving unknown-outcome fencing. Prove it with `.venv/bin/python -m pytest -q tests -k short_import_acceptance`.
