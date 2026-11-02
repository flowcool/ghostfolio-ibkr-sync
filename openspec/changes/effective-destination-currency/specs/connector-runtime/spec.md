## ADDED Requirements

### Requirement: Proven effective destination currency

For each destination activity, the connector SHALL distinguish the stored
nullable currency from the effective denomination of its unit price and fee.
It SHALL use the explicit, valid activity currency first. Only an explicitly
present null SHALL permit fallback to a valid currency from the proven security
profile of that activity. A missing field, blank string, invalid value or unknown
code SHALL remain uncertain. It SHALL NOT fall back to the source currency,
account base currency, symbol suffix, mapping guess or converted valuation field.

The current `assetProfile` SHALL take precedence over legacy `SymbolProfile`.
An invalid current profile SHALL NOT be hidden by a valid legacy profile.
Fallback proof SHALL bind the profile to the same activity/security in complete,
unredacted destination evidence, or in the exact created-row import response.
Historical proof SHALL retain its capture/version/hash binding. A profile from
another row or a stale unbound lookup SHALL NOT establish that denomination.
Unsupported or unavailable proof SHALL prevent automatic action on that row.
Existing redaction, active-profile and ownership requirements SHALL still apply.

The connector SHALL retain the raw field, profile currency, resolved currency,
provenance and uncertainty reason in private evidence. It SHALL NOT overwrite
the raw activity to make comparisons pass. An explicit KRW activity on a USD
profile SHALL remain KRW. An explicit currency/profile difference alone SHALL
NOT invalidate a legitimate override. Profile identity and unexpected profile
changes SHALL retain their existing preservation checks.

This rule SHALL apply to review comparison, reconciliation, accepted import
subsets, positive write readback, historical identity comparison, recovery
acceptance and historical dividend diagnostics. It SHALL NOT change the cash
base-currency guard or source conversion. The financial automatic allowlist
SHALL remain JPY, GBP, GBp, USD, EUR and CAD. Resolving KRW or SEK SHALL permit
comparison and conformity reporting without adding financial write authority.

Baseline: the existing Historical dividend comparison requirement already gives
explicit activity currency precedence and null-only fallback. The retained
2026-11-02 proof confirms the same representation on Ghostfolio 3.96.0.
Existing tests include `test_current_profile_takes_precedence_over_legacy`
and the `coherent_dividend_currency` cases. New commands below are future gates.

#### Scenario: Explicit override and proven null fallback
- **WHEN** `python -m pytest -q tests/test_ghostfolio.py tests/test_dividend_diagnostics.py -k effective_currency_resolution` covers explicit KRW on a USD profile, null/KRW, null/JPY, null/GBp, null/SEK, legacy-only profiles, both profile keys and absent or malformed evidence
- **THEN** explicit values win, only proven null fallback resolves, raw inputs stay unchanged and every unresolved case remains non-actionable.

#### Scenario: Exact denomination and scaling
- **WHEN** `python -m pytest -q tests/test_conversion.py tests/test_activity_reconciliation.py -k effective_currency_scaling` covers GBP/GBp, explicit overrides and inferred ZAc/ILA markets
- **THEN** GBP and GBp stay distinct denominations, common-unit calculations use exactly 100 GBp per GBP, price and fee scale together, no foreign exchange is used and inferred markets gain no new automatic authority.

### Requirement: Exact acceptance with nullable currency evidence

An accepted import SHALL prove the submitted identity, destination account,
active created ID, data source, UTC instant, type, quantity, unit price and fee
under the existing exact acceptance rules. Its effective currency SHALL equal
the submitted currency code exactly. Null plus the proven same profile currency
SHALL satisfy this currency check. A short response SHALL prove only its valid
accepted subset. No missing currency proof, duplicate identity or HTTP success
alone SHALL establish acceptance or authorize a later sale. An uncertain import
SHALL retain its account fence and SHALL NOT trigger an automatic resend.

Exact positive readback SHALL compare effective currency codes, without monetary
tolerance or display rounding. It SHALL NOT accept GBP in place of requested GBp,
even when scaled totals agree. All numeric values, instants, comments, notes,
ownership, tags, profile identity and other preserved fields SHALL retain their
exact checks. Raw request, raw response and profile context SHALL remain evidence.
Historical identity preview SHALL use effective currency while retaining its
stricter exact quantity, gross, fee, date, coverage and selection-replay rules.
Recovery SHALL use the same denomination rule without relaxing its independent
identity, settlement or existing-row preservation checks.

Baseline: `accepted_import_subset` currently compares raw currency. The
2026-11-02 import and reviewed PUT both return null/KRW. This is a connector
comparison defect, not an upstream write failure. No database repair is needed.

#### Scenario: Accepted subsets and subsequent holdings
- **WHEN** `python -m pytest -q tests/test_ghostfolio.py tests/test_orchestration.py -k effective_currency_acceptance` covers full/partial null-profile responses, explicit overrides, unknown proof, wrong accounts, drift, duplicate IDs and a subsequent sale
- **THEN** only exact proven created rows enter accepted state; uncertainty sends no repeat POST and cannot back a sale; all existing financial comparisons remain exact.

