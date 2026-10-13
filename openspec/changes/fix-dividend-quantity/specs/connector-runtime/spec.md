# Spec Delta

## MODIFIED Requirements

### Requirement: Flex selection and conversion

The connector SHALL select Trade children, exclude CASH/OPT, aggregate DETAIL dividend/payments-in-lieu/withholding by security/day, and select BASE_SUMMARY cash. Other cash types/levels and AssetSummary SHALL be ignored. Trade type SHALL be BUY for exact BUY, otherwise SELL. Quantities/prices SHALL be absolute; commission/withholding costs become fees, refunds/rebates clamp to zero. Nonpositive payments SHALL skip.

Dividend `<CCY> <rate> PER SHARE` rates SHALL accept positive finite numbers with optional decimal fractions and valid comma thousands grouping. Unrated payments-in-lieu SHALL NOT erase usable rates. Single-rate dividend/payment-in-lieu groups SHALL derive quantity from combined gross payment. Derived quantities SHALL use existing rounding: whole shares within strictly 1%, then six decimals. Ordinary/bonus components SHALL retain one common quantity only when their independently derived quantities coincide after this rounding. Reversal/replacement netting and the final positive replacement rate SHALL remain preserved.

Missing, malformed, ambiguous or incompatible quantity evidence, including partially rated ordinary/bonus components, SHALL produce quantity 1, unitPrice equal to gross payment before minor-unit scaling, and a WARNING explaining the reason. A reliably derived one-share quantity SHALL NOT trigger that warning. Gross income, withholding, minor-unit scaling, account/date/currency and stable dividend comment identity SHALL remain preserved. README SHALL explain conversion and fallback.

Commands below run offline; new scenarios name planned synthetic tests and expect passing assertions.

#### Scenario: Selected records
- **WHEN** Flex rows are parsed/converted
- **THEN** selection/aggregation applies; London GBP price/fee scale together to GBp.

Baseline evidence: README “How activities are converted”; `python3 -m pytest -q tests/test_parsing.py tests/test_conversion.py`.

#### Scenario: Thousands-formatted rate
- **WHEN** rates contain `1,234` or malformed `12,34`
- **THEN** the valid rate derives quantity; the malformed rate falls back with WARNING.

Check: `python3 -m pytest -v tests/test_conversion.py -k dividend_rate_format`.

#### Scenario: Dividend and payment in lieu
- **WHEN** rated dividend 20 at 0.25 and unrated payment-in-lieu 5 appear in either order
- **THEN** one activity has quantity 100 and gross income 25.

Check: `python3 -m pytest -v tests/test_parsing.py -k dividend_pil_quantity`.

#### Scenario: Ordinary and bonus
- **WHEN** components 25/0.25 and 75/0.75 appear in either order
- **THEN** one activity has quantity 100 and unitPrice 1; rounding-compatible quantities also agree.

Check: `python3 -m pytest -v tests/test_parsing.py -k dividend_common_quantity`.

#### Scenario: Uncertain quantity and legitimate one share
- **WHEN** quantity evidence is absent, partial or incompatible, or reliably implies one share
- **THEN** gross income remains exact; only uncertain cases emit fallback WARNING.

Check: `python3 -m pytest -v tests/test_conversion.py -k dividend_quantity_fallback`.

#### Scenario: Corrections and preserved accounting
- **WHEN** payments include reversals/replacements, withholding/refunds or minor-unit currencies
- **THEN** final payment/rate, fees, rounding and identity remain correct; nonpositive totals skip.

Check: `python3 -m pytest -v tests/test_parsing.py tests/test_conversion.py`.
