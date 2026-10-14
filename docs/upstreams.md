# Upstream inventory and monitoring

| Upstream | Pin or compatibility baseline | Monitoring and adoption |
| --- | --- | --- |
| [Supercronic](https://github.com/aptible/supercronic) | `SUPERCRONIC_VERSION=v0.2.49` and separate amd64/arm64 SHA256 pins in [Dockerfile](../Dockerfile) | Daily [dependency release watch](../.github/workflows/dependency-release-watch.yml) at 07:29 UTC; update the version and both checksums together in a reviewed PR |
| [Ghostfolio](https://github.com/ghostfolio/ghostfolio) | Release-watch baseline `3.80.2`, included, in [upstream-watch.yml](../.github/upstream-watch.yml); the operator chooses the running version | Daily [Ghostfolio release watch](../.github/workflows/upstream-release-watch.yml) at 07:17 UTC; review API compatibility before adoption |
| Python runtime and notification dependencies | Exact versions in [requirements.txt](../requirements.txt) | Ordinary update PRs from Renovate; security update PRs from Dependabot; no release notices |
| Python developer and CI dependencies | Exact versions in [requirements-dev.txt](../requirements-dev.txt) | Ordinary update PRs from Renovate; security update PRs from Dependabot; no release notices |
| Python/Debian base image | Python 3.12 slim with an immutable digest in [Dockerfile](../Dockerfile) | Renovate proposals within Python 3.12; CI image scans |
| GitHub Actions | Commit SHA pins in [.github/workflows](../.github/workflows) | Renovate proposals; CI review |

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
