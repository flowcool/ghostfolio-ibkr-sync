# Spec Delta

Commands with `v2_` selectors describe acceptance tests to add after approval. They have not run and SHALL NOT count as proof when zero tests are collected. Current behavior remains in the main spec until this change is implemented and archived.

## MODIFIED Requirements

### Requirement: Flex selection and conversion

The connector SHALL select Trade children excluding CASH/OPT, DETAIL dividend/PIL/withholding grouped by security/day for historical deduplication, then partitioned by source account and action for new writes, and BASE_SUMMARY cash; ignore other cash types/levels and AssetSummary. Trades SHALL use BUY for exact BUY and SELL for exact SELL; any other `buySell` value SHALL reject the row (error, run not ok, other trades unaffected); absolute quantity/price; commission/withholding fees with refunds/rebates clamped to zero. Nonpositive payments SHALL skip.

Cash Transactions SHALL establish payments/gross/withholding. Conversion SHALL preserve account, currency/scaling, cash-day UTC date; comments SHALL use the new v2 identity. Description inference and one-unit fallback SHALL be removed.

Each net-positive action SHALL require identical nonempty `accountId/conid/currency/actionID/exDate`, one unique `Re` with `payDate` matching cash day, and matching `date` OR `reportDate`. Associated quantities SHALL agree as positive finite decimals before numeric conversion, without rounding/tolerance. `Re` alone SHALL NOT establish payment.

Dividend/PIL portions of one action SHALL use one common quantity, never sum quantities. Distinct ordinary/bonus actions SHALL produce distinct activities, each with its own proven quantity. Zero-net actions SHALL provide no quantity; negative-net actions/mixed currencies/incompatible evidence SHALL reject the group. Results SHALL be row-order independent. Price SHALL be cash gross/quantity, irrespective of accrual money/rate. After numeric conversion/minor-unit scaling, quantity/price SHALL remain positive finite and fee nonnegative finite; overflow/positive underflow SHALL reject the group.

#### Scenario: Selected records
- **WHEN** baseline selection/conversion is replayed with enriched fixtures
- **THEN** trade selection, scaling and dates remain unchanged; dividend partition and v2 identities follow this delta, with gross and signed withholding conserved before fee clamping.

Baseline: README conversion table. Check: `.venv/bin/python -m pytest -q tests/test_parsing.py tests/test_conversion.py`.

#### Scenario: Quantity association
- **WHEN** fixtures cover unrated PIL (3 shares/gross 1.5), quantity 450 versus inferred 451, fractions/one-share, earlier date/late reportDate, wrong keys/dates, multiple Re, missing/invalid/conflicting quantities, Re without cash
- **THEN** supported quantities remain unchanged; unsupported groups reject; Re creates no payment.

Check: `.venv/bin/python -m pytest -v tests -k dividend_structured_quantity`.

#### Scenario: Final numeric limits
- **WHEN** fixtures cover quantity `1e-400`/`1e400`, decimal conflicts collapsing to one numeric value, price overflow/underflow, and GBP→GBp overflow of price/fee alongside normal scaling
- **THEN** unsafe groups reject locally, decimal conflicts before conversion; valid quantity/price/fee/cash totals remain correct.

Check: `.venv/bin/python -m pytest -v tests -k dividend_structured_numeric`.

#### Scenario: Components and money
- **WHEN** fixtures include split PIL, ordinary/bonus at equal/different rates, unequal quantities, signed zero/negative actions, mixed currencies and differing accrual gross/tax/rate
- **THEN** valid actions retain their own quantities and cash totals; invalid groups reject; distinct-action quantities can differ; permutation/accounting/identity assertions pass.

#### Scenario: Unknown trade side
- **WHEN** a synthetic Trade has `buySell` `SELL (Ca.)`, empty or lowercase `sell`, beside valid BUY and SELL rows
- **THEN** only the unknown row is rejected with an error, never counted by the holdings gate; valid rows convert unchanged.

Check: `.venv/bin/python -m pytest -q tests -k 'unknown_trade_side'`.

