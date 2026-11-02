# Design

## Context

See `proposal.md`. `parse_ibkr_datetime` in `ibkr.py` strips the Flex suffix and labels wall time as UTC. Saved query 1671605 contains 105 qualified rows with EST or EDT. The suffix identifies the query account timezone, not the exchange timezone.

## Goals / Non-Goals

**Goals:** correct new timestamps; reject unknown qualified tokens before account writes; compare dates by configured local day; preserve review evidence.

**Non-Goals:** a new conversion tool, historical writes, production service access, or sibling propagation.

## Decisions

1. Reuse `parse_ibkr_datetime`. Accept only fixed offsets EST=-05:00 and EDT=-04:00. Use no IANA lookup for source tokens. New tokens require a new change. Configured IANA `TZ` still controls local-day comparison.
2. Keep the event-only `IBKR#v2` identity. Reuse `date_eligible` and the reviewed correction path. The same local day is date-compatible, even when intraday times differ. It produces no date proposal and remains eligible for comment-only migration when other checks pass. A different local day requires reviewed correction; permissive retains its two-day BUY/SELL and three-day DIVIDEND limits.
3. Repair stored dates only through the existing reviewed correction path: manual `yes`, or profile authority where allowed. Require backup, durable journal and exact readback. Normal sync never rewrites stored dates. After release, any repair needs a separate operation step and operator GO. Build no new conversion tool.
4. Extend the existing cash preflight to reject an unknown qualified token on any Trade, CashTransaction, ChangeInDividendAccrual or CorporateAction. Fail the account before all financial writes, including cash and platform updates. Do not force `DRY_RUN`. Preserve supported unqualified legacy forms and existing cash prerequisites.

## Risks / Trade-offs

- **[Risk]** The account-token assumption is wrong. → G6 checks every saved Trade: its converted UTC date must be within one day of `tradeDate`. Any violation fails the gate and invalidates the assumption.
- **[Risk]** Corrected dates affect matching. → Run G1–G6. Include intraday legacy compatibility and US switch days 2026-03-08 and 2026-11-01 with both explicit tokens.

## Migration Plan

Replay copied backup XML offline. Retain inputs and results separately under ignored worktree `tmp/`. Release as a minor version. State that new activities get corrected instants and stored activities are not rewritten. Rollback is a code revert. Flag downstream propagation only if a shared helper changes; `parse_ibkr_datetime` is IBKR-specific.
