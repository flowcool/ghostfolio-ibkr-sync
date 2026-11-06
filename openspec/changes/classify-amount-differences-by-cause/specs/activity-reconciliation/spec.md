## ADDED Requirements

### Requirement: Ordered amount causes and correction authority

Broker-independent reconciliation SHALL evaluate ordered cause functions. Each
function SHALL accept a finding and return `(label, reason, action)` or `None`.
The action SHALL be `correct` or `information`. The first match SHALL win.
No match SHALL leave the existing correction path available. If that path proves
an exact replacement, it SHALL use `correct` with label `source-proven correction`.
A named cause SHALL NOT be an additional eligibility or authority gate.
`to_check` without a write SHALL apply when the source cannot prove the exact
replacement, including incomplete source, non-unique association or partial proof.
Existing profile bounds, manual consent, rejection and journal fences still apply.
An unsupported currency, incomplete evidence or conflicting association SHALL
not match a named cause. Identity and deduplication SHALL retain exact comparisons.
An amount allowance SHALL NOT establish either identity or source completeness.

The fixed order SHALL be declared-rate rounding, printed-gross rounding,
corroborated execution views, then the candidate omitted-withholding cause.
The last cause SHALL remain disabled until its real-data gate passes.
A broker-specific cause SHALL reject findings from another broker.
An informational cause SHALL cover only its proven fields. An independent fee,
quantity or other difference SHALL retain its independent source-proof and
correction checks. The first match SHALL NOT suppress or block it.

The registry SHALL express monetary differences as absolute ISO 4217 minor
units, including fractional minor units. It SHALL NOT use a percentage cause
threshold. Current correction profiles retain their separate absolute and
relative safety limits. Passing those limits SHALL NOT prove a cause.

`correct` SHALL request the existing one-to-one correction path. It SHALL NOT
execute HTTP or create another write path. Automatic correction SHALL require
an active profile, a persistent review file, a fresh complete uncached broker
source, a complete destination listing, exact replacement values and a mutually
unique association under the existing profile. Quantity SHALL have no tolerance.
BUY/SELL quantity SHALL stay exact. DIVIDEND quantity SHALL change only with
exact validated source quantity evidence. Old rate-derived quantity estimates
SHALL NOT qualify.

`information` SHALL request no correction. It SHALL apply only where the source
view does not prove a more exact authoritative replacement for that finding.
A proven exact source replacement SHALL remain correctable without proof of a
specific entry mistake. Small size alone SHALL NOT make it information.
All three information causes SHALL retain their existing predicates. They SHALL
prevent correction only for their proven fields where the source is not more exact.

Baseline: `classify_dividend_findings` proves one declared-rate cause.
`numeric_evidence` proves converter residue separately. Existing profiles and
`process_review` supply association, authority and the only correction writer.

#### Scenario: Ordering, field scope and source-proof fallback

- **WHEN** `python -m pytest -q tests/test_amount_differences.py -k registry` runs overlapping causes, cross-broker findings, unsupported currencies, missing evidence, fee side differences and unknown sub-unit gaps
- **THEN** the first fully qualified cause explains its fields; independent source-proven replacements keep existing correction eligibility; missing exact replacement proof yields to_check without a write; classification never sends a request.

#### Scenario: Existing authority without a named cause

- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k amount_cause_authority` runs exact source replacements without named causes under all profiles and manual yes, both gross caps, ambiguous matches, partial coverage, cached sources and source-proven dividend quantities
- **THEN** profiles and manual yes retain their existing eligible corrections; off retains manual review; missing exact replacement proof remains to_check; unsupported quantity changes and information-only fields produce no financial request.

### Requirement: Evidence-bound cause catalogue

Every registered cause SHALL define its exact predicates, real-data evidence,
action, authority and financial risk. New causes SHALL require reproducible
real broker evidence. A repeated capture SHALL NOT count as another event.
The following catalogue SHALL bound this change.

| Cause | Predicates and action | Real-data evidence | CFO risk and detection |
| --- | --- | --- | --- |
| IBKR declared-rate rounding | One complete single representation; exact equal quantity and fee; stored gross equals quantity times the uniquely matched payment Re grossRate; paid cash differs by exactly one minor unit. `information`; no correction authority. | Six JPY cases recorded in [PR 200](https://github.com/flowcool/ghostfolio-ibkr-sync/pull/200) and the archived coherent-dividend-report delta. | Can hide a real error with the same numeric shape. Reject missing/multiple action evidence, mismatched quantity/fee or conflicting identity; retain both cash and rate evidence visibly. |
| BD printed-gross cent rounding | EUR BUY/SELL source comparison only; exact quantity times COURS rounded HALF_UP to a cent equals printed BRUT; commission, VAT and signed net corroborate independently. Difference is nonzero and at most half a minor unit. `information`; no correction authority. | Six of 74 original trades: five BUY and one SELL, including a half-cent tie; original-text hashes and native replay agree. [Pinned parser](https://github.com/flowcool/ghostfolio-boursedirect-sync/blob/e49001c7d8181925dbab8275c001f939e47bbb97/ghostfolio_boursedirect_sync/notices.py). | Can hide a wrong price that happens to round to the same gross. Preserve original price and exact product; verify net independently. Never excuse a differing stored activity, fee or quantity with this source-only predicate. |
| DEGIRO corroborated execution views | Source API/CSV/execution comparison only; unique exact non-amount metadata, STOCK with contract size 1, supported cent currency, signed execution quantity times price corroborates all views; cent-valued cash views span no more than one minor unit and each stays within one minor unit of signed exact gross. `information`; no correction authority. | One SELL event in three retained captures; API/CSV gap is one minor unit; each view is half a unit from the exact execution total. [Pinned predicate](https://github.com/flowcool/ghostfolio-degiro-sync/blob/d404ee766cc3a7e1531d64fedc1dca280e51d353/ghostfolio_degiro_sync/sync.py). | Can hide a wrong execution or broker policy assumption. Keep complete row multiplicities, value date, order, sign, currency and independent execution proof. Do not claim universal HALF_EVEN/HALF_UP policy or FX tolerance. Never excuse a destination fee discrepancy. |
| Candidate omitted withholding | A fresh complete source proves the omission independently of gap size: stored fee is zero; validated cash withholding is positive; exact gross and quantity agree; complete action association excludes components, refunds and repeated representations. `correct`. | Operator-confirmed manual history and seven omission-shaped observations in two IBKR review generations. Six have equal gross/quantity but partial action coverage; one older target is unavailable. These saved cases are candidates, not qualified corrections. | Can hide a different payment, a tax refund or incomplete allocation. Require full uncached action evidence, unique matching, existing withholding validation and exact fee replacement. Current partial-coverage/missing-target cases SHALL fail. Manual provenance alone SHALL NOT prove an omission. |

The omitted-withholding row is a candidate named cause, not a prerequisite for
existing source-proven corrections. It SHALL NOT be
registered for automatic dispatch until at least one complete real-data omission
and its exact one-to-one source proof are retained. Its seven current observations
do not meet that gate. Until then the registry SHALL retain the three proven
information causes without enabling an unproved named omission cause. Existing
source-proven corrections SHALL remain available under profiles and manual yes,
with the generic label when no cause matches. Neither synthetic evidence nor
profile selection SHALL certify the named cause or remove its evidence gate.

For existing `correct` routing, conservative authority SHALL require a recognized
unique reference and its existing same-day/zero-gross rules. Balanced and
permissive authority SHALL use their existing mutually unique match rules,
date bounds and both gross caps. Fees SHALL NOT rank or identify candidates.
After qualified association, validated source fees SHALL retain their existing
no-fee-threshold treatment. `off` SHALL provide no automatic authority.
A manual `yes` SHALL use the same qualified update and exact source/association
proof. An unknown cause SHALL NOT prevent manual yes when the exact replacement
is source-proven. Manual yes SHALL NOT override incomplete source, ambiguous
association or an unresolved journal. Amount, fee, date, currency and comment
corrections SHALL retain the existing manual review contract.

The retained IBKR inventory contains 86 unexplained monetary observations.
Exact replacement proof and named-cause proof SHALL be assessed separately.

| Source-proof class at capture | Observations | Existing route |
| --- | --- | --- |
| Exact replacements proved from retained source and qualified association | 5 | Four profile-eligible observations and one manual-review observation; no named cause required. |
| Exact one-to-one replacement not proved | 81 | 18 partial-action-coverage observations, 12 rejected-association observations, 3 unavailable-target observations and 48 historical comparisons with inferred quantity or incomplete association proof. Keep to_check while those limits persist. |

These are capture observations, not unique events or present write authority.
The five source-proven cases retain their original profile limits or manual yes
requirement. A future run SHALL refresh source, target and authority normally.
The older GBP comparison has cent-display agreement, but its alleged rounding
mechanism was not reproduced. That missing explanation SHALL NOT block an
otherwise source-proven replacement; inferred quantity alone is insufficient.
BD coupon/representation and DEGIRO historical fee/FX diagnostics SHALL use the
same distinction. No generic FX or converter-residue cause was proved by this
inventory. Existing independently reproduced converter residue and profile
threshold behavior SHALL remain unchanged.

Evidence scope: 123 monetary candidate observations and 92 hashed files across
the retained three-connector corpus. Eight historical equation deltas remain
separate because their currency/context is not established. Repeated snapshots
and crossed candidates are observations, not event frequencies. Historical
completeness is not certified. Private evidence retains exact differences,
source paths and hashes; public artifacts SHALL exclude financial activity
values and identifiers. Synthetic or derived lab mutations SHALL NOT prove a
real-data cause.

#### Scenario: Proven source views and false acceptances

- **WHEN** `python -m pytest -q tests/test_amount_differences.py -k cause_catalogue` runs sanitized positive and negative cases for every catalogue predicate, source-only boundaries and mixed gross/fee differences
- **THEN** only the complete proven shapes return information; changing an independent predicate rejects the cause; no informational cause enables a destination update.

#### Scenario: Manual entry evidence is not an assumption

- **WHEN** `python -m pytest -q tests/test_amount_differences.py -k manual_entry` runs omitted withholding with complete and partial actions, missing targets, signed refunds, multiple candidates, inconsistent gross/quantity and manually entered but unexplained fees
- **THEN** only an independently proven complete omission can match the named cause after its real-data gate passes; retained omission-shaped cases remain to_check while their blockers persist; the disabled cause never blocks a separately qualified existing correction.

### Requirement: Existing corrections remain unchanged

For existing cases, the set of corrections produced with the registry SHALL be
identical to the set produced by the current profile and manual yes paths.
This SHALL cover amount, fee, date, currency and comment corrections, including
source-proven cases without a named cause. Eligibility, exact payloads, consent,
rejections, queue order and recovery SHALL remain unchanged. Registry absence,
no cause match, or a disabled candidate cause SHALL NOT remove an eligible
correction or add authority. Profile limits SHALL NOT be widened.
An information cause SHALL NOT block an independently proven correction field.

Baseline: the current activity-reconciliation and activity-correction-review
specifications, automatic_pairs, refresh_proposals and process_review.

#### Scenario: Profile and manual correction sets remain identical

- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py tests/test_activity_review.py -k amount_cause_non_regression` replays existing cases with and without registry explanations for off/conservative/balanced/permissive and manual yes, including amount, fee, date, currency, comment, no named cause, disabled omitted-withholding cause, mixed information/correction fields and pending recovery
- **THEN** both runs produce identical eligible correction sets, exact request payloads, retained consent, refusals, queue order and recovery results; only explanations and labels can differ.

