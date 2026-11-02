# Design

## Context

See proposal.md for scope. The connector-runtime delta binds the existing lab
proof files and future gates. The reconciliation delta records replay arithmetic
and the conflicts in the requested residual counts.

## Goals / Non-Goals

**Goal:** one currency rule at every comparison and positive acceptance boundary.
**Non-goals:** database repair, quantity-policy changes, new financial limits.

## Decisions

Reuse `_existing_dividend_amounts` and
`diagnostics._historical_destination_currency` as the observed fallback model.
Extract one pure resolver in `ghostfolio.py`. Return raw value, effective code,
profile provenance and refusal reason. Preserve current-profile precedence.
Do not globally replace raw currency in snapshots: that destroys evidence.

Use it in `changed_fields`, `candidate_reason`, `automatic_pairs`,
`numeric_evidence` and `group_diagnosis`. Keep `values_of` raw.
`refresh_proposals` removes a currency-only proposal only after conformity proof.
Keep `minor_unit_conversion` for source payloads and `denomination` for exact
GBP/GBp gross normalization. Do not use normalized gross for payload readback.

Use resolved currency in `accepted_import_subset`,
`identity_migration.exact_differences` and `identity_recovery.accepted_payload`.
Do not require profile currency to equal a legitimate explicit override.
Preserve exact historical migration rules and account-scoped acceptance.

Reuse `update_payload`, `expected_row`, `row_matches`, `recovery_read` and
`preserved_equal`. Add currency-specific business equality without changing
raw hashes or broadening ignored fields. Require unchanged profile context.
Persist actual raw readback as well as expected/request evidence.

## Risks / Trade-offs

- Stale profile evidence → bind it to the row and revalidate before dispatch.
- Generic diagnosis hides causes → distinguish currency, source, amount and identity failures.
- Compact replay lacks private evidence → separate observed counts from synthetic eligibility.
- Existing pending intents → retain their original contract and account fence.

## Migration Plan

Use a minor release for journal version 3. No SQL or historical data migration. Refresh derived
review evidence through existing atomic generations; clear changed consent.
G1–G4 must pass before financial enablement. Flag DEGIRO propagation under ADR 0007.

Rollback: stop writers, preserve review/state/journals, force simulation and
restore the qualified previous image. An unresolved new-policy journal requires
a compatible reader. Reverting code does not reverse financial writes.

## Approved compatibility decision

Record the new comparison contract in the existing v2 journal policy and evidence
maps only if G1 proves that the real code at tag `v4.0.0` fails closed on a pending
new-policy journal. A mocked rollback reader is insufficient. Preserve legacy
v1/v2 semantics. If fail-closed behavior cannot be proved, use a new explicit
journal version and classify the release as minor. No operator pass is required.

G2 stays synthetic and conditional. The saved review state has no profile-currency
evidence. Real-data eligibility requires G5 production observation.

G1 observed the real `v4.0.0` reader accepting an unknown policy in a v2
pending journal. It rejects journal version 3 before recovery. Use version 3 for
new intents. Preserve existing v1/v2 entries and their exact raw comparison.
The new reader can load mixed legacy and new entries in a version 3 journal.
