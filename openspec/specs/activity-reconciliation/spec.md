# activity-reconciliation Specification

## Purpose

Let operators select bounded automatic reconciliation rules while retaining exact source evidence, visible decisions and verified one-to-one writes.

## Requirements

### Requirement: Explicit reconciliation profiles

`ACTIVITY_RECONCILIATION` SHALL accept only `off`, `conservative`, `balanced` and `permissive`. Unset or blank SHALL mean `off`. Invalid values SHALL fail configuration before financial writes. A non-off profile SHALL require a valid persistent `ACTIVITY_REVIEW_FILE`. Missing or invalid `TZ` SHALL retain the existing whole-run simulation rule and SHALL NOT permit automatic financial writes.

`off` SHALL disable profile-authorized writes, not manual review, durable rejection, conformity reporting or pending-request recovery. The profile SHALL be permission for the bounded transformations below, not a confidence claim. Do not write `yes` on the operator's behalf. Journal automatic authority separately from manual consent. New candidates SHALL be eligible in the same run only under a freshly evaluated active profile, except invalidated-rejection and rebuilt-state cooldowns under activity-correction-review. Profile or TZ changes SHALL invalidate cached automatic eligibility before dispatch. Manual consent remains valid when its displayed operation, execution path and actionability are unchanged. An unresolved request SHALL remain unresolved after any profile change or disablement.

#### Scenario: Profile configuration and authority
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k profile_config` tests all values, missing review paths, invalid timezones, manual mode, new candidates and profile changes
- **THEN** only valid opt-in profiles permit automatic corrections; simulation and unresolved-request fences remain effective; automatic authority never appears as user approval.

### Requirement: Mapping-owned historical identity

The configured IBKR-to-Ghostfolio account mapping SHALL establish historical account ownership. A unique whole-comment legacy trade marker SHALL be replaceable when its tradeID occurs in the current validated report of the mapped source account and its activity belongs to the mapped destination. The connector SHALL NOT require historical cross-account coverage or proof of lifetime tradeID uniqueness. It SHALL refuse observed conflicting ownership, duplicate targets, conflicting source events, malformed references and occupied v2 identities. No inferred account mapping SHALL be added.

Legacy migration SHALL be a separate comment-only operation. Preserve the current date, security, type, currency, quantity, price, fee, owner, tags and notes exactly. A remaining difference SHALL produce a separate correction after migration is confirmed. Even when that difference requires manual review, it SHALL NOT prevent an independently safe comment-only migration. Do not combine this operation with a financial correction to avoid its limits. Preserve supported canonical notes; unsupported legacy notes SHALL remain refused under the existing comment grammar.

All non-off profiles SHALL permit eligible migration. `off` SHALL require literal manual approval for the same eligible proposal. Rebuild normal selection after a confirmed migration. Another source account's formerly globally suppressed trade SHALL become eligible only through ordinary account-scoped import checks. This consequence SHALL be documented. A current collision means competing source claims to the same legacy destination row, an occupied v2 identity or a target outside the mapped destination. Equal source IDs mapped to different destinations are independent and SHALL NOT alone constitute a collision. A detected current collision SHALL stop migration; absence of historical coverage alone SHALL NOT stop it. Offline historical maintenance SHALL retain its separate saved-evidence contract and operation authority.

#### Scenario: Comment-only migration and selection
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k legacy_migration` covers pure reference changes, remaining date/fee/quantity differences, manual mode, duplicates, moved ownership, failed relevant reports and a same-ID trades mapped to the same destination and to independent destinations
- **THEN** eligible migration preserves every non-comment value; a remaining correction is re-evaluated; detected ambiguity refuses migration; valid mappings need no historical proof; subsequent imports still pass their ordinary guards.

### Requirement: Unique matching and business dates

Every automatic association SHALL have the same mapped destination account, operation type, resolved security and compatible denomination. A conflicting nonempty ISIN SHALL exclude a candidate. Active YAHOO profiles and existing source validity checks SHALL remain required. A recognized v2 reference to another event SHALL exclude proximity matching. Resolve the security through the existing explicit mapping and supported aliases; a guessed symbol change SHALL NOT establish identity.

The conservative profile SHALL require a recognized unique source reference. Balanced and permissive profiles SHALL also accept unreferenced activities and ambiguous legacy dividend aliases when the complete current candidate set resolves to unique pairs. Fees SHALL NOT exclude, rank or disambiguate candidates. There SHALL be exactly one eligible target per source and one eligible source per target after all profile criteria and valid pair rejections. Never greedily select a candidate by row order, nearest time or smallest amount difference. An exact reference SHALL take precedence over proximity; a conflicting exact candidate SHALL NOT be ignored to obtain a proximity match. Threshold matches SHALL remain labelled `profile match`, not `exact identity`.

