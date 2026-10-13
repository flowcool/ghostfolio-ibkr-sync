# Spec Delta

Commands below are future offline acceptance checks: require selected passing assertions, not empty selections. Inputs SHALL be synthetic; private evidence stays outside Git.

## MODIFIED Requirements

### Requirement: Flex selection and conversion

The connector SHALL select Trade children, exclude CASH/OPT, aggregate DETAIL dividend/payments-in-lieu/withholding by security/day, and select BASE_SUMMARY cash. Other cash types/levels and AssetSummary SHALL be ignored. Trade type SHALL be BUY for exact BUY, otherwise SELL. Quantities/prices SHALL be absolute; commission/withholding costs become fees, refunds/rebates clamp to zero. Nonpositive payments SHALL skip.

Dividend rates SHALL be positive finite complete `<CCY> <rate> PER SHARE` tokens, with optional decimals and correctly grouped comma thousands separators, matching payment currency. Unrated PIL SHALL NOT erase usable evidence from unambiguously associated portions.

Ordinary/bonus distributions SHALL derive quantities separately from surviving portion totals/rates, including equal-rate distributions. Their quantities SHALL agree after existing rounding: snap to nearest positive integer only within strictly 1%, then six decimals. Use that common quantity once and derive price from total gross. Derived quantity/price SHALL be positive, finite and representable.

Signed rows SHALL cancel only unique opposite rows matching absolute amount, type, distribution label, currency and rate. Cancelled rates SHALL NOT support replacements. Ambiguous association/cancellation, partial reversals, conflicting rates, incompatible quantities, mixed currencies or missing/unrepresentable evidence SHALL cause quantity 1 with total-derived price and a reasoned WARNING. Results SHALL be row-order independent for unambiguous groups. A reliably inferred one-share result SHALL NOT warn as fallback.

Conversion SHALL preserve gross, withholding, minor-unit scaling, account, currency, UTC date and comment identity. Inferred quantities SHALL NOT certify entitlement. Fallback SHALL remain warning-only under existing outcome/notification rules.

#### Scenario: Selected records
- **WHEN** Flex rows are parsed/converted
- **THEN** selection/aggregation applies; London GBP price/fee scale together to GBp.

Baseline: README conversion table. Check: `python3 -m pytest -q tests/test_parsing.py tests/test_conversion.py`.

#### Scenario: Rates and portions
- **WHEN** rates include commas, malformed numbers, currency mismatches, overflow or dividend 20/0.25 plus unrated PIL 5 in either order
- **THEN** valid evidence derives quantity; that portion group yields quantity 100 and gross 25; unusable evidence falls back without crashing.

Check: `python3 -m pytest -v tests/test_parsing.py tests/test_conversion.py -k dividend_forward_rates`.

#### Scenario: Components and uncertainty
- **WHEN** ordinary 25/0.25 accompanies bonus 75/0.75 or 25/0.25; unique reversal/replacement changes ordinary to 30/0.30; or evidence is uncertain
- **THEN** quantities are 100, gross 100/50/105; uncertainty falls back. One-share, rounding-boundary, fee, identity and scaling assertions pass.

Check: `python3 -m pytest -v tests/test_parsing.py tests/test_conversion.py -k dividend_forward_components`.

## ADDED Requirements

### Requirement: Forward dividend upgrade guidance

README SHALL explain inference/fallback, compatibility impact, backup and prior-image-digest rollback. Existing activities and repeated income SHALL NOT be repaired by conversion. Historical dates/identities need explicit provenance; monetary reconciliation tolerances belong to the separate read-only change. Runtime rollback SHALL NOT be presented as financial restoration.

#### Scenario: Upgrade inspection
- **WHEN** operators inspect dividend guidance
- **THEN** affected inputs, unchanged deployment settings, backup, rollback and historical limits are explicit.

Check: `sed -n '/^## How activities are converted/,/^## /p' README.md`.