#### Scenario: Action partition and withholding
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_event_partition` covers split dividend/PIL, two ordinary/bonus actions, unequal action quantities, missing or conflicting tax association, refunds, zero/negative actions and multiple payment days
- **THEN** one activity is proposed per positive action; each tax row belongs to exactly one action; every source cash row is accounted for; ambiguous groups produce no dividend payload and fail that account's result while trades, safe sales, independent cash and later accounts continue.

Withholding SHALL join by nonempty source account, actionID, conid, currency and payment day. Missing tax exDate SHALL be allowed; a nonempty contradictory exDate SHALL reject the group. No amount ratio, description, arbitrary allocation or missing-tax guess SHALL establish ownership. Per-action signed withholding/refunds SHALL be summed before the existing zero-fee clamp. Separate fees can therefore differ from the old group-level clamp when opposite signed tax exists; the preview SHALL expose that difference, never hide it as rounding.

Each action SHALL have one payment day, one contract, one currency and one exDate within its source account. Conflicting, incomplete or negative-net action evidence SHALL reject the entire historical group, emit a reason and fail the account result without blocking independent cash or later accounts. Zero-net actions SHALL create no activity. An action seen again with changed financial values SHALL remain additive: no correction import or update is authorized. Where saved evidence exposes such a conflict, preview SHALL report it for manual review. Automatic sync is not a general financial reconciliation service. Withholding-only groups without a positive payment SHALL retain their existing not-payable outcome; report them without inventing a payment or failing solely because tax is present.

### Requirement: Versioned activity identity reader

Exact lowercase `IBKR#v` SHALL reserve versioned identities. Other `IBKR#<rest>` SHALL remain legacy. Accepted forms are:

- `IBKR#v2#<source-account>:TRADE:<tradeID>`
- `IBKR#v2#<source-account>:DIVIDEND:<actionID>`

The common grammar SHALL be `<BROKER>#v<N>#<source-account>:<KIND>:<source-id>`. `N` SHALL match `[1-9][0-9]*`; segments SHALL match `[A-Za-z0-9._-]+`. V2 SHALL map `TRADE` only to BUY/SELL and `DIVIDEND` only to DIVIDEND. Any other reserved identity SHALL return `invalid_identity` and stop before writes. Notifications SHALL omit identities. New eligible activities SHALL write exactly these v2 forms. No new legacy identity SHALL be generated.

The reader SHALL globally index v2 by source account and comment, not Ghostfolio account. For mapping, dividend v2 SHALL be connector-owned and excluded from proximity and historical diagnostics.

Baseline: ADR 0002/tests prove legacy behavior; two reports repeat 49 conflict-free action IDs.

#### Scenario: Strict dual reader
- **WHEN** `.venv/bin/python -m pytest -q tests -k versioned_identity_reader` covers legacy, valid and invalid comments
- **THEN** legacy and v2 load; invalid reserved identities stop before writes with `invalid_identity`.

#### Scenario: Write account-scoped identities
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_identity_writer` covers two source accounts with equal tradeID/actionID, BUY/SELL, dividend/PIL and different destination names/UUIDs
- **THEN** source-account/event identities differ across source accounts and remain byte-identical across destination remapping; financial conversion follows its existing rules except for the specified dividend partition.

Source row accountId SHALL equal the verified report account for every candidate. Missing, unsafe or conflicting source-account/event segments, or a generated comment over 2000 ASCII characters, SHALL fail the affected account before any financial write. IDs SHALL NOT be trimmed, escaped, hashed, truncated, case-folded or replaced by fallback legacy IDs. A future destination version SHALL require renewed limit validation before use.

Accepted v2 BUY/SELL SHALL update holdings and the global v2 index. Accepted v2 DIVIDEND SHALL update only that index, never holdings or the legacy-global trade-ID set. Manual proximity matches SHALL remain ephemeral and scoped to the verified source account; they SHALL NOT populate the legacy-global trade-ID set or suppress another account. Manual-tag advice SHALL show the exact proposed v2 identity, never recommend a newly written legacy marker. Only proven accepted rows SHALL update real-run state. Simulated rows SHALL update simulation state only.

#### Scenario: Same-run accepted state
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_accepted_state` covers multiple accounts, repeated queries, dividends, accepted subsets and omitted buys before sells
- **THEN** each v2 kind updates only its proper index/holdings; no second source account is suppressed by another account's v2 trade ID; omitted rows do not become existing or authorize a sale; equal tradeIDs manually matched in one source account do not suppress another account and advice uses the v2 grammar.

