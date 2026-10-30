# IBKR → Ghostfolio — agent guide

## Product

Community Docker connector that imports Interactive Brokers activities from Flex
Web Service reports into Ghostfolio. Docker-first, every setting through ENV,
unattended runs with `docker compose up -d` and an optional `CRON`. README.md is the installation entry point; docs/getting-started.md owns the
first-install path and docs/configuration.md owns the settings reference. Keep public artifacts free of personal
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
- Imports are additive. Optional activity review permits an exact one-to-one
  correction with manual `yes` or bounded profile authority. Qualification,
  durable journaling and exact readback remain required. Permit at most one
  correction per cycle. Never delete activities during sync
  (docs/adr/0003-additive-imports.md). Stable publication and production require
  separate explicit GO. Cleanup tools retain separate operator authorization.
- Deduplication by comment and proximity (docs/adr/0002); cash update is independent
  of imports (docs/adr/0004).
- `DRY_RUN` truthy runs the full pipeline without financial writes. Tests and
  automated tools never target a live portfolio.
- Credentials (`IBKR_TOKEN`, `GHOST_ACCESS_TOKEN`, `GHOST_TOKEN`) come only from ENV;
  never hardcoded, logged, committed or written to notes.
- Functional Python, no behavior classes; package code strictly typed (`scripts/check.sh`):
  [python conventions](.claude/rules/python-conventions.md),
  [security rules](.claude/rules/security.md).

## Durable work state

- OpenSpec change `clarify-operator-actions` is implemented and archived at `openspec/changes/archive/2026-10-27-clarify-operator-actions/`. All ten tasks have offline acceptance proof.
- Implementation and release for `clarify-operator-actions` are complete. Stable `v3.3.0` reuses the RC digest qualified in both labs. Beads owns the acceptance evidence.
- Stable publication does not authorize production deployment or financial operations.

- OpenSpec change `simplify-user-onboarding` is implemented and archived at `openspec/changes/archive/2026-10-28-simplify-user-onboarding/`. The primary Compose example uses one account; `compose.multi-account.yaml` retains the two-account setup. Detailed user guides live under `docs/`.

- OpenSpec change `profiled-activity-reconciliation` is implemented and archived at `openspec/changes/archive/2026-10-28-profiled-activity-reconciliation/`. Implementation and release are complete. Stable `v4.0.0` reuses the RC4 digest qualified in both labs with all three profiles. Beads holds the acceptance and verified publication evidence.

## Project boundaries (Florent 2026-10-30)

Each scope has one owner agent. Work only in the repositories and runtime of
your own project. This project: `ghostfolio-ibkr-sync`.

| Beads `project` | Agent | Owns |
| --- | --- | --- |
| `infra` | Claude, `~/claude_project/infra` | Production deployment (Komodo, GitOps `flowcool/mylittlemess`), image and catalog pins, schedules, collector task configuration, hosts and NAS outside the labs, Paperless configuration and permissions, SOPS secrets, backup, monitoring. |
| `BillCollector` | Codex | The engine only (`flowcool/BillCollector`): generic actions, scheduler, vault and TOTP, throttles, delivery, recipe schema, engine contract, upstream engine contributions. |
| `billcollector-recipes` | Codex | Every provider recipe end to end (`flowcool/billcollector-recipes`): portal exploration, selectors, history window, qualification on the exact engine revision, catalog release, upstream recipe contributions. |
| `ghostfolio-ibkr-sync`, `ghostfolio-degiro-sync`, `ghostfolio-boursedirect-sync` | Codex | Connector code, spec, lab tests, PRs and releases. The Ghostfolio financial operation, under Florent's GO. |

- **Routing.** For a need in another scope, search the open issues of the owner
  first. If no issue covers it, create one with
  `--metadata '{"project":"<owner>"}'`, the evidence, the exact need and its
  acceptance. Link it `related` to your issue. Never edit, deploy or test the
  code or runtime of another project.
- **Usual routes.** Portal, selector or history window: `billcollector-recipes`.
  Missing engine action, throttle, vault or delivery defect: `BillCollector`.
  Deployment, pin, schedule, task configuration, Komodo stack, NAS file,
  Paperless workflow or permission: `infra`. Importer behavior: the connector.
- **Release boundary.** A development project stops at a qualified release: an
  immutable image digest or catalog tag, with its proof. Infra deploys it.
- **Labs: free use on agentvm.** Create, configure, reset, restart, redeploy and
  scratch lab stacks under `stacks/a/` (Komodo server `a`). To add your own
  lab, open a `flowcool/mylittlemess` PR limited to `stacks/a/<lab>/` and its
  `komodo/sync.toml` entry; merge it on green CI. Separate authority remains for
  production, a login to a real broker or portal (Florent GO per provider),
  production secrets in a lab, and removal of proof. Reserve a shared lab and
  stop it after use (Infra runbook `docs/runbooks/ghostfolio-lab.md`).
- **Lab gate before merge.** Test the PR image in the lab before merge when the
  PR changes financial logic, deduplication or activity identity, Ghostfolio
  authentication, transport or writes, the state or journal format, a recipe,
  or a major dependency or base image. Connectors run the empty and golden
  Ghostfolio labs. Recipes and the engine run an isolated collector lab with
  synthetic fixtures. Other PRs need CI only.
- **Lab gate at release.** Every release passes the same lab scenarios on its
  exact digest. Promote that digest without a rebuild. Reuse the pre-merge proof
  when the digest is identical.

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
- **Git:** one branch and one PR per change. Sub-items, steps and review fixes
  are commits in that PR; never open separate or stacked PRs for them.
  Pullfrog is the sole reviewer.
  Require CI green and a completed Pullfrog review of the head. Resolve actionable
  threads. Ignore CodeRabbit and the known sticky `pullfrog-approval` status;
  every other CI failure remains blocking. Docs-only PRs need CI only.
  Open the PR yourself, then run `~/.agents/bin/pr-ship <n> --repo
  flowcool/ghostfolio-ibkr-sync` in one call. Exit 2 means re-run. Fix or answer
  actionable comments, resolve them and re-run. A pushed fix needs a review of
  the new head. After a second unresolved round, leave the PR open and report.
- **Docs:** Write repository documentation in English. Follow ASD-STE-100 writing principles.
  Use short sentences, one idea per sentence, active voice and direct instructions.
  Remove repetition. Keep commands, prerequisites, safety limits and recovery steps complete.
  Write README and user docs required by the spec only. No new plan, review
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
