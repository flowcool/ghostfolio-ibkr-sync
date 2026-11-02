# Tasks

## 1. Parser contract

- [ ] 1.1 Update the parser contract and offline tests. Accept only EST=-05:00 and EDT=-04:00 as query account timezone tokens. Use no IANA lookup for source tokens. Test midnight rollover, unqualified legacy compatibility, invalid and unknown tokens. Add fixtures for 2026-03-08 before and after the EST/EDT flip and 2026-11-01 with both tokens for the repeated hour. Verify with `python -m pytest -q tests/test_parsing.py -k datetime` (G1).
- [ ] 1.2 Extend the existing cash preflight to reject any unknown qualified token on Trade, CashTransaction, ChangeInDividendAccrual and CorporateAction. Prove account failure before all financial writes, including cash and platform updates, without forcing `DRY_RUN`. Retain existing cash suffix prerequisites and supported unqualified legacy forms. Verify with `python -m pytest -q tests/test_orchestration.py -k historical_diagnostic_preflight`.

## 2. Consumer chain

- [ ] 2.1 Update trade conversion, cash dividend day, corporate-action dates and deduplication to consume the same corrected instant. Verify with `python -m pytest -q tests -k datetime_timezone_chain` (G2).
- [ ] 2.2 Update activity review, reconciliation and identity migration evidence. Keep `IBKR#v2` unchanged. Compare dates by configured local day. Cover stored `2026-01-19T07:03:00Z` against source `2026-01-19T00:00:00Z` under `Europe/Paris`: no date proposal, comment-only migration eligible, stored instant preserved. Cover different local days and the existing permissive two/three-day limits. Keep stored-date repair in the existing reviewed correction path, with backup and exact readback. Build no conversion tool. Repair needs a separate operation step and operator GO after release. Verify with `python -m pytest -q tests/test_activity_review.py tests/test_activity_reconciliation.py tests/test_identity_migration.py -k 'timezone or migration'` (G3).

## 3. Acceptance gates

- [ ] 3.1 Replay the saved affected review input in simulation. Verify that the Tokyo `6266.T` proposal no longer proposes a Friday-to-Sunday date move. Record exact review output and correction readback from authorized labs (G5).
- [ ] 3.2 Run the empty and golden Ghostfolio lab scenarios with Tokyo, New York and London near-midnight synthetic trades on the same immutable image. Retain proof and stop both labs (G4).
- [ ] 3.3 Fetch retained Flex XML evidence from the state backup by SSH into ignored worktree `tmp/`. Never read live state. Keep inputs and replay outputs separate. Replay every Trade in every saved report through the candidate parser. Check that the converted UTC date is within one calendar day of `tradeDate`. Record input hashes, row counts and violations. Any violation fails G6 and invalidates the token assumption.
- [ ] 3.4 Run the complete numbered G1–G6 gates from the spec. Record failures and block release until every gate passes on the exact candidate.

## 4. Release preparation

- [ ] 4.1 Prepare a minor release note: new activities get corrected instants; no stored activity is rewritten. Flag downstream propagation in the PR only if a shared helper changes. `parse_ibkr_datetime` is IBKR-specific. Stable publication needs its separate operator GO.
