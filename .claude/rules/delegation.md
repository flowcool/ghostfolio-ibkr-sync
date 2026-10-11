# Operating model — delegation, model right-sizing, infra handoff

Canonical, repo-agnostic operating policy. **Genuinely shared across the ghostfolio-sync
siblings (ibkr / degiro / boursedirect): one byte-identical copy in each repo.** When it
changes, propagate the same bytes to all three (unlike `python-conventions.md`, which is
per-adapter and intentionally differs). The `.claude/rules/` path is a compatibility
location, not a dependency on a Claude session.

## Fleet

**Codex owns orchestration and execution. CodeRabbit reviews every PR.** Florent
permanently disconnected Claude on 2026-10-09. Codex may spawn persona sub-agents; it
decides tier and reasoning effort at spawn time.

Astra is **not** part of the fleet's automatic path — see "Astra" below.

## When to delegate — two independent decisions

Decide these separately. The old single tier-table conflated them and let the frontier
tier be picked like any other, which is the mistake this rule removes.

1. **Which tier** — driven by whether the task needs *judgment*.
2. **Automatic or explicit** — driven by *risk / state-write + tier cost*.

### Band A — automatic, pre-authorized, no need to ask

- **Tiers:** Luna (fast/affordable) and Sol (workhorse). **Reasoning effort is free to
  crank to max** — a Luna@max pass costs a fraction of one frontier pass, so there is no
  reason to throttle effort on the cheap tiers.
- **Allowed work — read-only or throwaway/reviewable artifact only:** scrape a page,
  fetch/parse a vendor doc, resolve one API fact, grep a changelog, run tests, generate a
  *draft* plan/design/summary, mechanical refactor fully covered by tests.
- **Parallel fan-out is allowed.**
- **Hard ceiling:** no write to shared/prod state, no scope decision, no merge. Those
  return the artifact to the main thread; they are never delegated to a Band A agent.

### Band B — explicit only

- Anything needing judgment, design arbitration, risk arbitration, or that writes state /
  decides scope stays in the main thread or is escalated on explicit request.
- Standing PR review is **CodeRabbit**, everywhere, automatically. It carries the review
  load by default.

## Model right-sizing — the cost/benefit rule

Pick the cheapest tier that can do the task. Never send a frontier model to read a doc.

| Task | Codex persona |
|---|---|
| Fetch doc / resolve one fact / grep / mechanical lookup | **Luna** (`gpt-6-luna`, fast & affordable) |
| Coding, everyday execution, balanced bounded work (default) | **Sol** (`gpt-6.1-sol`, workhorse) |
| Design / risk arbitration / independent review | **Astra** (`gpt-6-astra`, frontier) — **manual escalation only, see below** |

(Terra is legacy, folded into Sol.)

## Astra — rationed, manual escalation only

Astra is the frontier tier and the most expensive resource in the fleet. It is **never
triggered automatically** — not by a design gate, not by a risk surface, not by a PR.

- **Only Florent invokes Astra, by explicit nominal request**, for a specific question.
- No rule, skill, or heuristic in this repo may spawn Astra on its own.
- When a task looks like it needs Astra, the agent **states that and stops** — it surfaces
  the question for Florent to decide, it does not escalate itself.
- Everything that would otherwise have gone to Astra routes to **CodeRabbit on the PR +
  Band A self-review** instead.

Rationale: the frontier tier is affordable only au compte-gouttes. Making it a manual gate
(not a tier anyone can pick) caps spend at exactly what Florent authorizes, and stops the
per-document review proliferation that convergence discipline already forbids.

## Sub-agent charter (cost ownership)

A spawned Band A agent:
- returns the **fact plus its source**, not a reasoning essay;
- owns its cost/benefit: it stops when marginal cost exceeds value;
- **never self-escalates its tier.** If the task actually needs judgment, it says so and
  stops — it does not quietly promote itself to a bigger model and burn budget.

The orchestrator owns the tier choice by selecting the persona at spawn.

## Infra handoff boundary — these never happen inside a sync repo

Produce the artifact here (image to build, secret pointer, origin to expose); hand
execution to the infra agent via the `handoff` skill. Resolve the destination
infrastructure epic in Beads (current infra: `infra-8tt` family); record the source
project and issue explicitly.

- **Deploy / Komodo / image**: build + push image, container deploy, supercronic cron in prod.
- **Secrets / SOPS**: rotation, writes to the off-git SOPS store, access pointers.
- **Network / DNS / Traefik**: exposure, reverse-proxy, allowlisted origins.

(Real Ghostfolio production writes stay a separate in-repo authorization gate, not an infra
handoff — the sync code owns that logic; only its authorization is gated.)

## Convergence discipline

A design must *decide*, not proliferate. When a feasibility / GO-NO-GO gate is open for a
project, **do not create a new `docs/design/*` doc** until the gate has a verdict. Close or
supersede an existing design doc before adding another. The gate is the forcing function;
more documents are not progress.
