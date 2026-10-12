# Keep the sync runtime in one Python file

Date: 2026-10-12. Status: accepted (existing behavior).

The synchronization pipeline and its Ghostfolio helpers live in
[`ibkr_to_ghostfolio.py`](../../ibkr_to_ghostfolio.py). Keep the functional,
single-file structure rather than introducing a package as part of maintenance;
this preserves the small runtime and the identifiable source boundary consumed
by [DEGIRO's core projection](0007-pinned-degiro-core.md).

The sync imports `requests` and `pyyaml`; optional Apprise is loaded only in a
separate notification worker implemented in that same file. Tests and operator
cleanup tools are separate files, not additional sync modules. A broad extraction
would need explicit review, including downstream propagation, rather than being
treated as an incidental refactor. See [Development](../../README.md#development).
