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


[Back to the README](../README.md)
