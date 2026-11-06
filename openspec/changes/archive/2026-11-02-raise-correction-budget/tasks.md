# Tasks

Implementation follows the approved GO in `infra-8tt.101`. Labs, stable
publication and production deployment remain outside this implementation PR.

- [x] 1. Read the correction mechanism, Ghostfolio 3.96.0 source and indexed
  lab guidance. Choose fixed delay because the HTTP API exposes no completion
  signal. Record the RC N/D and the lab gate.
- [x] 2. Activate the connector RC budget and
  stop the whole financial run after the first unresolved correction. Preserve
  journal v3, fences, deferred approvals and notifications.
- [x] 3. Extend the offline mock and add tests for five dispatches, delayed jobs,
  stop-on-failure, v3 recovery mid-burst and shared multi-account budget.
- [x] 4. Update the activity-review spec delta, operator docs, CHANGELOG and
  the reproducible burst procedure.
- [x] 5. Run the full suite and `bash scripts/check.sh`; inspect diff and commit.
- [x] 6. Push one PR, run `~/.agents/bin/pr-ship <n> --repo
  flowcool/ghostfolio-ibkr-sync`, read back the merge commit, and append delivery
  evidence to `infra-8tt.101`.