### Requirement: Dividend action coverage

The positive action set SHALL contain each distinct `(accountId, actionID)` with exact Decimal net above zero, exclude zero, and reject missing, conflicting, or negative evidence.

Legacy exact comments SHALL win. Otherwise, complete v2 coverage SHALL mark the group existing. Partial coverage SHALL reject it, fail its account, and prevent legacy import. Before the no-coverage path, existing v2 dividend context SHALL be checked for the same source account, security and payment day. An unexpected actionID or context that cannot exclude an overlapping stored event SHALL block that group for manual review and fail its account result without blocking independent work. This is an exact-context safety check, not proximity matching or financial equivalence. No coverage without such conflict SHALL retain the existing proximity check, then partition eligible new groups into v2 action activities. Trades, safe sales, cash and later accounts SHALL continue. Partial v2 coverage SHALL retain the rc.5 failure outcome. New action-partition failures SHALL also fail the account result as specified above; other pre-existing local rejections SHALL retain their outcomes.

#### Scenario: Complete, partial and absent coverage
- **WHEN** `.venv/bin/python -m pytest -q tests -k "versioned_identity_reader or v2_generation_dedup"` covers complete, partial and absent multi-action sets plus zero-net and invalid actions
- **THEN** complete coverage skips, partial coverage fails only the account without import, absent coverage follows proximity then v2 selection, and invalid new action partitions fail as specified without emitting dividend rows.

#### Scenario: Historical generations and conservative precedence
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_generation_dedup` covers `IBKR#<tradeID>`, resolved-symbol/raw-symbol/ISIN `dividend#<key>#<date>`, mixed v2 rows, inactive markers, destination moves and overlapping windows
- **THEN** legacy-global trade IDs still suppress matching IDs globally; account-local exact historical dividend comments win before action coverage; full v2 coverage skips globally by source account; partial coverage blocks the whole group; v2 dividends never enter proximity or historical diagnostics.

Legacy precedence SHALL NOT certify event completeness. It can still suppress a later distinct event in the same historical security/day group. Preview SHALL report this limitation; no automatic backfill, repair, filling of partial coverage or ownership inference from equal amounts is authorized.

#### Scenario: Replaced identity or additional same-day event
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_action_conflict` covers replaced actionIDs, unrelated source accounts, changed financial values, unknown stored security context and legitimate additional same-day actions
- **THEN** detectable overlapping conflicts block without a new payout; ambiguous additional events require manual review; unrelated accounts continue. No claim is made that this guard detects revisions which also change day or security.

All candidates in a group SHALL pass validation before dispatch. One import batch SHALL NOT be treated as an atomic transaction: Ghostfolio can accept a subset. Partial acceptance SHALL preserve proven accepted identities and fail the account. Later imports SHALL retain partial-coverage refusal; no automatic filling or legacy fallback is allowed. Repeated failures can recur throughout the configured report window; logs and upgrade guidance SHALL expose the recovery requirement.

#### Scenario: Bounded recovery after partial acceptance
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_partial_recovery` covers partial server acceptance, uncertain requests and changed source evidence
- **THEN** normal reruns refuse incomplete coverage. A recovery preview identifies only exact missing action payloads from complete source evidence and a fresh destination snapshot. It preserves accepted rows and financial values. Uncertainty or changed evidence blocks dispatch.

