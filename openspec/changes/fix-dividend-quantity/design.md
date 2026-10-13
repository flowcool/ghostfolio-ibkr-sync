# Design

## Context

See proposal.md. Today, `parse_cash_dividends` keeps the last positive description; `convert_dividend_to_activity` extracts one rate.

## Goals / Non-Goals

**Goals:** sufficient quantity evidence inside the existing runtime.

**Non-Goals:** new grouping identities, modules or shared-helper changes.

## Decisions

Retain signed payment/component evidence in `parse_cash_dividends`; distinguish observed ordinary/bonus labels from portions paid as dividend/payment-in-lieu. Net reversals before evaluating components; preserve final positive replacement rates. Ambiguous component matching uses fallback, rather than guessing.

Reuse `convert_dividend_to_activity` rounding and total-derived price, `minor_unit_conversion`, withholding handling and existing comment construction. Validate complete rate tokens; simple comma removal would accept malformed numbers. Use existing logging for reasoned fallback warnings; notification/exit behavior stays unchanged.

Ghostfolio accepts numeric nonnegative quantity/price and calculates dividend income from their product; DIVIDEND does not change holdings. Sources: upstream 3.80.2 [validation](https://github.com/ghostfolio/ghostfolio/blob/3.80.2/libs/common/src/lib/dtos/create-order.dto.ts), [calculator](https://github.com/ghostfolio/ghostfolio/blob/3.80.2/apps/api/src/app/portfolio/calculator/portfolio-calculator.ts), [position factor](https://github.com/ghostfolio/ghostfolio/blob/3.80.2/apps/api/src/helper/portfolio.helper.ts); identical constraints checked in 3.86.0.

## Risks / Trade-offs

One-unit fallback preserves income but loses per-share meaning. Incompatible/partially rated components are preventive synthetic coverage, not observed report defects. Keep private XML outside Git.

## Migration Plan

Future deployment requires separate authorization. Rollback: revert implementation and restore the prior image digest; imported activities remain. Proposal rollback: revert its document commit.
