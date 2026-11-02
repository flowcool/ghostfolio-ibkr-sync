# Activity correction review delta

## ADDED Requirements

### Requirement: Effective currency in activity update payloads

Every activity update payload SHALL carry the resolved effective currency as a
valid ISO4217 code. A null stored activity currency SHALL use the
proven currency from its current symbol profile. If the effective currency is
missing, empty, invalid or conflicting, the proposal SHALL stay held and the
connector SHALL send no PUT. Identity maintenance apply, inspection and rollback
SHALL compare proven effective currencies at readback. All other preserved
fields SHALL stay exact. Journal fingerprints SHALL still bind raw evidence.

#### Scenario: Legacy comment migration

- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k legacy_comment_migration_null` runs with a null activity currency and a USD profile
- **THEN** the comment-only PUT carries `currency: USD`, Ghostfolio readback
  accepts the update, and the next run creates no proposal for that event.

#### Scenario: Unresolved currency

- **WHEN** a selected correction or pending journal cannot resolve one valid
  effective currency
- **THEN** the proposal or journal remains held with a reason and no PUT is
  sent.

### Requirement: Effective currency in pending correction recovery

Journal recovery SHALL validate the effective currency of the expected-after
evidence before confirming a pending intent. A legacy pending request with a
null currency MAY be read for exact already-applied readback when the expected
after evidence resolves to one valid currency. It SHALL never be resent. A
stale, conflicting or unresolved currency SHALL retain the account hold.

#### Scenario: Pending null-currency request

- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k pending_null_currency_journal` runs with a v3 pending request with `currency: null`
- **THEN** recovery sends no PUT; it confirms only an exact effective-currency
  readback, otherwise it keeps the journal pending and the proposal held.

#### Scenario: Identity maintenance readback

- **WHEN** a comment-only maintenance PUT sends `USD` and Ghostfolio returns
  a null activity currency with the same proven USD profile
- **THEN** apply and rollback accept the equivalent currency representation,
  reject every other field drift, and keep raw journal fingerprints unchanged.
