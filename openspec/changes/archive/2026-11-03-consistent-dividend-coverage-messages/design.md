# Design

## Context

`historical_dividend_findings` records destination rows that have no source
claim. `classify_dividend_findings` currently sends the
`destination outside proven source coverage` reason through the generic
uncertain-to-check branch. `log_historical_dividend_comparison` already knows
that this reason is an evidence limitation and does not call `record_action`.
This creates the contradictory block and companion messages.

## Decisions

1. Convert the existing `DIAGNOSTIC_LIMITATIONS` reasons from `to_check` to
   informational `evidence limitation` findings after ordinary classification. Reuse `_readable_set` and `_readable_action` so
   the block remains visible and says `No action needed.`
2. Keep `DIAGNOSTIC_LIMITATIONS` and the no-correction companion message. The
   same limitation remains explicit, while the detailed block and summary now
   carry the informational class.
3. Use the existing `DIAGNOSTIC_LIMITATIONS` policy for detailed action text too.
   Do not change `diagnostic_requires_action`, source coverage calculation,
   import selection or financial writes. Concrete discrepancies keep their
   existing `to_check` and notification behavior.
4. Add a synthetic 15-row regression for active/inactive rows and a mixed case. Assert the report has 15 informational
   blocks, zero to-check blocks and no `dividend_check` action. Assert the
   operator guide states the same rule. Check all named limitation reasons.

## Rollback

Revert the classification, tests and documentation commit. No runtime state or
financial data changes.
