# Activity correction review

Enable activity review only after qualification.
Read the [safety notes](../README.md#safety-first) first.

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

Use a dedicated persistent directory. Create it before starting the service.
Set owner `10001:10001`, directory mode `0700` and file mode `0600`.
The runtime user needs read/write access.
Symlinks, hard links and overlap with mapping, source or evidence files are refused.

```bash
mkdir -p review
chmod 700 review
sudo chown 10001:10001 review
```

Add this snippet to the existing service. It is not a complete Compose file.

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
±2 local calendar days; dividend proximity is inclusive ±3 days. Amount agreement
never grants approval. A manual BUY two days later remains a candidate even when
its quantity differs. A dividend three days later also remains a candidate.
Separate fills/actions are never combined. Dividend cash portions from one action
reuse normal withholding and quantity conversion. Partial action coverage and
conflicting context remain refused. Legacy dividend groups require independently unique one-to-one pairs.
The configured mapping owns historical trade-reference migration.

The schema-3 YAML contains a summary, groups, conforming activities and two
proposal sections in one operator file:

| Section | Operation | Preserved values |
| --- | --- | --- |
| `reference_updates` | Change the connector comment only | All other activity values |
| `activity_corrections` | Apply the exact displayed one-to-one correction | ID, account, owner, tags and supported notes |

Each entry shows its stable key, revision, source event, destination activity,
security, type, execution path, association evidence, profile authority and status.
`current` and `proposed` contain exact values. Read the complete proposed comment.
`operation fields` lists the fields that this decision can change.
A blocked status does not replace the association evidence.
No association label or confidence percentage grants correction authority.
The private `.state.yaml` companion retains full evidence and recovery bindings.
Do not edit that file. Do not move entries or add keys to the operator file.

This excerpt omits generated fields. Do not use it as an input file:

```yaml
version: 3
reference_updates:
  "<generated-key>":
    execution path: normal run
    source event: "IBKR#v2#SOURCE:TRADE:123"
    destination activity: "<existing-activity-id>"
    match evidence: legacy alias
    profile authority: conservative
    operation fields: [comment]
    current:
      comment: "IBKR#123"
    proposed:
      comment: "IBKR#v2#SOURCE:TRADE:123"
    decision: null
```

## Decide on a proposal

Edit only `decision`, between runs. Use lowercase literal `yes` to approve the
exact displayed operation. Plain and quoted `yes` have the same meaning.
Use lowercase literal `reject` to reject that source-target association.
Null stays pending. Boolean `true`, `no`, `y`, `Yes` and typos grant no authority.
The connector warns about unsupported non-null decisions.
A profile supplies separate authority. It does not write `yes` for you.

One source can select one target. One target can select one source.
Conflicting decisions block every affected correction before dispatch.
New candidates start blank. Changes to bound operation evidence clear consent.
An unavailable source suspends consent. No request uses cached source data.
Deleting an entry permits blank rediscovery. It does not authorize import.

Pending candidates hold related imports. Unrelated events continue.
An exact confirmed correction releases its alternatives without modifying them.
Ordinary import selection still applies its identity and holdings guards.

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

The private log names the container path, section, proposal key, held event and reason.
Proposal counts and held-event counts differ.
Use the Compose volume mapping to find the host file. For example,
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

### Proven numeric representations

Profiles compare exact source and destination gross values in major units.
They can normalize GBP and GBp by the fixed factor 100.
They do not use exchange rates or inferred market scaling.

A calculation residue must reproduce the existing converter's division,
fixed-unit multiplication and JSON number serialization.
For example, the converter can represent a scaled price of `1.8` as
`1.7999999999999998`. A nearby unexplained value is not that residue.
The evidence retains the source total, payload total, destination total,
unrounded difference, reproduced price and finite binary error bound.
Display totals use decimal half-even rounding once, after multiplication.
The connector does not round quantities or payload prices for matching.
Readback still requires the exact transmitted values.

### Mapping responsibility for historical references

The configured source-to-destination account mapping establishes ownership.
A unique current trade can upgrade its whole-comment legacy `IBKR#` reference.
The upgrade changes only the comment. It preserves every financial field,
account, owner, tag and supported note. A remaining difference becomes a
separate correction after exact readback confirms the reference upgrade.
Observed competing claims, duplicate targets and occupied v2 identities stop
migration. Equal trade IDs mapped to separate destinations are independent.
Historical cross-account coverage is not required.
After confirmed migration, the connector rebuilds normal selection.
Another account's previously suppressed trade can then pass its ordinary
account-scoped checks. Review the mapping before enabling a profile.
Historical maintenance retains its separate saved-evidence and operation GO.

### Compact-state recovery and downgrade

Back up the operator YAML, its `.state.yaml` companion and its journal together.
Keep them private in the same persistent directory. Stop all writers first.
Readers accept review schemas 1 and 2. The first schema-3 publication clears
legacy approvals once. New journal entries use version 2. Version-1 unresolved
requests remain readable with their original keys and revisions.
Old images refuse the new review and journal schemas.

A missing or corrupt private state stops correction. Do not delete a journal,
reset a pending request, or resend a request to recover.
For offline reconstruction, use the saved-input manifest from the maintenance
workflow. Run from the exact checkout, with all writers stopped:

```bash
python identity_migration.py rebuild-review --inputs INPUTS --review REVIEW
```

This command uses saved inputs and sends no HTTP request.
It retains surviving files under content-addressed `.retained-` names.
It clears all decisions and discloses lost rejection history.
It preserves unresolved journals and their account fences.
Rebuilt candidates cannot receive profile authority during the first later
live publication cycle. A subsequent run must validate them again.
A retained previous generation can recover unchanged decisions after interrupted
publication. An unknown generation stops without replacing either file.

Keep a schema-3 reader until every unresolved request is settled by exact
readback. A software downgrade does not restore activity data.
Reverse financial writes require separate authority and fresh preservation proof.

### Persistent false-match rejection

Set `decision: reject` for a false source-target association.
The connector retains that pair in private state and shows its rejected status.
It does not modify the target or reject the source event.
The same target remains available for every other event.
Fees, tags, notes, profile and timezone changes alone retain rejection.
Changes to identity, ownership, security, date, quantity, gross evidence, mapping
or relevant identity occupancy clear rejection and publish a blank candidate.
That candidate has no automatic authority during the invalidation cycle.

When every candidate is validly rejected, the source can resume ordinary import
checks. Recognized references still claiming that source retain their hold.
Existing identities, unresolved journals, corporate holds and holdings checks
still apply. Rejection grants no cleanup or historical-maintenance authority.
Missing sources suspend decisions. A complete listing can suspend an already
rejected absent target without restoring that pair's candidate hold.
An inactive or unreadable target retains its hold.
