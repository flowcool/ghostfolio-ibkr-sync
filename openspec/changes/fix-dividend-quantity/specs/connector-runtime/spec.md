# Spec Delta

Future checks SHALL assert synthetic inputs/mocked HTTP; never select zero tests.

## MODIFIED Requirements

### Requirement: Flex selection and conversion

The connector SHALL select Trade children excluding CASH/OPT, DETAIL dividend/PIL/withholding grouped by security/day, and BASE_SUMMARY cash; ignore other cash types/levels and AssetSummary. Trades SHALL use BUY for exact BUY, otherwise SELL; absolute quantity/price; commission/withholding fees with refunds/rebates clamped to zero. Nonpositive payments SHALL skip.

Cash Transactions SHALL establish payments/gross/withholding. Conversion SHALL preserve account, currency/scaling, cash-day UTC date/comment. Description inference and one-unit fallback SHALL be removed.

Each net-positive action SHALL require identical nonempty `accountId/conid/currency/actionID/exDate`, one unique `Re` with `payDate` matching cash day, and matching `date` OR `reportDate`. Associated quantities SHALL agree as positive finite decimals before numeric conversion, without rounding/tolerance. `Re` alone SHALL NOT establish payment.

Dividends/PIL and distinct ordinary/bonus actions SHALL use one common quantity, never sum quantities. Zero-net actions SHALL provide no quantity; negative-net actions/mixed currencies/incompatible evidence SHALL reject the group. Results SHALL be row-order independent. Price SHALL be cash gross/quantity, irrespective of accrual money/rate. After numeric conversion/minor-unit scaling, quantity/price SHALL remain positive finite and fee nonnegative finite; overflow/positive underflow SHALL reject the group.

#### Scenario: Selected records
- **WHEN** baseline selection/conversion is replayed with enriched fixtures
- **THEN** selection/gross/fees/scaling/date/identity remain unchanged.

Baseline: README conversion table. Check: `.venv/bin/python -m pytest -q tests/test_parsing.py tests/test_conversion.py`.

#### Scenario: Quantity association
- **WHEN** fixtures cover unrated PIL (3 shares/gross 1.5), quantity 450 versus inferred 451, fractions/one-share, earlier date/late reportDate, wrong keys/dates, multiple Re, missing/invalid/conflicting quantities, Re without cash
- **THEN** supported quantities remain unchanged; unsupported groups reject; Re creates no payment.

Check: `.venv/bin/python -m pytest -v tests -k dividend_structured_quantity`.

#### Scenario: Final numeric limits
- **WHEN** fixtures cover quantity `1e-400`/`1e400`, decimal conflicts collapsing to one numeric value, price overflow/underflow, and GBP→GBp overflow of price/fee alongside normal scaling
- **THEN** unsafe groups reject locally, decimal conflicts before conversion; valid quantity/price/fee/cash totals remain correct.

Check: `.venv/bin/python -m pytest -v tests -k dividend_structured_numeric`.

#### Scenario: Components and money
- **WHEN** fixtures include split PIL, ordinary/bonus at equal/different rates, unequal quantities, signed zero/negative actions, mixed currencies and differing accrual gross/tax/rate
- **THEN** valid groups retain quantity/cash totals; invalid groups reject; permutation/accounting/identity assertions pass.

Check: `.venv/bin/python -m pytest -v tests -k dividend_structured_components`.

## ADDED Requirements

### Requirement: Enriched dividend input and local rejection

Processing SHALL extract cash identity without quantity checks, deduplicate by account/comment/proximity, then validate new candidates; existing activities remain untouched/unverified.

ChangeInDividendAccruals SHALL be mandatory. Required attributes SHALL cover candidate payment/relevant accrual keys, plus `quantity/code/date/payDate/reportDate` on relevant accruals. Nonempty key mismatches SHALL exclude unrelated accruals; missing keys SHALL NOT prove irrelevance. Unrelated rows SHALL NOT block candidates. Withholding SHALL retain cash grouping without accrual-schema requirements. Missing section/relevant attributes SHALL block account dividends; present-but-empty evidence SHALL reject affected groups. Empty sections without payments SHALL be valid.

Rejections SHALL log distinct incompatibility/missing/contradiction reasons, never mark rejected payments imported, leave trades/cash operating, and SHALL NOT change success/exit/notifications. Other failures SHALL retain existing behavior.

#### Scenario: Compatibility and isolation
- **WHEN** old/empty/short-window exports, malformed unrelated rows beside valid candidates, relevant missing attributes versus empty values, and existing dividends with invalid/conflicting quantities are processed
- **THEN** identity→dedup→quantity order, rejection scopes/logs/retries, unrelated-row isolation and unchanged outcomes are asserted.

Check: `.venv/bin/python -m pytest -v tests -k dividend_structured_input`.

### Requirement: Forward dividend upgrade guidance

README/setup SHALL require enrichment before upgrade, explain rejections/removed inference and backup/prior-image-digest rollback without financial restoration. Extra fields SHALL retain prior-runtime compatibility.

#### Scenario: Upgrade inspection
- **WHEN** guidance is inspected
- **THEN** preparation/ENV/mounts and historical boundaries are explicit.

Check: `rg -n -A 35 'structured|enrich|rollback' README.md docs/ibkr-setup.md`.
