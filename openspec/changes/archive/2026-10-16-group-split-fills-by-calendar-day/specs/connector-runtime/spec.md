## MODIFIED Requirements

### Requirement: Mapping and duplicate reconciliation

Mapping SHALL prefer ISIN mappings, then IBKR symbols. Trade IDs SHALL suppress reimport. Manual matching SHALL use quantity and ±2 days, including summed fills. Ambiguous split fills SHALL only be summed within the same parsed calendar day, side, resolved ticker, and ISIN; nearby mismatches SHALL warn/skip. Dividends SHALL match by account/comment (including the old symbol comment), or, for existing active YAHOO dividends of the same account and symbol whose comment does not start with `dividend#` (manual or legacy rows), at ±3 days. Connector-comment rows (`dividend#…`) SHALL NOT enter the proximity index, so a distinct payment next to an imported one is imported. A proximity skip SHALL stay a skip. The comparison SHALL use the exact source gross and the existing row's quantity × unitPrice, normalized to a common major unit (minor-unit markets as in conversion) and rounded to its minor unit; an unsupported denomination SHALL be "not comparable". Equal amounts SHALL log INFO "amounts agree" with both fee values; equal amounts do not prove the same payment. Otherwise it SHALL log one WARNING naming both dates, both gross values with currencies (or "not comparable"), both fee values, and the operator action: check IBKR and add the payment by hand if it is distinct. It SHALL NOT change exit status or notifications.

#### Scenario: Existing entries
- **WHEN** existing entries match
- **THEN** duplicates are excluded; manual-buy exclusions warn.

Evidence: `python -m pytest -q tests/test_parsing.py tests/test_filters.py tests/test_orchestration.py -k 'test_resolve_symbol_prefers_mapping_then_ibkr_symbol or test_already_imported_trade_is_not_reimported or test_manual_buy_same_day_same_qty_is_not_reimported_and_warns or test_split_fills_summing_to_a_manual_sell_are_matched or test_dividend_match_window_is_exactly_three_days'`.

#### Scenario: Split-fill calendar-day boundary
- **WHEN** two ambiguous fills use supported dashed timestamps on different days of the same month and their combined quantity equals one nearby manual trade
- **THEN** the fills remain separate ambiguous groups and do not consume the manual trade; same-day dashed fills still reconcile by their sum.

Check: `.venv/bin/python -m pytest -q tests/test_filters.py -k 'split_fills'`.

#### Scenario: Distinct payment next to an imported one
- **WHEN** an active canonical row `dividend#<ISIN>#2026-07-15` (gross 25) exists and the report holds a distinct payment on 2026-07-16 (gross 100)
- **THEN** the 2026-07-16 payment is imported, no proximity log line appears.

Check: `.venv/bin/python -m pytest -q tests -k dividend_proximity_canonical`.

#### Scenario: Manual row near the payment
- **WHEN** a manual row without connector comment lies within ±3 days, once with equal gross and once with different gross
- **THEN** both payments are skipped; equal gross logs INFO "amounts agree", different gross logs one WARNING with both dates, both gross values, fee values and the operator action; exit status is unchanged.

Check: `.venv/bin/python -m pytest -q tests -k dividend_proximity_amount`.
