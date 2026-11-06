# Proposal

## Why

The activity review budget is one correction per run. Production has a reviewed
queue of historical date corrections. One correction per daily run drains the
queue too slowly. The destination recomputes market data and portfolio cache
asynchronously after an activity PUT.

## What changes

- Activate a connector RC budget of five corrections per run.
- Keep corrections sequential. Read the exact activity after every PUT before
  dispatching the next request.
- Use a 15-second minimum inter-correction delay in the RC. Stable promotion
  still requires the exact-digest burst gate. If the lab observes a longer
  background chain, revise the values in a new RC.
- Stop the whole financial run after the first failed or uncertain correction.
  Keep the journal, account fence, approvals and later deferred proposals.
- Keep journal version 3, no resend, shared multi-account budget, and the single
  consolidated notification path.

## Mechanism decision

Ghostfolio 3.96.0 at commit `2f21c2558684e8cc9974f1b2da683992a83ef3cb`
has no API completion signal for these jobs. The activity PUT returns after the
database update. The controller queues symbol gathering. A portfolio-changed
listener applies a five-second debounce and queues a Bull portfolio snapshot;
the processor writes Redis after calculation. These internal Redis/Bull events
are not observable by this connector through its HTTP API.

Use the existing fixed inter-correction delay plus exact readback. An API poll
cannot prove the background chain. A connector-side Bull/Redis observer would
need a new destination integration and is outside this change.

## Qualification gate

The exact RC image must pass the versioned empty and golden lab burst scenario
before stable promotion. The RC activates the permit for this lab validation.
The scenario measures the maximum request-bound market-data and portfolio-cache
completion time, adds a documented margin, and records the accepted `N` and `D`
in the digest-bound qualification evidence. It must dispatch `N` consecutive
corrections, prove exact readback before each next PUT, stop on the first failure
or uncertainty, and send no resend. Until that evidence exists, stable
promotion and production use remain unqualified.

## Non-goals

This change does not run labs, publish a stable tag, or deploy production. It
does not add an ENV override above the qualified ceiling. An ENV setting may
only lower the qualified budget or delay after a future separately approved
configuration change; this implementation exposes no bypass setting. Such a
setting may lower the count only. It must not reduce the qualified delay.

Ghostfolio image and version are not qualification dimensions. Each release records
the lab version as information. Exact readback and stop-on-uncertainty protect
data if a future chain exceeds D. Raise D in a new connector release.