Recovery SHALL require stopped competing writers, settled outstanding requests, complete source/action and destination evidence, a reviewed manifest of exact missing identities and financial fields, and a separately approved operation plan. A versioned, tested recovery command SHALL submit only those missing payloads, prove full coverage by readback, then prove zero reinsertions on normal simulation. Recovery is a distinct explicit import operation, not migration conversion or automatic retry. Missing recovery tooling blocks writer enablement; no temporary live script is an alternative.

### Requirement: Enriched dividend input and local rejection

Processing SHALL extract cash identity without quantity checks, deduplicate by account/comment/proximity, then validate candidates. Automatic sync SHALL leave existing activities untouched and unverified. Only the separately invoked maintenance conversion can replace a proven historical comment under its stricter contract. A separate dry-run diagnostic SHALL not change selection.

ChangeInDividendAccruals SHALL be mandatory. Required attributes SHALL cover candidate payment/relevant accrual keys and `quantity/code/date/payDate/reportDate`. Nonempty key mismatches SHALL exclude unrelated accruals; missing keys SHALL NOT prove irrelevance. Unrelated rows SHALL NOT block candidates. Withholding SHALL retain cash evidence without accrual-schema requirements; new action writes SHALL require the explicit tax association in Flex selection and conversion. Missing section/relevant attributes SHALL block account dividends; present-but-empty evidence SHALL reject affected groups. Empty sections without payments SHALL be valid.

Rejections SHALL log distinct reasons, never mark rejected payments imported, and leave trades/cash operating. Partial v2 coverage, action-context conflicts and the new action-partition failures specified in Flex selection and conversion SHALL fail the account result; other existing local rejections SHALL NOT change success, exit, or notifications. Other failures SHALL retain current behavior.

#### Scenario: Compatibility and isolation
- **WHEN** `.venv/bin/python -m pytest -q tests -k dividend_structured_input` runs old, empty, short-window, unrelated, missing, conflicting and partial-v2 cases
- **THEN** identity→dedup→quantity order, scopes, logs, retries and isolation remain; partial v2 and new action-partition failures change the account outcome as specified; other local rejections preserve their outcomes.

