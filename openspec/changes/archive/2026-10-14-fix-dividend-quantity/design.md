# Design

## Context

One account/annual window observed; others unverified.

## Goals / Non-Goals

Preserve cash; no historical certification/persistence.

## Decisions

`parse_cash_dividends` retains cash identity/signed totals/accruals without quantity validation. `process_account` deduplicates by account/comment and `_dividend_date_matches`, then validates new candidates.

Check candidate payments/relevant accruals; nonempty key mismatches exclude accruals, missing keys do not. Withholding retains cash grouping. Missing/empty attributes retain distinct rejection scopes.

Compare quantities as decimals before numeric conversion. `convert_dividend_to_activity`/`minor_unit_conversion` derive price from cash; check final quantity/price/fee for overflow/positive underflow, including GBP→GBp. Remove inference. Rejections stay local; other failures/shared helpers remain unchanged.

## Risks / Trade-offs

Short windows/revisions → reject/retry; retain matching rules.

## Migration Plan

README/setup follow docs/releasing.md: enrich query, preserve sections/settings, back up Ghostfolio, record prior digest, upgrade. Rollback restores image; extra fields remain; financial recovery is separate.