Compare dates from the canonical activity value in configured `TZ`, which must equal the Ghostfolio server timezone. Trades use their execution instant. Cash dividends use the written payment calendar day at 00:00 UTC, without converting the posting clock. The same local calendar day SHALL be date-compatible even when intraday instants differ. It SHALL produce no date proposal and SHALL remain eligible for comment-only migration when all other checks pass. Preserve its stored instant. A different local day SHALL be a real date difference and require the existing reviewed correction path. Conservative and balanced corrections SHALL retain the same local calendar day. Permissive corrections SHALL allow inclusive distance of two calendar days for BUY/SELL and three for DIVIDEND. Include weekends; do not infer exchange holidays. Use execution conversion for trades and corporate actions. Use the written calendar day for cash payments and accruals. Stored values and canonical replacement dates do not depend on `TZ`. Keep raw source text, UTC instants, local dates, source zone, configured timezone and actual elapsed difference visible. Missing, unknown or unsupported source timezone evidence SHALL refuse automatic date correction. A corrected date SHALL not change the event-only `IBKR#v2` comment; it SHALL change candidate and migration evidence when the date is part of the matching proof.

#### Scenario: Unique candidates and date boundaries
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k unique_matching` covers EST/EDT, Tokyo, London and New York midnight, DST, inclusive local-date edges, exact references and mapped aliases
- **THEN** only mutually unique supported pairs pass; ambiguity stays visible; profile matches are not labelled exact; corrected UTC instants and configured local days control selection.

#### Scenario: Identity and migration effect
- **WHEN** `python -m pytest -q tests/test_identity_migration.py -k 'timezone or legacy_migration'` replays one event before and after corrected timestamp conversion
- **THEN** `IBKR#v2#<account>:<kind>:<source-id>` remains the same event identity, and a stored date on the same configured local day remains eligible for comment-only migration despite an intraday difference; a different local day excludes comment-only migration and requires reviewed date correction within the active profile limits or manual approval.

### Requirement: Bounded gross differences and exact quantities

Compare gross amounts in a common supported major currency unit. Compute source gross from the validated source event and destination gross from its exact quantity times price. Normalize GBP/GBp by the fixed factor 100; do not apply foreign-exchange rates. Unknown denominations SHALL require manual review. Fees SHALL remain separate and SHALL NOT reduce or offset a gross discrepancy.

| Profile | Absolute gross limit | Relative gross limit |
| --- | --- | --- |
| conservative | zero, except proven calculation residue | zero, except that residue |
| balanced | one currency minor unit | 0.1% |
| permissive | one hundred currency minor units | 1% |

Both limits SHALL pass, inclusively, for exact references and profile matches. The relative difference SHALL be `abs(destination_gross - source_gross) / abs(source_gross)`. A missing, nonfinite, zero or negative source gross SHALL NOT qualify. Resolve the major-unit precision explicitly: JPY has zero decimals; GBP, USD, EUR and CAD have two. Automatic financial authority is a closed allowlist: JPY, GBP, GBp, USD, EUR and CAD. Existing helper support for other currencies SHALL NOT extend this allowlist. ZAc/ILA and inferred market scaling remain manual-only. Except GBP/GBp, both sides require the same currency. Thresholds SHALL be fixed profile constants in this increment, without additional tuning ENV variables. Beyond-limit candidates SHALL remain available for manual approval and SHALL NOT disappear from review.

BUY/SELL quantities SHALL be numerically exact for every automatic financial correction, even with an exact reference in permissive mode. A comment-only migration SHALL retain the old quantity. DIVIDEND quantity/price representation SHALL be replaceable when the existing validated IBKR accrual/cash conversion proves the source quantity and the resulting gross is within the selected profile. Do not infer a dividend quantity from equal gross alone. Source quantities such as 100 SHALL NOT be summed across distinct actions to fit a target. Security and operation type SHALL NOT change automatically. GBP/GBp is the only automatic denomination change in this increment.

After unique association, eligible corrections SHALL use validated source fees without a fee-matching threshold. Preserve ordinary commission-currency and withholding validation. Do not infer a fee conversion that the current converter does not support. A large fee difference SHALL remain visible even when automatically authorized.

#### Scenario: Financial profile boundaries
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k financial_limits` covers exact references and profile matches, both limit edges, small/large principals, JPY and GBP/GBp, unsupported denominations, different fees, ZAc/ILA inferred scaling, dividend representation and BUY/SELL quantity changes
- **THEN** both gross limits must pass; fees never determine identity; source-proven dividend quantities can change; BUY/SELL quantities cannot; outside-limit proposals remain manual.

### Requirement: Proven calculation residue without payload rounding

Use exact decimal source and destination values for financial decisions. Equal numeric spellings SHALL be equal. A difference SHALL qualify as calculation residue only when independently reproducing the existing conversion's multiply/divide/serialization operations explains it within the finite binary representation error of those operations. Equal rounded totals alone SHALL NOT prove that cause. For example, a reproduced `1.8` to `1.7999999999999998` scaling result can qualify; an unexplained 1 JPY difference SHALL use the profile thresholds.

For residue display and corroboration, round the normalized total once to the currency precision, using decimal half-even rounding. Do not round unit prices before multiplying. Do not round quantities. Preserve source decimals, exact destination values, transmitted payload numbers, unrounded difference, precision and the reproduced cause in private evidence. The comparison SHALL never round a beyond-limit difference down into a profile allowance. Payload construction and exact post-write readback SHALL not use matching tolerance or report rounding.

#### Scenario: Reproduced residue and real differences
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k numeric_residue` covers fixed scaling, repeating dividend quotients, large quantities, half-unit edges, unexplained sub-minor differences and exact wire readback
- **THEN** only a reproduced bounded calculation cause permits the residue exception; quantities stay exact; thresholds use unrounded amounts; intended payload and readback retain exact financial values.

