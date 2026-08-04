---
description: Review a PR on this repo using a cold sub-agent + optional CodeRabbit
---

# Review PR

## Step 1: Get the diff

```bash
# If PR number given:
gh pr diff <N> --repo flowcool/ghostfolio-ibkr-sync
# If working branch:
git diff main...HEAD
```

## Step 2: Cold sub-agent review (mandatory)

Launch a code-reviewer agent with NO context from this conversation:

```
Agent(
    subagent_type="everything-claude-code:code-reviewer",
    run_in_background=True,
    prompt="""Review this Python diff cold (no prior context).
Context: single-file sync script, requests+yaml, raise RuntimeError on failure.
Diff: <paste diff>
Report: correctness bugs only, skip style. Be concise."""
)
```

## Step 3: Repo-specific checklist (historical bugs)

Verify manually against these — sub-agents miss them:

- **Dockerfile**: no duplicate `VOLUME`, `chown` before `VOLUME`
- **Guard chains**: if guard added at call site, check callee doesn't have the same (dead code)
- **`except` scope**: `except RuntimeError` doesn't cover `requests.RequestException` — widen if needed
- **Deferred raise**: if exception deferred to let code run, verify return values aren't lost
- **Batch review**: reviewing multiple PRs together reveals cross-cutting patterns

## Step 4: Document findings

```bash
gh pr comment <N> --repo flowcool/ghostfolio-ibkr-sync --body "## Review sub-agent (YYYY-MM-DD)
<findings and corrections>"
```

## Step 5: Optional CodeRabbit second opinion

- Only on OPEN PRs (merged PRs get empty reviews)
- One PR at a time (rate limit ~5/hour)
- Trigger: `@coderabbitai review` as PR comment
- Wait for walkthrough before merging
