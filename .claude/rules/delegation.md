# Operating model — delegation, model right-sizing, infra handoff

Shared across the ghostfolio-sync siblings (ibkr / degiro / boursedirect). Identical
copy in each repo, maintained as a set (same convention as `python-conventions.md`).

## Fleet

Mixed fleet: **Claude orchestrates and spawns sub-agents; Codex executes code.**
Delegation and model right-sizing are decided by the orchestrator at spawn time.

## When to delegate

- **Default is inline.** A deterministic one-off stays in the main thread; repeated
  deterministic work becomes a script, not a sub-agent.
- **Pre-authorized to delegate** (scoped exception to the global "sub-agent only on
  explicit request" rule, for this family only): *bounded retrieval* — fetch one vendor
  doc page, resolve one API fact, grep a changelog, read a pinned reference. Cheap, read
  only, low risk.
- **Still needs explicit request / stays in main thread:** judgment, design, risk
  arbitration, anything that writes state or decides scope.
- Independent cross-review remains a separate, explicitly-requested handoff (Astra).

## Model right-sizing — the cost/benefit rule

Pick the cheapest tier that can do the task. Do not send a frontier model to read a doc.

| Task | Codex persona | Claude (orchestrator) |
|---|---|---|
| Fetch doc / resolve one fact / grep / mechanical lookup | **Luna** (`gpt-6-luna`, "fast & affordable") | `model: haiku` |
| Straightforward / balanced bounded work | **Terra** (legacy, folding into Sol) | `haiku`/`sonnet` |
| Coding, everyday execution (default) | **Sol** (`gpt-6.1-sol`, workhorse, active persona) | `sonnet` |
| Design, risk arbitration, independent review | **Astra** (`gpt-6-astra`, frontier) | `opus` / main thread |

## Sub-agent charter (cost ownership)

A spawned retrieval agent:
- returns the **fact plus its source**, not a reasoning essay;
- owns its cost/benefit: it stops when the marginal cost exceeds the value;
- **never self-escalates its tier.** If the task actually needs judgment, it says so and
  stops — it does not quietly promote itself to a bigger model and burn budget.
The orchestrator owns the tier choice by selecting the persona/model at spawn.

## Infra handoff boundary — these never happen inside a sync repo

Produce the artifact here (image to build, secret pointer, origin to expose); hand execution
to the infra agent via the `handoff` skill → infra epic (`infra-8tt` family / current infra).

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
