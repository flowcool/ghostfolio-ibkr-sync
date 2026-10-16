# Review propagation to the immutable DEGIRO core explicitly

Date: 2026-10-12. Status: accepted (existing behavior).

This repository is the canonical source for selected broker-independent
Ghostfolio helpers used by
[ghostfolio-degiro-sync](https://github.com/flowcool/ghostfolio-degiro-sync).
DEGIRO maintains an immutable byte projection, not a live dependency on this
repository's main branch. Its authoritative
[CORE_PROVENANCE.md](https://github.com/flowcool/ghostfolio-degiro-sync/blob/main/CORE_PROVENANCE.md)
owns the exact pin, hashes and selected units; the observed pin when recording
this ADR is `54958ab1035eb97a1f67f9072b79699813ec3800`, not a second pin to update here.

Changes to import, cash and Ghostfolio request helpers must flag downstream
propagation in the IBKR PR, even if adoption is deferred. In DEGIRO, review the
proposed source commit and selected-unit dependencies in a scratch checkout,
update provenance, explicitly regenerate the projection with `scripts/check_core.py`,
verify byte identity, and run offline regressions plus adapter-assumption checks.
Commit the pin, generated artifact and necessary tests together only with explicit
authorization. Never hand-edit the projection or change the sibling implicitly.
Main advancing is a review signal, not approval to propagate.

**Package layout (v3.0.0 release candidates).** The IBKR runtime is now the package
`ghostfolio_ibkr_sync` ([0001](0001-single-file-runtime.md), superseded) and the
single source file no longer exists. DEGIRO stays pinned to the last single-file
source commit recorded in its `CORE_PROVENANCE.md`, and this repository does not edit
DEGIRO. DEGIRO's `check_core` hardcodes a single-file `source_path`, so it cannot read
the package. Any future propagation needs a separate DEGIRO change that first updates
that source mapping for the package layout, then follows the review steps above.

Broker-specific parsing, comment indexing and orchestration stay outside the
projection. Differences between the frozen core and current IBKR behavior must
be reviewed, not hidden by a broad source refactor. Roll back an adopted
propagation atomically by reverting its exact commit; this does not undo financial
writes. These ADRs change no shared core, so they require no projection regeneration.
