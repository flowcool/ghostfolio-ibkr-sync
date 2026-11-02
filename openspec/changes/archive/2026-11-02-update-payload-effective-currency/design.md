# Design

`update_payload` remains the single runtime review payload builder. It resolves
the proposed row with `effective_currency` and refuses an unresolved result.
This preserves raw snapshot evidence while ensuring the wire body satisfies
Ghostfolio's `UpdateOrderDto`.

The standalone identity migration uses the same resolver before its comment PUT
and rollback PUT. Journal entries stay immutable. Recovery accepts a legacy
null request only for read-only confirmation when the after evidence resolves
to one valid currency; otherwise it retains the pending entry and account
hold. It never sends a second PUT.

The synthetic review server validates the DTO boundary and stores the normal
Ghostfolio nullable representation when a payload currency equals the profile
currency. Tests cover comment-only migration, fee correction, identity
migration and a pending null-currency journal.

Cleanup comment PUTs keep the complete explicit-identity gate. They also validate
the currency code before HTTP. This does not enable cleanup of null-currency rows.
Their resume path calls the same builders. Recovery imports build new payloads
from broker source values, not stored rows. Accepted-import comparison already
uses effective currency. Cash PUTs use account currency, not order currency.

Journal fingerprints bind exact raw evidence to detect edits. Readback compares
effective currency under the v3 currency policy. Legacy v1/v2 policies stay exact.
Rollback: revert this code change. Keep pending journals intact. The previous
reader still accepts v3; do not use it to dispatch the affected comment migration.

## Payload audit

- `activity_review.update_payload`: manual, profile, financial, legacy reference,
  historical review staging and offline reverse all share this builder. Resolve
  proposed effective currency; preserve raw `values_of` evidence.
- `ghostfolio.ghost_update_reviewed_activity`: validate the wire code before HTTP.
- `activity_review.recovery_read`: read only. A pending v3 NULL request can confirm
  an exact effective after-image; unresolved evidence stays pending. Never resend.
- `identity_migration.comment_payload`: forward maintenance and approved rollback
  share the resolver. Its journal binds the raw preimage and effective request.
  Maintenance readback compares proven effective currency and keeps all other
  preserved-field checks exact. Raw journal fingerprints stay unchanged.
- `cleanup_dividends.put_comment` and `cleanup_duplicates.put_comment`: validate
  explicit currency. Existing null/empty identity refusal remains. Cleanup resume
  calls these same builders; it does not replay an unchecked payload.
- `sync` trade/dividend create conversion: currency comes from source IBKR values.
  No create payload copies a stored order's nullable currency.
- `identity_recovery`: missing-action creates come from current source conversion.
  Stored and accepted rows use `effective_currency` for exact comparison only.
- `ghostfolio.accepted_import_subset`: compares effective returned currency with
  the submitted source code. No stored order becomes a create payload here.
- `ghostfolio.ghost_update_cash_balance`: account currency belongs to a separate
  account PUT. It does not use nullable order currency.

## Acceptance

Run `bash scripts/check.sh` for Ruff, strict mypy and all offline tests. Regression
cases cover comment migration and its quiet second run, fee correction, identity
apply/rollback, v3 NULL-request recovery, DTO rejection and cleanup refusal.
Run `openspec validate update-payload-effective-currency --strict` before archive.
The release owner qualifies a new immutable candidate in both labs separately.
