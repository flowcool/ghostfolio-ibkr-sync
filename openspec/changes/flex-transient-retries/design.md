# Design

## Context

See proposal.md. `fetch_flex_report` currently rejects every failed SendRequest; GetStatement polls Warn/1019 ten times. `_ibkr_get` already retries connection errors/timeouts after 10/30 seconds. Keep those separate.

## Goals / Non-Goals

**Goals:** bounded recovery using documented numeric codes and existing safeguards.

**Non-Goals:** new ENV settings, dependencies, financial logic, sibling Ghostfolio helpers or broader GetStatement retry classification.

## Decisions

- In `fetch_flex_report`, retry SendRequest codes 1001, 1004–1009, 1018, 1019 and 1021. The [official IBKR table](https://www.ibkrguides.com/clientportal/performanceandstatements/flex3error.htm) explicitly advises another attempt for these codes. Treat 1010–1017/1020 as requiring correction; stop conservatively for 1003, absent and unknown codes. Message matching could misclassify translated or altered responses.
- Use a fixed `(60, 120, 300, 600)` schedule: five attempts, 1080 seconds of sleeps. This preserves the approved minute-scale backoff below twenty minutes of scheduled waits. A configurable policy would add an unnecessary operational surface.
- Reuse `_ibkr_get`, the per-response XML size check, XML parsing and `_redact` on every attempt and final error. Stop immediately after Success; use only its reference and existing validated URL. Log retry code, attempt and delay without token, URL or XML dumps. Do not sleep after final SendRequest failure.
- Keep GetStatement's existing loop, Warn/1019 condition and explicit overrides; change default `max_retries` to 60 with `retry_delay=5`. Five minutes is a bounded increase over fifty seconds. Preserve the existing final-pending sleep and immediate 1018/other-error failures.
- Reuse `script_flex` and patched `time.sleep` for synthetic HTTP tests; assert requests, sleeps, last error, redaction and security regressions. Put retry guidance in README with the same values.

## Risks / Trade-offs

- Longer failed runs → finite application budgets; HTTP duration and existing network retries add time. This is not a twenty-minute wall-clock guarantee.
- Unknown future IBKR codes → immediate failure; extend the allowlist only after evidence.
- Warn may lack a code → preserve existing compatibility, without broadening error retries.

## Migration Plan

No configuration migration. After approved implementation, archive the change, replay mocked scenarios on main and deliver through an operator-authorized stable release. Record the installed digest before upgrade. Roll back by selecting the prior image digest and recreating the container with unchanged ENV/mounts under separate operator authorization. Financial records remain. A main revert alone does not republish `latest` under `release-publication`.
