# Design

## Context

`parse_ibkr_datetime()` rejects timezone suffixes and assumes UTC. `historical_dividend_comparison()` merges six checks; its logger prints raw dictionaries. Local dividend rejection still permits cash updates.

## Goals / Non-Goals

**Goals:** validate date provenance before writes; explain every anomaly from logs.

**Non-goals:** change import dates, deduplication, stored activities, or notification transport.

## Decisions

1. `load_config()` validates IANA `TZ` before processing any account. Missing or invalid `TZ` forces whole-run `DRY_RUN`, emits one WARNING, and adds the reason to the existing final notification. `parse_cash_dividends()` retains and validates relevant Flex suffixes. `process_account()` fails an account with a missing or invalid suffix before import, cash, or platform writes; suffix failure never enables `DRY_RUN`. Reuse failed-account handling.
2. `parse_ibkr_datetime()` accepts `YYYYMMDD;HHmmss TimeZone` but preserves general UTC conversion. Query 1671605 already emits it; v2.5.0 returns `None`. `historical_dividend_comparison()` compares source business day with the Ghostfolio instant rendered through `TZ`; Flex time remains provenance, not payment instant.
3. Split active/id/data-source/symbol/date/ISIN checks with expected/observed values. Keep symbol mapping authoritative and missing profile ISIN `unavailable`, not a failure; a nonempty conflicting ISIN still fails identity. The saved 44 groups (all missing profile ISIN, five Paris-midnight dates, no other failed checks) must reach amount comparison in the real dry run. `_dividend_date_matches()` supplies weak candidates only for explanation.
4. `log_historical_dividend_comparison()` renders human blocks with exact decimal text. Coherent details stay DEBUG; others and failed-check counts use INFO.

## Risks / Trade-offs

- **Breaking Flex prerequisite and forced ENV preview** → document staged migration and prior-image rollback.
- **Flex abbreviations are not IANA zones** → use IANA `TZ` only for destination conversion.
- **Private financial logs grow** → keep one bounded block per finding and repeat the privacy warning.