#### Scenario: Partition failure isolation
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_partition_isolation` covers a missing tax association and conflicting source actions beside valid trades, safe sales, cash and a later account
- **THEN** the affected group emits no dividend, the account result fails, existing rows remain untouched, and independent work continues.

## ADDED Requirements

### Requirement: Source identity evidence gates

Before enabling the writer, source qualification SHALL record capture hashes, report/query fields, account count, overlap window, event counts, revision/reversal coverage and conflicting associations. Evidence SHALL distinguish observations from vendor guarantees. Missing proof for a required qualification case SHALL block the affected writer capability; synthetic tests alone SHALL NOT prove IBKR stability.

Observed on 2026-10-21 by offline XML inspection:

| Capture | SHA-256 | Bounded observation |
|---|---|---|
| A, baseline | `8a50478e135af8e0ac2deac72d5aab3248c4915807622204e589512461926df4` | 135 trades with safe nonempty tradeID/accountId; 118 STK, 16 CASH, 1 OPT; one AccountInformation; nine cash-report currency rows |
| B, enriched | `30a04860bea149ed55b3308c326997446940ee8d7f2859e534e84284de33e539` | One source account; 55 payment rows, 50 withholding rows, 46 security/day groups, 49 positive actions, 154 accrual rows |
| C, timezone-enriched | `a8864f5d40ceccffac677d76cab97c2ffda37e06d0a6493f000ef4f50b0fd134` | Same action set and normalized payment evidence as B; timezone suffix differs |

Three groups contain two actions. All 50 withholding rows match payment account/action/contract/currency/day. All 50 lack exDate. No fee-clamp total difference was observed between action and historical grouping in these captures; this does not prove future refund cases. Payment evidence normalized here means contract, currency, exDate, calendar day, payment type and amount, grouped by account/action. These captures establish repeatability over two nearby acquisitions of one account. They do not establish lifetime stability, future revisions, complete short windows or cross-account uniqueness. B and C are diagnostic section captures, not complete runnable reports with AccountInformation.

The inspected [IBKR cash reference](https://www.ibkrguides.com/reportingreference/reportguide/cash%20transactionsfq.htm) and [accrual reference](https://www.ibkrguides.com/reportingreference/reportguide/change%20in%20dividend%20accrualsfq.htm) do not establish actionID lifetime or uniqueness. No such guarantee is assumed.

| Gate | Required proof before enabled writes |
|---|---|
| G1: bounded event stability | Define qualified report windows and required revision/reversal/repayment cases before enablement. Saved overlaps SHALL match events independently of actionID and record whether it is retained, replaced or reused. Record case counts and missing coverage explicitly; nearby captures alone leave revision qualification pending. Finite observations SHALL NOT certify lifetime stability. Reuse for independent payable events blocks this grammar. Replacement conflicts require the conservative guard and operator review; unhandled cases require a revised proposal. |
| G2: account scope | Record authoritative or saved multi-account observations when available; label absent evidence unknown. Global uniqueness is informational, not an enablement prerequisite: always retain the account segment. Equal synthetic tradeIDs/actionIDs in two source accounts MUST prove independent identities and deduplication. |
| G3: complete partition | Prove payment, PIL, tax/refund and accrual association, cancellation handling, and complete windows for the qualified cases. Cash totals must conserve exactly before clamping. No stable identity proof can turn an incomplete event window into a complete financial record. |

Trade qualification SHALL likewise check overlapping-report stability, repeated/conflicting IDs, source-account equality and corrections. A changed trade under an already stored identity SHALL require manual review, never an automatic correction.

#### Scenario: Source qualification remains bounded
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_source_qualification` replays qualified saved-input summaries and synthetic revision, reuse, multi-day, missing-account, incomplete-window and cross-account counterexamples
- **THEN** each evidence claim has an explicit status and scope; a failed or missing gate prevents the corresponding write capability; no fixture result is reported as a vendor guarantee.

### Requirement: Destination comment compatibility gates

The destination qualification reference SHALL be Ghostfolio 3.86.0, source commit `ef47c0d1b2c48fa4e97fb381561b514e657928cf`. Existing local lab documentation binds it to image digest `sha256:929a54a1972c48f3cfb30af2db6f9f2aaeb610a9cc5f53264f1df1629eb43078`. This is saved deployment evidence, not a current runtime observation. Production desired configuration uses mutable `latest`; version drift SHALL require renewed qualification.

Pinned source observations:

- [Config](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/libs/common/src/lib/config.ts) sets `COMMENT_MAXIMUM_LENGTH` to 2000.
- [Create DTO](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/libs/common/src/lib/dtos/create-order.dto.ts) and [update DTO](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/libs/common/src/lib/dtos/update-order.dto.ts) validate an optional string, trim its ends and enforce that maximum. No comment character filter appears there. [Order schema](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/prisma/schema.prisma) has nullable String with no narrower declared column limit.
- [Import service](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/apps/api/src/app/import/import.service.ts) compares comment and financial fields without accountId; a changed comment can defeat server deduplication.
- [API setup](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/apps/api/src/main.ts) transforms and whitelists DTO fields and limits JSON bodies to 10mb. That request-size bound is separate from comment length.

The writer SHALL use only ASCII `[A-Za-z0-9._-]+` in account and source-ID segments. `#` and `:` SHALL appear only as grammar separators. Full length SHALL be at most 2000 characters: `15 + len(account) + len(tradeID)` for TRADE, `18 + len(account) + len(actionID)` for DIVIDEND. Valid inputs need no trimming or Unicode length interpretation. Existing historical reader acceptance SHALL NOT acquire the writer's new length restriction.

G4 SHALL verify the image/source binding, realistic identity lengths, permitted punctuation and two-account otherwise identical payloads by exact byte-for-byte import/readback in an isolated synthetic lab. Local boundary tests SHALL cover 1999/2000/2001 against the source-backed 2000-character maximum; a lower arbitrary writer cap SHALL NOT replace that contract. Unicode, whitespace and reserved characters SHALL reject locally. Source inspection does not replace this pending round-trip gate.

