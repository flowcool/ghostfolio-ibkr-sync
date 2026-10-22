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

Each action SHALL have one payment day, one contract, one currency and one exDate within its source account. Conflicting, incomplete or negative-net action evidence SHALL reject the entire historical group, emit a reason and fail the account result without blocking independent cash or later accounts. Zero-net actions SHALL create no activity. An action seen again with changed financial values SHALL NOT create a correction import. With review disabled, no update is authorized. With review enabled, only the separately approved one-to-one replacement specified in activity-correction-review SHALL update an existing action. Invalid or incomplete action evidence SHALL remain non-actionable. Where saved evidence exposes a conflict, preview SHALL report it for manual review. Withholding-only groups without a positive payment SHALL retain their existing not-payable outcome; report them without inventing a payment or failing solely because tax is present.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.


### Requirement: Mapping and duplicate reconciliation

Mapping SHALL prefer ISIN mappings, then IBKR symbols. The existing matching rules below SHALL apply when ACTIVITY_REVIEW_FILE is disabled. When enabled, activity-correction-review SHALL first inspect complete supported source events, including existing identities, and hold events with pending candidates before ordinary selection. No blank approval or deleted review entry SHALL authorize a related import. Review SHALL NOT combine trade fills or dividend actions into one correction. Trade IDs SHALL suppress reimport. Manual matching SHALL use quantity and ±2 days, including summed fills. Ambiguous split fills SHALL only be summed within the same parsed calendar day, side, resolved ticker, and ISIN; nearby mismatches SHALL warn/skip. Dividends SHALL match by account/comment (including the old symbol comment), or, for existing active YAHOO dividends of the same account and symbol whose comment does not start with `dividend#` (manual or legacy rows), at ±3 days. Connector-comment rows (`dividend#…`) SHALL NOT enter the proximity index, so a distinct payment next to an imported one is imported. A proximity skip SHALL stay a skip. The comparison SHALL use the exact source gross and the existing row's quantity × unitPrice, normalized to a common major unit (minor-unit markets as in conversion) and rounded to its minor unit; an unsupported denomination SHALL be "not comparable". Equal amounts SHALL log INFO "amounts agree" with both fee values; equal amounts do not prove the same payment. Otherwise it SHALL log one WARNING naming both dates, both gross values with currencies (or "not comparable"), both fee values, and the operator action: check IBKR and add the payment by hand if it is distinct. It SHALL NOT change exit status or notifications.

#### Scenario: Existing entries
- **WHEN** existing entries match
- **THEN** duplicates are excluded; manual-buy exclusions warn.

Evidence: `python -m pytest -q tests/test_parsing.py tests/test_filters.py tests/test_orchestration.py -k 'test_resolve_symbol_prefers_mapping_then_ibkr_symbol or test_already_imported_trade_is_not_reimported or test_manual_buy_same_day_same_qty_is_not_reimported_and_warns or test_split_fills_summing_to_a_manual_sell_are_matched or test_dividend_match_window_is_exactly_three_days'`.

#### Scenario: Split-fill calendar-day boundary
- **WHEN** two ambiguous fills use supported dashed timestamps on different days of the same month and their combined quantity equals one nearby manual trade
- **THEN** the fills remain separate ambiguous groups and do not consume the manual trade; same-day dashed fills still reconcile by their sum.

Check: `.venv/bin/python -m pytest -q tests/test_filters.py -k 'split_fills'`.

#### Scenario: Distinct payment next to an imported one
- **WHEN** an active canonical row `dividend#<ISIN>#2026-07-15` (gross 25) exists and the report holds a distinct payment on 2026-07-16 (gross 100)
- **THEN** the 2026-07-16 payment is imported, no proximity log line appears.

Check: `.venv/bin/python -m pytest -q tests -k dividend_proximity_canonical`.

#### Scenario: Manual row near the payment
- **WHEN** a manual row without connector comment lies within ±3 days, once with equal gross and once with different gross
- **THEN** both payments are skipped; equal gross logs INFO "amounts agree", different gross logs one WARNING with both dates, both gross values, fee values and the operator action; exit status is unchanged.

Check: `.venv/bin/python -m pytest -q tests -k dividend_proximity_amount`.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.


