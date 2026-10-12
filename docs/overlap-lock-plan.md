# Per-destination overlap protection proposal

Date: 2026-10-12. Status: **proposal, awaiting operator approval**.
This document changes no runtime, Compose configuration or deployment. Approval
of this document's merge is not approval to implement or deploy the proposal.

## Problem and scope

`run_sync` reads all existing activities once, before processing configured
accounts. Two concurrent runs can read the same snapshot and both import a
candidate. Taking a lock only around the POST does not fix the stale snapshot.

Propose a non-blocking Linux `fcntl.flock` per Ghostfolio destination account,
held from before that snapshot until account processing and cash updates finish.
Imports remain additive. Do not change financial matching, retries, cash-after-
failed-import policy, or introduce automatic activity correction/deletion.

## Identity and storage

- Configuration: require `STATE_DIR` for live runs; recommended container path
  `/state`, on a writable persistent local volume. No fallback to `/tmp`, the
  container writable layer, or an automatically chosen host path.
- Resolve configured Ghostfolio names to stable account IDs with the existing
  account-list request after authentication, before reading activities. Require
  exactly one matching account per configured name; missing/ambiguous matches
  fail before financial writes. Freeze these IDs for the run instead of looking
  up names again while processing. Duplicate targets share one lock.
- Key: SHA-256 of UTF-8 `json.dumps({"host": validated_host, "target": account_id},
  sort_keys=True)`, using Python's default separators and ASCII escaping. File:
  `STATE_DIR/<hex-key>.lock`. No broker identity, token, account name, PID or
  schedule in the key. Renaming a destination or rotating a token must not
  change its lock.
- Use the same validated final Ghostfolio base URL string (trailing slash
  removed) across participating writers, including any API base path. Validate
  it in both authentication modes; forbid credentials/query/fragment. Do not
  resolve aliases using DNS or silently normalize paths. Different aliases,
  ports or URL spellings can produce different locks for one instance: exact
  URL alignment is a deployment prerequisite, not automatic detection.
- Require a private directory owned by the runtime UID with mode `0700`;
  lock files must be regular, owner-matching, single-link files with mode
  `0600`. Open without following symlinks, validate the open descriptor, and
  keep it non-inheritable. Translate filesystem errors into fixed diagnostics;
  never log the path, key, account ID, host, credentials or raw OS exception.
- Never unlink, replace, rotate or truncate lock files during use. An empty
  persistent file is not a stale lock: possession belongs to the open file
  description, not a PID stored in the file. Removing/replacing it can let
  another process lock a different inode and bypass exclusion.

The volume must be shared by **all cooperating writers** for that destination,
not merely persisted separately for each container. Persistence keeps the
namespace/inode stable across recreation; it does not keep a lock held after
process exit. The directory is a private lock namespace, not a financial journal.

## Run lifecycle and failure policy

```text
validate local config/mapping -> authenticate -> resolve destination IDs
  -> acquire all unique destination locks in sorted key order (LOCK_EX|LOCK_NB)
  -> read existing activities once -> fetch/process each query -> update cash
  -> close all lock descriptors in finally
```

Acquire all configured destination locks before the shared activities snapshot.
If any is busy, release those already acquired and fail the entire invocation
with exit 1 and fixed message `Another synchronization owns this account`.
No waiting, automatic retry, partial account processing or financial write.
Sorted acquisition and all-or-nothing failure avoid lock-order surprises;
disjoint destination sets can still run concurrently.

Missing/unsafe/unwritable state or unsupported locking fails closed with fixed
diagnostics and exit 1. Record a fixed startup failure reason for the existing
notification path, without changing financial failure handling. Locks cover
Flex fetching as well as imports and cash; slower broker polling therefore
extends lock ownership. Release before optional notifications. Normal completion,
exceptions and process termination close descriptors; process death releases
kernel locks once all references are closed. Do not pass them to worker children.

Dry-run stays read-only financially and requires no state volume or exclusive
lock. Its preview may race a live run and is not authoritative reconciliation
evidence. Unsupported platforms may preview, but live synchronization must not
silently run without protection. Do not add an opt-out flag in the first release.

**These are proposed behavior decisions needing operator approval:** mandatory
state for live runs, rejection of ambiguous names, stable ID binding, fail-whole-
run on contention (rather than skip one account), and unlocked preview mode.

## Comparison with DEGIRO and propagation