### Requirement: Relevant conflicts and already conforming activities

A unique current v2 identity whose expected and preserved values already match SHALL be reported as `already consistent`, with no correction proposal or PUT. Classify it before unrelated incomplete dividend contexts. This SHALL NOT release an unresolved journal, a duplicate identity, contradictory source evidence, a relevant corporate-action hold or an observed contradiction on that activity.

For discrepancy diagnosis, report the source events and destination activity IDs that cause each conflict. A missing ISIN on an unrelated same-day symbol SHALL NOT alone block an otherwise resolved mapped pair or conforming activity. Resolve the supported mapped security first. Retain conflicts where the same mapped security/action scope actually overlaps, identity coverage is partial, references duplicate a source event, or the relevant security cannot be resolved. Distinct source actionIDs alone SHALL NOT certify cash completeness. Complete valid action evidence and unique pairs SHALL permit separate legacy dividend migrations despite their shared old symbol/day marker. A shared legacy marker SHALL NOT be reported as an exact one-action identity.

#### Scenario: Conformity and localized dividend conflicts
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k conformity` covers already-equal v2 activities, unrelated same-day missing ISINs, mapped-security collisions, partial action coverage, duplicate IDs, uncertain journals and two distinguishable legacy dividends
- **THEN** conforming activities require no correction; actual conflicts retain their hold and identify all causes; independently unique dividend pairs remain eligible without a guessed aggregate conversion.

### Requirement: Grouped diagnosis without aggregate correction

Build groups from shared source or target candidates, not from a sum of proposal rows. Show distinct source events, distinct destination activities, dates, quantities, gross and fees. Count every event and activity once. Keep currencies separate unless supported fixed-unit normalization applies. Label aggregate agreement separately from identity or allocation proof. Show the unrounded difference and the monetary display.

Groups that need activity fusion, splitting or an unresolved alternative assignment SHALL remain manual in every profile. Do not allow a locally plausible one-to-one update to silently stand for a whole aggregate group. A group whose criteria reduce every required association to disjoint unique pairs SHALL permit those one-to-one operations; preserve leftover candidates and ordinary holds explicitly. No grouped write, deletion or automatic BUY/SELL quantity change is introduced.

#### Scenario: Split fills and distinguishable dividends
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k group_diagnosis` tests four source trades against two targets with equal total quantity/gross and a one-minor-unit fee difference, plus two source dividends against two distinct-gross legacy targets
- **THEN** source and target totals are not multiplied by candidate count; split fills remain manual; only independently unique dividend pairs can execute within their profile.

### Requirement: Sequential execution and visible outcomes

Automatic corrections SHALL reuse the same qualified request, lock, durable before/after intent, exact readback and account-failure fence as manual corrections. Apply every currently eligible automatic correction, comment-only migration and manual approval in one connector run, across all configured accounts. There SHALL be no per-run correction count cap. Dispatch the oldest first-eligible operation revision first, with stable key tie-breaking and migration before its dependent correction. Every next correction SHALL wait at least the fixed twenty-eight-second delay after the previous confirmed correction. No profile or ENV setting SHALL lower that delay or add a count cap. There SHALL be no additional run duration bound beyond existing process and request timeouts. New automatic candidates SHALL NOT jump ahead of retained eligible manual work. Report queue position and remaining eligible runs as a current-inventory estimate, not a completion promise. Deferred automatic work SHALL be re-evaluated from fresh evidence on later runs; do not force reruns or request redundant approval.

Show `already consistent`, `automatically corrected`, `automatic work deferred`, `manual review required`, `rejected association` and `blocked` separately. Simulation SHALL show `would correct`, never claim actual completion. Show the selected profile, actual correction fields and authority. Journal eligibility SHALL include configured TZ and the exact source/destination instants and computed local dates. Automatic success SHALL not require an intervention notification; manual decisions, conflicts and uncertain outcomes SHALL use existing consolidated notifications without private financial details.

#### Scenario: Profile execution and simulation
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k profile_execution` covers new automatic candidates, long correction chains, confirmation, failure, restart, profile changes, oldest-eligible queue order, manual starvation prevention, queue estimates and dry-run with mocked HTTP
- **THEN** every eligible correction applies in one run with the fixed delay, exact readback controls completion, uncertainty is never resent, simulation writes no financial data and outcomes distinguish actual work from preview.

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