#### Scenario: Comment boundaries
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_comment_limits` runs both identity kinds at 1999/2000/2001 characters with invalid separators, whitespace, Unicode and punctuation
- **THEN** only valid ASCII identities of at most 2000 characters become payloads; no transformation or legacy fallback occurs; invalid existing reserved comments still stop globally.

### Requirement: Offline historical identity migration preview

An explicit maintenance tool SHALL produce an offline preview before any conversion. The automatic importer SHALL remain additive. Proposed interface: `python identity_migration.py preview --inputs <inputs.yaml> --output <new-directory>`, from the versioned checkout, outside the runtime image like existing cleanup tools. Preview, apply and rollback SHALL use one maintenance engine and shared pure conversion rules. The interface and tests do not exist yet.

The keyed YAML input SHALL reference saved Flex reports, a complete exact Ghostfolio activity snapshot with count/version evidence, the complete declared inventory of every configured source account able to import into the portfolio, explicit source-account to destination-account mapping, symbol mapping and IANA TZ. Reports SHALL cover each affected window for all such accounts. Missing accounts or incomplete windows SHALL make affected trade conversions non-actionable; an operator declaration alone SHALL NOT prove report completeness. Files SHALL be opened read-only. The preview SHALL NOT load credentials, authenticate, fetch reports, issue HTTP, update cash/platforms, send notifications or write back to input locations. An existing output path, any input/output overlap or symlink redirection SHALL fail before output. Outputs SHALL be private: directory 0700, files 0600. All mutations SHALL be disabled even when inherited `DRY_RUN=false`.

Only exact and unique 1→1 matches SHALL be eligible for comment conversion:

- Trades: an owned legacy `IBKR#<tradeID>` row and exactly one proven source account/trade event.
- Dividends: an owned historical resolved-symbol, raw-symbol or ISIN `dividend#<key>#<date>` row covering exactly one positive action. Multiple payment/PIL portions of that one action are allowed. Several actions represented by one row are excluded.
- Both: unique source and destination ownership; same destination account, active YAHOO context, side/type, resolved security, supported denomination, source calendar day under the proven historical date policy, exact quantity, gross and fee. Retain the stored UTC instant. Compare original JSON numbers as decimals, not reconstructed floats. Both historical group-level and proposed action-level fee clamps SHALL equal the stored fee; any difference blocks conversion. Any rounding or amount tolerance from the diagnostic report SHALL NOT grant migration eligibility. Missing or conflicting evidence SHALL block conversion.

Preview SHALL list each source event and each in-scope historical row once, with activity ID, source reference, old/new comment, association cardinality, existing fields, expected financial fields, exact differences, evidence status and reason. Counts SHALL distinguish eligible replacement, already v2, absent/new candidate, aggregate, ambiguous, conflicting, partial coverage, unsupported and outside-window. The manifest SHALL bind schema/version, input hashes, source/destination scope, window/TZ, mapping hash, tool commit, destination image/version, planned ordered replacements and before/after row fingerprints. Equal input bytes SHALL give equal ordered decisions and manifest hash; timestamps SHALL stay outside the hashed plan.

The preview SHALL replay the complete import selection with the declared configuration against the original snapshot and a copy with only planned comments replaced. The full selected event/payload set and holdings decisions SHALL be identical, not merely counts. In particular, removing a legacy-global trade marker SHALL NOT expose a previously suppressed trade in another source account. Any difference blocks the affected conversion. Bind this proof to the inventory, windows, mappings, tool and snapshot hashes; changed configuration invalidates it. This bounded proof makes no guarantee about undeclared future accounts.

