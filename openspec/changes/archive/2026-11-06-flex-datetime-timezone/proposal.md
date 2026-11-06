# Proposal

## Why

Flex returns qualified execution clocks and ledger posting clocks in the same text format. The earlier implementation corrected EST/EDT execution instants. It also converted dividend posting clocks, which can move a payment to the next UTC day. Keep execution instants and payment calendar days separate. The approved correction preserves existing 00:00 UTC payment dates and documents the Ghostfolio timezone limit.

## What Changes

- Convert qualified Flex timestamps with fixed offsets: EST=-05:00 and EDT=-04:00. The suffix is the query account timezone, not the exchange timezone. Do not use an IANA lookup for source tokens.
- Reject every other qualified token. Fail the affected account before any financial write, including cash and platform updates. Do not force `DRY_RUN`. New tokens require a new change.
- R1: keep trade execution instants from EST/EDT converted to UTC.
- R2: check `tradeDate` against the execution day in a known exchange zone. Hold a mismatch with a reason. Exclude FX value dates. Never infer the exchange zone from currency.
- R3: use the calendar day written in dividend, payment-in-lieu and withholding `dateTime`. The posting clock does not define an execution instant. Anchor the day at 00:00 UTC. Use this rule for accrual association, deduplication, review and identity migration.
- R4: use ENV `TZ` for local-day tolerance and scheduling. Require it to equal the Ghostfolio server timezone. Log the comparison timezone at startup. Source values and canonical replacement timestamps do not depend on `TZ`.
- R5: use Python stdlib `zoneinfo` only. Add no date library.
- Keep the 00:00 UTC payment anchor. Document the Ghostfolio 3.96.0 browser-display and server-valuation limits. A noon-UTC anchor would avoid the demonstrated previous-day display in western zones. It needs historical-data conversion and a separate operator GO.
- Keep source text, parsed instant and source calendar day available for review evidence.
- Keep `IBKR#v2` identity event-only. Compare source and stored dates by local calendar day under configured `TZ`. The same local day produces no date proposal and remains eligible for comment-only migration when other checks pass.
- Add offline parser, US switch-day, caller and lab validation after approval. Add G6: every saved imported Trade (an `assetCategory` outside `SKIP_ASSET_CATEGORIES`) must have a converted UTC date within one day of `tradeDate`. `CASH` and `OPT` Trade rows are skipped in the import and review paths before any date use; FX `tradeDate` is a value date and can move across a weekend. A violation in a non-skipped category fails the gate and invalidates the token assumption. Implementation follows the approved tasks.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `connector-runtime`: qualified Flex dateTime conversion and invalid-zone handling.
- `activity-reconciliation`: source and destination date comparison after corrected instants.
- `activity-correction-review`: correction and migration evidence for corrected timestamps.

## Impact

Affected code is `parse_ibkr_datetime` and all callers in `ibkr.py`, `sync.py`, `corporate_actions.py`, `activity_review.py` and identity migration. Affected records are `Trade`, `CashTransaction` (all qualified tokens; required suffix for Dividends, Payment In Lieu Of Dividends and Withholding Tax), `ChangeInDividendAccrual`, and `CorporateAction`; `AccountInformation`, `CashReport` and unrelated cash rows are inspected but do not carry this parser result. Normal sync never rewrites stored activities. Stored dates can be repaired only through the existing reviewed correction path, with backup and exact readback. A separate operation step after release needs operator GO. `IBKR#v2#<account>:<kind>:<source-id>` contains no date, but date changes can alter candidate matching and migration eligibility.

| Flex record type | Scope | Evidence |
| --- | --- | --- |
| `Trade` | convert execution dateTime | saved report and parser tests |
| `CashTransaction` | reject unknown qualified tokens on all types; read the written dividend/PIL/withholding calendar day and keep required suffix | saved report and runtime spec |
| `ChangeInDividendAccrual` | date evidence only | saved report and dividend conversion |
| `CorporateAction` | convert event timestamps | corporate-action parser |
| Other sections | inspect, no parser result | saved report inventory |

## Non-goals

This revision includes no historical write, Ghostfolio write, production service access, release, or sibling DEGIRO change. It defines a minor release for implementation. The release note must state that new activities get corrected instants and no stored activity is rewritten. The PR flags downstream propagation only if a shared helper changes; `parse_ibkr_datetime` is IBKR-specific.

Corporate-action Trade readers match the event security by ISIN and contract before parsing dates. CASH/FX rows without an ISIN do not feed these dates. A regression covers a CASH row outside the imported-category G6 bound.
