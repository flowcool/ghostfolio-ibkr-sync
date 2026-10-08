# Plan — Automatic Ghostfolio authentication

Date: 2026-10-08
Epic: Automatic Ghostfolio authentication
Status: design

## Problem

`GHOST_TOKEN` is a Ghostfolio **JWT bearer** that expires. The README itself
tells the operator to "set a calendar reminder" and regenerate it by hand
(README "Token expiry", "Security considerations"). When it lapses, the daily
cron fails with HTTP 401 until someone notices and re-pastes a new token.

Ghostfolio already exposes an exchange endpoint (README §"Get an auth token"):

```
POST {GHOST_HOST}/api/v1/auth/anonymous
Content-Type: application/json
{"accessToken": "<long-lived security token>"}
-> { "authToken": "<short-lived JWT bearer>" }
```

The **security token** (shown once in the Ghostfolio UI) is long-lived; the
`authToken` it returns is the thing that expires. If the sync exchanges the
security token for a fresh JWT on every run, manual renewal disappears.

## Goal

Add an opt-in mode where the operator supplies `GHOST_ACCESS_TOKEN` (the
long-lived security token) instead of `GHOST_TOKEN` (the JWT). Legacy
`GHOST_TOKEN` keeps working unchanged. Mutually exclusive.

## Delivery boundary (two child commits, one PR each)

### PR1 — credential selection + token-exchange helper (offline)

Scope: pure/validated code + offline tests. No startup wiring, no login side
effect in legacy mode.

1. **Credential selection** in `load_config()` (currently requires `GHOST_TOKEN`,
   `ibkr_to_ghostfolio.py:60`):
   - Read both `GHOST_TOKEN` and `GHOST_ACCESS_TOKEN` from `os.environ` only
     (never hardcoded/logged — `security.md`).
   - Treat absent / empty / whitespace-only as "not set" deterministically.
   - Both set -> `RuntimeError` (explicit conflict, no silent precedence).
   - Neither set -> `RuntimeError` (same class as today's missing-var error).
   - Preserve opaque nonblank credential bytes verbatim (no trimming of the
     secret itself beyond the set/unset decision, no normalization).
   - Record the resolved `auth_mode` ("legacy" | "access") in config.

2. **`ghost_exchange_access_token(host, access_token)` helper**:
   - Reuse the existing SSRF prefix-assertion pattern
     (`IBKR_ALLOWED_STMT_PREFIXES`, `ibkr_to_ghostfolio.py:42`) adapted to
     `GHOST_HOST`: reject unsafe URL components before any request.
   - Single `requests.post` to `/api/v1/auth/anonymous`, `allow_redirects=False`,
     tuple `timeout=(connect, read)` (match the IBKR call style).
   - Accept **only** a JSON object whose token field is a nonempty, printable
     ASCII, header-safe string (it becomes an HTTP header value). Reject
     everything else.
   - Fixed error messages for HTTP / network / JSON / token-shape failures.
     Never echo the request body, the access token, or the returned token.

Tests (`tests/`, offline, `requests` mocked):
- selection matrix: absent / empty / whitespace / both-present / opaque bytes;
- helper: happy path, non-2xx, network error, non-JSON, missing/blank/non-ASCII
  token, redirect attempt, host rejected;
- legacy mode performs **no** login call.

### PR2 — per-run authentication wiring + README (integration)

Scope: resolve auth in `main()` after local validation (config + mapping) and
**before** any Ghostfolio read or financial write; docs.

1. In `main()` (`ibkr_to_ghostfolio.py:1328`), after `load_config()` and
   `load_mapping()` succeed and before `ghost_get_existing_orders()`:
   - legacy mode -> use `GHOST_TOKEN` as today (zero behavioral change);
   - access mode -> call the helper exactly **once** per invocation (including
     `DRY_RUN` — token exchange is an auth read, not a financial write) and
     store the resolved bearer in config.
   - Invalid mapping must prevent the exchange (ordering); an authentication
     failure must prevent downstream reads, account processing and writes
     (`return 1`, no partial run).
2. Thread the resolved bearer to `ghost_headers()` (`ibkr_to_ghostfolio.py:328`)
   and every Ghostfolio helper. No helper reads the env var directly.
3. No re-authentication mid-run; no uncertain write replay on auth failure.
4. README: document both modes, env table (`GHOST_ACCESS_TOKEN`), examples,
   expiry behavior (access mode = no manual renewal), rollback, and the cleanup
   scripts' manual-token exception.

Tests: synthetic integration — startup ordering (mapping-invalid blocks
exchange; auth-fail blocks reads), exactly-once exchange, dry-run issues a token
but writes nothing, legacy path unchanged.

## Security notes (`.claude/rules/security.md`)

- New external HTTP call -> run `security-review` before merge.
- Host validation = SSRF guard; reuse the proven prefix-assertion, do not
  regress PR #6.
- `GHOST_ACCESS_TOKEN` and the returned bearer: env-only, never logged, never in
  an exception message or a URL.

## Rollback

Revert the scoped implementation commit before deployment. Legacy `GHOST_TOKEN`
remains the documented fallback, so rollback is config-only on the operator
side. Parent-epic rollback contract preserved. Production execution/deployment
requires separate authorization (operator runs pull + stack recreate on the NAS;
see CLAUDE.md "Gotchas ops").

## Open question

Confirm the `/api/v1/auth/anonymous` contract on the deployed Ghostfolio version
(POST `{accessToken}` -> `{authToken}`). Minimum supported version in CLAUDE.md
is 2.248.0; verify the field names there and that 3.x did not rename them.
