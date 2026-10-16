# Tasks

## 1. Versioned reader

- [ ] 1.1 Amend ADR 0002; add a pre-loop parser/index; run `.venv/bin/python -m pytest -q tests -k versioned_identity_reader`.
- [ ] 1.2 Add action coverage, precedence, exclusions and account-local failure; prove them with the same command.

## 2. Import acceptance and guidance

- [ ] 2.1 Fail known short 2xx responses while preserving safe results and continuation; update README troubleshooting; run `.venv/bin/python -m pytest -q tests -k short_import_acceptance`.