#### Scenario: Historical preview and recovery remain exact
- **WHEN** `python -m pytest -q tests/test_identity_migration.py tests/test_identity_recovery.py -k effective_currency` covers null-profile equality, explicit overrides, invalid current profiles, quantity/fee/date differences, occupied identities and selection replay
- **THEN** currency representation alone ceases to reject exact rows, every other migration/recovery guard remains effective, input hashes stay unchanged and no network call occurs in offline preview.

### Requirement: Numbered effective currency qualification gates

Implementation SHALL pass the following gates. Proposal validation SHALL NOT
be reported as runtime acceptance. Retained evidence SHALL bind the exact code,
inputs, comparison policy, connector digest and destination image/version.

1. **G1 — Offline behavior.** Run the scenario commands in all three deltas,
   then `bash scripts/check.sh`. Use synthetic data, denied sockets and mocked
   HTTP. Require explicit/null/missing/invalid/profile-drift cases, all supported
   denominations, exact GBP/GBp scaling, readback failures and old pending journals.
   Numeric tolerances SHALL NOT enter acceptance or preserved-field checks.
2. **G2 — Saved review simulation.** Run
   `python -m pytest -q -s tests/test_activity_reconciliation.py -k effective_currency_replay`
   with `EFFECTIVE_CURRENCY_REPLAY_INPUT` naming the read-only private `r.yaml`.
   Require SHA-256
   `13e3e0ecb71deeeca48b251c66262d703442e66b8ea2fdee1e495794be82f314`.
   Retain input hashes before and after. Deny sockets, credentials and writes to
   source evidence. Use private output and simulation only. Report the counts
   and evidence limits in the reconciliation delta. A missing input SHALL fail
   this explicit gate. A schema-3 view alone SHALL NOT be treated as its private
   state or as a complete runtime source/target snapshot.
3. **G3 — Empty and golden labs.** Publish one immutable candidate image before
   qualification. Reserve each instance through the Infra lab runbook. Run the
   installed candidate in both empty first-install and golden upgrade scenarios
   with the same connector digest. Record each actual Ghostfolio digest/version.
   Use the versioned `lab.py` runner and separate lab credentials. Preserve all
   existing stored rows and native cash. Qualify null-profile imports, review
   conformity, comment-only migration, explicit overrides, GBP/GBp corrections,
   unknown-profile refusal and restart recovery. Observe background effects.
   Keep one PUT per process. Stop dependent work on uncertainty; never resend.
   Finish with `down` and `verify-stopped` for both owned instances. Retain proof,
   stopped containers and logs. Missing scenario support in the runner blocks
   this gate and requires an Infra-owned prerequisite, not an improvised bypass.
4. **G4 — Exact readback and repeat.** In each lab, bind the submitted request,
   import response, post-PUT GET, raw nullable currency and profile evidence to
   exact financial and preserved-field checks. HTTP success is insufficient.
   Reopen review and journal in fresh processes. Require no repeat correction
   or import after confirmation. Inject unavailable, before-only and changed
   profile readback; require a retained unresolved intent and no resend. Promote
   only the digest that passed both labs, without rebuilding it. Failed or
   incomplete evidence requires a new qualified candidate.

For G3, the existing command is
`python3 ghostfolio/scripts/lab.py qualification-profiles --qualification-image "$QUALIFICATION_IMAGE" --product-checkout "$PRODUCT_CHECKOUT" --product-python "$PRODUCT_PYTHON" --operation-ref "$OPERATION_REF" --output "$LAB_PROOF"`.
Run it from each reserved lab directory, under that runbook's prerequisites.
Currency-specific scenario coverage SHALL be verified before using its result.
This proposal does not execute these future lab or publication steps.

#### Scenario: Qualification of the installed candidate
- **WHEN** the G3 `python3 ghostfolio/scripts/lab.py qualification-profiles` command above runs with the same immutable connector image in each reserved lab and the required currency scenarios are supported
- **THEN** its evidence proves the installed candidate's exact readback, preservation, background completion and restart behavior in both scenarios; a missing or failed case keeps G3/G4 incomplete and cannot qualify enablement or stable promotion.

**Retained evidence references**

Private locations are recorded in the owning work items. These files are
read-only evidence, not repository fixtures or new production observations.

| File | SHA-256 | Proven scope |
| --- | --- | --- |
| `result.json` | `d731f8f350df9d286d6fd741bfb4a54a1b1dab29efcaf5fca9ee0a95c650a92a` | Pinned source and lab investigation summary |
| `gate2-result.json` | `b5ec8d5a4f7804947ab39e61f83416d9426bba0714760edfc0384d49896635a0` | One KRW import, one reviewed PUT, null/KRW GET, preservation |
| `database-currency.json` | `f2d105b9e28a50ecd7a0f429c244eb8e2e213be9843f00dfbe4f339c5bdf7602` | Stored Order NULL and profile KRW |
| `offline-results.json` | `1e56276d265220fa679b88d23f2aa6e42961cc21022383234e66563b59bb5962` | 22 synthetic legacy and diagnostic controls |
| `input-summary.json` | `fbdae1b9a81fe51149c2a57bcb444be4f60dd4b4578233176e888718701bed9c` | Original review counts and input hashes |

The source proof identifies Ghostfolio 3.96.0 at upstream commit
`2f21c2558684e8cc9974f1b2da683992a83ef3cb` and observed destination digest
`sha256:97b9dd2e8b07610bfa383480b911065f7497070f53c302c037ab8a1b596ccae5`.
This evidence SHALL NOT replace G3/G4 for the future connector candidate.
