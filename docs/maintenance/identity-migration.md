# Historical identity migration

**Before apply or reversal:** obtain separate approval for the exact operation,
verified backup, qualified target image and preservation proof. Stop destination
writers and shared-review-file writers. Settle outstanding requests independently.
Stop on changed evidence, target drift, uncertainty or failed readback. Preserve
journals and rows. Only the guarded journal-owned reversal described below can
restore unchanged converted comments; it never removes newly imported activities.

## Historical maintenance with the shared review file

Use this path for exact historical comment replacements. Use normal activity
review for one-to-one financial corrections. Both paths use the same private
`ACTIVITY_REVIEW_FILE`; their request journals and execution authority differ.
A yes in this file never starts historical maintenance during normal sync.
These commands run from the versioned checkout, outside the container image.
Use the development environment for the selected checkout.

1. Stop the connector and other writers of the shared review file. Obtain complete
   saved source reports and an unredacted destination snapshot. Build the
   [migration inputs](#offline-historical-identity-evidence-preview) below.
2. Stage exact historical proposals into the same file:

   ```sh
   .venv/bin/python identity_migration.py review \
     --inputs private/inputs.yaml --review private/activities.yaml
   ```

   The command is offline. It keeps other proposals. It stages only exact eligible
   comment changes in `reference_updates`, with `execution path: historical maintenance`
   and `evidence level: exact`. It preserves the stored timestamp and every financial
   value. It does not repair a discrepant amount or split an aggregate. A pending
   request in the companion review journal refuses staging and preparation.
   Staging again starts a new historical review: it clears previous maintenance
   approvals and removes stale maintenance candidates.
3. Inspect the generated current/proposed values and full comment. Edit only
   `decision: yes` for the desired entries. Plain or quoted lowercase yes is accepted.
   Leave the rest blank or use `decision: reject` to skip it. A historical rejection
   does not release an import hold. Profiles cannot approve historical maintenance.
4. Prepare the exact approved historical subset:

   ```sh
   .venv/bin/python identity_migration.py prepare \
     --inputs private/inputs.yaml --review private/activities.yaml \
     --output private/selected-maintenance
   ```

   This is still offline. It reconstructs each selected proposal. It refuses edited
   values or changed evidence. It replays full import selection and holdings before
   and after exactly that subset. It does not reuse the proof for the full candidate
   set. No selected yes or a failed proof produces no apply manifest. The output is
   a private manifest and its SHA-256. The manifest binds the review-file bytes, private state bytes and selected keys.
5. Obtain a separate approved operation plan. Follow the
   [guarded maintenance requirements](#explicit-application-of-reviewed-historical-comments)
   below and use the selected manifest, its hash and exact write count. Include
   the same review file in apply:

   ```sh
   .venv/bin/python identity_migration.py apply \
     --inputs private/inputs.yaml --review private/activities.yaml \
     --manifest private/selected-maintenance/manifest.json \
     --manifest-sha256 '<selected-manifest-sha256>' \
     --approval private/migration-approval.json \
     --approval-sha256 '<operation-approval-sha256>' \
     --journal private/migration-apply.yaml \
     --host https://ghostfolio.example.test
   ```

   Preparation and apply hold the same review lock as the connector.
   The example host and hashes are placeholders. Apply reads `GHOST_TOKEN` from ENV.
   It rebuilds the selected manifest and rechecks the review bytes before dispatch.
   Successful apply removes its confirmed selections from the review file. If file
   cleanup fails after a completed journal, stop and inspect that journal; do not
   retry apply. Staging again requires fresh yes choices, including after rollback.
   Any file edit requires a new preparation and operation approval. Consent does
   not replace backup, exact-image preservation qualification, measured pacing,
   destination writer exclusion or proof that previous requests have settled.
   Keep all writers stopped until exact financial readback and the operation's
   normal-import selection checks pass. Resume the connector only under that plan.

`reference_updates` means comment only. `activity_corrections` means a displayed
replacement that can change financial values. `exact` and `probable` describe
association evidence, not acceptance of an amount. `blocked` never executes,
even with yes. The daily connector can migrate a unique legacy trade reference under the current
account mapping. Historical maintenance retains its separate operation authority.

Keep the schema-3 review file, its `.state.yaml` companion and both journals private. Preserve pending intent;
never delete a journal to resume. Existing [inspection and rollback](#guarded-comment-rollback-and-resume-inspection)
operate on the maintenance journal and require their own unchanged-row checks.
An older connector refuses schema 3. The first upgrade from schema 1 or 2 clears
old approvals once. Keep a private pre-upgrade copy and retain the compatible reader.

### Preservation comparison

Raw snapshots, preimages and fingerprints remain exact tamper evidence. Live
preservation compares business values rather than raw response bytes. Equivalent
numeric spellings and timezone offsets are equal, with no monetary tolerance.
The exclusions follow the inspected [Ghostfolio 3.90.0 activity implementation](https://github.com/ghostfolio/ghostfolio/blob/3.90.0/apps/api/src/app/activities/activities.service.ts)
and retained paired reads; they are not proof of request settlement.
The named exclusions are activity `updatedAt`, derived `value`, `valueInBaseCurrency`,
`feeInBaseCurrency`, `feeInAssetProfileCurrency`, `unitPriceInAssetProfileCurrency`;
account `updatedAt`; and profile `updatedAt`, `activitiesCount`, `dateOfFirstActivity`
and `watchedByCount`. Ghostfolio derives the last two from the earliest activity
and watchlist relationships in its [profile enrichment implementation](https://github.com/ghostfolio/ghostfolio/blob/3.90.0/apps/api/src/services/symbol-profile/symbol-profile.service.ts).
Changing an activity date or a watchlist must not invalidate consent or readback
through those derived fields. Other profile fields remain checked.
Historical maintenance still compares native account balances
when present in the capture. Normal review consent excludes independent account
balance changes; it continues to check account identity. All other fields remain checked.
The snapshot reader parses all response numbers as exact decimals, including nested
profile weights. Unknown fields are not discarded. Business or unknown-field drift stops further
writes. A changed implementation invalidates earlier previews; prepare them again.
A pending result remains uncertain even when a read shows the original comment.
The isolated image qualification must test background profile enrichment after PUT.
A change outside the named exclusions remains a refusal; offline comparison tests
do not establish that the live background jobs have settled.

## Offline historical identity evidence preview

Run from the versioned checkout, outside the runtime image:

```sh
python identity_migration.py preview --inputs inputs.yaml --output new-review
```

This stage validates saved evidence and publishes a deterministic manifest. It
has no network client and does not load runtime configuration or credentials.
Inherited `DRY_RUN=false` does not enable writes. It never edits an activity or
an input. It classifies exact historical eligibility and lists proposed comment
replacements. It replays complete import selection before and after the proposed
comment changes. The manifest keeps `actionable: false`: this offline proof does
not authorize conversion, apply or rollback.

Use keyed YAML with unique string keys. Quote dates and numeric identifiers.
Paths are relative to the YAML file. Absolute paths are also accepted. Hash each
saved file with SHA-256. Use the exact checkout commit as `tool_commit`.
The following example uses synthetic identifiers and placeholder hashes:

```yaml
schema: ibkr-migration-inputs-v1
tool_commit: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
timezone: Europe/Paris
window: ["2026-01-01", "2026-01-31"]
inventory_complete: true
accounts:
  U1: destination-account
symbol_mapping: {}
replay_order: [january-U1]
reports:
  january-U1:
    path: report.xml
    sha256: "<64 lowercase hexadecimal characters>"
    source_account: U1
snapshot:
  path: snapshot.json
  sha256: "<64 lowercase hexadecimal characters>"
  count: 1
  complete: true
  unredacted: true
  captured_at: "2026-02-01T00:00:00Z"
  capture_ref: saved-full-capture
  destination_version: "3.86.0"
  destination_image: "sha256:<64 lowercase hexadecimal characters>"
```

Declare every configured source account that can import into this portfolio.
Map each source account to its destination account. Supply at least one saved
report per account. Each report must identify that account through
`AccountInformation` and carry valid statement bounds. Bounds and the inventory
declaration establish input scope; they do not prove complete event coverage.
The union of saved statement bounds must cover every day of `window` for every
configured source account. Adjacent and overlapping reports are allowed. A gap
or short window blocks all proposed replacements. An account with no events still
needs a saved report with complete window bounds. The inventory declaration alone
cannot replace that report evidence.

Set `replay_order` to the intended query order. List each saved report key exactly
once. Shared simulated state advances across queries in this order, including
queries that map to the same destination account.
Use an IANA timezone and the same explicit symbol mapping as the intended replay.
Changed mappings or any changed input bytes change the manifest hash.

The complete snapshot is a JSON object with `activities` and `count`. Its count
must equal both the activity list length and the declared snapshot count. Supply
the saved original JSON numbers, not rounded floats or numeric strings. The tool
reads quantity, unit price and fee as exact decimals. Each row needs a unique
`id`, `comment`, `quantity`, `unitPrice`, `fee`, timezone-aware `date`, `type`,
`accountId`, `currency`, boolean `isDraft`, `tags`, and `assetProfile` or
`SymbolProfile`. Legitimate null comments, account assignments, currencies and
profiles remain visible as excluded evidence. Null financial numbers,
missing context, duplicate JSON keys and non-finite numbers are refused. Preserve
all original fields, including fields outside this minimum.

The output parent must exist. The output path must be new. Inputs and outputs
must have no symlink component and must not overlap. YAML aliases and duplicate
keys are refused. The tool checks every captured input again before publication.
It publishes `manifest.json` and `manifest.sha256` in a new directory with mode
0700. Files have mode 0600. The manifest preserves row evidence and fingerprints;
its exact decimals are strings. Equal input bytes produce equal output bytes and
hashes. Existing outputs are never replaced. Keep these private outputs outside
version control. A refused command exits nonzero and publishes no review.

### Exact historical eligibility

Only a unique source event and a unique owned historical row can qualify.
Trades require the exact legacy `IBKR#<tradeID>` comment. A trade ID claimed by
several source accounts blocks every affected replacement. Dividend comments can
use the resolved symbol, raw source symbol or ISIN in
`dividend#<key>#<YYYY-MM-DD>`. They must belong to the mapped destination account
and represent exactly one positive action. Split dividend and PIL portions of
that action are allowed. A row that represents several positive actions is an
aggregate and cannot qualify. A proven zero-net action claims no payment row.
Its signed tax still contributes to the historical fee comparison.

Both kinds require active YAHOO context, the same mapped account, side/type,
resolved security and supported currency. Any supplied conflicting account,
profile, ISIN or denomination evidence blocks eligibility. The source calendar
day must equal the stored instant's calendar day in the declared IANA timezone.
The proposed replacement retains the original stored timestamp byte for byte.
Quantity, unit price, gross and fee must match exactly. The tool compares original
decimals using exact fractions. It does not reconstruct numbers from floats.
Rational values such as `23/10` in expected fields and differences mean exact
ratios, not rounded amounts. The historical group fee and the proposed action fee
must each equal the stored fee after currency scaling and zero clamping. Opposite
signed tax or refunds cannot be hidden by netting or a rounding tolerance.

Manual, inactive, excluded, non-YAHOO, unsupported and unproven rows stay unchanged.
Duplicate old rows, conflicting source captures, occupied v2 identities and
partial action coverage block affected replacements. Identical events repeated
across saved reports have one decision with all source references. Duplicate
trade rows inside one report do not establish unique ownership. Malformed source
cash omitted by the runtime reader remains visible and blocks affected dividend
subsets. Outside-window history stays visible and unchanged.

The manifest lists each source event under `events` and each saved row under
`rows`. Event decisions retain source references, evidence variants, old/new
comments, associated activity IDs, association counts, expected financial fields,
exact differences, occupied IDs and an exclusion reason. Row decisions retain
all original fields, their fingerprint and links to source decisions. Separate
counts cover eligible replacements, already-v2 identities, absent/new candidates,
aggregates, ambiguity, conflicts, partial coverage, unsupported evidence and
outside-window decisions. `replacements` contains only proposed comment changes
with ordered IDs and before/after row fingerprints.

Historical deduplication remains more permissive than migration eligibility.
An exact historical comment can suppress an import without proving complete
events or exact financial values. The preview compares the full ordered payloads
and holdings decisions across the declared inventory and windows. It uses the runtime identity reader, selection,
manual matching, dividend coverage, holdings gates and accepted-state rules.
Buys and dividends advance isolated simulation state before sales. The snapshot
capture time supplies the replay clock. Input rows remain unchanged.

`selection_proof` records both replays, their hashes, query order and capture
clock. It compares payload fields and holdings decisions, not counts. A changed
payload, newly exposed trade, changed sale decision or unavailable replay blocks
all proposed replacements. This includes release of a legacy-global trade marker
that previously suppressed another configured source account. Exclusions remain
visible with `selection-changed`, `selection-unavailable` or `incomplete-window`.
An equal replay clears the selection gate. It does not certify source event
completeness, destination API preservation or authorization for maintenance.

The manifest binds input hashes, source and destination account mapping, symbol
mapping, windows, timezone, query order, tool commit, actual implementation file
hashes and destination image/version. `ordered_row_fingerprints` preserves snapshot
row order and before/after fingerprints, including unchanged rows. The existing
`replacements` list stays ordered by activity ID.

Any configuration, query order, account inventory, mapping, window, timezone,
source file, snapshot, tool revision or destination image/version change
invalidates this proof. Generate and review a new preview. Undeclared future
accounts are outside the proof. A future account could reuse a historical trade
ID; no lifetime or global uniqueness claim follows from this bounded replay.
No financial correction, split, insertion or deletion is proposed.

## Explicit application of reviewed historical comments

`identity_migration.py apply` is separate maintenance outside the runtime image.
It changes only reviewed historical comments. It never invokes cleanup deletion,
imports activities, updates cash or loads the runtime configuration. Preview stays
strictly offline. `DRY_RUN=false` does not authorize maintenance.

**Qualification remains pending.** Synthetic HTTP tests prove the tool's guards.
They do not prove G5 preservation, reverse PUT behavior, background effects or a
safe live cadence. Before any real use, obtain image-backed G5 evidence and
measured batch/pacing evidence for the exact destination version and immutable
image. Do not invent batch or pacing limits. A missing proof blocks real use.
The existing cleanup executors remain unqualified for v2 history.

Obtain a separately validated operation plan and operator GO. The plan must bind
the target, recoverable backup, stopped competing writers, independently settled
requests, exact write count, measured batch size, pause, stop rules and recovery.
Keep all writers stopped through readback. This includes cron, manual imports,
cleanup and other maintenance. The local lock protects only the same journal path.
References in an approval file are declarations, not proof of those conditions.
Confirm the current destination image/version independently before the operation.

Review a private approval file and its SHA256. Use this schema; the numeric limits
below are placeholders and must come from the qualified operation plan:

```json
{
  "schema": "ibkr-migration-approval-v1",
  "host": "https://ghostfolio.example.com",
  "manifest_sha256": "<reviewed-manifest-sha256>",
  "destination_version": "<qualified-version>",
  "destination_image": "sha256:<qualified-image-digest>",
  "owner_id": "<verified-destination-user-id>",
  "operation_plan_ref": "<validated-plan-and-separate-go>",
  "backup_ref": "<verified-recoverable-backup>",
  "writer_exclusion_ref": "<all-competing-writers-stopped-proof>",
  "settlement_ref": "<independent-outstanding-request-settlement-proof>",
  "preservation_qualification_ref": "<image-backed-G5-proof>",
  "pacing_qualification_ref": "<image-backed-measurement-proof>",
  "writers_stopped": true,
  "requests_settled": true,
  "write_count": "<replace-with-approved-integer>",
  "batch_size": "<replace-with-measured-positive-integer>",
  "pause_seconds": "<replace-with-measured-nonnegative-number>"
}
```

The three limit fields must be JSON numbers. String placeholders are refused.
`write_count` must equal the manifest replacement count. A batch is a sequence of
individual PUTs with complete readback after each PUT. The command waits for
`pause_seconds` between batches. It provides no default live limits.

Supply a session bearer only through `GHOST_TOKEN` in ENV. The command performs
no token exchange and reads no broker credentials. The target URL must contain
no credentials. Run only the command authorized by the operation plan:

```sh
.venv/bin/python identity_migration.py apply \
  --inputs private/inputs.yaml --review private/activities.yaml \
  --manifest private/selected-maintenance/manifest.json \
  --manifest-sha256 <reviewed-manifest-sha256> \
  --approval private/migration-approval.json \
  --approval-sha256 <reviewed-approval-sha256> \
  --journal private/migration-apply.yaml \
  --host https://ghostfolio.example.com
```

The command requires the shared review file and rebuilds the exact selected
manifest from `prepare`. A plain `preview` manifest cannot authorize apply. It
requires byte equality with the reviewed selected manifest. Preview remains `actionable: false`: approval of its content
alone never grants GO. Changed inputs, mapping, inventory, selection, implementation
bytes or target bindings require a new review. A preview with no replacements or
an unresolved selection gate is refused.

Apply creates an exclusive 0600 YAML journal with keyed rows and a companion lock.
Preserve both files. Existing journals, symlinks and journal/evidence collisions
are refused. Each record keeps the original full row, before/after fingerprints,
old/new comment and request status. Exact decimal evidence is stored as strings.
Keep the journal private. It contains no token.

Before the first PUT and each later PUT, a complete unredacted activities GET must
match every reviewed row and ID, including owner and identity occupancy. This is
stricter than checking only the rows selected for conversion. The command verifies
input bytes again before dispatch. Each listed row needs the approved `userId`.

The explicit PUT whitelist contains `id`, `accountId`, `comment`, `currency`,
`date`, `fee`, `quantity`, `symbol`, `type`, `unitPrice`, `dataSource` and tag IDs.
It preserves the stored timestamp and uses only eligible YAHOO profiles. It never
echoes raw GET fields into PUT. A number that cannot survive the JSON transport
conversion exactly is refused before the first write. The pinned API can enqueue
market-data gathering; synthetic readback does not qualify delayed background effects.

Before each PUT, the journal durably records `pending`. The command sends one
request with no redirect follow-up or automatic retry. Complete readback must
prove exactly the target comment and unchanged IDs, ownership, financial values,
dates, tags, profiles and all other captured fields. Only then does the row become
`verified`. A completely verified run records `complete`.

Stop on any stale or incomplete state, failed persistence, HTTP failure, redirect,
timeout, normalization or changed context. A failed command exits nonzero.
A row remains `pending` after an uncertain PUT or failed readback; verified earlier
rows remain explicit. Never retry under a new journal to bypass uncertainty.
An old-comment or absent-row readback cannot settle a delayed request. Keep writers
stopped and require independent completion/cancellation evidence before any new
operation, retry or reversal. Use the guarded inspection and rollback path below.
There is no automatic apply retry or resume.

Reverting the tool's code does not reverse converted comments. Preserve all rows,
inputs and journals. After v2 history exists, retain an rc.5-or-newer qualified
reader. Comment reversal requires its separately guarded maintenance path and
operation approval. Database restore is not the normal rollback; it requires its
own approval and reconciliation of intervening writes.


## Guarded comment rollback and resume inspection

Inspect a complete saved capture without HTTP or credentials:

```sh
python identity_migration.py inspect --journal migration.yaml \
  --manifest review/manifest.json --manifest-sha256 "$MANIFEST_SHA256" \
  --snapshot current.json --snapshot-sha256 "$SNAPSHOT_SHA256"
```

The command prints one state per journal-owned activity: `original`, `converted`,
`absent` or `drift`. A pending apply or reverse request adds `uncertain:`.
Inspection does not modify the journal. Old-comment, absent-row and converted-row
readbacks never clear uncertainty. The snapshot must contain the complete,
unredacted activity list and its matching count. Preserve original JSON numbers
and all fields. Equivalent numeric representations do not block reversal; changed values do.

Rollback uses the original reviewed manifest and the existing private journal:

```sh
python identity_migration.py rollback --journal migration.yaml \
  --manifest review/manifest.json --manifest-sha256 "$MANIFEST_SHA256" \
  --approval rollback-approval.json --approval-sha256 "$APPROVAL_SHA256" \
  --host https://ghostfolio.example.test
```

The separately approved rollback command reads `GHOST_TOKEN` from ENV.
It uses the same single-request HTTP helper and full whitelisted PUT payload as
apply. It restores only the original comments of unchanged journal-owned rows.
It checks IDs, ownership, financial numbers, currency, date, tags, profiles and
all other captured fields. It retains newly imported v2 rows. It never inserts
or deletes an activity and never changes cash or platform state.

The separate JSON approval uses schema `ibkr-migration-rollback-approval-v1`.
It requires `journal_sha256` for the exact current journal bytes and
`manifest_sha256` for the original reviewed manifest. Supply the same `host`,
`destination_version` and `destination_image`. Supply the apply approval's
prerequisite fields: `operation_plan_ref`, `backup_ref`, `writer_exclusion_ref`,
`settlement_ref`, `preservation_qualification_ref`, `pacing_qualification_ref`,
`owner_id`, `writers_stopped: true` and `requests_settled: true`. Set `write_count`
to the exact number of remaining converted rows. Set `batch_size` and
`pause_seconds` from qualified measurements. There are no default limits.

For each pending request, supply an entry under `settlements`, keyed by activity
ID. Each entry needs `direction` (`apply` or `rollback`), `outcome` (`completed`
or `cancelled`), `independent: true` and a nonempty `evidence_ref`. For example:

```json
{"settlements":{"synthetic-row":{"direction":"apply","outcome":"cancelled",
  "independent":true,"evidence_ref":"approved-independent-cancellation-proof"}}}
```

This declaration references evidence from a separately authorized operation.
It is not proof by itself. Use request-bound completion or cancellation proof
when available. A deployment-specific cancellation or quiescence proof needs
its own approved operation. A GET result cannot replace it. Without independent
proof, retain uncertainty and stop. The command checks that the settled outcome
agrees with the full current row. It records accepted settlement evidence in the
journal. It does not retry apply.

Before any reverse PUT, the command checks every journal row and freezes the
complete current snapshot. It checks that snapshot before and after each PUT,
including rows absent from the journal. It durably records `rollback_status:
pending` and the inverse payload before dispatch. Only an exact readback marks
that row `verified`. A timeout, drift, normalization or failed readback stops the
command and retains pending state. Earlier verified reversals remain explicit.
`rolled_back` means that all required comment reversals completed. Further work
after an interrupted reversal needs fresh independent settlement evidence where
pending, a new approval bound to the current journal, and the same full checks.
An already consumed approval cannot replay writes.

These offline tests do not qualify the destination image, background jobs,
measured pacing or actual rc.5 preservation. G5/G6 and separate operation GO
remain required before real maintenance. After failure, stop writers, force
`DRY_RUN=true`, retain every row and journal, and keep rc.5 or a newer qualified
dual reader. Never run pre-rc.5 code after any imported or converted v2 activity.
Comment reversal cannot remove newly imported v2 history. Resume writers only
after exact mixed-history review and separate GO. A database restore remains a
separate operation with reconciliation of intervening writes.

[Back to the README](../../README.md)

[Maintenance index](../maintenance.md)
