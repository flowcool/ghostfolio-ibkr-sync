# Tasks

## 1. Parser contract

- [x] 1.1 Update the parser contract and offline tests. Accept only EST=-05:00 and EDT=-04:00 as query account timezone tokens. Use no IANA lookup for source tokens. Test midnight rollover, unqualified legacy compatibility, invalid and unknown tokens. Add fixtures for 2026-03-08 before and after the EST/EDT flip and 2026-11-01 with both tokens for the repeated hour. Verify with `python -m pytest -q tests/test_parsing.py -k datetime` (G1).
- [x] 1.2 Extend the existing cash preflight to reject any unknown qualified token on Trade, CashTransaction, ChangeInDividendAccrual and CorporateAction. Prove account failure before all financial writes, including cash and platform updates, without forcing `DRY_RUN`. Retain existing cash suffix prerequisites and supported unqualified legacy forms. Verify with `python -m pytest -q tests/test_orchestration.py -k historical_diagnostic_preflight`.

## 2. Consumer chain

- [ ] 2.1 Update trade conversion, cash dividend day, corporate-action dates and deduplication to consume the same corrected instant. Prove that corporate-action security matching excludes a CASH/FX row without an ISIN before date parsing, even when its date fails the imported-category G6 bound. Verify with `python -m pytest -q tests -k datetime_timezone_chain` (G2).
- [ ] 2.2 Update activity review, reconciliation and identity migration evidence. Keep `IBKR#v2` unchanged. Compare dates by configured local day. Cover stored `2026-01-19T07:03:00Z` against source `2026-01-19T00:00:00Z` under `Europe/Paris`: no date proposal, comment-only migration eligible, stored instant preserved. Cover different local days and the existing permissive two/three-day limits. Keep stored-date repair in the existing reviewed correction path, with backup and exact readback. Build no conversion tool. Repair needs a separate operation step and operator GO after release. Verify with `python -m pytest -q tests/test_activity_review.py tests/test_activity_reconciliation.py tests/test_identity_migration.py -k 'timezone or migration'` (G3).

## 3. Acceptance gates

- [ ] 3.1 Replay the saved affected review input in simulation. Verify that the Tokyo `6266.T` proposal no longer proposes a Friday-to-Sunday date move. Record exact review output and correction readback from authorized labs (G5).
- [ ] 3.2 Run the empty and golden Ghostfolio lab scenarios with Tokyo, New York and London near-midnight synthetic trades on the same immutable image. Retain proof and stop both labs (G4).
- [ ] 3.3 Fetch retained Flex XML evidence from the state backup by SSH into ignored worktree `tmp/`. Never read live state. Keep inputs and replay outputs separate. Replay every saved `Trade` row through the candidate parser, but scope G6 to imported asset categories (`assetCategory` not in `SKIP_ASSET_CATEGORIES`). `CASH` and `OPT` Trade rows are skipped in the import and review paths before any date use; FX `tradeDate` is a value date and can move across a weekend. Record input hashes, rows per category, violations per category, and the imported-category result. Any violation in a non-skipped category blocks G6 and invalidates the token assumption.
- [ ] 3.4 Run the complete numbered G1–G6 gates from the spec. Record failures and block release until every gate passes on the exact candidate.

## 4. Release preparation

- [ ] 4.1 Prepare a minor release note: new activities get corrected instants; no stored activity is rewritten. Flag downstream propagation in the PR only if a shared helper changes. `parse_ibkr_datetime` is IBKR-specific. Stable publication needs its separate operator GO.

## Review round 2 evidence

The offline EST/EDT fixed-offset replay covers six saved reports and 776 Trade rows. STK: 686 rows, zero violations. CASH: 86 rows, 12 excluded deviations. OPT: four rows, zero excluded deviations. G6 passes for all 686 imported rows. This checks the token assumption. Candidate-parser acceptance remains open.

Checked call sites: `ibkr.parse_trades` copies fields without date use. `app.select_account_activities` filters categories before trade conversion and holdings checks. `sync.convert_trade_to_activity` rejects skipped categories before reading `dateTime`. `sync._match_manual_entry` and `sync.filter_trades_by_holdings` receive the filtered candidates from `app`. `activity_review.source_events` filters categories before conversion for review and identity migration. `ibkr.parse_cash_dividends`, `ibkr.flex_provenance_failures` and `sync._dividend_day` read cash payment records, not Trade rows. `corporate_actions.event_inventory` reads CorporateAction records, not Trade rows.

Corporate-action Trade readers select the event security by ISIN and contract before date use. CASH/FX rows without an ISIN do not feed these dates. Add a regression with an excluded CASH row whose UTC date is more than one day from tradeDate.
