## MODIFIED Requirements

### Requirement: Mapping and duplicate reconciliation

Mapping SHALL prefer ISIN mappings, then IBKR symbols. Trade IDs SHALL suppress reimport. Manual matching SHALL use quantity and ±2 days, including summed fills; nearby mismatches SHALL warn/skip. Dividends SHALL match by account/comment (including the old symbol comment), or, for existing active YAHOO dividends of the same account and symbol whose comment does not start with `dividend#` (manual or legacy rows), at ±3 days. Connector-comment rows (`dividend#…`) SHALL NOT enter the proximity index, so a distinct payment next to an imported one is imported. A proximity skip SHALL stay a skip. It SHALL log INFO "treated as the same payment" when source gross and the existing row's quantity × unitPrice are equal after rounding to the source currency's minor unit, in the same currency. Otherwise it SHALL log one WARNING naming both dates, both gross values with currencies (or "not comparable") and "check manually". It SHALL NOT change exit status or notifications.

#### Scenario: Existing entries
- **WHEN** existing entries match
- **THEN** duplicates are excluded; manual-buy exclusions warn.

Evidence: `python -m pytest -q tests/test_parsing.py tests/test_filters.py tests/test_orchestration.py -k 'test_resolve_symbol_prefers_mapping_then_ibkr_symbol or test_already_imported_trade_is_not_reimported or test_manual_buy_same_day_same_qty_is_not_reimported_and_warns or test_split_fills_summing_to_a_manual_sell_are_matched or test_dividend_match_window_is_exactly_three_days'`.

#### Scenario: Distinct payment next to an imported one
- **WHEN** an active canonical row `dividend#<ISIN>#2026-07-15` (gross 25) exists and the report holds a distinct payment on 2026-07-16 (gross 100)
- **THEN** the 2026-07-16 payment is imported, no proximity log line appears.

Check: `.venv/bin/python -m pytest -q tests -k dividend_proximity_canonical`.

#### Scenario: Manual row near the payment
- **WHEN** a manual row without connector comment lies within ±3 days, once with equal gross and once with different gross
- **THEN** both payments are skipped; equal gross logs INFO, different gross logs one WARNING with both dates, both gross values and "check manually"; exit status is unchanged.

Check: `.venv/bin/python -m pytest -q tests -k dividend_proximity_amount`.

### Requirement: Current operational limits

The connector SHALL retain documented boundaries: 365-day guidance; daily data; manual corporate actions/history/token renewal; additive corrections; proximity skips of distinct payments next to manual or legacy rows (warned, never imported); UTC dates; unconverted cash/commission currencies; Yahoo quality; net, nonchronological checks; nontransactional buy/sell phases; preview without server acceptance; buffered 10 MiB Flex responses; no overlap protection.

#### Scenario: Operator checks limits
- **WHEN** limitations are read
- **THEN** these boundaries are visible, and `GHOST_CURRENCY` is not documented as a setting.

### Requirement: Actionable historical dividend evidence

The source `YYYYMMDD` SHALL remain the IBKR business day. Historical identity SHALL compare it with the destination instant's calendar day in `TZ`. An absent destination profile ISIN SHALL be unavailable evidence and SHALL NOT block amount comparison; a nonempty conflict SHALL fail identity.

Dry-run details SHALL name each failed or unavailable active/id/data-source/symbol/date/ISIN check with expected/observed values. Human blocks SHALL show security, source and destination UTC/local dates, activity IDs, and supported quantity/gross/fee/currency. INFO SHALL count failed checks. Canonically absent sources skipped by import deduplication SHALL remain absent and SHALL name the skip path that import selection takes, with the same predicate and input set (connector-comment rows excluded), in its order: `skipped by historical comment` when the account's old `dividend#<symbol>#<date>` comment is among the existing dividend comments of any activity, active or not; otherwise `skipped by proximity`. Each SHALL show the available weak-candidate values and active status; `skipped by proximity` SHALL also show source and candidate gross. Neither label SHALL certify identity. A finding left uncertain by missing, unsupported or conflicting currency context SHALL keep its reason and SHALL show the observed source and destination currency values and provenance. Outside-window rows SHALL show destination security, date, and values. No finding SHALL repair data or change selection.

Baseline: the v2.5.0 dry run emitted 114 opaque findings. Saved evidence measured missing profile ISIN in 44/44 groups, Paris-midnight dates in 5/44, and no other failed identity checks. The first replay of this change passed identity for 44/44 and compared 39: three unproven component partitions, two unsupported-currency (KRW) groups, and two absent groups skipped by old symbol comments but labeled proximity.

#### Scenario: Separate identity checks and local dates
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_identity'` exercises all six checks, Paris winter/summer dates, absent ISIN, and conflicting ISIN
- **THEN** each check exposes expected/observed values, local calendar matches certify date, missing ISIN permits amount comparison, and conflicting ISIN blocks it.

#### Scenario: Actionable private report
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_actionable'` exercises outside-window rows and proximity skips
- **THEN** private human-readable details and aggregate counts expose the required evidence without certifying weak identity or changing data.

#### Scenario: Skip cause and observed currency
- **WHEN** `.venv/bin/python -m pytest -v tests -k 'historical_diagnostic_skip_cause'` exercises an absent group with an old symbol comment and a proximity candidate, the same with an inactive comment carrier, an absent group with only a proximity candidate, an absent group whose only nearby row is canonical, and unsupported, missing and conflicting source/destination currency context
- **THEN** the first two show `skipped by historical comment`, the third `skipped by proximity` with both gross values, an absent group whose only nearby row has a connector comment is not proximity-skipped, each finding stays absent or uncertain, currency findings keep their reason and show observed source/destination currency and provenance, and import selection is unchanged.

#### Scenario: Real read-only acceptance
- **WHEN** the operator-authorized `DRY_RUN=1 LOG_LEVEL=DEBUG .venv/bin/python ibkr_to_ghostfolio.py` runs with the approved real-data ENV and private log capture
- **THEN** zero financial writes occur; all 44 previously blocked groups pass the active, id, data-source, symbol and local-date checks, with ISIN pass or unavailable; each reaches exact amount comparison or stays uncertain only with `component partition identity not proven` or a currency-context finding that shows the observed currency, never a component assignment inferred from amounts; the outcome matches the replay baseline of 39 compared, 3 unproven partitions and 2 unsupported currency, and any other cause or count fails acceptance and is reported; every remaining anomaly is explainable from the log; both absent groups log `skipped by historical comment`, reconciled with their evidence rows; and both unsupported-currency groups show a `currency context:` line naming KRW.
