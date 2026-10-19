# Spec Delta

## ADDED Requirements

### Requirement: Versioned activity identity reader

Exact lowercase `IBKR#v` SHALL reserve versioned identities. Other `IBKR#<rest>` SHALL remain legacy. Accepted forms are:

- `IBKR#v2#<source-account>:TRADE:<tradeID>`
- `IBKR#v2#<source-account>:DIVIDEND:<actionID>`

The common grammar SHALL be `<BROKER>#v<N>#<source-account>:<KIND>:<source-id>`. `N` SHALL match `[1-9][0-9]*`; segments SHALL match `[A-Za-z0-9._-]+`. V2 SHALL map `TRADE` only to BUY/SELL and `DIVIDEND` only to DIVIDEND. Any other reserved identity SHALL return `invalid_identity` and stop before writes. Notifications SHALL omit identities. No v2 SHALL be written.

The reader SHALL globally index v2 by source account and comment, not Ghostfolio account. For mapping, dividend v2 SHALL be connector-owned and excluded from proximity and historical diagnostics.

Baseline: ADR 0002/tests prove legacy behavior; two reports repeat 49 conflict-free action IDs.

#### Scenario: Strict dual reader
- **WHEN** `.venv/bin/python -m pytest -q tests -k versioned_identity_reader` covers legacy, valid and invalid comments
- **THEN** legacy and v2 load; invalid reserved identities stop before writes with `invalid_identity`.

### Requirement: Dividend action coverage

The positive action set SHALL contain each distinct `(accountId, actionID)` with exact Decimal net above zero, exclude zero, and reject missing, conflicting, or negative evidence.

Legacy exact comments SHALL win. Otherwise, complete v2 coverage SHALL mark the group existing. Partial coverage SHALL reject it, fail its account, and prevent legacy import. No coverage SHALL retain current behavior. Trades, safe sales, cash and later accounts SHALL continue. Partial v2 coverage SHALL be the sole exception to the existing local-rejection outcome.

#### Scenario: Complete, partial and absent coverage
- **WHEN** the reader command covers complete, partial and absent multi-action sets plus zero-net and invalid actions
- **THEN** complete coverage skips, partial coverage fails only the account without import, absent coverage follows legacy selection, and invalid actions retain current rejection.

### Requirement: Exact short import acceptance

A valid 2xx response SHALL map each returned row to one submitted `(accountId, comment)` and verify financial fields. A shorter known set SHALL retain proven creations, warn with omitted comments and an instruction to inspect Ghostfolio before rerun, avoid retry, and fail the account. Sales SHALL use only accepted buys. Cash and later accounts SHALL continue. Unknown-outcome fencing and identifier-free notifications SHALL remain.

Baseline: the current short-count test is clean; the pinned lab returned HTTP 201 without creation for a duplicate.

#### Scenario: Proven short response
- **WHEN** `.venv/bin/python -m pytest -q tests -k short_import_acceptance` runs full, short and unknown responses
- **THEN** only full acceptance is clean; short acceptance preserves the exact returned subset without retry; unknown outcomes retain their write fence.

## MODIFIED Requirements

### Requirement: Enriched dividend input and local rejection

Processing SHALL extract cash identity without quantity checks, deduplicate by account/comment/proximity, then validate candidates. Existing activities remain untouched and unverified. A separate dry-run diagnostic SHALL not change selection.

ChangeInDividendAccruals SHALL be mandatory. Required attributes SHALL cover candidate payment/relevant accrual keys and `quantity/code/date/payDate/reportDate`. Nonempty key mismatches SHALL exclude unrelated accruals; missing keys SHALL NOT prove irrelevance. Unrelated rows SHALL NOT block candidates. Withholding SHALL retain cash grouping without accrual-schema requirements. Missing section/relevant attributes SHALL block account dividends; present-but-empty evidence SHALL reject affected groups. Empty sections without payments SHALL be valid.

Rejections SHALL log distinct reasons, never mark rejected payments imported, and leave trades/cash operating. Only partial v2 coverage SHALL fail the account; other local rejections SHALL NOT change success, exit, or notifications. Other failures SHALL retain current behavior.

#### Scenario: Compatibility and isolation
- **WHEN** `.venv/bin/python -m pytest -q tests -k dividend_structured_input` runs old, empty, short-window, unrelated, missing, conflicting and partial-v2 cases
- **THEN** identity→dedup→quantity order, scopes, logs, retries and isolation remain; only partial v2 changes the account outcome.
