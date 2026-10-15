## ADDED Requirements

### Requirement: Native run evidence format

The connector SHALL emit evidence through its normal Python and container entry points, without a mounted observer. Evidence SHALL be emitted at DEBUG level only (`log.debug`); at INFO or any higher threshold no `RUN_EVIDENCE` line SHALL appear, and every existing INFO line, including the per-activity `[DRY RUN] would import` list, SHALL stay unchanged. Each evidence message SHALL contain the exact prefix `RUN_EVIDENCE ` followed by one compact JSON object on one physical line. The normal logging timestamp and level SHALL precede the message. A consumer SHALL remove only the logging or transport wrapper before parsing the prefix. JSON string escaping SHALL prevent field contents from creating extra log lines. JSON numbers SHALL be finite and retain the numeric value used in the request; display rounding SHALL NOT apply. Booleans SHALL NOT substitute for numbers.

Every object SHALL have these envelope fields:

| Field | Meaning |
| --- | --- |
| `v` | Integer schema version, initially `1` |
| `runId` | Unique invocation identifier; shared by all events in that invocation |
| `account` | One-based configured account ordinal; null for run events |
| `accountId` | Resolved Ghostfolio destination ID; null before resolution or for run events |
| `dry_run` | Effective boolean simulation mode, including forced preview |
| `kind` | `run`, `window`, `activity`, `import` or `cash` |
| `value` | Object defined by the corresponding requirement |

Run start SHALL have `kind=run` and `value={"stage":"start"}`. Normal completion SHALL have `value={"stage":"end","exitCode":0}` or the actual existing exit code. Configuration failures SHALL retain a paired start/end when normal finalization occurs. Before valid configuration, `dry_run` SHALL reflect the safe simulation decision. Subsequent events SHALL reflect effective mode after safety guards. An interruption or incomplete log SHALL NOT be represented as success. Acceptance SHALL require one start, one successful end, one known version and a consistent effective mode for the selected account. README SHALL state that acceptance needs `LOG_LEVEL=DEBUG` and that the production INFO log is unchanged.

Evidence SHALL use explicit allowed fields. It SHALL NOT dump ENV, configuration, XML, HTTP headers, URLs, credentials, tokens or raw response bodies. Account IDs, comments, symbols and financial values needed by the checks SHALL remain present in private logs. Public examples SHALL use synthetic values. Existing financial guards, requests, selection, exits and notifications SHALL remain unchanged.

#### Scenario: Native invocation and safe framing
- **WHEN** `python3 -m pytest -q tests/test_run_evidence.py -k native_evidence_format` runs the native main path twice with mocked HTTP, multiple accounts, forced preview, configuration failure, an interrupted run, credential sentinels and newline/quote characters in an activity comment
- **THEN** at DEBUG, events parse as one JSON object per line; at INFO, zero `RUN_EVIDENCE` lines appear and the existing INFO lines are byte-identical to the current output; invocation/account identities remain distinct; original field values survive parsing; secrets are absent from evidence; missing end events cannot pass acceptance; request and exit behavior stays unchanged.

### Requirement: Explicit Flex period evidence

For each successfully fetched Flex report, in simulation and live mode, the connector SHALL emit exactly one `kind=window` event for that account ordinal. It SHALL use explicit, consistent `FlexStatement.fromDate/toDate` values, formatted as `YYYY-MM-DD`. It SHALL NOT infer bounds from activity dates. Its value SHALL be `{"status":"valid","fromDate":"2026-07-01","toDate":"2026-07-31"}` for those synthetic bounds.

Missing, invalid, reversed or conflicting bounds SHALL produce `{"status":"unavailable","fromDate":null,"toDate":null}`. This event SHALL NOT add an import guard or change the existing outcome. A consumer requiring a proven period SHALL reject unavailable bounds. Its existing 0–365-day check remains a consumer rule, not a new connector gate. Repeated consistent statement bounds SHALL produce one event. Separate reports SHALL remain separate account events even when their periods agree.

