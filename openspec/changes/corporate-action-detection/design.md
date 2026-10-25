# Design

## Context

See proposal.md. The candidate stores XMLs and bindings together. `retained_inventories` scans all objects. Activity review uses current reports; its correction journal is separate. Main specs retain the prior candidate contract until this reopened change is implemented and archived.

## Goals / Non-Goals

Bound routine report retention and repeated work. Preserve original safety evidence. Add no reconciliation lifecycle, quota, retention ENV or financial treatment.

## Decisions

- Reuse `inventory`, `source_chain`, `decide` and `candidate_held`. Preserve exact quantities, mappings, date proofs, revisions and conservative holds. `ghost_corporate_evidence` keeps native acceptance behind its existing qualification gate.
- Extend `retain_report` with durable UTC acquisition time. Expire ordinary reports after 720 hours on the next run, including simulation. Repeated observations and file timestamps cannot renew the same acquisition. A legacy object without a trusted timestamp receives one persisted migration timestamp, never guessed age.
- Separate the ordinary archive from referenced safety reports. Select complete immutable XMLs and original bindings needed for known events, revisions, coverage, trades, anchors and official dates. Prove redundancy against source facts and decision inputs; current holding agreement alone is insufficient. Do not retain all overlaps forever. Use a verified active index and per-run caches; avoid parsing expired ordinary archives during each reconciliation.
- Reuse `safe_path`, `atomic_yaml`, `check_store` and the store lock. Publish and sync a versioned reference generation before removing eligible objects. Recover a crash before or after publication without reviving retired bindings or losing active evidence. Resume interrupted cleanup idempotently. Protect all configured inputs and external files.
- In `refresh_corporate_decisions`, resolve all configured owners first. Treat missing, invalid or unresolved co-owner evidence as unknown, never event-free. Hold all affected co-owners before review/import; unrelated destinations retain their guards.
- Reuse `finalize_run` and the consolidated notification. Maintenance failure reports once per run without changing exit status or trade eligibility by itself. Required-evidence failure retains existing fences. Activity-review files and journals remain outside rotation.

## Risks / Trade-offs

Useful safety history can grow with actual events and chains; 30 days is not a total byte bound. Expired archives may require fresh operator exports. Unprovable redundancy preserves evidence and reports the limitation. Multi-year synthetic tests must show stable ordinary retention and no per-acquisition safety growth for unchanged facts.

## Migration Plan

Adopt legacy evidence conservatively; preserve original bytes. Rollback stops writers, forces simulation and restores the complete pre-migration state/evidence backup before older code. Reverting code alone cannot undo rotation or financial writes.
