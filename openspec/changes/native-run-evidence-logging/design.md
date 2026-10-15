## Context

The removed lab adapter emitted `LAB_EVIDENCE` JSON. Preserve its `window`, `preview` and `cash` value shapes so the consumer can use native logs.

## Goals / Non-Goals

Add three DEBUG evidence kinds in one task. Keep existing behavior and INFO output unchanged. Do not add run metadata, lifecycle events, import stages or provider requests.

## Decisions

Use a small logging helper in the single runtime file. It serializes compact JSON with `allow_nan=False` and calls `log.debug`. Skip serialization when DEBUG is disabled. If a value cannot be serialized as finite JSON, omit that evidence without changing the financial operation. The lab rejects missing evidence.

- `fetch_flex_report`: after each successful fetch, reuse `historical_dividend_report_window`. Emit its two-date tuple as a JSON list, or null when bounds are unavailable. Do not invent a period or add a guard.
- `ghost_import_activities`: in dry run, emit the full input list once per call, including an empty list. Keep every payload field and timezone-qualified date. Keep the readable preview unchanged. Emit no preview in real mode.
- `ghost_update_cash_balance`: after existing currency guards, emit the target before the dry-run return or PUT. Use `accountId`, `balance` and `currency`. Do not round balance. This line describes a target, not confirmed stored state.

Each message is `LAB_EVIDENCE ` plus an object with only `kind` and `value`. The normal timestamp and DEBUG prefix precede it. JSON escaping keeps each message on one physical line. Do not serialize configuration, ENV, XML, URLs, headers or credentials.

## Risks / Trade-offs

Private logs contain payload identifiers and financial values. Use synthetic public examples. Missing or nonfinite evidence cannot prove lab acceptance. Stored-state readback and provider checks remain external.

## Verification and Rollback

Use synthetic reports and mocked HTTP. Compare formatted INFO bytes with the pre-change implementation under a fixed timestamp. Check exact payload equality, precision, escaping, invalid bounds, nonfinite values and existing guard results. Run the full offline pytest suite. Revert the code commit to remove the logs. The coordinator owns archive and release.
