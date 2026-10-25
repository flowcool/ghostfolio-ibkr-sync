## Mechanism

Reuse `candidate_qualification`, `promote`, `same_digest`, `registry_version_absent` and the current stable/highest-RC source checks. Extract the candidate metadata reader from `plan`; add verification-only mode to `promote` so all image checks run before any publication.

A workflow_dispatch on main receives a stable tag, qualified digest and expected previous latest digest. The repository token has contents/package write only. The executor requires one matching non-prerelease draft with an exact source commit and nonempty notes. It refuses an existing stable tag or image version, a newer/equal stable release and a changed current stable release. It verifies the highest RC, qualification, signature and native source identities, then creates an annotated tag and publishes the draft using GITHUB_TOKEN. Those writes do not trigger the old release or tag workflows.

The executor reconstructs the publication event from the actual API response, checks out the accepted RC commit in an isolated worktree and runs the existing exact-digest promotion mechanism from the reviewed tooling checkout. The legacy release guard still verifies the real stable tag, main ancestry and registry absence. Proof artifacts retain preflight, actual release response, final index and result.

## Verification and recovery

Use existing release/image checks plus isolated mocked API/subprocess boundary probes. CI and Pullfrog must pass for the exact tooling head before dispatch. A failed write stops dependent writes and reports the phase and possible partial state. Never rerun to overwrite a version. Inspect release, tag and registry state; explicit digest recovery can restore recorded latest only under the operation GO. Stable publication does not deploy. Roll back tooling with a scoped revert.
