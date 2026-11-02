## ADDED Requirements

### Requirement: Effective currency in association and financial evidence

Manual candidate discovery, automatic association, numeric evidence and grouped
diagnosis SHALL use the proven effective destination currency from
connector-runtime. An observed null SHALL NOT reject a supported pair when the
bound profile proves its denomination. Resolving a currency SHALL remove only
that blocker. It SHALL NOT prove ownership, uniqueness, source completeness,
business dates, quantity or an acceptable amount difference.

Legacy trade migration SHALL retain mapping-owned comment-only authority in
every non-off profile. Remaining financial or date differences SHALL stay
separate. Dividend migration SHALL retain its source validity, amount, date,
coverage and mutual-uniqueness gates. Equal dividend gross alone SHALL NOT prove
source quantity or ownership. The existing spec permits source-proven dividend
representations with different quantity/price values; migration preserves the
old representation and correction is a separate operation. This change SHALL
NOT introduce a new quantity-equality rule for dividend comment migration.

The existing closed financial allowlist, both inclusive gross limits, exact
BUY/SELL correction quantities and fixed GBP/GBp factor SHALL remain unchanged.
No profile SHALL gain a larger budget than one correction PUT per run.
Financial eligibility SHALL use unrounded amounts. Exact acceptance SHALL use
neither those eligibility thresholds nor diagnostic display rounding.

Baseline: `automatic_pairs` rejects raw null currency before recognizing legacy
trade authority. `numeric_evidence` separately rejects it, then review replaces
the error with a generic message. The 22 controls in `offline-results.json`
prove the contrast and show that this generic message is not an eligibility
verdict. They do not qualify all real review entries.

