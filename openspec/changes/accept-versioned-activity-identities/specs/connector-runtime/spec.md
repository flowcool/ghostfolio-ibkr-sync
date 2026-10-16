# Spec Delta

## ADDED Requirements

### Requirement: Versioned activity identity reader

The connector SHALL recognize legacy trade comments `IBKR#<tradeID>`, legacy dividend comments `dividend#<SYMBOL|ISIN>#<date>`, and these reader-only identities:

- `IBKR#v2#<source-account>:TRADE:<tradeID>`
- `IBKR#v2#<source-account>:DIVIDEND:<actionID>`

The shared grammar SHALL be `<BROKER>#v<N>#<source-account>:<KIND>:<source-id>`. Versions are positive broker generations. Segments SHALL contain only ASCII letters, digits, `.`, `_`, or `-`. This change SHALL NOT write versioned comments or change activities.

An invalid or unknown `IBKR#v` comment SHALL stop the run before financial writes. Partial v2 coverage of one legacy security/day dividend group SHALL reject that group and produce a nonzero run; other processing SHALL continue.

Baseline: ADR 0002 and reconciliation tests cover legacy comments. Two saved reports have the same 49 payment actions and no observed identity conflict.

#### Scenario: Legacy, complete v2, invalid and partial identity
- **WHEN** `.venv/bin/python -m pytest -q tests -k versioned_identity_reader` runs legacy, v2, invalid and partial cases
- **THEN** legacy and complete v2 identities deduplicate; invalid input stops before writes; partial dividend coverage degrades only the affected account without a legacy import.

### Requirement: Exact short import acceptance

A valid 2xx response SHALL map each created row to one submitted `(accountId, comment)`. A shorter set SHALL retain proven creations, emit one WARNING naming omitted comments, make no retry, and fail the account. Cash and later accounts SHALL continue. Unknown-outcome fencing and identifier-free notifications SHALL remain.

Baseline: `test_import_short_accepted_count_is_not_a_failure` records the current clean outcome; the pinned lab returned HTTP 201 with no creation for a duplicate.

#### Scenario: Proven short response
- **WHEN** `.venv/bin/python -m pytest -q tests -k short_import_acceptance` runs full, short and unknown responses
- **THEN** only full acceptance is clean; known short acceptance is not retried and fails visibly while preserving exact created holdings; unknown outcomes retain their write fence.
