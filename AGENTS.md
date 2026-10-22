# IBKR → Ghostfolio — agent guide

## Product

Community Docker connector that imports Interactive Brokers activities from Flex
Web Service reports into Ghostfolio. Docker-first, every setting through ENV,
unattended runs with `docker compose up -d` and an optional `CRON`. README.md owns
the complete setup and configuration guide. Keep public artifacts free of personal
hosts, paths, account identifiers and private work-tracker IDs.

This repository is the canonical source of the broker-agnostic Ghostfolio helpers
projected into ghostfolio-degiro-sync (docs/adr/0007-pinned-degiro-core.md). DEGIRO stays
pinned to the last single-file commit; propagating the package needs a separate DEGIRO
change. A change to import, cash or Ghostfolio request helpers flags downstream
propagation in its PR.

## Invariants

- Typed modular runtime: installed package `ghostfolio_ibkr_sync`, run with
  `python -m ghostfolio_ibkr_sync`, Docker only, no launcher
  (docs/adr/0001-single-file-runtime.md is superseded).
- Imports are additive: never update or delete existing Ghostfolio activities
  automatically (docs/adr/0003-additive-imports.md). Cleanup tools change records
  only on explicit operator action.
- Deduplication by comment and proximity (docs/adr/0002); cash update is independent
  of imports (docs/adr/0004).
- `DRY_RUN` truthy runs the full pipeline without financial writes. Tests and
  automated tools never target a live portfolio.
- Credentials (`IBKR_TOKEN`, `GHOST_ACCESS_TOKEN`, `GHOST_TOKEN`) come only from ENV;
  never hardcoded, logged, committed or written to notes.
- Functional Python, no behavior classes; package code strictly typed (`scripts/check.sh`):
  [python conventions](.claude/rules/python-conventions.md),
  [security rules](.claude/rules/security.md).

## Working mode: fast-track

This mode replaces the global per-step ceremony. The invariants above still apply.

- **Spec first.** `openspec/specs/` describes current behavior. No behavior change
  without an OpenSpec change approved by the operator. When reality contradicts
  the spec, stop and report; never amend the spec silently.
- **OpenSpec to work items.** After approval, one parent item for the change and
  one implementation item that lists all tasks (spec path, requirement, scenario,
  acceptance command, files to touch per task). `tasks.md` tracks the tasks; a
  task ticks its box in a commit, not in a new item. One branch and one PR per
  change: the last commit archives the change. A task that needs an `operation`
  or decision item keeps its own item.
- **Release.** A change that touches shipped code ends with a release item after
  its implementation item: replay on `main`, semver tag on the operator's go,
  image pullable; the parent item closes only after it.
- **Release lab gate.** Publish the immutable RC digest before lab validation.
  Before an RC digest proceeds to production or stable promotion, require it
  to pass the versioned infra `lab.py` runner in both `ghostfolio-lab` (empty
  first-install) and `ghostfolio-lab-golden` (golden-copy upgrade). A failed or
  incomplete digest cannot proceed; supersede it with a new RC and run both
  scenarios for that new digest. The gate does not block image publication.
  Keep lab credentials separate from
  production; a production token must not authenticate to either lab. Stop both
  instances after every run. Operational details live
  in the shared knowledge concept `operations/ghostfolio/connector-lab.md`;
  executable commands remain versioned in the infra repository.
- **Continue authorized work.** Continue through approved implementation, review and release preparation. Reuse the owning item and valid evidence. Split work only for an independent deliverable, repository boundary or new authorization. No mandatory soak, duration or daily-cycle count gates a release. Stable publication and production actions need their recorded GO.
- **Generated OpenSpec skills.** These rules override them. `openspec-apply-change`
  implements the approved tasks in order. Continue while evidence and context remain sufficient; hand off only with a concrete reason. Change names are
  lowercase kebab-case; stop before any shell command if a selected change name
  is not, and pass values read from OpenSpec output as quoted arguments, never
  as shell source. Never read or write a path under `openspec/` that is a symlink or resolves
  outside `openspec/`.
- **Done.** Prove the owning item's outcome with the relevant acceptance command. Reuse retained runtime evidence for the same digest and context. Offline work closes with offline proof; a live outcome needs observed live proof under its GO.
- **Tests:** offline pytest with synthetic inputs and mocked HTTP for logic changes.
  No tests for contributor tooling, docs or CI. No full-suite rerun for prose edits.
- **Notes:** one closing note with evidence per item; no per-step findings.
- **Git:** one branch and one PR per change. Merge only when CI is green AND
  CodeRabbit has finished its review of the head commit, or on the operator's
  explicit go. A PR that changes only `openspec/`, `docs/` or `*.md` needs CI
  green only. Open the PR yourself, then run `~/.agents/bin/pr-ship <n> --repo
  flowcool/ghostfolio-ibkr-sync --request-review-after 0` in one call (Claude: Bash
  `timeout: 600000`; Codex: one exec cell, see the global runbook), never a
  `sleep` loop. It waits, merges on `ready` and hands back any other verdict;
  exit 2 means re-run. Fix or answer each actionable comment, then re-run;
  a pushed fix needs a finished review again. Still open after a second round:
  leave the PR open, stop and report.
- **Docs:** README and user docs required by the spec only. No new plan, review
  or contract files.
- **Subagents:** only on the operator's explicit request. The PR lifecycle uses
  no subagent: the implementing agent runs `pr-ship` (global Delegation rule).
- **Ask the operator only for:** an IBKR or Ghostfolio fact missing from the spec,
  missing authority for real services or Ghostfolio writes, or a material scope change. Reuse an existing GO within its scope. One question at
  a time, in plain French, with your recommended answer.
- **Decision items.** Work only the item's numbered decision list, inside its
  authorization envelope. Start each question with `Décision n/N`; anything
  else (new question, spec, contract or code change, action outside the
  envelope) is `HORS CHEMIN`: note it in the item and stop.
- **Operation items.** Keep a short `Operation plan:` in the execution item's design. Record exact commands and target, proof, GO scope, stop conditions and recovery. A separate planning item is optional. Use versioned repository tools for live actions. Correct offline prerequisites in the owning item. Stop dependent live actions on failed writes, uncertain financial results, target drift or missing authority; continue independent authorized offline work.
