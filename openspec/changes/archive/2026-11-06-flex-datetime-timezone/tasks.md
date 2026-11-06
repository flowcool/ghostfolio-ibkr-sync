# Tasks

## 1. Parser contract

- [x] 1.1 Update the parser contract and offline tests. Accept only EST=-05:00 and EDT=-04:00 as query account timezone tokens. Use no IANA lookup for source tokens. Test midnight rollover, unqualified legacy compatibility, invalid and unknown tokens. Add fixtures for 2026-03-08 before and after the EST/EDT flip and 2026-11-01 with both tokens for the repeated hour. Verify with `python -m pytest -q tests/test_parsing.py -k datetime` (G1).
- [x] 1.2 Extend the existing cash preflight to reject any unknown qualified token on Trade, CashTransaction, ChangeInDividendAccrual and CorporateAction. Prove account failure before all financial writes, including cash and platform updates, without forcing `DRY_RUN`. Retain existing cash suffix prerequisites and supported unqualified legacy forms. Verify with `python -m pytest -q tests/test_orchestration.py -k historical_diagnostic_preflight`.

## 2. Consumer chain

- [x] 2.1 Update trade conversion, corporate-action execution dates, and deduplication. Payment days now use the written calendar day under section 5. Prove that corporate-action security matching excludes a CASH/FX row without an ISIN before date parsing, even when its date fails the imported-category G6 bound. Verify with `python -m pytest -q tests -k datetime_timezone_chain` (G2).
- [x] 2.2 Update activity review, reconciliation and identity migration evidence. Keep `IBKR#v2` unchanged. Compare dates by configured local day. Cover stored `2026-01-19T07:03:00Z` against source `2026-01-19T00:00:00Z` under `Europe/Paris`: no date proposal, comment-only migration eligible, stored instant preserved. Cover different local days and the existing permissive two/three-day limits. Keep stored-date repair in the existing reviewed correction path, with backup and exact readback. Build no conversion tool. Repair needs a separate operation step and operator GO after release. Verify with `python -m pytest -q tests/test_activity_review.py tests/test_activity_reconciliation.py tests/test_identity_migration.py -k 'timezone or migration'` (G3).

## 3. Acceptance gates

- [x] 3.1 Replay the saved affected review input in simulation. Verify that the Tokyo `6266.T` proposal no longer proposes a Friday-to-Sunday date move. Record exact review output and correction readback from authorized labs (G5).
- [x] 3.2 Run the empty and golden Ghostfolio lab scenarios with Tokyo, New York and London near-midnight synthetic trades on the same immutable image. Retain proof and stop both labs (G4).
- [x] 3.3 Fetch retained Flex XML evidence from the state backup by SSH into ignored worktree `tmp/`. Never read live state. Keep inputs and replay outputs separate. Replay every saved `Trade` row through the candidate parser, but scope G6 to imported asset categories (`assetCategory` not in `SKIP_ASSET_CATEGORIES`). `CASH` and `OPT` Trade rows are skipped in the import and review paths before any date use; FX `tradeDate` is a value date and can move across a weekend. Record input hashes, rows per category, violations per category, and the imported-category result. Any violation in a non-skipped category blocks G6 and invalidates the token assumption.
- [x] 3.4 Run the complete numbered G1–G6 gates from the spec. Record failures and block release until every gate passes on the exact candidate.

## 4. Release preparation

- [x] 4.1 Prepare a minor release note: new activities get corrected instants; no stored activity is rewritten. Flag downstream propagation in the PR only if a shared helper changes. `parse_ibkr_datetime` is IBKR-specific. Stable publication needs its separate operator GO.

## Review round 2 evidence

The offline EST/EDT fixed-offset replay covers six saved reports and 776 Trade rows. STK: 686 rows, zero violations. CASH: 86 rows, 12 excluded deviations. OPT: four rows, zero excluded deviations. G6 passes for all 686 imported rows. This checks the token assumption. Candidate-parser acceptance remains open.

Checked call sites: `ibkr.parse_trades` copies fields without date use. `app.select_account_activities` filters categories before trade conversion and holdings checks. `sync.convert_trade_to_activity` rejects skipped categories before reading `dateTime`. `sync._match_manual_entry` and `sync.filter_trades_by_holdings` receive the filtered candidates from `app`. `activity_review.source_events` filters categories before conversion for review and identity migration. `ibkr.parse_cash_dividends`, `ibkr.flex_provenance_failures` and `sync._dividend_day` read cash payment records, not Trade rows. `corporate_actions.event_inventory` reads CorporateAction records, not Trade rows.

Corporate-action Trade readers select the event security by ISIN and contract before date use. CASH/FX rows without an ISIN do not feed these dates. Add a regression with an excluded CASH row whose UTC date is more than one day from tradeDate.

## Implementation scope and retained proof

The initial implementation had offline proof for G1, G2, G3 and candidate-parser
G6. G5 had the saved review simulation and mocked exact readback. Native
qualification below now completes tasks 3.1, 3.2 and 3.4 on the released digest.