No alias activity, replacement financial activity, deletion or split SHALL be proposed. Keep manual, inactive, excluded, non-YAHOO, unsupported and unproven rows unchanged. Keep outside-window history visible and unchanged. An already occupied v2 identity, several old rows claiming one event, a legacy trade ID claimed by several accounts, or a partial v2 group SHALL block every affected replacement. Exact historical import deduplication remains more permissive than migration eligibility; preview SHALL explain this difference.

#### Scenario: Exact migration preview
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_migration_preview` exercises exact trade/dividend matches, oldest symbols, one-action split PIL, multi-action aggregates, duplicated ownership, manual/inactive rows, rounding differences, absent sources, short windows, mixed generations, opposite-signed tax clamps and a legacy-global trade marker suppressing another configured account
- **THEN** only unique exact 1→1 rows with unchanged before/after selection are eligible; every other row has one visible exclusion reason; source gross and signed tax totals reconcile; no source or destination input changes.

#### Scenario: Offline and deterministic boundary
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_migration_offline` runs repeated previews with all network access denied, inherited false DRY_RUN, exact JSON decimals, invalid snapshots, changed mappings and output/input overlaps
- **THEN** previews use no network or credentials, write only a new private output directory, reject incomplete/redacted inputs, preserve every input hash, and produce identical decisions for identical inputs.

### Requirement: Explicit maintenance conversion and rollback boundary

Historical conversion SHALL be a separate explicit maintenance action, never a sync option or an effect of `DRY_RUN=false`. Proposed `apply` and `rollback` subcommands SHALL require the approved manifest hash and a private journal. Neither subcommand is authorized by proposal approval. A versioned, tested operation plan and separate Florent GO SHALL bind exact targets, commands, evidence, write count, batch sizes, pacing, stop rules and rollback. Batch and pacing limits SHALL come from qualification of update/background effects, not an assumed safe default. Reuse `cleanup_recovery.py` atomic YAML journal persistence and locking; adapt `cleanup_duplicates.py` explicit PUT construction only after preservation qualification. Its pair validation and delete executor SHALL NOT be reused for this comment-only operation.

Apply SHALL stop every competing writer, obtain a recoverable backup, re-read complete unredacted state and compare every planned row and identity occupancy with its manifest before the first write. Stale input, version/mapping drift, incomplete evidence or unavailable writer exclusion SHALL stop. Only the comment of listed eligible activities SHALL change; IDs, ownership, quantity, price, gross, fee, currency, date, tags and profiles SHALL remain unchanged. No insert/delete, cash/platform update or aggregate conversion is allowed.

The pinned [activity update controller](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/apps/api/src/app/activities/activities.controller.ts) exposes PUT by activity ID. Its update DTO requires financial fields; a comment-only body is insufficient. Its service can enqueue market-data gathering. G5 SHALL prove the exact whitelisted full request, scope/ownership checks, numeric/date/tag/profile preservation, background effects and reverse request on the qualified image. No raw GET object SHALL be echoed into PUT. If preservation cannot be proved, apply remains unavailable and a revised proposal is required.

Before dispatch, the journal SHALL durably record each row's original comment/full fingerprint, target comment and pending request. Readback SHALL prove each conversion before advancing. A timeout, unknown result, server normalization, changed context or failed readback SHALL stop with the pending state retained; no automatic retry. Known completed subsets SHALL remain explicit. A later run SHALL require independent evidence that the pending request has completed or cannot still take effect before retry or reversal. Request-bound evidence is preferred where available; deployment-specific cancellation/quiescence proof requires its own authorized operation. An old-comment or absent-row readback alone SHALL NOT settle a delayed request. If no such proof is available, retain uncertainty and stop.

Rollback SHALL restore only journal-owned converted comments after complete readback proves the recorded v2 comment and unchanged financial/ownership context. Drift SHALL block reversal. Retain all newly imported v2 rows: this migration rollback cannot remove them. A global database restore is not the normal rollback and requires its own operation and reconciliation of intervening writes.