### Requirement: Additive imports and independent cash

New imports SHALL remain additive. Existing activities SHALL change only through the optional yes-approved one-to-one correction flow in activity-correction-review. Disabling that flow SHALL retain the existing no-update guarantee. No review flow SHALL delete an activity. Unresolved symbols SHALL drop/retry the reduced batch with degradation. Accounts SHALL run sequentially despite failures. Cash SHALL be independent of ordinary import success. A failed or unresolved correction SHALL fence all later financial writes for its account, including cash and platform writes. Pending proposals alone SHALL NOT block independent cash. Clean/degraded runs SHALL exit 0/1.

#### Scenario: Partial failure
- **WHEN** import fails or sections are absent
- **THEN** import failure permits cash; missing CashTransactions degrades; absent BASE_SUMMARY only warns.

Evidence: README “How it works”; `python -m pytest -q tests/test_orchestration.py tests/test_ghostfolio.py -k 'test_import_failure_fails_the_account_keeps_state_untouched_but_still_updates_cash or test_missing_cash_transactions_section_fails_the_run_but_still_imports_trades or test_report_without_cash_row_is_a_warning_not_a_failure or test_unresolved_symbol_is_dropped_and_batch_retried'`.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.


### Requirement: Current operational limits

The connector SHALL retain documented boundaries: 365-day guidance; daily data; manual corporate actions/history/token renewal; additive imports with optional explicitly approved corrections; proximity skips next to manual or legacy rows (INFO when amounts agree, WARNING otherwise, never imported; a distinct payment there needs a manual add); trust principle: a row with a connector comment (`dividend#…`) is ours and trusted by exact identity, and with review disabled a user edit of such a row is out of contract; enabled review SHALL expose validated per-event differences for approval; UTC dates; unconverted cash/commission currencies; Yahoo quality; net, nonchronological checks; nontransactional buy/sell phases; preview without server acceptance; buffered 10 MiB Flex responses; no general overlap protection. Enabled correction dispatch SHALL require exclusive writes and persistent recovery evidence as specified in activity-correction-review. README SHALL describe the new reader floor for notes-bearing references and the persistent-volume requirement.

#### Scenario: Operator checks limits
- **WHEN** limitations are read
- **THEN** these boundaries are visible, and `GHOST_CURRENCY` is not documented as a setting.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.


### Requirement: Enriched dividend input and local rejection

With review disabled, processing SHALL extract cash identity without quantity checks, deduplicate by account/comment/proximity, then validate candidates. Automatic sync SHALL leave existing activities untouched and unverified in that mode. With review enabled, complete supported action evidence SHALL be validated before proposing a correction, including an already stored identity. Only explicit yes approval SHALL authorize the reviewed one-to-one update. The separate bulk maintenance conversion SHALL retain its stricter contract. The dry-run diagnostic itself SHALL not change selection or authorize a correction.

ChangeInDividendAccruals SHALL be mandatory. Required attributes SHALL cover candidate payment/relevant accrual keys and `quantity/code/date/payDate/reportDate`. Nonempty key mismatches SHALL exclude unrelated accruals; missing keys SHALL NOT prove irrelevance. Unrelated rows SHALL NOT block candidates. Withholding SHALL retain cash evidence without accrual-schema requirements; new action writes SHALL require the explicit tax association in Flex selection and conversion. Missing section/relevant attributes SHALL block account dividends; present-but-empty evidence SHALL reject affected groups. Empty sections without payments SHALL be valid.

Rejections SHALL log distinct reasons, never mark rejected payments imported, and leave trades/cash operating. Partial v2 coverage, action-context conflicts and the new action-partition failures specified in Flex selection and conversion SHALL fail the account result; other existing local rejections SHALL NOT change success, exit, or notifications. Other failures SHALL retain current behavior.

#### Scenario: Compatibility and isolation
- **WHEN** `.venv/bin/python -m pytest -q tests -k dividend_structured_input` runs old, empty, short-window, unrelated, missing, conflicting and partial-v2 cases
- **THEN** identity→dedup→quantity order, scopes, logs, retries and isolation remain; partial v2 and new action-partition failures change the account outcome as specified; other local rejections preserve their outcomes.

