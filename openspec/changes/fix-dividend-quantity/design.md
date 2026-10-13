# Design

## Context

One account/annual window supports the proposed associations, not universal IBKR semantics.

## Goals / Non-Goals

Preserve payment evidence; no historical certification/persistence.

## Decisions

Extend `parse_cash_dividends` with signed action totals/accrual revisions; compare decimal quantities before numeric conversion. Remove unreliable description inference.

Reuse `convert_dividend_to_activity`, `minor_unit_conversion` and source totals; derive price from cash.

In `process_account`, distinguish missing attributes from empty values. Reuse account/comment deduplication and `_dividend_date_matches` before quantity checks. Local rejection logs SHALL NOT affect account outcome/finalization. Other failures remain unchanged. Shared helpers remain unchanged.

## Risks / Trade-offs

Short windows/quantity revisions → reject/retry. Unobserved accounts/windows require evidence, not relaxed matching.

## Migration Plan

README/setup SHALL follow docs/releasing.md compatibility notices. Enrich the query, preserve existing sections/settings, back up Ghostfolio, record prior digest, then upgrade. Rollback restores the image; extra fields remain; financial recovery is separate.