#### Scenario: Currency blocker and independent legacy gates
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py -k effective_currency_legacy` covers null/explicit USD, JPY, GBp, KRW and SEK trades, eligible dividends, missing accruals, gross/date excess, ISIN conflicts, duplicate aliases and different dividend representations
- **THEN** proven fallback removes the currency blocker, valid identity-only trades retain their authority, dividends retain every independent gate, and neither a generic message nor equal gross authorizes a write.

### Requirement: Precise currency and eligibility diagnosis

Private review and diagnostic evidence SHALL state raw currency, resolved
denomination and provenance. Missing activity fields, invalid activity codes,
unproven profile currency, conflicting denominations, unsupported automatic
financial currencies and missing exact source evidence SHALL have distinct
plain-English reasons. Known independent blockers SHALL also be named, including
amount limits and conflicting identity claims. Diagnosis SHALL distinguish
an unavailable financial calculation from an ineligible comment-only migration.
It SHALL NOT describe an eligible KRW/SEK trade migration as financially blocked
solely because automatic financial correction lacks precision for that currency.

Group totals SHALL use effective denominations with exact existing scaling.
They SHALL NOT put proven null/JPY rows into a fictitious null-currency group.
Missing proof SHALL remain visible and SHALL NOT be omitted as a zero total.
Historical dividend reports SHALL keep their current quantities, amounts,
display rounding, categories and no-write boundary. A diagnostic `to check`
finding SHALL NOT automatically become a profile or maintenance hold.

#### Scenario: Distinct reasons and grouping
- **WHEN** `python -m pytest -q tests/test_activity_reconciliation.py tests/test_dividend_diagnostics.py -k effective_currency_diagnosis` covers missing/invalid/unsupported currencies, exact source gaps, explicit overrides, equal KRW/JPY, null-profile groups and a dividend representation difference
- **THEN** evidence names each actual reason and provenance, valid identity migration is not mislabelled, totals use proven units and diagnostic findings do not silently change financial authority.

### Requirement: Replay expectations respect evidence and current limits

G2 SHALL use the hash-bound `r.yaml` defined in the connector-runtime delta.
It SHALL distinguish observed baseline, controlled simulation and real-data
eligibility. The 2026-11-02 proof bundle establishes nullable semantics; this
proposal SHALL reuse that proof without another service investigation.

| Scope | Baseline | Controlled simulation expectation |
| --- | --- | --- |
| All proposals | 174: 148 corrections and 26 reference updates | Removing exactly the proven 108 leaves 66 existing candidates: 40 other corrections and 26 references |
| Currency-only corrections | 108 pending: KRW 69, JPY 25, USD 10, GBp 3, SEK 1 | Zero for this class once each matching profile is proven; no currency PUT |
| Held null-currency references | 25: JPY 18, GBp 4, USD 3 | All 25 pass the currency check with matching bound profile proof |
| Legacy trades within those 25 | 16: 13 with equal quantity/price/fee, plus IBRX, MU and GOOG with fee differences | All 16 can qualify for comment-only migration when ownership and identity gates pass; financial/date differences stay separate |
| Dividends within those 25 | 9 | All 9 require source amount/accrual/date/uniqueness proof after currency resolution; none has a mandatory remaining hold proved by the compact view alone |
| Other reference | One PAF.L already eligible and deferred | Keep it eligible if fresh evidence is unchanged; do not count it among the 25 newly unblocked rows |

The count 66 is a bounded comparison projection on the existing candidate set.
It SHALL NOT be promised as the final count after full rediscovery. The 25
currency checks are not 25 executions. Simulation SHALL report zero financial
requests, zero newly confirmed journals and at most one `would correct` for the
shared budget. Qualified eligible work beyond that budget SHALL stay deferred.

The compact view omits full profile and source evidence. G2 SHALL first assert
this limitation. Without bound supplemental proof, fallback and automatic action
SHALL remain uncertain. It SHALL NOT copy the proposed source currency into a
profile and call that real destination proof. A second, explicitly synthetic
simulation can supply matching profiles and complete source fixtures to isolate
the currency fix. With all other gates deliberately satisfied, its expected
result is 25 newly eligible references, plus the one already eligible reference.
An actual saved-evidence replay SHALL enumerate each still-unproven gate and
SHALL NOT present synthetic eligibility as real-data qualification.

The following rows were requested as residual holds. Their observed differences
SHALL stay visible, but their current profile consequences differ from that claim.
Values below come from the compact view's exact observed differences. Source
cash/accrual proof is still required for an actual eligibility decision.

| Security and destination day | Observed difference | Consequence under the current spec |
| --- | --- | --- |
| 2768.T, 2026-06-10 | Destination gross 8250 vs source 8249 JPY | +1 JPY; both balanced limits pass |
| 1976.T, 2026-06-26 | 4500 vs 4501 JPY | -1 JPY; both balanced limits pass |
| 7399.T, 2026-06-29 | 1000 vs 1001 JPY | -1 JPY; both balanced limits pass |
| 5658.T, 2026-06-29 | 3000 vs 3001 JPY | -1 JPY; both balanced limits pass |
| 7297.T, 2026-06-29 | 1500 vs 1499 JPY | +1 JPY; both balanced limits pass |
| 9273.T, 2026-09-28 | 7200 vs 7199 JPY | +1 JPY; both balanced limits pass |
| PAF.L, 2025-12-09 | Stored 7.370505 GBP vs source cash 7.37 GBP | Already eligible/deferred; +0.000505 GBP passes both limits; outside the 25 |
| PAF.L, 2026-03-17 | Stored quantity 451 vs source 450; price differs | Requires profile proof: under a GBp profile, stored gross is 2.470000000000000072 GBP, not a proved material gross discrepancy |
| 4543.T, 2025-12-02 | Stored 1 × 1500 vs source 100 × 15 JPY | Equal gross; source-proven comment-only representation is permitted; quantity remains 1 during migration |

The replay SHALL also include 7272.T: stored 1 × 1000 vs source 100 × 10 JPY.
It has the same representation issue as 4543.T. It SHALL NOT silently receive
a different quantity policy. Historical maintenance's exact-quantity contract
remains stricter than runtime profile migration and SHALL NOT be substituted.

#### Scenario: Hash-bound simulation and count limits
- **WHEN** `python -m pytest -q -s tests/test_activity_reconciliation.py -k effective_currency_replay` reads the configured private input, tests missing-proof controls and runs the separate controlled simulation with denied sockets
- **THEN** it prints baseline 174, conditional comparison projection 66, currency-only 108 to 0, currency checks 25 to 25 passing, the 16/9 reference split, the separate already-eligible row, actual unresolved proof and zero financial requests; all source hashes stay unchanged.

**Review decisions and HORS CHEMIN**

Claude approved the following decisions:

1. Retain current balanced limits. Derive residual counts from evidence only.
   No fixed set of eight residual holds is required.
2. Keep 4543.T and 7272.T eligible for comment-only migration when source and
   uniqueness proof passes. Preserve the stored quantity during migration.
3. The saved review state has no profile-currency evidence. G2 cannot prove
   real-data eligibility offline. Keep its synthetic counts conditional and
   require G5 production observation after deployment.
