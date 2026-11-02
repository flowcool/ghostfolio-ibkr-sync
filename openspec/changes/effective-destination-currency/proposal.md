# Proposal

## Why

Ghostfolio 3.96.0 stores an activity currency override as null when it equals
the security profile currency. Raw-field comparison creates 108 false currency
corrections and prevents 25 legacy references from passing the currency check.

## What Changes

- Resolve destination currency from the explicit activity value. Only an observed
  null permits fallback to the proven currency of that activity's profile.
- Use this rule for review, reconciliation, import acceptance, positive readback,
  historical identity preview and recovery. Retain raw values and provenance.
- Remove representation-only corrections. Preserve real denomination differences,
  exact financial values, profile authority limits and uncertain outcomes.
- Give each remaining hold its actual cause. Currency resolution alone does not
  prove source completeness, amount agreement or unique ownership.

### Source scope

The saved `flex-latest.xml` inventory has SHA-256
`fc4ce5ce5ae3e9e7ad67b79a3ab24f739da8d6c399f464211d1d9b1aa3d78d9a`.
The table covers its record types. No source parsing change is proposed.

| Flex record | Scope |
| --- | --- |
| Trade (126) | In: destination comparison for supported BUY/SELL |
| CashTransaction (238) | In: existing dividend payment/withholding evidence |
| ChangeInDividendAccrual (153) | In: existing dividend quantity evidence |
| AccountInformation (1) | Out: account ownership and cash currency rules stay fixed |
| CashReportCurrency (9) | Out: cash updates stay independent |
| ConversionRate (12207) | Out: no foreign-exchange conversion |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: common destination-currency and exact acceptance contract.
- `activity-correction-review`: effective comparison with raw evidence and exact readback.
- `activity-reconciliation`: currency provenance, legacy eligibility and precise diagnosis.

## Impact

Patch-level bug fix within 4.0.x, subject to compatibility gates. No database
migration or historical financial conversion. Review generations can change;
pending journals must retain their original comparison contract.

Changed shared import/request helpers require an explicit DEGIRO propagation
notice under ADR 0007. DEGIRO remains pinned; adoption needs its own change.

## Non-goals

This delivery contains proposal artifacts only. Runtime code, service access,
financial writes, release and publication are excluded. New financial limits,
new mandatory quantity holds and date conversion are excluded. Claude reviews
the proposal, including the replay-count conflicts recorded in the delta specs.
