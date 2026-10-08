# Build and release guarantees

Every pull request to `main`, including documentation-only changes, runs Python
regression tests, an audit of the complete Python CI environment and container builds/scans for
amd64 and arm64. PR builds never log in to GHCR or publish images. CodeQL
analyzes Python independently. Dependency Review rejects newly introduced
moderate or worse dependency vulnerabilities, including development scope.
The native CodeQL merge rule rejects new medium or worse security findings
and error-level findings; a successful analysis alone is insufficient.
The mandatory checks must pass before merging.

Only `main`, `staging` and `v*` tag refs may publish. `latest` is selected only
for `refs/heads/main`; a release tag publishes its full and minor versions.
A tag build first checks that the tag is exactly `vMAJOR.MINOR.PATCH` (no
pre-release suffix, no leading zeros) and that its commit is on `main`; otherwise
it fails before login and push, so no misleading image tag is published.
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

## Ghostfolio release watch

A daily 07:17 UTC check and manual workflow open one compatibility issue per
new stable Ghostfolio release from the configured baseline, initially 3.80.2.
Policy and affected endpoint checklist live in `.github/upstream-watch.yml`.
All releases since the baseline are considered, so multiple releases between
runs are not lost. Drafts and prereleases are ignored. Existing open or closed
notices are recognized by immutable release ID; closed notices are not reopened.

Issues link official release notes and an upstream compare view. Keyword hints
help triage but never certify compatibility. Review upstream API changes and
add offline regression fixtures where needed. The watcher never probes the NAS
or changes a deployed version. Disable `upstream-release-watch.yml` in Actions
and revert its merge to roll back; existing notices can be closed.
