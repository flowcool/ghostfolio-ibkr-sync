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
manual runs without publishing. Builds for the same ref are serialized.
The Python base is pinned by its multiarchitecture digest; Dependabot proposes reviewed Docker digest updates.
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

## Stable publication

The next published stable release starts the stable channel. Existing minor
`:X.Y` and staging aliases stay frozen without deletion. `release-image.yml`
requires a published, non-draft, non-prerelease GitHub Release with an exact
`vX.Y.Z` tag without leading zeros whose commit is on main. Only `:X.Y.Z` is
published; only the current stable release advances `:latest`. Main, staging,
tag pushes, manual runs and schedules never publish images.

Release publication is serialized. It refuses existing version manifests and
uncertain registry responses, then rechecks absence before manifest creation.
Both native architectures must pass security and isolated runtime checks. Their
published configuration digests must match the checked images, and the assembled
manifest must contain those amd64 and arm64 images before `latest` promotion.
SBOM and provenance accompany the published native images.
The assembled manifest digest is signed keylessly with cosign using the release
workflow identity, and the signature is verified before `latest` promotion.
Verify an installed image with:

```bash
cosign verify \
  --certificate-identity-regexp '^https://github.com/flowcool/ghostfolio-ibkr-sync/\.github/workflows/release-image\.yml@refs/tags/v' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/flowcool/ghostfolio-ibkr-sync@sha256:<manifest-digest>
```

Images published before this guarantee have no signature.
If signing still fails after retries, the version stays published without a
signature and cannot be re-signed by the workflow (the single-publication guard
refuses it). Publish a superseding patch release instead of signing by hand: a
manual signature carries a personal identity and fails the command above.

A published, non-draft GitHub prerelease with an exact `vX.Y.Z-rc.N` tag
(`N >= 1`, no leading zeros) on main publishes only `:X.Y.Z-rc.N`, with the same
checks and publication guard. It never creates or moves `latest`, `X.Y.Z` or
`X.Y`. A stable `vX.Y.Z` is refused unless it is on the commit of its highest
RC, when one exists. RC tags are not for normal use; see
[Releasing](../docs/releasing.md#release-candidate-optional).

Weekly security checks do not refresh tags. Maintainers must merge fixes and
select a new release; compatibility-neutral security fixes increment PATCH.
A rerun refuses an existing version even if its `latest` promotion failed.
Explicit recovery may promote only the verified manifest digest of the current
stable release, as described in [Releasing](../docs/releasing.md#recover-a-failed-latest-promotion).
Publication does not deploy or recreate a running container.

## Rollback

Revert a maintenance merge through a PR and wait for all required checks.
Repository administrators can temporarily disable the maintenance rulesets if
a broken required workflow prevents its own repair; restore them after the
repair passes. To roll back an image operationally, use the recorded digest of
a previous good build. GHCR version tags are mutable and are not an immutable
rollback record. Git tag protections do not make container tags immutable.
Record the installed digest before upgrading, and preserve ENV and mounts when
selecting it for rollback. Image rollback does not restore financial records or
undo cash updates. No GitHub change deploys or recreates a running container.

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