#### Scenario: Guarded conversion and reverse conversion
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_migration_apply_rollback` mocks exact successful updates, stale manifests, concurrent writers, profile effects, numeric normalization, partial completion, timeouts and post-conversion edits
- **THEN** only approved comments change; full readback proves preservation; uncertain requests are not retried; rollback restores only unchanged journal-owned comments and preserves newly imported v2 activities.

### Requirement: Writer release order and sibling compatibility

The released reader floor SHALL remain rc.5, commit `246b890d8cf2b6a58e99bbbf0169aa5f846c23bc`, image `sha256:32a034c96c2a675329e0aa38a3003a0352db8cec013ea74b6d04ac04cc8a9369`. Existing delivery evidence records 72 reader/acceptance tests, 1701 total tests, immutable publication, eight successful native lab invocations, empty first-install 142 creations, golden upgrade zero creations, zero idempotence creations and both instances stopped. This session inspected that evidence and local Git ancestry; it performed no new runtime replay.

Order SHALL be: proposal approval; implementation-task creation; offline implementation/qualification and review; archive and main replay; separate GO for an unused immutable writer RC numbered rc.6 or later; publish digest; both versioned empty/golden lab scenarios PASS on that same digest; separately authorized production preview/soak; separately authorized comment conversion after reviewed migration preview; stable promotion only under a new GO. A failed digest SHALL be superseded, never promoted. Lab tests SHALL include new v2 creates, repeat runs, mixed history, short/partial acceptance, bounded recovery, maintenance and rollback on isolated synthetic rows. Expected sets and counts SHALL derive from each fixed report/snapshot pair; earlier reader counts SHALL NOT be extrapolated to the writer partition. Lab credentials SHALL remain separate from production. Stop both instances after runs.

Before any newly imported or converted v2 row exists, the previous validated rollback procedure remains applicable. Afterwards, safe halt SHALL stop writers and force simulation, then restore rc.5 or a newer qualified dual reader. Pre-rc.5 code SHALL NOT run against mixed history. Reader rollback preserves rows, does not repair data, and can still refuse partial dividend coverage. Re-enable writes only after exact mixed-generation preview and a separate GO. G6 SHALL prove this behavior using the actual rc.5 image, including complete and partial action sets, before production writing.

The common grammar SHALL remain broker-specific in generation: IBKR v2 and the Bourse Direct BD v3 target contract. The inspected Bourse Direct checkout at `3193086cd0223b0bfb18a388c53f1e0c65327dce` defines v3 in its proposed notice-import spec, but its runtime still contains v1/v2 writers; no delivered v3 writer is asserted. DEGIRO at `e8908adabd5453c9b57cb2dd687dc92a81ce15b2` writes unversioned account-scoped comments. Its authoritative CORE_PROVENANCE pins the IBKR single-file source at `5749146ff297133a6a85d9006bba60b65d9f7cde`; package adoption remains separate. DEGIRO remains pinned pending its separately owned generation decision. No sibling writer changes are implied. G7 SHALL compare sibling readers and request helpers at pinned revisions. Every changed broker-agnostic import/cash/request helper SHALL flag DEGIRO propagation under ADR 0007 and require a separate downstream change. Amend ADR 0002, README and upgrade instructions with exact formats, required matching Trade accountId, historical limits, comment cap, recovery prerequisites, preview/maintenance separation and the rc.5 rollback floor. Existing cleanup tools SHALL NOT run against v2 history until separately qualified; document that restriction and their outside-image boundary; add no new ADR.

#### Scenario: Mixed-history rollback and downstream boundary
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_release_compatibility` runs a compatibility matrix for old/new comments, complete/partial sets, sibling namespaces and proposed maintenance changes
- **THEN** the matrix preserves reading of all historical generations, excludes pre-rc.5 rollback after v2, records pending image-backed proofs, and leaves sibling generations and pins unchanged.

All G1–G7 evidence, current destination runtime/image confirmation, a complete saved migration-input replay and image-backed import/maintenance/rollback results remain necessary. None is certified by strict OpenSpec validation. Material counterexamples SHALL stop the affected work and return the proposal for approval; they SHALL NOT become implicit implementation assumptions.
