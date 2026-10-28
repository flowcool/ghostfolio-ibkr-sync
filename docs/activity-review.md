# Activity correction review

Activity review is an opt-in, qualified workflow. Read the [README safety notes](../README.md#safety-first) before enabling it. The full contract is kept here so the landing page stays readable.

## When to use

Set `ACTIVITY_REVIEW_FILE` to enable persistent proposals for supported BUY,
SELL and DIVIDEND events. Blank retains the existing additive import path.
The reader accepts a canonical v2 first line, one blank separator line and
preserved user notes, even after review is disabled.

## Safety limits

Review dispatch is qualified for Ghostfolio image
`sha256:929a54a1972c48f3cfb30af2db6f9f2aaeb610a9cc5f53264f1df1629eb43078`
with **at most one correction per connector run**, across all configured accounts.
Other approved proposals remain unchanged for later runs and keep their import
holds. The zero inter-correction delay is unused with this single-correction
limit; it does not certify immediate repeated runs or background completion.
Verify the destination image before enabling review. A different image requires
renewed qualification. No ENV setting changes this budget. Production activation
and stable publication retain their separate approval. See
[qualification evidence and limits](releasing.md#activity-review-qualification).

## Configure persistent review

Mount a dedicated persistent directory. The parent must exist. Files must be
owned by the runtime user, readable and writable, mode `0600`. Symlinks, hard
links and overlap with mapping/source/evidence inputs are refused. Create the
host `review` directory with mode `0700` owned by `10001:10001`. Merge these
additions into the existing service; this is not a standalone Compose file.
Prepare the directory before starting the service:

```bash
mkdir -p review
chmod 700 review
sudo chown 10001:10001 review
```


```yaml
services:
  ibkr-sync-individual:
    environment:
      DRY_RUN: "true"
      ACTIVITY_REVIEW_FILE: /review/activities.yaml
    volumes:
      - ./review:/review
```

## Review a proposal

Review acquires and validates all configured reports once before corrections,
then reuses them for normal processing. Exact references take priority over
proximity, including outside the date window. Other candidates require the same
account, operation type, security and denomination. Trade proximity is inclusive
±2 UTC calendar days; dividend proximity is inclusive ±3 days. Amount agreement
never grants approval. A manual BUY two days later remains a candidate even when
its quantity differs. A dividend three days later also remains a candidate.
Separate fills/actions are never combined. Dividend cash portions from one action
reuse normal withholding and quantity conversion. Partial action coverage and
conflicting context remain refused. Legacy dividend aggregates are excluded.
Current report windows do not prove historical cross-account coverage for
legacy-global `IBKR#<tradeID>` upgrades; those remain non-actionable.

The schema-2 YAML contains two sections in the same private file:

| Section | What you approve | What stays unchanged |
|---|---|---|
| `reference_updates` | The connector reference in `comment` only | Date, quantity, price, fee, account, activity ID, tags and notes |
| `activity_corrections` | The displayed one-to-one replacement, including any financial changes | Activity ID, account, owner, tags and preserved notes |

Each proposal shows `execution path`, `evidence level`, stable keys, source
account/event, destination account/activity, match reason, current/full proposed
values, changed fields, status and `approve`. Read the full proposed comment.
`exact` means the association is proven by the supported identity evidence.
`probable` means a supported proximity match needs your judgment. `blocked` means
required evidence is missing or conflicting; even yes cannot make it writable.
These levels describe the association, not the correctness of a financial amount.
No confidence percentage grants authority.

The file is generated. Do not create proposal keys or move entries between sections.
A reference-only proposal has `changed fields: [comment]`. A financial correction
shows exact before/after values under `current values` and `proposed values`. Numbers are exact plain-decimal text from the transmitted
payload and original response JSON. Equivalent numeric spellings compare equal;
financial tolerance never grants authority. Dates compare as full UTC instants.

For example, these excerpts show two generated entries. The real file also
contains the binding and complete values. Do not copy this abbreviated example
as an input file:

```yaml
version: 2
reference_updates:
  "<generated-key>":
    section: reference_updates
    evidence level: exact
    execution path: historical maintenance
    source event: "IBKR#v2#U1:TRADE:123"
    activity id: "<existing-activity-id>"
    changed fields: [comment]
    approve: yes
activity_corrections:
  "<another-generated-key>":
    section: activity_corrections
    evidence level: probable
    execution path: normal run
    changed fields: [comment, quantity]
    approve: null
```

## Approve a proposal

Edit only `approve`, between runs. Locate the generated proposal and change:

```yaml
approve: yes
```

Only lowercase `yes`, plain or quoted, approves the displayed replacement.
Every other approval value is skipped for that cycle. Blank/null stays pending;
`no`, `true`, `y`, `Yes` and typos do not approve anything. A non-null skipped
choice produces a warning. It is not stored as a rejection and does not release
the related import hold. Unknown fields, invalid bindings and invalid schemas
remain errors. One source can select one target and one target one source.
Conflicting approvals dispatch nothing for the affected account. New proposals
start blank. Changed source, target, owner, tags, notes, mapping or relevant
identity occupancy clears approval. A shorter report retains `source unavailable`
with its approval suspended; unchanged evidence can resume on return.

Pending proposals hold related imports before ordinary deduplication and holdings
selection. Unrelated events continue. Deleting an entry causes blank rediscovery.
There is no rejection choice: resolve false matches manually in Ghostfolio.
Release requires an exact manual/connector correction, or positive proof that
all former candidates now belong to other identified events. Missing or inactive
targets stay held. New candidates are checked before ordinary selection resumes;
that selection can still refuse an import.

## Choose the execution path

The `execution path` tells you how an approved proposal can run:

| Execution path | Command | Separate operation authorization |
|---|---|---|
| `normal run` | Normal connector cycle, after correction activation is qualified | Subject to the configured correction contract |
| `historical maintenance` | `identity_migration.py prepare`, then separately authorized `apply` from the checkout | Required; yes alone never authorizes maintenance |

Historical conversion uses this same file, but runs outside the daily connector.
For example, an old global trade reference may need historical cross-account
proof that current runtime reports cannot supply. Keep the connector and other
review-file writers stopped while staging, approving, preparing and applying
that maintenance selection. Normal refresh can replace the staged evidence and
clear its approval. Do not copy a yes onto a new proposal.

Follow the [shared-file historical workflow](maintenance/identity-migration.md#historical-maintenance-with-the-shared-review-file).
Preparation checks the exact subset you approved. A proof for all candidates
does not authorize a smaller selection. Preparation sends no financial request. Preparation and apply hold the shared
review lock. Apply requires this file and removes confirmed selections. Staging
again clears historical approvals; review and approve them again, including after rollback.
Apply still requires the reviewed target, qualified preservation and pacing,
settled requests, exclusive destination writers, backup and a separate operation GO.
Do not bypass a blocked runtime trade by editing its evidence or execution path.

Schema 1 remains readable. The first schema-2 refresh clears old approvals once;
read the new presentation before setting yes again. Journals retain pending
request fences. An older connector refuses schema 2. Keep a private file copy
before upgrade; do not downgrade or edit a pending journal to resume writes.

## Execute an approved correction

After qualification, each unchanged approved correction sends one whitelisted
PUT. It preserves activity ID, account, owner, tags and non-reference notes.
It sends no correction POST/DELETE. Whole-comment recognized legacy references
alone can be replaced. Legacy references followed by notes are ambiguous.
Canonical v2 notes and manual notes survive exactly. Unsupported profiles,
changed profile metadata, unpreservable numbers, ambiguous references, API trimming
and overlength comments keep affected corrections unavailable.

Before PUT, `<review-file>.journal.yaml` records full before/after evidence,
request and bindings. Requests are sequential; exact readback precedes the next
request. The qualified limit defers remaining approvals unchanged. Holdings and
identity indexes are rebuilt before ordinary imports; a corrected BUY counts once.
A correction failure blocks later imports, cash and platform writes on that account.
Other safe accounts continue. Ordinary import failures keep independent cash.
Failure notifications retain the single summary without financial details.

## Recovery

Recovery reads immediately, then after 2, 5 and 10 seconds. These waits do not
prove settlement. Only complete expected-after evidence resolves a request,
including a separately authorized manual correction to that exact state.
Unchanged old state, drift, deletion or unavailable evidence retains the account
block across restarts. There is no retry PUT, reset, abandon or interactive prompt.
Logs identify account/activity, expected fields and observed differences.
Never delete or edit a journal to resume. Preserve its private financial evidence.

Simulation refreshes proposals and clears stale approvals without financial writes
or consuming valid `yes`. It cannot resolve a real pending journal or release
its account block, even when expected-after values appear. A later live run must
verify and durably record completion.

`<review-file>.lock` excludes overlapping cooperating runs. Atomic synced
replacement and byte checks detect observed edits before dispatch/publication.
Advisory locking cannot exclude arbitrary editors. Require exclusive destination
writers and edit the review only between runs. File syntax/schema, unknown
proposal and lock errors stop all accounts sharing the file. A non-yes approval is skipped; it does not block unrelated account writes. A detected edit preserves operator
files and pending intent and stops the affected run.

## Disable review

To disable preview, stop the connector and remove the ENV value. Keep its files.
Do not disable review to bypass uncertainty; stop writers until exact readback
resolves it. Software rollback does not restore data. After notes-bearing writes,
retain a qualified notes-compatible reader; bare-v2 rc.5 alone is insufficient.
Offline journal inspection can prepare a guarded reverse payload for an unchanged
confirmed row only. Reversal requires separate authority and never runs automatically.
See [journal inspection](#activity-review-journals) and
[release qualification](releasing.md#activity-review-qualification).


### User action required and container path

The private log names the configured ACTIVITY_REVIEW_FILE container path, section,
proposal key, held event and reason. A proposal count is not a held-event count.
Resolve the host path from your Compose volume mapping. For example,
`./review:/review` maps `/review/activities.yaml` to
`./review/activities.yaml`, relative to the Compose project directory.
Keep the existing corporate-action mount at `/state`; review uses `/review`.
The connector does not discover host mounts.

For an eligible `normal run` proposal, compare current and proposed values and
execution path. Edit only `approve` between runs. Only lowercase literal `yes`
approves that exact eligible proposal. Never approve proposals in bulk. Simulation
executes no financial write. Already approved work waiting for the qualified limit
remains automatic work; do not approve again or force reruns.

For missing proof, invalid/stale choices or conflicts, inspect the reason and
restore current source and destination proof. `yes` cannot make blocked work
executable. Historical maintenance needs the documented preparation and separate
operation authorization; normal sync cannot execute it. For an uncertain request,
inspect the preserved journal and exact destination readback. Do not resend,
delete or edit the journal to release a hold. False matches need the documented
manual resolution and retain separate cleanup authority.


## Activity review journals

Optional normal-run review uses a separate private journal. It calls no cleanup,
migration, recovery-submit or deletion executor. Do not pass its journal to those
tools. Keep `<review-file>.journal.yaml` and its companion lock on the volume.
Never delete or edit an unresolved journal to release an account. Only live exact
expected-after evidence resolves it.

For offline inspection, load YAML without mutation. Compare its full `before`,
`after`, `request`, binding and status with an exact saved JSON snapshot.
`activity_review.inspect_reverse(entry, observed_row)` prepares a whitelisted
reverse request only for an unchanged confirmed after image. It sends no request.
Reversal needs separate explicit authority and fresh ownership/unchanged-row
checks. Software rollback does not restore financial data.

Runtime and offline identity readers use the first line of notes-bearing v2
comments. Extended reading does not qualify destructive maintenance tools;
their existing separate image-qualification boundary remains.
