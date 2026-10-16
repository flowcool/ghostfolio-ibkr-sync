# Design

## Context

Legacy identity is account-local; proximity sees v2; short imports pass.

## Decisions

1. Add a pure parser beside `ghost_get_existing_orders`. Reserve exact `IBKR#v`; preserve legacy comments.
2. Build and validate the global v2 index before the account loop. Extend `dividend_dedup_decision` with action coverage and legacy precedence. Exclude v2 from proximity and diagnostics.
3. Reuse `accepted_import_subset`. Keep known returned rows, fail omissions without retry, and continue sales from accepted holdings, cash and later accounts.
4. Amend ADR 0002 and README. A later change owns writes and migration.

## Risks and rollback

One-account evidence forbids numeric-only constraints. rc.5 needs a GO after rc.4. Before v2 writes, restore rc.4. Afterwards, rc.5 is the rollback floor.
