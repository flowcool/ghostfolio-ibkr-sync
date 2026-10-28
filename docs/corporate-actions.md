# Corporate-action safety

The Flex query must select **Corporate Actions**, including when it is empty.
Follow the [required fields](ibkr-setup.md#corporate-actions-required).
A missing section holds all BUY/SELL for that source account. Unrelated securities,
other accounts and independent cash keep their existing guards. A pending or
uncertain financial write keeps its stronger account-wide fence.

Set `CORPORATE_ACTION_STATE_FILE` inside a persistent directory owned by the
container user. Use directory mode `0700` and file mode `0600`. Mount the directory,
not a single file. The companion `.evidence/` directory retains immutable complete
reports with source account, query, declared period, mapping fingerprint and hashes.
The connector reparses those reports after an event leaves the current window.
Hashes detect changed evidence; they do not authenticate a coordinated rewrite.
Keep the entire directory private and back it up with its input evidence.
Ordinary reports expire automatically after **30 days (720 hours)** from durable UTC
acquisition time, on the next run. Simulation also performs this local maintenance.
There is no retention ENV setting, quota or maintenance command. Re-reading the same
acquisition or changing file timestamps does not renew its age. Legacy reports receive
one persisted migration time and a full 30-day grace period. Invalid or future acquisition
times cannot justify early removal.

The connector keeps selective complete originals for known events, revisions,
conflicts, relevant trades, dated position anchors, identities and continuous coverage.
It removes a redundant safety copy only after it verifies surviving originals and their
source facts. A matching holding, closed position or manual reconciliation does not
retire required evidence. Useful safety history can still grow with new facts and
required chains; 30 days is not a total storage bound. Different dated quantity anchors
or query/mapping bindings can prevent proof of redundancy and remain retained.
Additional compatible Flex columns can complete older evidence; changed shared facts
or event legs remain conflicts.

A versioned `.references.yaml` companion records active acquisitions and pending
cleanup. The `.rotation` marker prevents recovery from reviving obsolete bindings
if that index is lost. The connector publishes and verifies durable references before
removal. Restarts retry interrupted cleanup. Only required safety originals and the
current source enter normal reconciliation. Each required XML is hash-verified and
parsed once per run; later reconciliations reuse facts and reject file metadata changes.

Maintenance-only failure logs a warning and joins the configured consolidated
notification once per run. It does not change exit status or otherwise safe imports.
Missing or invalid required evidence still holds affected BUY/SELL. Independent cash
keeps its existing guards. Proposals, mappings, official input documents and correction
journals remain outside rotation. Reconciliation still uses current logs and proposals;
the user handles manual cleanup and reruns analysis. There is no persistent reconciliation
job or archive replay. Keep a private copy for an investigation longer than 30 days,
or obtain another broker export. Expired ordinary archives cannot be recovered here.

Run simulation first. A valid report with the required section initializes missing
state and publishes its bounded inventory. Review the inventory before live mode.
Missing/unwritable state or active holds make simulation exit **1**. Live mode
holds BUY/SELL if state, permissions, locks or evidence are unavailable. Cash keeps
its existing guards. No available report window proves a complete lifetime history.

Findings separate identity, effective quantity, acquisition cost/dates and cash.
Current quantity agreement does not certify historical cost. A cost/date difference
alone does not hold proven units. Missing dates, source coverage, before quantities,
reverse legs or explicit old/new ISIN mappings keep the event unresolved. Both ISINs
of a transition must map explicitly to one active destination profile. An unmatched
pre-event trade in an already-normalized history remains held. Boundary-day trades
remain ambiguous. Acknowledgment and an activity-review `yes` cannot release a hold.

### Official effective-date evidence

Set optional `CORPORATE_ACTION_EVIDENCE_FILE` to a private YAML file. For each event,
verify the market effective date in an official issuer, exchange or broker document.
Retain the document locally. Record its SHA256 and public HTTPS source URL.
Use a URL without credentials, query or fragment. The
connector checks the file binding and digest; it does not fetch that URL or verify
arbitrary document prose. The operator owns that date qualification. Dates from
broker processing or report publication are insufficient.

```yaml
version: 1
events:
  SOURCE_ACCOUNT:
    ACTION_ID:
      effective_date: '2025-03-27'
      source_url: https://issuer.example/official-announcement
      document: announcement.txt
      sha256: replace-with-the-64-character-document-sha256
```

Resolve `document` relative to the YAML file. Keep both files private. This input
supplies a dated fact; it grants no financial approval. Quantity proof still needs
complete linked reverse legs or an independent source position and a continuous
source trade/event chain. Open Positions remains optional. If it supplies an opening
anchor, use a single SUMMARY position for the verified contract in an earlier retained
report. Missing anchors or gaps keep forward quantities unproven. An empty or missing
Ghostfolio holding cannot prove a closed source chain.

### Native splits, notifications and recovery

Native split evidence requires an authenticated stable Ghostfolio **3.91.0 or newer**,
complete profile split reads and exact effective-quantity reconciliation. A user-wide
holding must agree with the complete visible account composition. No tolerance accepts
a quantity residue. The separate image-backed non-admin read qualification remains
pending; native evidence stays disabled as a release proof until it passes. Profile
reads require `readMarketData`, or `readMarketDataOfOwnAssetProfile` for an owned
profile. Administrator access is not a runtime prerequisite. The connector never
registers native splits, remaps identifiers, creates action cash or repairs history.

Detailed findings appear every run. With Apprise configured, active holds notify each
completed run. Nonblocking findings without required user action notify on first appearance or
material change. Required user actions repeat each completed run until resolved.
Proven resumption also notifies. These reasons join the existing failure/expiry/preview
summary in **one dispatch**, including observed conditions in simulation. Bodies use
fixed codes and counts. Companion `.notifications.yaml` state records only confirmed
delivery under a separate lock. Timeout or failed persistence leaves notices eligible;
a crash after send can cause a later duplicate. Losing only delivery state does not
create a financial hold.

For state loss, stop writers, preserve all surviving evidence, and run simulation.
Inspect the reconstructed inventory and any missing windows before enabling writes.
Do not delete or reinitialize state to clear a known hold. Complete loss of both state
and evidence cannot be distinguished from first installation. Review the available
bounded history; do not claim a trusted lifetime baseline. For runtime rollback, stop
writers and force simulation **before** using an older image without these guards.
Before an older image reads this store, restore a complete pre-migration backup of
state, companions and evidence. Keep current correction journals separately. A code
revert alone cannot undo rotation or restore financial data.

## Reader compatibility and upgrade

After a correction writes a notes-bearing reference, retain a qualified reader
that supports those extended comments. Bare-v2 rc.5 support alone is insufficient.
For bare v2 history, retain rc.5 or a newer qualified dual reader. See
[identity formats and reader floor](configuration.md#how-activities-are-converted)
and [review qualification](activity-review.md) before selecting a rollback image.

[Back to installation](getting-started.md) · [README](../README.md)