Baseline mechanism: existing historical-window tests in `tests/test_dividend_diagnostics.py`; current native logs do not expose the computed pair. These additions are proposed behavior.

#### Scenario: Proven and unavailable periods
- **WHEN** `python3 -m pytest -q tests/test_run_evidence.py -k native_evidence_window` exercises both modes with valid, absent, malformed, reversed, repeated-consistent and conflicting bounds, plus two accounts and a period longer than 365 days
- **THEN** each fetched report emits one explicit period or unavailable event; no dates are invented; long periods do not gain a new connector rejection; request counts and existing results stay unchanged.

### Requirement: Complete activity and import evidence

Each activity passed to the import step SHALL emit one `kind=activity` event before any POST. Its value SHALL contain `stage` plus all ten payload fields: `accountId`, `comment`, `currency`, `dataSource`, `date`, `fee`, `quantity`, `symbol`, `type`, `unitPrice`. Stage SHALL be `preview` in simulation and `submitted` in live mode. Dates SHALL preserve the timezone-qualified payload timestamp. Values SHALL describe the final converted candidate, after mapping, scaling and existing selection. No rounding, redaction, truncation or default substitution SHALL affect these fields. Retries SHALL NOT duplicate candidate events.

In live mode, each confirmed accepted activity SHALL emit one additional activity event with `stage=accepted`, the same field set, and the canonical symbol from the verified import response. Submitted rows SHALL NOT be labelled accepted merely because a POST succeeded. Dropped or server-skipped rows SHALL have no accepted event. Uncertain responses SHALL NOT produce inferred acceptance.

Each normally completed account attempt SHALL emit exactly one `kind=import` summary. Its value SHALL have `requested`, `accepted`, `simulated`, `ok`. Requested SHALL count initial import candidates across buy/dividend and sell phases, excluding retry duplicates. Simulation SHALL set `accepted=0`, `simulated=requested`, and retain the existing import success result. Live mode SHALL set `simulated=0`; accepted SHALL count verified accepted rows. `ok` SHALL reflect the combined import result, including degraded dropped symbols. When acceptance is uncertain, `accepted` SHALL be null and `ok=false`. An account that fails before reaching import selection SHALL use `ok=false`; it SHALL NOT certify a zero-creation run. A normal account with no import calls SHALL emit explicit zero counts and `ok=true`.

The existing `New trade activities: N` and `New dividend activities: N` lines SHALL remain. So SHALL `[DRY RUN] would import N activities` for each nonempty preview phase. For a successful preview, the sum of these declarations SHALL equal the count of preview activity events. A successful idempotence run SHALL have explicit zero trade/dividend counters and a zero, successful import summary for the selected account.

#### Scenario: Exact candidate and acceptance records
- **WHEN** `python3 -m pytest -q tests/test_run_evidence.py -k native_evidence_import` exercises BUY, SELL and DIVIDEND, fractional quantities, minor-unit scaling, both modes, dropped symbols, retries, server skips, canonical returned symbols and uncertain responses
- **THEN** JSON fields equal the actual payloads or verified accepted rows; candidate events occur once per initial candidate; all phase totals reconcile; preview acceptance is zero; uncertain acceptance is null; no extra HTTP call occurs.

#### Scenario: Empty import is explicit
- **WHEN** `python3 -m pytest -q tests/test_run_evidence.py -k native_evidence_zero` exercises deduplicated accounts with no import calls and an account failure before selection
- **THEN** normal accounts log zero requested/accepted/simulated and both existing zero counters; early failure logs a failed summary and cannot pass as idempotence.

### Requirement: Provider validation inputs and acceptance boundary

Every candidate event SHALL expose `dataSource`, `symbol` and `currency` exactly as sent or previewed. These fields SHALL supply the unique provider lookup triples used by the acceptance consumer. The connector SHALL NOT log `provider` validation success or invent `marketPrice` from candidate `unitPrice`. It SHALL add no provider HTTP request.

