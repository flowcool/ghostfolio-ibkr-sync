## ADDED Requirements

### Requirement: Ordered amount causes and correction authority

Broker-independent reconciliation SHALL evaluate ordered cause functions. Each
function SHALL accept a finding and return `(label, reason, action)` or `None`.
The action SHALL be `correct` or `information`. The first match SHALL win.
No match SHALL produce `to_check` and SHALL NOT authorize a financial write.
An unsupported currency, incomplete evidence or conflicting association SHALL
not match a cause. Identity and deduplication SHALL retain exact comparisons.
An amount allowance SHALL NOT establish either identity or source completeness.

The fixed order SHALL be declared-rate rounding, printed-gross rounding,
corroborated execution views, then a source-proven manual entry error.
A broker-specific cause SHALL reject findings from another broker.
An informational cause SHALL cover only its proven fields. An independent fee,
quantity or other monetary difference SHALL remain to check. The first match
SHALL NOT suppress it.

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
A proven exact source value and an identified entry error SHALL use `correct`;
small size alone SHALL NOT turn that error into accepted information.

Baseline: `classify_dividend_findings` proves one declared-rate cause.
`numeric_evidence` proves converter residue separately. Existing profiles and
`process_review` supply association, authority and the only correction writer.

#### Scenario: Ordering, field scope and default refusal

- **WHEN** `python -m pytest -q tests/test_amount_differences.py -k registry` runs overlapping causes, cross-broker findings, unsupported currencies, missing evidence, fee side differences and unknown sub-unit gaps
- **THEN** the first fully qualified cause wins for its fields; unmatched fields stay to check; neither an amount threshold nor a report classification produces a request.

#### Scenario: Cause and profile are independent gates

- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k amount_cause_authority` runs proven errors with off/conservative/balanced/permissive profiles, recognized and unreferenced rows, both gross caps, ambiguous matches, partial action coverage, cached sources and source-proven dividend quantities
- **THEN** only complete uniquely associated errors within existing authority become automatic corrections; other candidates remain visible; unsupported quantity changes and informational causes produce no financial request.

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
| Source-proven manual entry error | A fresh complete source proves every replacement field and a specific entry mistake independently of gap size. In this increment, recognize omitted withholding only: stored fee is zero; validated cash withholding is positive; exact gross and quantity agree; complete action association excludes components, refunds and repeated representations. `correct`. | Operator-confirmed manual history and seven omission-shaped observations in two IBKR review generations. Six have equal gross/quantity but partial action coverage; one older target is unavailable. These saved cases are candidates, not qualified corrections. | Can hide a different payment, a tax refund or incomplete allocation. Require full uncached action evidence, unique matching, existing withholding validation and exact fee replacement. Current partial-coverage/missing-target cases SHALL fail. Manual provenance alone SHALL NOT prove an omission. |

The manual-entry row is a candidate correction contract. It SHALL NOT be
registered for automatic dispatch until at least one complete real-data omission
and its exact one-to-one source proof are retained. Its seven current observations
do not meet that gate. Until then the registry SHALL retain the three proven
information causes and the correct-action routing contract without enabling an
unproved automatic cause. Neither synthetic evidence nor profile selection
SHALL remove this evidence gate.

For the `correct` cause, conservative authority SHALL require a recognized
unique reference and its existing same-day/zero-gross rules. Balanced and
permissive authority SHALL use their existing mutually unique match rules,
date bounds and both gross caps. Fees SHALL NOT rank or identify candidates.
After qualified association, validated source fees SHALL retain their existing
no-fee-threshold treatment. `off` SHALL provide no automatic authority.
A manual `yes` SHALL use the same qualified update and exact source/association
proof. It SHALL NOT override unknown cause, incomplete source or an unresolved
journal. Other manual operations outside this registry retain their existing
review contract; they SHALL NOT be presented as cause-authorized corrections.

The retained inventory also contains unexplained IBKR dividend/trade gross and
fee differences, BD coupon and historical representation differences, and
DEGIRO historical fees/FX diagnostics. They SHALL remain `to_check` with no
cause-authorized write. The older GBP discrepancy has cent-display agreement;
its alleged stored-price rounding mechanism was not reproduced. It SHALL NOT
be promoted to a proven entry error. No generic FX or converter-residue cause
was proved by the scanned real proposals. Existing independently reproduced
converter-residue behavior SHALL remain under its current separate contract.

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
- **THEN** only an independently proven complete omission returns correct; all retained omission-shaped cases remain to check while their recorded blockers persist.

### Requirement: Cause-bound reviewed execution and downstream adoption

Cause evidence SHALL bind to the existing proposal revision and journal
eligibility. Source, target, cause, profile or timezone changes SHALL invalidate
cached automatic eligibility before dispatch. Existing pending journals SHALL
remain recoverable. No new cause field SHALL permit resend or silently clear
uncertainty. Preserve activity ID, account, owner, tags, notes and unrelated
fields. Preserve qualification, durable before/after intent, exact financial
readback, the existing correction delay and the failure fence on later writes.
Sync SHALL never delete an activity or combine multiple source events into a
single update. Simulation SHALL write no financial data and consume no consent.
Unknown cause and profile deferral SHALL remain distinct from failed requests.

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

## MODIFIED Requirements

### Requirement: Bounded gross differences and exact quantities

Compare gross amounts in a common supported major currency unit. Compute source gross from the validated source event and destination gross from its exact quantity times price. Normalize GBP/GBp by the fixed factor 100; do not apply foreign-exchange rates. Unknown denominations SHALL require manual review. Fees SHALL remain separate and SHALL NOT reduce or offset a gross discrepancy.

| Profile | Absolute gross limit | Relative gross limit |
| --- | --- | --- |
| conservative | zero, except proven calculation residue | zero, except that residue |
| balanced | one currency minor unit | 0.1% |
| permissive | one hundred currency minor units | 1% |

Both limits SHALL pass, inclusively, for exact references and profile matches. A changed amount SHALL also require a proven correct-action cause or the existing independently reproduced converter-residue proof. Profile limits alone SHALL NOT classify an unknown discrepancy as a manual entry error or authorize its automatic correction. Informational causes SHALL NOT authorize an amount correction. The relative difference SHALL be `abs(destination_gross - source_gross) / abs(source_gross)`. A missing, nonfinite, zero or negative source gross SHALL NOT qualify. Resolve the major-unit precision explicitly: JPY has zero decimals; GBP, USD, EUR and CAD have two. Automatic financial authority is a closed allowlist: JPY, GBP, GBp, USD, EUR and CAD. Existing helper support for other currencies SHALL NOT extend this allowlist. ZAc/ILA and inferred market scaling remain manual-only. Except GBP/GBp, both sides require the same currency. Thresholds SHALL be fixed profile constants in this increment, without additional tuning ENV variables. Beyond-limit candidates SHALL remain available for manual approval and SHALL NOT disappear from review.

BUY/SELL quantities SHALL be numerically exact for every automatic financial correction, even with an exact reference in permissive mode. A comment-only migration SHALL retain the old quantity. DIVIDEND quantity/price representation SHALL be replaceable when the existing validated IBKR accrual/cash conversion proves the source quantity and the resulting gross is within the selected profile. Do not infer a dividend quantity from equal gross alone. Source quantities such as 100 SHALL NOT be summed across distinct actions to fit a target. Security and operation type SHALL NOT change automatically. GBP/GBp is the only automatic denomination change in this increment.

After unique association, eligible corrections SHALL use validated source fees without a fee-matching threshold. Preserve ordinary commission-currency and withholding validation. Do not infer a fee conversion that the current converter does not support. A large fee difference SHALL remain visible even when automatically authorized.

#### Scenario: Financial profile boundaries
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k financial_limits` covers exact references and profile matches, both limit edges, small/large principals, JPY and GBP/GBp, unsupported denominations, different fees, ZAc/ILA inferred scaling, dividend representation and BUY/SELL quantity changes
- **THEN** both gross limits and the independent cause gate must pass; fees never determine identity; source-proven dividend quantities can change; BUY/SELL quantities cannot; outside-limit proposals remain manual.


### Requirement: Proven calculation residue without payload rounding

Use exact decimal source and destination values for financial decisions. Equal numeric spellings SHALL be equal. A difference SHALL qualify as calculation residue only when independently reproducing the existing conversion's multiply/divide/serialization operations explains it within the finite binary representation error of those operations. Equal rounded totals alone SHALL NOT prove that cause. For example, a reproduced `1.8` to `1.7999999999999998` scaling result can qualify; an unexplained 1 JPY difference SHALL remain to_check without a cause-authorized write even when it is within profile thresholds.

For residue display and corroboration, round the normalized total once to the currency precision, using decimal half-even rounding. Do not round unit prices before multiplying. Do not round quantities. Preserve source decimals, exact destination values, transmitted payload numbers, unrounded difference, precision and the reproduced cause in private evidence. The comparison SHALL never round a beyond-limit difference down into a profile allowance. Payload construction and exact post-write readback SHALL not use matching tolerance or report rounding.

#### Scenario: Reproduced residue and real differences
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k numeric_residue` covers fixed scaling, repeating dividend quotients, large quantities, half-unit edges, unexplained sub-minor differences and exact wire readback
- **THEN** only a reproduced bounded calculation cause permits the residue exception; quantities stay exact; thresholds use unrounded amounts; intended payload and readback retain exact financial values.
