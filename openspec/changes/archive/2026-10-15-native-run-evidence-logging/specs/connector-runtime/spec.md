## ADDED Requirements

### Requirement: Minimal native lab evidence

The connector SHALL emit only three new evidence kinds through `log.debug`: `window`, `preview` and `cash`. Each message SHALL be `LAB_EVIDENCE ` followed by compact JSON with exactly `kind` and `value`. The normal timestamp and DEBUG logging prefix SHALL precede the message. JSON escaping SHALL keep each message on one physical line. JSON numbers SHALL be finite. Unserializable or nonfinite evidence SHALL be omitted without changing existing operations. At INFO, output SHALL be byte-identical to the pre-change implementation. Existing behavior, guards, requests and notifications SHALL remain unchanged. Evidence SHALL NOT dump secrets, URLs, XML, ENV, configuration, headers or response bodies. README SHALL state that lab acceptance needs `LOG_LEVEL=DEBUG`.

#### Scenario: Framing and INFO compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_run_evidence.py -k 'format or info or nonfinite'` runs with synthetic inputs and mocked HTTP
- **THEN** DEBUG evidence parses on single physical lines, preserves escaped payload text and finite numbers, excludes configuration secrets, and adds no HTTP calls; formatted INFO bytes equal the pre-change output, including the per-activity preview list.

### Requirement: Flex window evidence

For each successfully fetched report, the connector SHALL emit one `window` value from `historical_dividend_report_window`. A proven value SHALL be a two-element JSON list such as `["2025-10-16","2026-10-15"]`. Unavailable bounds SHALL be null. No new bound or import guard SHALL be added.

#### Scenario: Fetched report periods
- **WHEN** `.venv/bin/python -m pytest -q tests/test_run_evidence.py -k window` fetches synthetic reports with valid, repeated, missing, invalid, reversed and conflicting bounds through mocked HTTP
- **THEN** each successful fetch emits one matching list or null; retries and existing results stay unchanged.

### Requirement: Complete dry-run preview evidence

For each `ghost_import_activities` call in dry run, the connector SHALL emit one `preview` value containing the complete activity list, including an empty list. Every payload field SHALL remain exact, including timezone-qualified `date`, `dataSource` and `accountId`. Real imports SHALL emit no preview evidence. Existing readable preview lines SHALL remain unchanged.

#### Scenario: Exact payload preview
- **WHEN** `.venv/bin/python -m pytest -q tests/test_run_evidence.py -k preview` exercises empty lists, BUY, SELL and DIVIDEND payloads with fractional numbers and escaped comments in both modes
- **THEN** preview JSON equals the full payload list, no dry-run POST occurs, and real import requests and results stay unchanged.

### Requirement: Exact cash target evidence

After existing cash currency guards pass, `ghost_update_cash_balance` SHALL emit one `cash` value with exactly `accountId`, `balance` and `currency`. Balance SHALL retain its unrounded numeric value in dry run and real run. The evidence SHALL describe the target, not certify a successful PUT or stored state. Failed guards SHALL retain their existing outcome.

#### Scenario: Cash targets and guards
- **WHEN** `.venv/bin/python -m pytest -q tests/test_run_evidence.py -k cash` exercises zero, negative and sub-cent balances, both modes, currency guards and failed PUTs with mocked HTTP
- **THEN** valid target values match the request without rounding, dry run sends no PUT, and existing guard and failure results stay unchanged.
