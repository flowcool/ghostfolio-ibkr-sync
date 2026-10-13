# Spec Delta

Future checks SHALL select passing assertions with synthetic inputs/mocked HTTP, never empty selections.

## MODIFIED Requirements

### Requirement: Flex selection and conversion

The connector SHALL select Trade children, exclude CASH/OPT, aggregate DETAIL dividend/PIL/withholding by security/day, and select BASE_SUMMARY cash. Other cash types/levels and AssetSummary SHALL be ignored. Trade type SHALL be BUY for exact BUY, otherwise SELL. Quantities/prices SHALL be absolute; commission/withholding costs become fees; refunds/rebates clamp to zero. Nonpositive payments SHALL skip.

Cash Transactions SHALL establish payments, gross and withholding. Conversion SHALL preserve account, currency/minor-unit scaling, cash-day UTC date and comment identity. Description inference and one-unit fallback SHALL be removed.

For each net-positive action, association SHALL require identical nonempty `accountId/conid/currency/actionID/exDate`, one unique `Re` with `payDate` equal to cash day, and `date` OR `reportDate` equal to that day. All associated revisions SHALL agree numerically on one positive finite representable IBKR `quantity`, without rounding/tolerance. `Re` alone SHALL NOT establish payment.

Dividends/PIL sharing an action SHALL use quantity once. Distinct ordinary/bonus actions SHALL share one quantity, never sum quantities. Zero-net actions SHALL provide no quantity; negative-net actions, mixed currencies or incompatible evidence SHALL reject the group. Results SHALL be row-order independent. Price SHALL be paid gross/quantity, positive/finite/representable, irrespective of accrual amounts, tax or gross rate.

#### Scenario: Selected records
- **WHEN** baseline selection/conversion is replayed with enriched fixtures
- **THEN** selection, gross, fees, scaling, date and identity remain unchanged.

Baseline: README conversion table. Check: `python3 -m pytest -q tests/test_parsing.py tests/test_conversion.py`.

#### Scenario: Quantity association
- **WHEN** fixtures exercise unrated PIL (3 shares, gross 1.5), quantity 450 versus inferred 451, fractional/one-share quantities, earlier date, late reportDate, incorrect keys/dates, multiple Re, missing/invalid/conflicting quantities or Re without cash
- **THEN** only exact supported associations yield unchanged IBKR quantities; unsupported groups reject; Re creates no payment.

Check: `python3 -m pytest -v tests -k dividend_structured_quantity`.

#### Scenario: Components and money
- **WHEN** fixtures include split PIL, ordinary/bonus at equal/different rates, unequal quantities, signed zero/negative actions, mixed currencies and differing accrual gross/tax/rate
- **THEN** valid groups use quantity once and cash totals; invalid groups reject; permutation, accounting and identity assertions pass.

Check: `python3 -m pytest -v tests -k dividend_structured_components`.

## ADDED Requirements

### Requirement: Enriched dividend input and local rejection

ChangeInDividendAccruals SHALL be mandatory. Required attributes SHALL be association keys on payment/accrual rows, plus `quantity/code/date/payDate/reportDate` on accrual rows. Missing section/attributes SHALL block account dividends; present-but-empty evidence SHALL reject only affected groups. Empty sections without payments SHALL be valid.

Deduplication SHALL precede quantity checks. Existing activities SHALL remain untouched/unverified. Rejections SHALL log distinct incompatibility/missing/contradiction reasons, never mark rejected payments imported, leave trades/cash operating, and SHALL NOT change global success, exit status or notifications.

#### Scenario: Compatibility and isolation
- **WHEN** old exports, empty sections with/without payments, short-window omissions, rejected groups beside valid entries, and existing dividends with changed quantities are processed
- **THEN** scope, logs, retries, deduplication and unchanged outcomes are asserted.

Check: `python3 -m pytest -v tests -k dividend_structured_input`.

### Requirement: Forward dividend upgrade guidance

README/setup SHALL require query enrichment before upgrade, distinguish rejection cases, remove inference compatibility, and explain backup/prior-image-digest rollback without financial restoration. Additional fields SHALL remain compatible with the prior runtime.

#### Scenario: Upgrade inspection
- **WHEN** guidance is inspected
- **THEN** preparation, unchanged ENV/mounts and separate historical reconciliation/maintenance are explicit.

Check: `rg -n -A 35 'structured|enrich|rollback' README.md docs/ibkr-setup.md`.
