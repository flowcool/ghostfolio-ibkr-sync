---
name: review-pr
description: Review a PR on this repo using a cold sub-agent and a manually requested CodeRabbit review
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

## Step 5: Request a CodeRabbit second opinion

- Use an OPEN PR whose changes are ready; merged PRs cannot be reviewed.
- Request one PR at a time. OSS quotas depend on the repository; do not assume
  paid-plan limits. Public repositories below 10 stars require manual requests.
- Post `@coderabbitai review` as a PR comment after the final push. Use
  `@coderabbitai full review` only when a complete new pass is needed.
- Verify the review completed for the current PR head. A walkthrough, summary,
  skipped notice or pending status alone does not prove a completed review.
- Address confirmed findings. If corrections add commits, request another
  incremental pass and record the completed review URL and reviewed head SHA.
- If CodeRabbit is unavailable, record the reason and let the maintainer decide
  whether to merge. Preserve required CI and the independent review above.

## Step 6: After merge — release, then remember merge is not deployment

Release first (CLAUDE.md § Git): `git tag -a vX.Y.Z <merge-sha>` (patch bump for a fix) + push + `gh release create vX.Y.Z --verify-tag --latest`. Docs/CI/skill-only merges need no release.

No Watchtower on ugreen: the NAS keeps the image of its last recreate. After merge, tell the operator
the change is NOT live until pull + recreate, and show what runs now:

```bash
ssh ugreen 'docker image inspect -f "{{.Created}}" $(docker inspect -f "{{.Image}}" ghostfolio-ibkr-sync-individual); docker exec ghostfolio-ibkr-sync-individual printenv APP_VERSION'
```

Image older than the merge commit, or no APP_VERSION → not deployed. Deployment is the operator's call.