The acceptance consumer retains the provider lookup. The old observer checks HTTP 200, matching top-level symbol/dataSource/currency and a positive finite numeric, nonboolean `marketPrice`. Native activity events replace that observer's lookup inputs; they do not replace the response proof. Consumer migration SHALL keep that proof. Unmodified consumers that require `LAB_EVIDENCE` are not compatible with this grammar.

External evidence SHALL remain external: instance/image identity, mapping/source hashes, UTC day, selected account, before/after activity IDs and raw stored fields, account snapshots, and pinned report-checker identity/result. Wrapper identity becomes obsolete when the native consumer is adopted; image/source identity remains required. Logs SHALL NOT claim baseline preservation or stored cash equality. The consumer SHALL still compare quantities, timestamps, identities, gross, fees, type/currency totals and all account balances against independent readback. Financial preflight SHALL remain a readback check before broker access.

#### Scenario: Provider inputs without a new request
- **WHEN** `python3 -m pytest -q tests/test_run_evidence.py -k native_evidence_provider` uses repeated and distinct mapped provider triples, including GBp, ZAc and ILA
- **THEN** every candidate exposes the correct triple, distinct lookups can be derived without loss, no validation success is invented, and the HTTP trace has no added provider GET.

### Requirement: Exact cash target and outcome evidence

Both modes SHALL emit `kind=cash` with value fields `status`, `accountId`, `currency`, `balance`. After existing base/account currency guards succeed, simulation SHALL emit `status=preview`; live mode SHALL emit `status=target` before PUT and `status=updated` only after the existing successful response. Balance SHALL preserve the finite target value without the readable log's two-decimal rounding. Currency SHALL be the checked denomination; accountId SHALL be the exact destination. A successful target SHALL NOT certify stored-state equality.

A rejected, failed or uncertain cash update SHALL NOT emit preview/updated success. If a target is known, failure SHALL emit `status=failed` with that target. If no usable cash target exists, it SHALL emit `status=unavailable`, with unavailable currency/balance as null. Nonfinite values SHALL NOT enter JSON. No missing value SHALL be replaced with zero. These evidence statuses SHALL preserve the existing warning/failure behavior and independent cash processing after import failure. Existing human cash lines SHALL remain.

#### Scenario: Cash precision and guarded outcomes
- **WHEN** `python3 -m pytest -q tests/test_run_evidence.py -k native_evidence_cash` exercises both modes with zero, negative, sub-cent and three-decimal balances, matching/missing/mismatched currencies, missing/nonfinite cash and failed/uncertain PUTs after import success and failure
- **THEN** events identify the exact destination, denomination and unrounded target; updated follows only a successful existing PUT; unavailable/failed events cannot pass as success; writes, warnings and exits retain their prior behavior.

### Requirement: Native evidence and readable report coexist

Evidence lines SHALL remain separate from dividend report blocks. The connector SHALL preserve existing report text, indentation, coverage, summary counts and zero-candidate markers. Machine JSON SHALL NOT become part of a human dividend block. README SHALL document the versioned grammar, all event fields, simulation versus acceptance, cash statuses, private-log handling, minimum log level, and the independent provider/readback checks. It SHALL state that changing images alone does not migrate an external lab consumer.

#### Scenario: Normal entry point preserves report checks
- **WHEN** `python3 -m pytest -q tests/test_run_evidence.py -k native_evidence_pipeline` runs the native main path with synthetic Flex/HTTP responses for preview, real import, zero-creation rerun and final preview, then passes the captured report through the existing checker
- **THEN** the complete event stream reconciles without monkeypatching observer wrappers; the checker accepts unchanged human blocks; preview sends no financial writes; real counts match verified responses; all evidence stays in the normal logger output.

#### Scenario: Public consumer guidance
- **WHEN** `rg -n -A 90 'Native run evidence' README.md` runs after implementation
- **THEN** the section documents the grammar and its limits with synthetic examples, including the external provider GET and stored-state readback obligations.
