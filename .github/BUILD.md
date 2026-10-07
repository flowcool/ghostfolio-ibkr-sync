# Build and release guarantees

Every pull request to `main`, including documentation-only changes, runs Python
regression tests, a runtime dependency audit and container builds/scans for
amd64 and arm64. PR builds never log in to GHCR or publish images. CodeQL
analyzes Python independently. The mandatory checks must pass before merging.

Only `main`, `staging` and `v*` tag refs may publish. `latest` is selected only
for `refs/heads/main`; a release tag publishes its full and minor versions.
Manual builds use GitHub's selected ref without a separate checkout override.
Builds for the same ref are serialized. A weekly `main` run pulls a fresh base
and rebuilds without cache, so OS package updates are not hidden by old layers.
Images include provenance and an SBOM. High/critical image vulnerabilities with
available fixes fail CI; unfixed findings do not block publication.

Runtime requirements pin the complete dependency closure. Dependabot proposes
weekly Python, Actions and Docker updates; security alerts and security repair
PRs are enabled. Supercronic is a separate upstream binary: updating its version
also requires both architecture checksums. Never auto-merge dependency changes
without the required checks.

## Rollback

Revert a maintenance merge through a PR and wait for all required checks.
Repository administrators can temporarily disable the maintenance rulesets if
a broken required workflow prevents its own repair; restore them after the
repair passes. To roll back an image operationally, use the recorded digest of
a previous good build. GHCR version tags are mutable and are not an immutable
rollback record. Git tag protections do not make container tags immutable.
No GitHub change deploys or recreates the NAS container.
