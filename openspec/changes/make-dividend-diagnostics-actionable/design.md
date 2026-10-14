# Design

## Context

`parse_ibkr_datetime()` rejects timezone suffixes and assumes UTC. `historical_dividend_comparison()` merges six checks; its logger prints raw dictionaries. Local dividend rejection still permits cash updates.

## Goals / Non-Goals

**Goals:** validate date provenance before writes; explain every anomaly from logs.

**Non-goals:** change import dates, deduplication, stored activities, or notification transport.

## Decisions

1. `load_config()` validates IANA `TZ`. `parse_cash_dividends()` retains and validates suffixes on relevant rows. `process_account()` checks before import, cash, or platform writes, then reuses failed-account/final-notification handling. Automatic simulation cannot protect earlier accounts.
2. `parse_ibkr_datetime()` accepts suffixes but preserves general UTC conversion. `historical_dividend_comparison()` compares source business day with the Ghostfolio instant rendered through `TZ`; Flex time remains provenance, not payment instant.
3. Named evidence checks keep symbol mapping authoritative and missing profile ISIN `unavailable`. `_dividend_date_matches()` supplies weak candidates only for explanation.
4. `log_historical_dividend_comparison()` renders human blocks with exact decimal text. Coherent details stay DEBUG; others and failed-check counts use INFO.

## Risks / Trade-offs

- **Breaking query/ENV requirements** → document staged migration and prior-image rollback.
- **Flex abbreviations are not IANA zones** → use IANA `TZ` only for destination conversion.
- **Private financial logs grow** → keep one bounded block per finding and repeat the privacy warning.
