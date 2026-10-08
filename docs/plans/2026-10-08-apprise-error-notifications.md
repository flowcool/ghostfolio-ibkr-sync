# Plan — Optional Apprise error notifications

Date: 2026-10-08
Epic: Optional Apprise error notifications
Status: design

## Problem

The daily cron fails into logs and a boolean. On the NAS nobody reads the logs,
so a broken run (expired token, IBKR outage, bad mapping) goes unnoticed for
days. We want an **opt-in** notification on failure, without destabilizing a
sync whose whole value is being boring and correct.

## Why the defensive design is justified

Apprise is powerful (one URL syntax for Discord/Slack/Telegram/ntfy/Gotify/…)
but:
- it pulls a **large transitive dependency closure**, against this repo's
  "garder minimaliste" ethos (runtime = `requests` + `pyyaml` only, image
  installs `requirements.txt` only);
- its plugins do blocking network I/O and a library-level timeout does **not**
  stop a hung plugin thread;
- library output can echo destination credentials (tokens inside the notify URL).

Hence: an **isolated subprocess worker** with a hard parent deadline, kill/reap,
discarded output, an explicit env allowlist, and a pinned+audited dependency
closure. Heavy, but it keeps the notifier from ever harming the sync.

## Delivery boundary (three child commits, one PR each)

### PR1 — structured run outcomes + orchestration boundary (no sending)

Valuable and low-risk on its own; land regardless of transport choice.

1. Introduce a **run-local bounded outcome dict**: controlled stages
   (`config`, `mapping`, `ghost_startup`, `account`, `unexpected`), counts, and
   account **ordinals** (never IDs). It records expected and unexpected failures
   with **no raw errors, URLs, IDs or financial values**.
2. Fix the `main()` inconsistency: the config-error path currently
   `sys.exit(1)` (`ibkr_to_ghostfolio.py:1336`) while every other path
   `return 1`. Make the owned path `return 1` so `main()` is uniformly testable.
3. `process_account()` signature and its `(unmapped, ok)` tuple contract stay
   **unchanged**; account isolation preserved; external `SystemExit` /
   `KeyboardInterrupt` propagate (no synthetic finalization).

Tests: outcome recording per stage, config path returns 1, no notification side
effects.

### PR2 — isolated Apprise transport + pinned dependency closure

1. **Config**: `APPRISE_URLS` = bounded JSON string list (blank / `[]` =
   disabled); `APPRISE_TIMEOUT` = int 1..30, default 10. Invalid settings
   **disable** delivery with one fixed warning and never fail the sync.
2. **Worker mode** (`python ibkr_to_ghostfolio.py --notify-worker` or a dedicated
   entry): never invokes sync; lazy-imports Apprise; reads a fixed argv/stdin
   payload (<=32 KiB); explicit environment allowlist; discards library output.
3. **Parent**: one deadline covering worker import+init+send+shutdown;
   kill+reap on timeout and on exceptional paths; returns a fixed delivery status;
   no application-level retries.
4. **Dependency closure**: pin a published, compatible Apprise base release and
   its complete Linux transitive closure in a **separate** manifest (not the lean
   runtime `requirements.txt`); audit in an isolated env (`pip-audit`). Decide
   whether the image installs it (new image surface) or it ships as an optional
   layer — document the image-size/attack-surface tradeoff.

Tests: hanging worker (deadline + reap), secret/output canaries (token never in
captured output), missing dependency (graceful disable), malformed settings.

### PR3 — failed-run finalizer + policy docs

1. A single finalizer: a completed **failed** run makes **at most one** logical
   dispatch attempt (covers startup / mapping / ghost-startup / unexpected /
   multiple failed accounts).
2. Gates: success, warning-only, disabled, and `DRY_RUN` paths spawn **no**
   worker; raw `DRY_RUN` suppression works **before** config validation.
3. Summary content = fixed title / stage / reason + UTC time + counts + account
   ordinals only. No raw errors, URLs, IDs, financial values.
4. Notification errors/timeouts **never** change the original exit status and
   never prevent account continuation.
5. README: destinations, dependencies, bounded worker overhead, uncertain
   timeout / no-retry semantics, silent warnings & dry-run, import-failure
   limit, rollback.

Tests: end-to-end over every gate, interrupted runs, synthetic secret/financial
canaries, exactly-one-dispatch.

## Security notes (`.claude/rules/security.md`)

- New dependency + new external I/O -> `security-review` before merge.
- Canaries: a synthetic secret and a synthetic financial value must never appear
  in captured worker output or in the notification payload.
- Env allowlist for the worker: pass only what Apprise needs; never the whole
  environment (IBKR/Ghostfolio tokens must not reach the notifier process).

## Rollback

Each PR reverts independently before deployment. With `APPRISE_URLS` unset the
feature is inert, so the running sync is unaffected until the operator opts in.
Parent-epic rollback contract preserved. Production execution/deployment
requires separate authorization.

## Note (recorded, not a blocker)

Lighter alternatives were weighed (single generic webhook POST via `requests`,
no new dependency; or a Healthchecks.io dead-man-switch ping). Operator chose
full Apprise for its multi-provider URL syntax; this plan implements that.
