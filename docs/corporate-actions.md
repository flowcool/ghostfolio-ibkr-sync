# Corporate-action safety

Select **Corporate Actions** in Flex, even when empty.
Use the [required fields](ibkr-setup.md#corporate-actions-required).
A missing section blocks all BUY/SELL for that source account.
Unrelated securities keep their existing guards.
Other accounts and independent cash keep their guards.
An uncertain financial write still blocks the whole account.

Set `CORPORATE_ACTION_STATE_FILE` in a persistent directory owned by the container user.
Use mode `0700` for the directory and `0600` for files.
Mount the directory, not one file. Keep it private and back it up with input evidence.

The companion `.evidence/` directory stores complete, immutable reports.
Each report binds the source account, query, period, mapping fingerprint and hashes.
The connector reparses reports after events leave the current window.
Hashes detect changes. They cannot authenticate a coordinated rewrite.

Ordinary reports expire **30 days (720 hours)** after their stored UTC acquisition time.
The next run removes them. Simulation also performs this maintenance.
No ENV setting, quota or command controls retention.
Re-reading a report or changing timestamps does not reset its age.
Legacy reports get one stored migration time and a 30-day grace period.
Invalid or future acquisition times cannot permit early removal.

Required safety originals stay retained. They cover events, revisions, conflicts,
relevant trades, dated positions, identities and continuous coverage.
The connector removes a redundant copy only after verifying surviving originals and source facts.
Matching holdings, closed positions and manual reconciliation do not retire required evidence.

**30 days is not a storage limit.** Safety history can grow.
Different dated quantities or query/mapping bindings can prevent removal.
Compatible extra Flex columns can complete old evidence.
Changed shared facts or event legs remain conflicts.

The versioned `.references.yaml` index records active acquisitions and pending cleanup.
If the index is lost, `.rotation` prevents recovery of obsolete bindings.
References are stored and verified before removal. Restarts retry interrupted cleanup.
Normal reconciliation uses required safety originals and the current source only.
Each required XML is hash-checked and parsed once per run.
Later reconciliations reuse those facts and reject file metadata changes.

A maintenance-only failure logs a warning and joins the configured notification once per run.
It changes neither the exit status nor otherwise safe imports.
Missing or invalid evidence still blocks affected BUY/SELL. Cash keeps its guards.
Rotation excludes proposals, mappings, official documents and correction journals.

Use current logs and proposals for reconciliation. Clean up manually and rerun analysis.
There is no persistent reconciliation job or archive replay.
For investigations longer than 30 days, keep a private copy or obtain another broker export.
Expired ordinary archives cannot be recovered.

Run simulation first. A valid report with Corporate Actions initializes missing state.
Review the reported inventory before live mode. It covers available history only.
Missing or unwritable state and active holds make simulation exit **1**.
Live mode blocks BUY/SELL when state, permissions, locks or evidence are unavailable.
Cash keeps its guards. No report window proves lifetime history.

Findings separate identity, effective quantity, cost, dates and cash.
Matching current quantities does not prove historical cost.
A cost/date difference alone does not block proven units.

Events stay unresolved when dates, coverage, prior quantities, reverse legs or ISIN mappings are missing.
Both old and new ISINs must map explicitly to one active destination profile.
Unmatched pre-event trades stay blocked in already-normalized history.
Boundary-day trades remain ambiguous.
Acknowledgment or activity-review `yes` cannot release a hold.

### Official effective-date evidence

Set optional `CORPORATE_ACTION_EVIDENCE_FILE` to a private YAML file.
Verify each market effective date in an official issuer, exchange or broker document.
Keep the document locally. Record its SHA256 and public HTTPS source URL.
The URL must contain no credentials, query or fragment.

The connector checks the file binding and digest. It does not fetch the URL or interpret the document.
You must verify the date. Broker processing dates and report publication dates are insufficient.

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

Resolve `document` relative to the YAML file. Keep both files private.
This input records a dated fact. It does not approve a financial write.
Quantity proof needs complete linked reverse legs.
Alternatively, use an independent source position with a continuous source trade/event chain.

Open Positions is optional.
For an opening anchor, use one SUMMARY position for the verified contract.
It must come from an earlier retained report.
Missing anchors or gaps leave forward quantities unproven.
An empty or missing Ghostfolio holding cannot prove a closed source chain.

### Native splits, notifications and recovery

Native split evidence requires:

- Authenticated stable Ghostfolio **3.91.0+**.
- Complete profile split reads and exact effective quantities.
- User-wide holdings that match the complete visible account composition. No quantity residue is accepted.
- `readMarketData`, or `readMarketDataOfOwnAssetProfile` for an owned profile.
  Administrator access is not required.

Non-admin reads still need image-backed qualification.
Until then, native evidence cannot serve as release proof.
The connector never registers splits, remaps identifiers, creates action cash or repairs history.

Logs show detailed findings every run.
When notices are due, configured Apprise sends **one summary** after the completed run:

- Active holds and required actions repeat until resolved.
- Other nonblocking findings notify on first appearance or material change.
- Proven resumption also notifies.
- Failure, expiry and forced-preview reasons share that summary, including in simulation.

Bodies use fixed codes and counts.
`.notifications.yaml` records confirmed delivery under a separate lock.
Timeouts or failed persistence leave notices eligible. A crash after send can cause a duplicate.
Lost delivery state alone does not create a financial hold.

After state loss:

1. Stop writers. Preserve surviving evidence.
2. Run simulation. Check the rebuilt inventory and missing windows.
3. Enable writes only after review.

Do not delete or reinitialize state to clear a hold.
Complete loss of state and evidence looks like first installation.
Available history cannot establish a trusted lifetime baseline.

Before rollback to an older image:

1. Stop writers and force simulation.
2. Restore a complete pre-migration backup of state, companions and evidence.
3. Keep current correction journals separately.

A code revert cannot undo rotation or restore financial data.

## Reader compatibility and upgrade

After a correction writes a notes-bearing reference, retain a qualified reader
that supports those extended comments. Bare-v2 rc.5 support alone is insufficient.
For bare v2 history, retain rc.5 or a newer qualified dual reader. See
[identity formats and reader floor](configuration.md#how-activities-are-converted)
and [review qualification](activity-review.md) before selecting a rollback image.

[Back to installation](getting-started.md) · [README](../README.md)