#### Scenario: Partition failure isolation
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_partition_isolation` covers a missing tax association and conflicting source actions beside valid trades, safe sales, cash and a later account
- **THEN** the affected group emits no dividend, the account result fails, existing rows remain untouched, and independent work continues.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.


### Requirement: Versioned activity identity reader

Exact lowercase `IBKR#v` SHALL reserve versioned identities. Other `IBKR#<rest>` SHALL remain legacy. Accepted identity markers are:

- `IBKR#v2#<source-account>:TRADE:<tradeID>`
- `IBKR#v2#<source-account>:DIVIDEND:<actionID>`

The common grammar SHALL be `<BROKER>#v<N>#<source-account>:<KIND>:<source-id>`. `N` SHALL match `[1-9][0-9]*`; segments SHALL match `[A-Za-z0-9._-]+`. V2 SHALL map `TRADE` only to BUY/SELL and `DIVIDEND` only to DIVIDEND. A whole-comment marker SHALL remain valid. A canonical marker on the first line followed by one blank line and preserved user notes SHALL also be valid. Readers SHALL extract only that marker for identity and indexing; note text SHALL NOT become part of the source identity. Malformed or ambiguous first-line markers SHALL remain invalid. Any other reserved identity SHALL return `invalid_identity` and stop before writes. Notifications SHALL omit identities. New imports SHALL write exactly these v2 forms without added notes. Reviewed corrections SHALL write the same first-line marker and preserve user notes under activity-correction-review. No new legacy identity SHALL be generated.

The reader SHALL globally index v2 by source account and extracted identity marker, not Ghostfolio account or full notes-bearing comment. For mapping, dividend v2 SHALL be connector-owned and excluded from proximity and historical diagnostics.

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

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.


### Requirement: Destination comment compatibility gates

The destination qualification reference SHALL be Ghostfolio 3.86.0, source commit `ef47c0d1b2c48fa4e97fb381561b514e657928cf`. Existing local lab documentation binds it to image digest `sha256:929a54a1972c48f3cfb30af2db6f9f2aaeb610a9cc5f53264f1df1629eb43078`. This is saved deployment evidence, not a current runtime observation. Production desired configuration uses mutable `latest`; version drift SHALL require renewed qualification.

Pinned source observations:

- [Config](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/libs/common/src/lib/config.ts) sets `COMMENT_MAXIMUM_LENGTH` to 2000.
- [Create DTO](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/libs/common/src/lib/dtos/create-order.dto.ts) and [update DTO](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/libs/common/src/lib/dtos/update-order.dto.ts) validate an optional string, trim its ends and enforce that maximum. No comment character filter appears there. [Order schema](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/prisma/schema.prisma) has nullable String with no narrower declared column limit.
- [Import service](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/apps/api/src/app/import/import.service.ts) compares comment and financial fields without accountId; a changed comment can defeat server deduplication.
- [API setup](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/apps/api/src/main.ts) transforms and whitelists DTO fields and limits JSON bodies to 10mb. That request-size bound is separate from comment length.

The writer SHALL use only ASCII `[A-Za-z0-9._-]+` in account and source-ID segments. `#` and `:` SHALL appear only as grammar separators. For bare generated identities, full length SHALL be at most 2000 characters: `15 + len(account) + len(tradeID)` for TRADE, `18 + len(account) + len(actionID)` for DIVIDEND. Valid inputs need no trimming or Unicode length interpretation. Existing historical reader acceptance SHALL NOT acquire the writer's new length restriction. Reviewed comments with preserved notes SHALL require separate exact-image round-trip qualification of the combined 2000-character limit, encoding and DTO trimming. Unicode notes SHALL NOT be treated as Unicode identity segments. Failure to preserve notes SHALL make the correction non-actionable, never truncate user text.

G4 SHALL verify the image/source binding, realistic identity lengths, permitted punctuation and two-account otherwise identical payloads by exact byte-for-byte import/readback in an isolated synthetic lab. Local boundary tests SHALL cover 1999/2000/2001 against the source-backed 2000-character maximum; a lower arbitrary writer cap SHALL NOT replace that contract. Unicode, whitespace and reserved characters SHALL reject locally. Source inspection does not replace this pending round-trip gate.