Reviewed sibling source at commit
`29fcb52495fb8881aa75ae193605f9a1dfe18b75`:
[account_journal and run_sync_locked](https://github.com/flowcool/ghostfolio-degiro-sync/blob/29fcb52495fb8881aa75ae193605f9a1dfe18b75/degiro_to_ghostfolio.py).

DEGIRO uses a private `STATE_DIR`, a host/target SHA-256 key, `.lock` files,
`LOCK_EX|LOCK_NB`, descriptor ownership checks and close-in-finally. It knows a
target ID from configuration and takes the live lock before source/target reads.
Its `.yaml` files additionally fence durable uncertain writes; IBKR must not
read or overwrite those journals as part of this proposal.

Match the sibling's lock-file/key protocol where possible. Cross-adapter
exclusion is conditional on equal validated URL, target ID, shared inode and
compatible runtime UID/permissions; test it offline before claiming support.
Separate named volumes, copied files or equal filenames on different hosts do
not coordinate. A UID mismatch must fail safely, not relax directory permissions.

Implementation should remain in the IBKR adapter's orchestration and small
functional helpers inside `ibkr_to_ghostfolio.py`, not a new dependency or module.
The frozen DEGIRO projection must be reviewed if any common function changes.
In particular, passing a pre-resolved ID may tempt a change to
`ghost_find_account_id`: prefer keeping its projected API untouched and make
binding an adapter concern. List every common-function change in the eventual
implementation PR; never update the sibling pin implicitly.

## Existing-user migration and release strategy

Propose a **major release / breaking-change notice**: live configurations that
currently work without `STATE_DIR` would stop. Confirm versioning with the
operator before implementation. The planning PR has no runtime release impact.

1. Announce the new requirement and document the exact container runtime UID
   from the built image, not an assumed numeric ID. Do not grant world access.
2. Quiesce scheduled, one-off and other cooperating writers; wait for active
   processes to finish. A mixed old/new fleet is not protected.
3. Prepare one private persistent local lock directory shared across writers
   of the same destination; set ownership to the actual runtime UID and mode
   `0700`. Use a bind mount, or explicitly initialize ownership on a named
   volume; a fresh root-owned volume is not assumed writable by the app user.
4. Add the writable `/state` mount and `STATE_DIR=/state` to every participating
   container. Separate Compose projects must reference the same actual storage,
   not similarly named project-prefixed volumes. Plain Python runs need the
   same directory and compatible UID. Keep mapping mounts read-only.
5. Use one exact final Ghostfolio URL for cooperating writers. Confirm destination
   resolution and lock identity offline/with explicitly authorized read-only
   checks. Recreate containers on the approved version, first with dry-run.
6. Exercise two isolated synthetic processes sharing a directory, then verify
   the actual deployment's storage/ownership without live financial writes.
   Resume schedules only after every relevant writer uses the protocol.

Readonly-root deployment remains possible: only `/state` is writable persistent
storage; `/tmp` can separately be a tmpfs for the crontab in the later image
hardening work. This plan makes no Compose, Dockerfile or entrypoint changes.
Do not alter an operator's choice of `:latest`; explain that adopting it after
the breaking release requires migration. Offer a version/digest pin for controlled
rollout, without switching a deployment automatically.

Rollback: quiesce all writers, select the previous known-good image digest and
restore previous configuration. Leave the private state directory intact; no
cleanup is required. Old code again has no overlap protection, so maintain a
single writer per destination. Never delete lock files to force recovery while
any writer could be running. Document image-tag mutability separately.

## Limits and verification required before implementation ships

`flock` is advisory, local mutual exclusion, not distributed locking or a
Ghostfolio uniqueness constraint. Restrict this first implementation to Linux
processes sharing a tested local filesystem on one host. NFS/SMB semantics,
multi-host replicas, non-cooperating imports/UI edits and cleanup tools are not
covered. A busy lock is not proof of a hung process; never auto-kill its owner.

It also does not resolve requests that may continue server-side after a client
timeout or crash. Once the client exits, the lock can release while an old
request remains in flight. Durable uncertainty fencing/recovery is a separate
design; do not claim exactly-once delivery or change cash semantics here.

Offline implementation tests must prove: same destination excludes concurrent
processes; different destinations proceed; same-account renames/token changes
keep identity; acquisition precedes the activities snapshot; all-or-nothing
multi-account failure; exceptions/termination release descriptors; file inode
is retained; children do not inherit the lock; missing/unsafe/symlinked/wrong-
owner storage fails closed with fixed diagnostics; dry-run needs no state;
no financial calls on lock failure; sibling protocol collision when sharing
the same namespace; no journal modification. Run full pytest and py_compile
before each implementation commit and record security review for state/URL handling.

References: [Python fcntl](https://docs.python.org/3/library/fcntl.html) and
[Linux flock(2)](https://man7.org/linux/man-pages/man2/flock.2.html).

## Approval gate

Operator must approve the proposed identity, lifecycle, contention policy and
breaking migration before an implementation issue/PR begins. Deployment remains
a separate explicitly authorized operation. This plan alone closes no financial
reconciliation or durable-recovery gap.
