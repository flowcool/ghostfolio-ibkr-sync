# Upstream inventory and monitoring

| Upstream | Pin or compatibility baseline | Monitoring and adoption |
| --- | --- | --- |
| [Supercronic](https://github.com/aptible/supercronic) | `SUPERCRONIC_VERSION=v0.2.51` and separate amd64/arm64 SHA256 pins in [Dockerfile](../Dockerfile) | Daily [dependency release watch](../.github/workflows/dependency-release-watch.yml) at 07:29 UTC; update the version and both checksums together in a reviewed PR |
| [Ghostfolio](https://github.com/ghostfolio/ghostfolio) | Release-watch baseline `3.80.2`, included, in [upstream-watch.yml](../.github/upstream-watch.yml); the operator chooses the running version | Daily [Ghostfolio release watch](../.github/workflows/upstream-release-watch.yml) at 07:17 UTC; review API compatibility before adoption |
| Python runtime and notification dependencies | Exact versions in [requirements.txt](../requirements.txt) | Ordinary update PRs from Renovate; security update PRs from Dependabot; no release notices |
| Python developer and CI dependencies | Exact versions in [requirements-dev.txt](../requirements-dev.txt) | Ordinary update PRs from Renovate; security update PRs from Dependabot; no release notices |
| Python/Debian base image | Python 3.14 slim with an immutable digest in [Dockerfile](../Dockerfile) | Renovate proposals within Python 3.14; CI image scans |
| GitHub Actions | Commit SHA pins in [.github/workflows](../.github/workflows) | Renovate proposals; CI review |

## Ghostfolio compatibility review

The connector API contracts were reviewed through Ghostfolio **3.98.0**.
See the reviews for [3.94.0](https://github.com/flowcool/ghostfolio-ibkr-sync/issues/331),
[3.95.0](https://github.com/flowcool/ghostfolio-ibkr-sync/issues/333),
[3.96.0](https://github.com/flowcool/ghostfolio-ibkr-sync/issues/334),
[3.97.0](https://github.com/flowcool/ghostfolio-ibkr-sync/issues/351) and
[3.98.0](https://github.com/flowcool/ghostfolio-ibkr-sync/issues/353).
This is a source contract review with offline regression checks.
It does not replace qualification of a connector image in both labs.

Ghostfolio 3.94.0 deprecates the singular `/api/v1/account` routes but retains them.
The connector still uses these routes for account reads and cash updates.
Ghostfolio 3.95.0 can store an activity currency as `null` when it matches the
asset profile currency. The connector resolves the effective currency from that
activity's profile and sends a valid currency on an activity PUT.
Ghostfolio 3.98.0 removes biometric devices when a Security Token is rotated.
The token exchange at `/api/v1/auth/anonymous` and bearer JWT contract remain unchanged.
After you rotate a Security Token, update `GHOST_ACCESS_TOKEN` before the next run.

The release-watch baseline `3.80.2` is a notice history boundary.
It is not a tested-version pin or a new minimum requirement.
The Compose examples connect to your existing Ghostfolio deployment.
They do not install or pin its image.

## Dependency adoption

[renovate.json](../renovate.json) and [dependabot.yml](../.github/dependabot.yml)
own the update policy. Supercronic adoption is manual because a version change
must include both architecture checksums. The watcher does not change pins.

Both release watches run on `main`. They acknowledge notices in open and closed
issues and ignore pull-request markers. Supercronic notices are deduplicated by
version, including equivalent spellings, and limited to ten per run. The separate
Ghostfolio watch deduplicates by release ID and retains its compatibility
checklist. Neither watch upgrades, merges or deploys anything, nor accesses
financial accounts. CI audits and scans remain independent of these notices.

Rollback: revert the scoped change through a reviewed PR. No deployment or
repository security-setting change is part of this monitoring policy.
