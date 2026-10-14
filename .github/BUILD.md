# Build and release guarantees

Every pull request to `main`, including documentation-only changes, runs Python
regression tests, an audit of the complete Python CI environment and container builds/scans for
amd64 and arm64 on native Ubuntu runners. Container runtime checks use synthetic
inputs with no network access, including a real scheduled tick. Validation runs
never log in to GHCR or publish images. CodeQL
analyzes Python independently. Dependency Review rejects newly introduced
moderate or worse dependency vulnerabilities, including development scope.
The native CodeQL merge rule rejects new medium or worse security findings
and error-level findings; a successful analysis alone is insufficient.
The mandatory checks must pass before merging.

`docker-publish.yml` validates main, staging, tag pushes, pull requests and
manual runs without publishing. Its publication job is removed. Existing GHCR
images and aliases remain untouched; stable release publication is delivered
separately. Builds for the same ref are serialized. The Python base is pinned by
its multiarchitecture digest; Dependabot proposes reviewed Docker digest updates.
A weekly `main` run pulls that pinned base and rebuilds without cache, then runs
the same isolated runtime checks and security scans on both native architectures.
It does not advance the base digest or publish an image; base-image fixes require
merging a digest update. High/critical image vulnerabilities with available fixes
fail CI. The supercronic binary is excluded from the blocking scan and remains
covered by a separate advisory scan that never blocks.

Runtime requirements pin the complete dependency closure. Once enabled for this
repository, Renovate proposes weekly Python, GitHub Actions and Docker updates
after 14 days for Python and 3 days for Actions and images. Major updates require
Dependency Dashboard approval; merges stay manual. Dependabot owns security
alerts and repair PRs. Its ordinary update limits become zero after the
Dependency Dashboard is open. Supercronic is a separate upstream binary:
updating its version also requires both architecture checksums. Never auto-merge
dependency changes without the required checks.

## Rollback

Revert a maintenance merge through a PR and wait for all required checks.
Repository administrators can temporarily disable the maintenance rulesets if
a broken required workflow prevents its own repair; restore them after the
repair passes. To roll back an image operationally, use the recorded digest of
a previous good build. GHCR version tags are mutable and are not an immutable
rollback record. Git tag protections do not make container tags immutable.
No GitHub change deploys or recreates a running container.

## Ghostfolio release watch

A daily 07:17 UTC check and manual workflow open one compatibility issue per
new stable Ghostfolio release from the configured baseline, initially 3.80.2.
Policy and affected endpoint checklist live in `.github/upstream-watch.yml`.
All releases since the baseline are considered, so multiple releases between
runs are not lost. Drafts and prereleases are ignored. Existing open or closed
notices are recognized by immutable release ID; closed notices are not reopened.

Issues link official release notes and an upstream compare view. Keyword hints
help triage but never certify compatibility. Review upstream API changes and
add offline regression fixtures where needed. The watcher never probes a
running deployment or changes a deployed version. Disable
`upstream-release-watch.yml` in Actions
and revert its merge to roll back; existing notices can be closed.
