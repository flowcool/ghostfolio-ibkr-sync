## Behavior

Describe the problem and resulting behavior. Keep this PR focused on one change.

## Release impact

<!-- Version bump (none/patch/minor/major), breaking or operational change,
migration steps, rollback. Write "None" if there is no impact. Required, in
plain words, when the PR is labeled breaking-change or compat. -->

## Verification

- Command:
- Expected result:
- Observed result:

Use synthetic inputs and isolated state. Do not attach secrets or private data.

## Scope and lab gate

- Scope: <!-- Connector code/spec/lab/release, or docs only. Route managed
  production deployment, pins, schedules, host files and lab-runner defects to Infra. -->
- Pre-merge lab trigger: <!-- Financial logic; deduplication/activity identity;
  Ghostfolio authentication/transport/writes; state/journal format; major
  dependency/base image. Otherwise write "None" and explain why. -->
- Lab proof: <!-- For a trigger: tested PR image identity and source commit,
  empty + golden results, retained evidence and final stopped verification.
  Every release also needs both scenarios on its exact digest. Reuse this proof
  only if the digest is identical. -->

See [scope and lab gates](https://github.com/flowcool/ghostfolio-ibkr-sync/blob/main/CONTRIBUTING.md#scope-and-lab-gates).

## AI assistance

State whether AI assisted this change and what the author verified.

## Pullfrog review

Pullfrog is the sole reviewer. Require a completed review of the final head,
resolve actionable threads and keep all technical CI checks green. Ignore
CodeRabbit and the known sticky `pullfrog-approval` status only. Docs-only PRs
need CI only. Run `pr-ship` under the repository's Git workflow.

Review evidence: <!-- completed review URL and reviewed commit SHA -->
