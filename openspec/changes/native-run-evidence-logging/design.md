## Context

See proposal.md. The existing observer captures `window`, `preview`, `provider`, `import` and `cash`. Native logs omit complete identities, outcomes and cash precision. The acceptance checks also use external snapshots and run metadata.

## Goals / Non-Goals

Expose existing financial decisions through native logs. Keep provider validation and stored-state verification in the acceptance consumer. Add no HTTP request or financial gate.

## Decisions

Use `log.debug` only (Florent 2026-10-15: evidence never at INFO; existing INFO lines unchanged) with message `RUN_EVIDENCE ` followed by compact JSON. The envelope is `v`, `runId`, `account`, `accountId`, `dry_run`, `kind`, `value`. See the delta for exact fields. JSON escapes embedded newlines and preserves payload numbers. Human-only text was rejected because it loses field identity and precision.

`main` creates the invocation ID; `run_sync` supplies account ordinals; `finalize_run` emits the normal terminal event. Missing terminal events invalidate acceptance. Existing notifications remain unchanged.

| Evidence | Native line | Existing mechanism reused |
| --- | --- | --- |
| window | `kind=window`: status, fromDate, toDate | `process_account`, `historical_dividend_report_window` |
| preview | `kind=activity`: stage, ten payload fields | `ghost_import_activities` |
| provider inputs | activity dataSource, symbol, currency | Existing converted payload |
| import | `kind=import`: requested, accepted, simulated, ok | `process_account`, `ghost_import_activities`, `accepted_import_subset` |
| cash | `kind=cash`: status, accountId, currency, balance | `ghost_update_cash_balance`, `parse_cash_report`, `parse_base_currency` |

Log proposed rows once before import retries; log accepted rows only from verified responses. Aggregate import counts once per account. Unknown acceptance is null, never zero. Cash success follows existing guards and response handling; decimal display rounding is excluded.

`log_historical_dividend_comparison` and existing creation counters retain their text. New evidence lines are separate messages, outside report blocks.

## Risks / Trade-offs

- Financial identifiers in logs → keep logs private; publish synthetic examples only; whitelist fields and exclude credentials, URLs, headers and response bodies.
- Consumer compatibility → version the grammar; migrate the external consumer separately. Its provider GET supplies marketPrice and validates the logged triple.
- Missing evidence → acceptance fails closed; connector behavior stays unchanged.

## Migration Plan

Approve first; implement one task per session. Document the grammar in README. Review shared-helper propagation downstream. Target rc.3 with a new soak. A separate release item owns archive, main replay, operator-authorized tag and pullable image. Deployment, lab gates and soak require their own authorized work. Roll back to the prior image digest and matching consumer; never undo financial records automatically.