#### Scenario: Comment boundaries
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_comment_limits` runs both identity kinds at 1999/2000/2001 characters with invalid separators, whitespace, Unicode and punctuation
- **THEN** only valid ASCII identities of at most 2000 characters become payloads; no transformation or legacy fallback occurs; invalid existing reserved comments still stop globally.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.


### Requirement: Explicit maintenance conversion and rollback boundary

Bulk historical conversion through the migration tool SHALL remain a separate explicit maintenance action, never an implicit effect of `DRY_RUN=false`. Per-activity review under activity-correction-review SHALL have its own optional configuration and exact yes approval; it SHALL NOT reuse migration approval or loosen the migration tool's manifest, eligibility, settlement or rollback requirements. The `apply` and `rollback` subcommands SHALL require the approved manifest hash and a private journal. Neither subcommand is authorized by proposal approval. A versioned, tested operation plan and separate Florent GO SHALL bind exact targets, commands, evidence, write count, batch sizes, pacing, stop rules and rollback. Batch and pacing limits SHALL come from qualification of update/background effects, not an assumed safe default. Reuse `cleanup_recovery.py` atomic YAML journal persistence and locking; adapt `cleanup_duplicates.py` explicit PUT construction only after preservation qualification. Its pair validation and delete executor SHALL NOT be reused for this comment-only operation.

Apply SHALL stop every competing writer, obtain a recoverable backup, re-read complete unredacted state and compare every planned row and identity occupancy with its manifest before the first write. Stale input, version/mapping drift, incomplete evidence or unavailable writer exclusion SHALL stop. Only the comment of listed eligible activities SHALL change; IDs, ownership, quantity, price, gross, fee, currency, date, tags and profiles SHALL remain unchanged. No insert/delete, cash/platform update or aggregate conversion is allowed.

The pinned [activity update controller](https://github.com/ghostfolio/ghostfolio/blob/ef47c0d1b2c48fa4e97fb381561b514e657928cf/apps/api/src/app/activities/activities.controller.ts) exposes PUT by activity ID. Its update DTO requires financial fields; a comment-only body is insufficient. Its service can enqueue market-data gathering. G5 SHALL prove the exact whitelisted full request, scope/ownership checks, numeric/date/tag/profile preservation, background effects and reverse request on the qualified image. No raw GET object SHALL be echoed into PUT. If preservation cannot be proved, apply remains unavailable and a revised proposal is required.

Before dispatch, the journal SHALL durably record each row's original comment/full fingerprint, target comment and pending request. Readback SHALL prove each conversion before advancing. A timeout, unknown result, server normalization, changed context or failed readback SHALL stop with the pending state retained; no automatic retry. Known completed subsets SHALL remain explicit. A later run SHALL require independent evidence that the pending request has completed or cannot still take effect before retry or reversal. Request-bound evidence is preferred where available; deployment-specific cancellation/quiescence proof requires its own authorized operation. An old-comment or absent-row readback alone SHALL NOT settle a delayed request. If no such proof is available, retain uncertainty and stop.

Rollback SHALL restore only journal-owned converted comments after complete readback proves the recorded v2 comment and unchanged financial/ownership context. Drift SHALL block reversal. Retain all newly imported v2 rows: this migration rollback cannot remove them. A global database restore is not the normal rollback and requires its own operation and reconciliation of intervening writes.

#### Scenario: Guarded conversion and reverse conversion
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_migration_apply_rollback` mocks exact successful updates, stale manifests, concurrent writers, profile effects, numeric normalization, partial completion, timeouts and post-conversion edits
- **THEN** only approved comments change; full readback proves preservation; uncertain requests are not retried; rollback restores only unchanged journal-owned comments and preserves newly imported v2 activities.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.


### Requirement: Writer release order and sibling compatibility

The released reader floor SHALL remain rc.5, commit `246b890d8cf2b6a58e99bbbf0169aa5f846c23bc`, image `sha256:32a034c96c2a675329e0aa38a3003a0352db8cec013ea74b6d04ac04cc8a9369`. Existing delivery evidence records 72 reader/acceptance tests, 1701 total tests, immutable publication, eight successful native lab invocations, empty first-install 142 creations, golden upgrade zero creations, zero idempotence creations and both instances stopped. This session inspected that evidence and local Git ancestry; it performed no new runtime replay.

