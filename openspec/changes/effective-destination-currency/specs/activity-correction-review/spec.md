## ADDED Requirements

### Requirement: Currency representation does not create a correction

Review SHALL compare the effective destination currency defined in
connector-runtime with the currency of the validated source conversion.
Null with proven matching profile currency SHALL NOT be a changed operation
field. If this is the only difference on a unique current v2 activity,
review SHALL report `already consistent` and remove the obsolete currency-only
proposal without a PUT. It SHALL retain all unresolved-journal, source,
identity, ownership and corporate-action fences before doing so.

If another field differs, review SHALL retain that difference and evaluate the
actual operation independently. It SHALL preserve the raw nullable field in
current evidence and show the effective currency and its provenance separately.
A legacy comment-only migration SHALL keep the current financial fields and raw
nullable currency. It SHALL NOT materialize the profile currency as a financial
edit. A subsequent financial correction SHALL require its own fresh evaluation.

An explicit KRW activity on a USD profile SHALL be compared as KRW. A source USD
activity against that destination SHALL retain a real currency discrepancy.
GBP and GBp SHALL remain different operation denominations. Exact fixed-unit
normalization can establish financial eligibility but SHALL NOT erase a required
currency, price or fee change. Unknown profile evidence SHALL leave the row
uncertain; neither a blank decision nor a profile SHALL turn it into conformity.

Baseline: `changed_fields` compares raw currency. The 108 pending currency-only
entries counted in `input-summary.json` therefore describe a representation
difference. The complete proof references are in the connector-runtime delta.

#### Scenario: Conformity and retained real differences
- **WHEN** `python -m pytest -q tests/test_activity_review.py tests/test_activity_reconciliation.py -k effective_currency_comparison` covers equal v2 rows, a fee discrepancy, legacy comments, KRW/USD overrides, GBP/GBp changes, unknown profiles and unresolved journals
- **THEN** proven representation-only proposals disappear without requests, other differences remain visible, legacy migrations change only comments and uncertainty never becomes automatic action.

### Requirement: Currency evidence survives refresh and exact recovery

Raw preimages, input hashes and journal fingerprints SHALL remain tamper evidence.
Effective comparison SHALL NOT rewrite saved activity captures, pending request
evidence or accepted identities. Fresh review SHALL rebuild decisions from source
and target proof. A changed operation, proof of denomination, target profile or
actionability SHALL invalidate the affected approval under the existing rules.
An effective currency value SHALL NOT serve as consent or an identity claim.
Profile-only null representation changes SHALL NOT create a financial operation.

New intents SHALL bind the effective currency, raw currency, profile identity,
profile currency, request and comparison policy before dispatch. The actual
observed raw readback SHALL remain available after confirmation. Exact readback
SHALL allow only the proven explicit/null representation equivalence. It SHALL
still reject a real denomination change, numeric drift, changed profile context,
owner/tag/note changes and every other unapproved preserved-field difference.
It SHALL NOT use normalized gross equality as replacement proof.

Existing pending journals SHALL remain readable and immutable. Their original
comparison contract SHALL NOT be silently reinterpreted by this fix. A pending
entry that does not meet its contract SHALL retain its account fence. It SHALL
NOT be discarded, regenerated or resent. New-policy and legacy entries SHALL
be distinguishable before recovery evaluates them. Unsupported policy or reader
compatibility SHALL fail closed. Confirmed success SHALL permit local cleanup
and index refresh once, without another request after restart.

No Ghostfolio database migration is required. Existing review schemas SHALL
remain readable. Derived comparison evidence belongs in private state and the
existing evidence sections. A refreshed view can get a new generation; changes
to displayed operations clear their consent. An upgrade SHALL NOT bulk approve
or reject entries. Rejection bindings, cooldowns and journal-key aliases SHALL
retain their safety rules. Existing pending journals block related financial
work even when an obsolete currency-only view entry disappears.

The activity-review guide SHALL explain raw versus effective currency, the
profile-proof limit, real denomination changes, remaining holds and the need to
preserve journals before downgrade. This requires no new operator command or ENV.

Baseline: existing Exact replacement, Verified correction, Durable files and
Bounded read-only recovery requirements already require exact evidence and
immutable uncertain requests. `row_matches` currently uses raw field equality.

#### Scenario: Positive readback with exact preservation
- **WHEN** `python -m pytest -q tests/test_activity_review.py -k effective_currency_readback` covers null/same-profile results, overrides, GBP/GBp, numeric/date/metadata drift, fresh profile changes, timeouts, before-only results and restarts
- **THEN** only complete exact expected-after evidence confirms a new-policy intent, actual raw readback is retained and each uncertain logical request sends at most one PUT.

#### Scenario: Upgrade and downgrade evidence
- **WHEN** `python -m pytest -q tests/test_activity_review.py -k effective_currency_persistence` loads old review generations, v1/v2 pending journals, new-policy entries, edited evidence, rejected pairs and a rollback reader
- **THEN** original journals and aliases stay intact, changed operations lose stale consent, unsupported recovery remains held and no downgrade or state rebuild causes a resend or financial conversion.
