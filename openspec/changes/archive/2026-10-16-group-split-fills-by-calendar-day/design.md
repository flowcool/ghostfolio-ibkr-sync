# Design

## Context

`filter_trades_by_holdings()` first calls `_match_manual_entry()`. That helper already uses `parse_ibkr_datetime()` to decide whether a fill is within the ±2-day manual-match window. An ambiguous fill therefore has a supported parsed timestamp before it reaches split-fill grouping.

## Goals / Non-Goals

**Goals:** Preserve calendar-day identity across every supported IBKR timestamp format.

**Non-Goals:** Change parsing, the manual-match window, quantity tolerance, ticker resolution, or import policy.

## Decisions

- Reuse `parse_ibkr_datetime()` in `filter_trades_by_holdings()` and take the `YYYY-MM-DD` prefix from its ISO result. Slicing the raw value is format-dependent.
- Preserve side, resolved ticker, and ISIN in the key. These dimensions prevent unrelated fills from reconciling.
- Keep the existing invalid-timestamp outcome. `_match_manual_entry()` cannot return `ambiguous` without a parsed timestamp; a defensive fallback preserves the old raw key if that invariant ever changes.
- Test compact and dashed same-day fills, plus dashed fills on two days of one month. The different-day test verifies that the manual entry is not consumed.
- No sibling propagation is required. This is IBKR Flex trade reconciliation, not a projected Ghostfolio helper.

## Risks / Trade-offs

- **Risk:** Parsing each ambiguous fill twice adds work. **Mitigation:** The input is bounded by the Flex window, and correctness is more important than a new cache or data shape.
- **Risk:** Separate ambiguous groups produce one warning per day. **Mitigation:** That matches the manual-action boundary and avoids silent suppression.

## Migration Plan

Merge after synthetic tests and the full repository gate pass. Roll back by reverting the merge commit.
