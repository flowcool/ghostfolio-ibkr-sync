# Design

## Context

`parse_ibkr_datetime()` rejects timezone suffixes and assumes UTC. `historical_dividend_comparison()` merges six checks; its logger prints raw dictionaries. Local dividend rejection still permits cash updates.

## Goals / Non-Goals

**Goals:** validate date provenance before writes; explain every anomaly from logs.

**Non-goals:** change import dates, deduplication, stored activities, or notification transport.

## Decisions

1. `load_config()` validates IANA `TZ` before processing any account. Missing or invalid `TZ` forces whole-run `DRY_RUN`, emits one WARNING, and sends the final notification with the reason even when every account succeeds (operator decision 2026-10-14: a forced preview silently stops production writes); an operator-chosen `DRY_RUN` stays silent. `parse_cash_dividends()` retains and validates relevant Flex suffixes. `process_account()` fails an account with a missing or invalid suffix before import, cash, or platform writes; suffix failure never enables `DRY_RUN`. Reuse failed-account handling.
2. `parse_ibkr_datetime()` accepts `YYYYMMDD;HHmmss TimeZone` but preserves general UTC conversion. Query 1671605 already emits it; v2.5.0 returns `None`. `historical_dividend_comparison()` compares source business day with the Ghostfolio instant rendered through `TZ`; Flex time remains provenance, not payment instant.
3. Split active/id/data-source/symbol/date/ISIN checks with expected/observed values. Keep symbol mapping authoritative and missing profile ISIN `unavailable`, not a failure; a nonempty conflicting ISIN still fails identity. The saved 44 groups (all missing profile ISIN, five Paris-midnight dates, no other failed checks) must pass identity in the real dry run: active, id, data-source, symbol and local date pass; only ISIN may be `unavailable`. Each then reaches exact amount comparison or stays uncertain with one of two closed causes permitted by the existing evidence rules (operator decision 2026-10-14, after the first replay compared 39/44): `component partition identity not proven`, or missing, unsupported or conflicting currency context with the observed currency shown. The replay baseline over these 44 groups is 39 compared, 3 unproven partitions, 2 unsupported currency; any other cause or count fails acceptance and is reported. Matching amounts never assign components. `_dividend_date_matches()` supplies weak candidates only for explanation.
4. `log_historical_dividend_comparison()` renders human blocks with exact decimal text. Coherent details stay DEBUG; others and failed-check counts use INFO.
5. An absent group names the skip path in import-selection order, with the selection's own predicate and input. `process_account()` passes its unmutated `existing_dividend_comments` set to `historical_dividend_comparison()`; this set holds every `dividend#` comment of every activity type, active or not. `(account_id, f"dividend#{symbol}#{date}") in existing_dividend_comments` yields `skipped by historical comment`, with the evidence rows that carry that comment and their active status. Only without it does a `_dividend_date_matches()` match yield `skipped by proximity`. Both stay non-certifying. Replay evidence: both absent groups were skipped by the old comment, not by proximity. Known limit: a comment carried by a non-DIVIDEND activity also skips import but has no dividend evidence row; the label still names the comment path, with no candidate. The diagnostic mirrors selection and never changes it.
6. When missing, unsupported or conflicting currency context keeps a finding uncertain, the existing reason text stays unchanged and the human block adds one line `currency context: source=<value|missing> destination=<value|missing> provenance=<activity|profile>`. Replay evidence: two groups carry KRW; the log printed only the generic reason. No currency is added to the supported list.

## Risks / Trade-offs

- **Breaking Flex prerequisite and forced ENV preview** → document staged migration and prior-image rollback.
- **Flex abbreviations are not IANA zones** → use IANA `TZ` only for destination conversion.
- **Private financial logs grow** → keep one bounded block per finding and repeat the privacy warning.
- **Acceptance below 44/44 comparisons** → only two closed causes are accepted and the 39/3/2 baseline is fixed; any other cause or count fails acceptance.
