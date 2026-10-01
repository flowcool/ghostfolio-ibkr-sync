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

## Step 3b: A/B dry run on the NAS (mandatory for any change to sync logic)

Real data, no writes (`DRY_RUN=1`): run `main` and the PR branch, then compare the logs without timestamps.
The sync output must change only where the PR intends; anything else is a regression. Skip only for
docs/CI-only PRs.

```bash
# run from the PR branch checkout
DRY='ssh ugreen docker exec -i -e DRY_RUN=1 -e LOG_LEVEL=DEBUG ghostfolio-ibkr-sync-individual python -'
git show main:ibkr_to_ghostfolio.py | $DRY > $TMPDIR/dry_main.log 2>&1;  echo "main rc=$?"
$DRY < ibkr_to_ghostfolio.py              > $TMPDIR/dry_branch.log 2>&1; echo "branch rc=$?"
strip() { sed -E 's/^[0-9-]+ [0-9:]+ //' "$1"; }
diff <(strip $TMPDIR/dry_main.log) <(strip $TMPDIR/dry_branch.log)
grep -ci "IBKR_TOKEN\|[?&]t=" $TMPDIR/dry_branch.log   # must be 0
```

Report in the PR comment: exit codes, ERROR count, the diff explained line by line, "New ... activities" counts.

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

## Step 6: After merge — merge is not deployment

No Watchtower on ugreen: the NAS keeps the image of its last recreate. After merge, tell the operator
the change is NOT live until pull + recreate, and show what runs now:

```bash
ssh ugreen 'docker image inspect -f "{{.Created}}" $(docker inspect -f "{{.Image}}" ghostfolio-ibkr-sync-individual); docker exec ghostfolio-ibkr-sync-individual printenv APP_VERSION'
```

Image older than the merge commit, or no APP_VERSION → not deployed. Deployment is the operator's call.
