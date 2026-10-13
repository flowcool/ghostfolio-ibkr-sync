# IBKR → Ghostfolio — agent guide

## Product

Community Docker connector that imports Interactive Brokers activities from Flex
Web Service reports into Ghostfolio. Docker-first, every setting through ENV,
unattended runs with `docker compose up -d` and an optional `CRON`. README.md owns
the complete setup and configuration guide. Keep public artifacts free of personal
hosts, paths, account identifiers and private work-tracker IDs.

This repository is the canonical source of the broker-agnostic Ghostfolio helpers
projected into ghostfolio-degiro-sync (docs/adr/0007-pinned-degiro-core.md). A change
to import, cash or Ghostfolio request helpers flags downstream propagation in its PR.

## Invariants

- Single-file runtime: `ibkr_to_ghostfolio.py` (docs/adr/0001-single-file-runtime.md).
- Imports are additive: never update or delete existing Ghostfolio activities
  automatically (docs/adr/0003-additive-imports.md). Cleanup tools change records
  only on explicit operator action.
- Deduplication by comment and proximity (docs/adr/0002); cash update is independent
  of imports (docs/adr/0004).
- `DRY_RUN` truthy runs the full pipeline without financial writes. Tests and
  automated tools never target a live portfolio.
- Credentials (`IBKR_TOKEN`, `GHOST_ACCESS_TOKEN`, `GHOST_TOKEN`) come only from ENV;
  never hardcoded, logged, committed or written to notes.
- Functional Python, no classes, no type hints:
  [python conventions](.claude/rules/python-conventions.md),
  [security rules](.claude/rules/security.md).

## Working mode: fast-track

This mode replaces the global per-step ceremony. The invariants above still apply.

- **Spec first.** `openspec/specs/` describes current behavior. No behavior change
  without an OpenSpec change approved by the operator. When reality contradicts
  the spec, stop and report; never amend the spec silently.
- **OpenSpec to work items.** After approval, one parent item for the change and
  one self-contained item per task (spec path, requirement, scenario, acceptance
  command, files to touch). Closing an item ticks its task in `tasks.md`; archive
  the change when every item is closed.
- **One item = one fresh session.** Claim, implement, prove, close, stop. Do not
  start the next item or arm a goal across items. Budget about 150 tool calls;
  above that, stop and report the state.
- **Generated OpenSpec skills.** These rules override them. `openspec-apply-change`
  implements one task per session, not every task until done. Change names are
  lowercase kebab-case; stop before any shell command if a selected change name
  is not, and pass values read from OpenSpec output as quoted arguments, never
  as shell source.
- **Done = the item's scenario replayed for real** (command and observed output in
  the closing note). Green offline tests alone are not done.
- **Tests:** offline pytest with synthetic inputs and mocked HTTP for logic changes.
  No tests for contributor tooling, docs or CI. No full-suite rerun for prose edits.
- **Notes:** one closing note with evidence per item; no per-step findings.
- **Git:** one branch and one PR per item. Merge only when CI is green AND
  CodeRabbit has finished its review of the head commit, or on the operator's
  explicit go. Wait with one blocking command, not a `sleep` loop:
  `timeout 1800 gh pr checks <n> --watch`. Fix or answer each actionable comment;
  a pushed fix needs a finished review again. Still open after a second round, or
  timeout: leave the PR open, stop and report.
- **Docs:** README and user docs required by the spec only. No new plan, review
  or contract files.
- **Subagents:** only on the operator's explicit request.
- **Ask the operator only for:** an IBKR or Ghostfolio fact missing from the spec,
  a run against real services, a Ghostfolio write, a scope change. One question at
  a time, in plain French, with your recommended answer.
