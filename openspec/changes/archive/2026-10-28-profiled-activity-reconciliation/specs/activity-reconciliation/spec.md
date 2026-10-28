# Activity reconciliation delta

## Purpose

Let operators select bounded automatic reconciliation rules while retaining exact source evidence, visible decisions and verified one-to-one writes.

## ADDED Requirements

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

Compare business dates by converting full timezone-aware instants into configured `TZ`. Conservative and balanced corrections SHALL retain the same local calendar day. Permissive corrections SHALL allow inclusive distance of two calendar days for BUY/SELL and three for DIVIDEND. Include weekends; do not infer exchange holidays. Use the existing validated IBKR conversion for replacement timestamps. Keep UTC instants, local dates, timezone and actual elapsed difference visible. Missing source timezone or unsupported precision SHALL refuse automatic date correction.

#### Scenario: Unique candidates and date boundaries
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k unique_matching` covers repeated same-day identical trades, both conflict directions, exact-reference precedence, mapped aliases, fee differences, unsupported profiles, midnight, DST, dividend UTC midnights in negative/positive offset zones and inclusive local-date edges
- **THEN** only mutually unique supported pairs pass; ambiguity stays visible; profile matches are not labelled exact; no UTC/local-day substitution or fee-based selection occurs.

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

### Requirement: Bounded execution and visible outcomes

Automatic corrections SHALL reuse the same qualified request, lock, durable before/after intent, exact readback and account-failure fence as manual corrections. Share one finite execution budget across automatic corrections, comment-only migration and manual approvals. The existing qualified budget of one PUT per connector run SHALL remain the shipped limit until exact-image evidence qualifies a different limit. No profile SHALL override it. Dispatch the oldest first-eligible operation revision first, with stable key tie-breaking and migration before its dependent correction. New automatic candidates SHALL NOT jump ahead of retained eligible manual work. Report queue position and remaining eligible runs as a current-inventory estimate, not a completion promise. Deferred automatic work SHALL be re-evaluated from fresh evidence on later runs; do not force reruns or request redundant approval.

Show `already consistent`, `automatically corrected`, `automatic work deferred`, `manual review required`, `rejected association` and `blocked` separately. Simulation SHALL show `would correct`, never claim actual completion. Show the selected profile, actual correction fields and authority. Journal eligibility SHALL include configured TZ and the exact source/destination instants and computed local dates. Automatic success SHALL not require an intervention notification; manual decisions, conflicts and uncertain outcomes SHALL use existing consolidated notifications without private financial details.

#### Scenario: Profile execution and simulation
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k profile_execution` covers new automatic candidates, budget contention, confirmation, failure, restart, profile changes, oldest-eligible queue order, manual starvation prevention, queue estimates and dry-run with mocked HTTP
- **THEN** one qualified budget applies, exact readback controls completion, uncertainty is never resent, simulation writes no financial data and outcomes distinguish actual work from preview.
