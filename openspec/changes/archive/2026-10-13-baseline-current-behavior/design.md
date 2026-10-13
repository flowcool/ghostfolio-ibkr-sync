# Design

## Context

See proposal.md. Source: `5e43c60`. Main specs are empty. Private report SHA-256:
`8a50478e135af8e0ac2deac72d5aab3248c4915807622204e589512461926df4`.

## Goals / Non-Goals

**Goals:** traceable current behavior.

**Non-Goals:** runtime changes.

## Decisions

README/tests prove scenarios; the real report proves inventory. No production simulation log was found; a synthetic report was rejected.

Existing mechanisms: startup `load_config`/`load_mapping`/`ghost_exchange_access_token`/`entrypoint.sh`; input `fetch_flex_report`/`parse_trades`/`parse_cash_dividends`/`parse_cash_report`; conversion `resolve_symbol`/`convert_trade_to_activity`/`convert_dividend_to_activity`/`minor_unit_conversion`; reconciliation `ghost_get_existing_orders`/`filter_trades_by_holdings`/`_dividend_date_matches`; writes `process_account`/`accepted_import_subset`/`ghost_import_activities`/`ghost_update_cash_balance`; outcomes `finalize_run`/`legacy_token_expiry_days`/`send_notification`.

Sibling mechanisms: ghostfolio-degiro-sync copies this file's Ghostfolio import, readback and cash helpers as `ghostfolio_core.py`; a helper change flags downstream propagation. Schedule (`entrypoint.sh`, five numeric CRON fields) matches the siblings. Unlike them, IBKR writes when DRY_RUN is absent.

Real-report observation: `convert_dividend_to_activity` books 8 of 46 dividend groups as one unit. Causes: a rate with a thousands separator (`KRW 1,234 PER SHARE`) does not match; a same-day payment in lieu, which has no rate, follows the dividend row and replaces its description (6 groups); one payment in lieu stands alone. The total stays correct; quantity and per-share price do not.

Retain unknowns; propose no repairs.

## Risks / Trade-offs

One report cannot establish absent categories or server acceptance. Grouped scenarios leave detailed edge cases in cited sources. Preserve private XML/manifest: Git cannot reproduce inventory alone.

## Migration Plan

None. Separate authorization for apply/archive. Rollback: revert the document commit.

## Open Questions

Can trade IDs collide across accounts? What happens with multi-account statements, mixed-currency dividends or shared cash targets? Is the non-BUY→SELL fallback financially correct? Are other categories and `.JO`/`.TA` conversions correct on real trades? Is a one-unit dividend acceptable when a rate exists in another row or uses a thousands separator? Production outcomes remain unverified; code observations are insufficient.
