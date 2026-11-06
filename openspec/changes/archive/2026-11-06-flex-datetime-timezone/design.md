# Design

## Context

See `proposal.md`. `parse_ibkr_datetime` in `ibkr.py` already converts qualified EST/EDT clocks to UTC. The suffix identifies the query account timezone, not the exchange timezone. This is correct for execution instants. Cash payment posting clocks must instead retain their written calendar day under R3 below.

## Goals / Non-Goals

**Goals:** correct new execution instants and payment calendar days; reject unknown qualified tokens before account writes; compare dates by configured local day; preserve review evidence.

**Non-Goals:** a new conversion tool, historical writes, production service access, or sibling propagation.

## Decisions

1. Reuse `parse_ibkr_datetime`. Accept only fixed offsets EST=-05:00 and EDT=-04:00. Use no IANA lookup for source tokens. New tokens require a new change. Configured IANA `TZ` still controls local-day comparison.
2. Keep the event-only `IBKR#v2` identity. Reuse `date_eligible` and the reviewed correction path. The same local day is date-compatible, even when intraday times differ. It produces no date proposal and remains eligible for comment-only migration when other checks pass. A different local day requires reviewed correction; permissive retains its two-day BUY/SELL and three-day DIVIDEND limits.
3. Repair stored dates only through the existing reviewed correction path: manual `yes`, or profile authority where allowed. Require backup, durable journal and exact readback. Normal sync never rewrites stored dates. After release, any repair needs a separate operation step and operator GO. Build no new conversion tool.
4. Extend the existing cash preflight to reject an unknown qualified token on any Trade, CashTransaction, ChangeInDividendAccrual or CorporateAction. Fail the account before all financial writes, including cash and platform updates. Do not force `DRY_RUN`. Preserve supported unqualified legacy forms and existing cash prerequisites.

## Risks / Trade-offs

- **[Risk]** The account-token assumption is wrong. → G6 checks every saved imported Trade (`assetCategory` outside `SKIP_ASSET_CATEGORIES`): its converted UTC date must be within one day of `tradeDate`. `CASH` and `OPT` rows are excluded from import before date use. FX `tradeDate` is a value date that can move across a weekend. Any violation in a non-skipped category blocks G6 and invalidates the assumption.
- **[Risk]** Corrected dates affect matching. → Run G1–G6. Include intraday legacy compatibility and US switch days 2026-03-08 and 2026-11-01 with both explicit tokens.

## Migration Plan

Replay copied backup XML offline. Retain inputs and results separately under ignored worktree `tmp/`. Release as a minor version. State that new activities get corrected instants and stored activities are not rewritten. Rollback is a code revert. Flag downstream propagation only if a shared helper changes; `parse_ibkr_datetime` is IBKR-specific.

Corporate-action Trade readers match the event security by ISIN and contract before parsing dates. CASH/FX rows without an ISIN do not feed these dates. A regression covers a CASH row outside the imported-category G6 bound.

Preserve effective destination currency comparison from the preceding change. Retain journal version 3 and its immutable comparison policy. Same-local-day handling applies only when constructing new proposals; exact journal recovery still compares the full stored instant.

## Calendar-day correction (R1–R5)

Trade `dateTime` defines an execution instant. `tradeDate` defines its exchange
business day. Use an explicit venue-to-IANA table for KRX, TSEJ, LSE, NASDAQ,
NYSE, ARCA, BYX and TSE. Unknown venues stay unchecked. Do not infer a zone from
a currency, symbol, SMART route or ambiguous dark-pool code. Missing or invalid
`tradeDate` for a known venue, or a day mismatch, holds the trade with a reason
before import and review conversion. CASH and OPT stay excluded before this check.

Cash dividend, payment-in-lieu and withholding clocks are ledger posting clocks.
Validate their complete source text with the existing token rules. Then read the
calendar day as written. Do not convert the clock to UTC to obtain this day.
Apply the same rule to qualified and date-only accruals. Keep the payment at
00:00 UTC. Keep `IBKR#v2` unchanged. No stored activity is converted automatically.

ENV `TZ` controls local-day tolerance, diagnostic display and scheduling. It must
equal the Ghostfolio server TZ. Log the validated timezone at startup. It must
never change the source value or canonical replacement timestamp. Local-day
eligibility and preservation of a compatible stored instant can still depend on TZ.
Use stdlib `zoneinfo`; add no dependency.

Ghostfolio 3.96.0 formats table dates in the browser timezone. Its portfolio
calculator derives valuation dates in the server process timezone. Thus 00:00Z
can display or value on the previous day west of UTC. Keep this known limit.
A noon-UTC anchor would avoid the demonstrated western-zone shift, but needs a
historical-data conversion under a separate operator GO. It cannot preserve a
single day in every possible timezone. Trades retain their actual instant.
Pinned source: Ghostfolio tag 3.96.0, commit
`2f21c2558684e8cc9974f1b2da683992a83ef3cb`, value.component.ts (browser) and
portfolio-calculator.ts (server). Native lab measurement remains a release task.

Offline acceptance: full pytest and `scripts/check.sh`; cover US switch days,
19:00–23:59 EST/EDT, the four requested comparison zones, review, accruals,
deduplication and identity migration. Roll back with a code revert. Preserve
journals and historical activities. Labs and release remain outside this PR.