The candidate parser replays the same six retained XML hashes: STK 686 with zero
violations, CASH 86 with 12 excluded deviations, OPT four with zero deviations.
The saved compact review omits destination profile, owner and tag proof. Its
controlled simulation uses the saved Flex source and synthetic destination metadata.
The Tokyo source instant is 2026-01-19T00:00:00+00:00. The simulation keeps its stored
2026-01-19T07:03:46.203000+00:00 instant and emits no date proposal for that row.
No financial request or confirmed journal is produced. Input hashes remain unchanged.
Private replay output and hashes belong to the owning work item, not this repository.


## 5. Payment calendar-day correction (approved R1-R5)

- [x] 5.1 Amend the delta and docs for execution instants, exchange-day checks, written payment days and the accepted Ghostfolio timezone limit.
- [x] 5.2 Separate payment calendar-day parsing. Cover payments, withholding, accruals, deduplication, review and identity migration. Keep corporate-action execution conversion.
- [x] 5.3 Hold known-venue tradeDate mismatches with a reason. Exclude FX and do not infer unknown venue zones.
- [x] 5.4 Log validated comparison TZ. Prove canonical values and replacement dates under Europe/Paris, Asia/Bangkok, America/Los_Angeles and Asia/Kolkata. Run full pytest and scripts/check.sh.
- [x] 5.5 Add CHANGELOG and prepare PR delivery details. Merge origin/main before push. Record PR and pr-ship merge proof in the owning work item. Keep native labs, release and historical conversion open for their owner.

## 6. Exact-candidate native acceptance

The native date runner is versioned by Infra PRs
[416](https://github.com/flowcool/mylittlemess/pull/416),
[419](https://github.com/flowcool/mylittlemess/pull/419) and
[421](https://github.com/flowcool/mylittlemess/pull/421).
The final runner commit is `9085abd7052f8c41245a931a26d90c776937c267`.
Both native runs use connector commit
`e18d8475944078adb5e176a77a8d173b80aa60b6` and the v4.3.1 digest
`sha256:9f342462b6f7e0089009d66eb799116f1629dcb4447f7132bfdd5a2a66a90fc6`.
The private acceptance record owns the retained paths. No private input or
financial value is published here.

- Task 3.1 / G5: retain the saved affected-input simulation above. In both
  `phase2/empty/` and `phase2/golden/`, `preview-review.json` and
  `correction-preview-review.json` preserve the compatible Tokyo intraday
  timestamp without a date proposal. They expose one true two-day repair.
  `correction-result.json`, `correction-readback.json`, `journal-readback.json`
  and `correction-jobs.json` prove the exact native PUT, one confirmed journal
  entry, and completed market and portfolio jobs. `recovery-result.json` and
  `repeat-result.json` prove no resend.
- Task 3.2 / G4: each `fixture.json`, `prepare-result.json` and
  `import-readback.json` binds 18 TSEJ, NYSE and LSE trades to exchange and
  tradeDate evidence. Cases include midnight crossings, both US clock changes
  and both repeated-hour tokens. Twelve late New York dividend, payment-in-lieu
  and withholding components form four written-day payments at 00:00 UTC.
  Each `final.json` proves preservation of original activities and cash.
- Task 3.4 / G1-G6: reuse the exact-source offline result: 3311 tests passed,
  one skipped; Ruff and strict mypy passed. The source and test trees match
  between the tested commit `64c04cb7b7800339d149c621444a0ae2d02de98f`, reviewed
  commit `31123fd7ac860ae428fc11ae07aa3c6a3c1dbae9` and released commit above.
  `offline-source-tree-binding.json` records that binding. G6 retains the six
  input hashes and the 686 imported STK rows with zero violations. G4 and G5
  now have the native proof above.

Each `server-dates.json` measures 110 observations through the actual compiled
Ghostfolio 3.98.0 date constructor and holding calculator. The record includes
the bundle hash. It covers UTC, Europe/Paris, Asia/Bangkok, America/Los_Angeles
and Asia/Kolkata. It confirms server date bucketing and the accepted previous-day
effect west of UTC. It does not claim a complete portfolio valuation or browser
rendering test.

Both `result.json` records report PASS, zero broker requests and stopped cleanup.
Both final stopped checks report `running=0`. Retained result SHA256 values:

- Empty: `9eb33fced187d072779e971544bba39d64770db2ed67e8093a1ec10367807c79`.
- Golden: `c4c2f1156a55e13ee0799b0e2dd3ebfa8f4c2918194dc8fbad8309afc5acf11f`.

The retained `proof-sha256.json` manifest has SHA256
`b68bd3d3d6d35b55e4ab9d7b9584ad3c055d0f1ec8ff182d72411407046ad115`.
All 82 recorded artifact hashes were checked at reconciliation. They match.
The earlier failed harness attempt remains retained. These results refer only
to the final native runs with the corrected Infra currency comparison policy.
