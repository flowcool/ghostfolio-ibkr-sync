# Design

## Context

See proposal.md. `finalize_run` ignores ordinary successful warnings. `RunOutcome` has no user-action inventory. `log_historical_dividend_comparison` emits items to check at INFO. Python logs to stderr; Supercronic wraps those lines at INFO.

## Goals / Non-Goals

Make required actions explicit without changing financial decisions. Keep existing state, approvals, retries and exit codes. Add no alert database or logging dependency.

## Decisions

- Every repeated reminder needs a concrete user action and observable resolution proof. Representation limits and automatically retried maintenance stay visible without manufacturing an impossible user action.
- Log `ghostfolio-ibkr-sync build <APP_VERSION>` so a stable image copied from a qualified RC does not present its build provenance as a published release version.

- Extend `outcome.py` with typed, run-local action records and fixed public reason codes. Existing selectors, converters, review and diagnostic functions return reporting evidence to `process_account` and `run_sync`. Register decisions explicitly; do not infer actions from log text or count every WARNING. Recompute relevant checks from acquired reports and existing destination/review evidence, including deduplicated events. Group repeated observations of one event/reason without adding them twice. Separate records that need user action from approved work awaiting a later cycle.
- Reuse `finalize_run`, `build_failure_summary` and `send_notification`. Add required-action counts and safe instructions to the existing single dispatch. Failures retain priority. Report disabled, invalid, sent, failed, timeout and not-required delivery states. Keep worker isolation and one attempt. Existing corporate notification fingerprints remain independent; no fingerprint suppresses an active required action.
- Reuse `process_review`, `classify_dividend_findings` and the current formatters. Report unique held events separately from proposal counts. Explain normal approval, missing proof, historical maintenance and uncertain requests. Reuse configured container paths and document volume resolution. Avoid Docker socket access or a host-path ENV.
- Use two filtered standard logging handlers in `__main__.run`: DEBUG/INFO to stdout; WARNING and above to stderr. Preserve message text and LAB_EVIDENCE payloads. Start pinned Supercronic with `-passthrough-logs -split-logs`; its own lifecycle logs remain distinguishable. Verified v0.2.51 `main.go` flags and `cron/cron.go:runJob` connect child streams directly. Redirecting stderr alone would preserve the misleading wrapper.

## Risks / Trade-offs

Daily reminders can repeat. Florent chose repetition until resolution. Missing source evidence does not prove resolution. Report retained limits. Existing source windows do not establish lifetime coverage.

Incorrect instructions could authorize a write. Keep blocked and maintenance cases distinct; never recommend bulk yes or journal edits.

## Migration Plan

Prove offline action, transport and privacy cases. Update user guidance. No file-schema migration. Follow the existing release and lab gates under their authority. No production activation here. Local rollback reverts the change; deployed rollback uses the last compatible reader and preserves all state and journals.
