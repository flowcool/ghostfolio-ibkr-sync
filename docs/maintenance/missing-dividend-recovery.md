# Missing dividend recovery

**Before submission:** obtain separate approval for the exact target and reviewed
missing actions. Keep a verified backup, stop competing writers and settle every
outstanding request independently. Stop on target drift, uncertain dispatch or
failed readback. Preserve rows, manifest and journal. There is no automatic resend
or financial rollback. The preview below is offline and grants no write authority.

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

[Maintenance index](../maintenance.md)
