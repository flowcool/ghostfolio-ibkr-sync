# Proposal

## Why

Ghostfolio 3.96.0 requires a valid `currency` in every activity update. It
stores a redundant activity currency as `null` when it equals the symbol
profile currency. Comment migrations and identity maintenance can therefore
build an invalid PUT from a stored row.

## What changes

- Every activity update payload sends the resolved effective ISO4217 currency.
- A null activity value uses only the proven profile currency of that row.
- An unresolved or conflicting currency holds the proposal and sends no PUT.
- Journal recovery validates the effective currency before it confirms a
  pending intent. It never resends a null or stale currency.
- Offline Ghostfolio PUT doubles enforce the required valid currency rule.

## Scope

The change covers normal review corrections, comment-only and fee/identity
migrations, and the review journal recovery/readback path. Cleanup PUTs validate
the currency code and keep their existing null-row refusal. Imports, cash
updates and historical data conversion keep their existing
authorization boundaries.

## Modified capabilities

- `activity-correction-review`: effective currency is mandatory in every PUT
  payload and journal recovery is fail-closed.
- `connector-runtime`: update payloads never carry a null or empty currency.

## Non-goals

No stored activity is rewritten outside an approved correction. No release,
lab run, production write or tag is part of this change.