### Requirement: Cause-bound reviewed execution and downstream adoption

Optional cause evidence SHALL refer to the existing source/target proof.
A missing cause or a label-only change SHALL NOT revoke existing consent or
eligibility. Source, target, profile or timezone changes SHALL retain the existing
invalidation rules before dispatch. Existing pending journals SHALL
remain recoverable. No new cause field SHALL permit resend or silently clear
uncertainty. Preserve activity ID, account, owner, tags, notes and unrelated
fields. Preserve qualification, durable before/after intent, exact financial
readback, the existing correction delay and the failure fence on later writes.
Sync SHALL never delete an activity or combine multiple source events into a
single update. Simulation SHALL write no financial data and consume no consent.
Missing replacement proof and profile deferral SHALL remain distinct from failed requests.

DEGIRO propagation SHALL be a routed recommendation under ADR 0007. Its owner
must adapt the pinned projection for the package layout, review dependencies,
regenerate provenance and prove adapter compatibility separately. Bourse Direct
adoption SHALL be routed to its importer owner against the delivered IBKR/BD
reconciliation contract. This repository SHALL change neither sibling pin nor
runtime. Their source-view rules SHALL NOT become IBKR event causes.

#### Scenario: Exact readback and uncertainty remain authoritative

- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k amount_cause_execution` runs correction confirmation, changed evidence, profile changes, dry-run, old pending journals, failed and interrupted readback, restart and unrelated-account preservation with mocked HTTP
- **THEN** only the existing writer sends a qualified request; confirmed exact readback controls success; uncertain requests fence later writes and are never resent; preserved fields and simulation authority remain exact.

#### Scenario: Sibling boundaries remain explicit

- **WHEN** `git diff --name-only origin/main...HEAD` is inspected for the approved implementation
- **THEN** only this repository changes, the PR names ADR 0007 propagation and the BD recommendation, and no sibling pin or generated projection is silently updated.