Order SHALL be: proposal approval; implementation-task creation; offline implementation/qualification and review; archive and main replay; separate GO for an unused immutable writer RC numbered rc.6 or later; publish digest; both versioned empty/golden lab scenarios PASS on that same digest; separately authorized production activation; separately authorized comment conversion after reviewed migration preview; stable promotion only under a new GO. No soak duration or daily-cycle count SHALL gate release. Reuse valid candidate evidence when its artifact, inputs and relevant environment are unchanged. A failed digest SHALL be superseded, never promoted. Lab tests SHALL include new v2 creates, repeat runs, mixed history, short/partial acceptance, bounded recovery, maintenance and rollback on isolated synthetic rows. Expected sets and counts SHALL derive from each fixed report/snapshot pair; earlier reader counts SHALL NOT be extrapolated to the writer partition. Lab credentials SHALL remain separate from production. Stop both instances after runs.

Before any newly imported or converted v2 row exists, the previous validated rollback procedure remains applicable. After a reviewed correction writes a notes-bearing reference, rollback SHALL retain a qualified reader that supports that extended comment. Bare-v2 rc.5 support alone SHALL NOT qualify it. Afterwards, safe halt SHALL stop writers and force simulation, then restore rc.5 or a newer qualified dual reader for bare v2 history, or the new notes-compatible reader when such comments exist. Pre-rc.5 code SHALL NOT run against mixed history. Reader rollback preserves rows, does not repair data, and can still refuse partial dividend coverage. Re-enable writes only after exact mixed-generation preview and a separate GO. G6 SHALL prove this behavior using the actual rc.5 image, including complete and partial action sets, before production writing.

The common grammar SHALL remain broker-specific in generation: IBKR v2 and the Bourse Direct BD v3 target contract. The inspected Bourse Direct checkout at `3193086cd0223b0bfb18a388c53f1e0c65327dce` defines v3 in its proposed notice-import spec, but its runtime still contains v1/v2 writers; no delivered v3 writer is asserted. DEGIRO at `e8908adabd5453c9b57cb2dd687dc92a81ce15b2` writes unversioned account-scoped comments. Its authoritative CORE_PROVENANCE pins the IBKR single-file source at `5749146ff297133a6a85d9006bba60b65d9f7cde`; package adoption remains separate. DEGIRO remains pinned pending its separately owned generation decision. No sibling writer changes are implied. G7 SHALL compare sibling readers and request helpers at pinned revisions. Every changed broker-agnostic import/cash/request helper SHALL flag DEGIRO propagation under ADR 0007 and require a separate downstream change. Amend ADR 0002, README and upgrade instructions with exact formats, required matching Trade accountId, historical limits, comment cap, recovery prerequisites, preview/maintenance separation and the rc.5 rollback floor. Existing cleanup tools SHALL NOT run against v2 history until separately qualified; document that restriction and their outside-image boundary; add no new ADR.

#### Scenario: Mixed-history rollback and downstream boundary
- **WHEN** `.venv/bin/python -m pytest -q tests -k v2_release_compatibility` runs a compatibility matrix for old/new comments, complete/partial sets, sibling namespaces and proposed maintenance changes
- **THEN** the matrix preserves reading of all historical generations, excludes pre-rc.5 rollback after v2, records pending image-backed proofs, and leaves sibling generations and pins unchanged.

All G1–G7 evidence, current destination runtime/image confirmation, a complete saved migration-input replay and image-backed import/maintenance/rollback results remain necessary. None is certified by strict OpenSpec validation. Material counterexamples SHALL stop the affected work and return the proposal for approval; they SHALL NOT become implicit implementation assumptions.

#### Scenario: Optional review compatibility
- **WHEN** `.venv/bin/python -m pytest -q tests/test_activity_review.py -k review_runtime_contract` exercises this requirement with review disabled, enabled and later disabled after a notes-bearing correction
- **THEN** the disabled baseline remains valid, the explicit review exception follows activity-correction-review, and all supported historical reference generations remain readable.
