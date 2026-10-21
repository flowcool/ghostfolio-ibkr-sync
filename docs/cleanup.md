# Inspecting an interrupted cleanup

Run the commands below from the repository root, not from `docs/`.
For recovery after a shortened Flex query, first read the
[query-window and cleanup safeguards](ibkr-setup.md#2-create-a-flex-query).

The cleanup tools are operator maintenance commands, outside the container image.
They do not log in by themselves: they read only `GHOST_TOKEN` and `GHOST_HOST`, even if the
sync uses `GHOST_ACCESS_TOKEN`. Before a cleanup session, get a session token with the curl
command in [Ghostfolio Setup](../README.md#1-choose-how-the-sync-authenticates) and export it as `GHOST_TOKEN`.
Heuristic pair matching still requires a reviewed dry-run, verified backup and quiet
portfolio writers. The recovery feature does not authorize financial repair by itself.

Do not run the existing pair cleanup tools against v2 activity history until
they are separately qualified. The dividend recovery preview below is a distinct
offline command. It does not use the pair cleanup executor.

For a separately authorized cleanup, select an explicit journal path:

```bash
python cleanup_duplicates.py --apply --journal cleanup-pairs.yaml
# Dividend equivalent: python cleanup_dividends.py --apply --journal dividend-pairs.yaml
```

Apply stores a private keyed YAML journal before the first mutation. Each pair records
both verified activity preimages, user/account identity, intended comment and PUT/DELETE
states. Updates are written atomically and synced to disk; an exclusive companion lock
prevents concurrent use of the same journal. Preserve both files with your backup.
Credentials are not stored; keep the journal private because it contains portfolio data.

After an interruption or error, inspect without writes:

```bash
python cleanup_duplicates.py --resume cleanup-pairs.yaml
```

Inspection checks every pair against fresh user-scoped API records. A timeout may have
committed: the fresh retained comment and deletion target decide the next action, not
a stale status flag. Missing or changed retained records, different owners, values,
accounts, currencies, sources or tags are refused. A missing synced record counts as
complete only if the retained manual record is verified with the intended comment.
Legacy JSON snapshots do not contain the required outcome/ownership contract and are
not accepted as recovery journals.

For a separately authorized resume, quiesce other writers, retain the journal, and run:

```bash
python cleanup_duplicates.py --resume cleanup-pairs.yaml --apply
```

Dividend journals with date gaps above 7 days remain available for read-only
inspection, including journals created before this safeguard. `--resume --apply`
refuses them before any mutation; verify and reconcile those payments manually.

Recovery revalidates immediately before mutation, skips a PUT already verified as
committed, and skips a DELETE already verified as complete. An unchanged untouched
pair can continue normally. Repeated successful recovery sends no further mutations.
An unknown mutation stops the run for another inspection; there is no automatic
compensation or reinjection. The API has no conditional writes or pair transaction,
so other writers must remain stopped during apply/resume. A readonly inspection does
not constitute a guarantee against later concurrent edits.


## Offline preview of missing v2 dividend actions

Use `identity_recovery.py preview` only to inspect a saved partial import.
Run it from the repository root with the development dependencies installed.
The tool stays outside the container image. It reads no credentials or ENV
configuration and sends no HTTP requests. Inherited `DRY_RUN=false` does not
enable writes. Only the separate `submit` command can send an import.

Prepare these private inputs:

- The complete, unchanged Flex XML used for the original submission. It must
  contain one statement with explicit date bounds, Account Information, Cash
  Transactions and the required dividend accrual evidence. Keep all actions,
  payment portions and associated tax rows. Do not shorten the report.
- A fresh, complete, unredacted saved Ghostfolio response. Use the original JSON
  numbers. The response must contain `activities` and its full `count`. Each row
  needs its ID, comment and original quantity, unit price and fee. Accepted rows
  also need account, date, currency, active state and security profile context.
- A keyed JSON evidence file with the schema below. Keep the original submitted
  payloads, not values reconstructed from accepted rows. Record every outstanding
  request for this attempt. A settlement reference must point to independent
  completion or cancellation proof. An absent row or old-comment readback alone
  cannot settle a delayed request. Capture the destination after settlement.

The evidence file uses this structure. Replace the illustrative values with
verified capture metadata. Include every original action payload for each
affected security/day group, including the already accepted actions.

```json
{
  "schema": "ibkr-recovery-evidence-v1",
  "source_sha256": "<original-submission-source-file-sha256>",
  "destination_sha256": "<fresh-snapshot-file-sha256>",
  "source_complete": true,
  "destination_complete": true,
  "unredacted": true,
  "source_account": "U123",
  "destination_account": "destination-account-id",
  "window": ["2026-01-01", "2026-01-31"],
  "symbol_mapping": {},
  "tool_commit": "<original-submission-tool-commit>",
  "destination_version": "<captured-version>",
  "destination_image": "sha256:<captured-image-digest>",
  "snapshot_ref": "<private-capture-reference>",
  "snapshot_captured_at": "2026-02-01T12:00:00Z",
  "requests": {
    "original-request-id": {
      "status": "completed",
      "settlement_ref": "<independent-completion-or-cancellation-proof>",
      "settled_at": "2026-02-01T11:00:00Z",
      "payloads": [
        {
          "accountId": "destination-account-id",
          "comment": "IBKR#v2#U123:DIVIDEND:action-id",
          "currency": "USD",
          "dataSource": "YAHOO",
          "date": "2026-01-10T00:00:00+00:00",
          "fee": 3.75,
          "quantity": 100,
          "symbol": "EXAMPLE",
          "type": "DIVIDEND",
          "unitPrice": 0.25
        }
      ]
    }
  }
}
```

`symbol_mapping` contains the exact original ISIN-to-symbol mapping. The only
settled request statuses are `completed` and `cancelled`. Completeness and
settlement declarations need external evidence. The offline tool cannot prove
that an omitted request or source action does not exist.

Review the evidence file and obtain its SHA256 before running:

```bash
.venv/bin/python identity_recovery.py preview \
  --source private/source.xml \
  --destination private/activities.json \
  --evidence private/recovery-evidence.json \
  --evidence-sha256 <reviewed-evidence-sha256> \
  --output private/recovery-preview
```

The output parent must exist. The command creates a new directory with mode
0700 and `manifest.json` and `manifest.sha256` with mode 0600. Existing outputs,
symlinks and input/output overlap are refused. Keep the output private. Identical
input bytes produce an identical manifest hash. The manifest binds all input
hashes and capture metadata. It lists only the exact missing import payloads,
accepted-row fingerprints and group coverage. Original JSON decimals are read
without float rounding. Fingerprints retain their exact decimal representation;
missing import payloads use the runtime's numeric conversion rules.

The preview compares all source actions with the original submitted payloads.
It refuses changed financial values, missing quantity or tax evidence, duplicate
identities, unresolved requests, overlapping manual or unexpected v2 actions,
and changed ownership or active context. Accepted rows are never changed.
Already complete groups produce no missing payload. A group without any proven
accepted action is outside this recovery path.

An exact historical comment can suppress a group without proving its event
completeness. The preview refuses that ambiguity. Equal amounts do not establish
ownership. Saved evidence proves only its declared accounts and window; it does
not establish lifetime action identity or future snapshot freshness.

Review the manifest before any operation. A preview authorizes no import,
historical conversion or retry. Submission requires a separate approved operation
plan, stopped competing writers, settled outstanding requests and fresh evidence
checks. Recovery must submit only reviewed missing actions, prove full coverage
by readback and prove zero reinsertions in normal simulation. The submission
command below implements that path. Its synthetic tests do not qualify the source,
the current destination image or writer enablement. Normal sync keeps refusing
partial action coverage.


## Explicit submission of reviewed missing actions

`identity_recovery.py submit` is a separate maintenance import. It does not change
comments, update cash, delete records or resume a prior journal. Keep all competing
writers stopped through submission, readback and simulation. This includes cron,
manual imports, cleanup tools and other maintenance commands. The local journal
lock protects only the same journal path. It does not stop other writers.

Before use, obtain a separate approved operation plan with the exact target,
commands, backup, writer exclusion, request settlement, stop conditions and recovery
procedure. Keep independent completion or cancellation proof for all outstanding
requests. Negative readback does not settle a delayed request. Verify the current
destination version and immutable image against the qualified target. Any drift
requires renewed qualification. These checks are operator prerequisites. A JSON
declaration cannot establish them by itself.

Create a private approval file and review its hash. Use this schema:

```json
{
  "schema": "ibkr-recovery-approval-v1",
  "host": "https://ghostfolio.example.com",
  "manifest_sha256": "<reviewed-manifest-sha256>",
  "destination_version": "<qualified-version-from-evidence>",
  "destination_image": "sha256:<qualified-image-digest-from-evidence>",
  "operation_plan_ref": "<approved-plan-and-operator-go>",
  "backup_ref": "<verified-private-backup>",
  "writer_exclusion_ref": "<proof-all-competing-writers-are-stopped>",
  "settlement_ref": "<independent-proof-all-outstanding-requests-are-settled>",
  "writers_stopped": true,
  "requests_settled": true
}
```

The host must be a credential-free base URL. Supply a session bearer through
`GHOST_TOKEN` in ENV. The command reads this credential only for `submit`. It does
not exchange tokens, read broker credentials or load the connector configuration.
Do not put a credential in a command argument or the approval file.

Run only the command authorized by that plan:

```bash
.venv/bin/python identity_recovery.py submit \
  --source private/source.xml \
  --destination private/activities.json \
  --evidence private/recovery-evidence.json \
  --evidence-sha256 <reviewed-evidence-sha256> \
  --manifest private/recovery-preview/manifest.json \
  --manifest-sha256 <reviewed-manifest-sha256> \
  --approval private/recovery-approval.json \
  --approval-sha256 <reviewed-approval-sha256> \
  --journal private/recovery-submit.yaml \
  --host https://ghostfolio.example.com
```

The command rebuilds the preview and checks every reviewed input. It creates an
exclusive 0600 keyed YAML journal and a companion lock. Preserve both. It reads
all destination activities in one GET and requires the snapshot to match the
reviewed snapshot. It checks the input hashes again before dispatch. Snapshot
numeric representation and row order are compared conservatively; a mismatch
requires fresh evidence and a new reviewed preview.

Before the single POST to `/api/v1/import`, the command durably records `unknown`.
It sends only the manifest's missing payloads with the existing numeric conversion
rules. It sends no redirect follow-up or automatic retry, including on a rejected
symbol. A complete accepted response needs unique new row IDs and exact ownership,
identity, security, date, currency, quantity, price and fee. A partial response
records `partial` and stops. An error or ambiguous response leaves `unknown`.

After complete acceptance, the journal records `accepted_unverified`. A fresh
complete GET must prove all expected actions, exact accepted row IDs, unchanged
existing rows and no extra rows. The command then uses the normal runtime reader
and dividend selection rule with simulation enabled. Every recovered source group
must select `existing`, with zero reinsertions. This check covers the reviewed
recovery groups and window. It does not certify unrelated source groups or a full
connector run. Only then does the journal record `complete` and a readback hash.
The normal simulation uses a third GET. No normal sync import or cash update runs.

Stop on stale evidence, unresolved requests, writer drift, journal persistence
failure, HTTP errors, redirects, malformed responses, partial acceptance, changed
rows, incomplete coverage or simulation refusal. A failed command exits nonzero.
Do not retry it with another journal. `prepared` proves no dispatch by this command;
`unknown` requires independent settlement evidence; `partial` preserves the proven
accepted subset; `accepted_unverified` requires readback investigation. An existing
journal is always refused. There is no automatic resume command.

Keep writers stopped after failure. Preserve accepted rows and all evidence.
Settle any delayed request independently. Obtain fresh complete snapshots, a new
reviewed preview and a new operation approval before further recovery. Reverting
the tool does not undo imported activities. Never delete accepted actions as an
automatic rollback. Retain an rc.5-or-newer reader after v2 history exists.


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
timezone: Europe/Zurich
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
  --inputs private/inputs.yaml \
  --manifest private/review/manifest.json \
  --manifest-sha256 <reviewed-manifest-sha256> \
  --approval private/migration-approval.json \
  --approval-sha256 <reviewed-approval-sha256> \
  --journal private/migration-apply.yaml \
  --host https://ghostfolio.example.com
```

The command rebuilds the complete offline preview and requires byte equality with
the reviewed manifest. Preview remains `actionable: false`: approval of its content
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
operation, retry or reversal. This apply slice has no resume or rollback command.

Reverting the tool's code does not reverse converted comments. Preserve all rows,
inputs and journals. After v2 history exists, retain an rc.5-or-newer qualified
reader. Comment reversal requires its separately guarded maintenance path and
operation approval. Database restore is not the normal rollback; it requires its
own approval and reconciliation of intervening writes.

[Back to the README](../README.md)
