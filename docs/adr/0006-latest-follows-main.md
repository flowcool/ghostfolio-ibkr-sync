# Publish latest from stable releases and leave upgrade control to the operator

Date: 2026-10-12. Status: accepted (existing behavior).

The original decision below was superseded by the stable-channel decision
approved on 2026-10-14. The replacement is recorded in this ADR; the filename
remains for existing links.

## Original decision

The former policy published `:latest` from main and weekly rebuilds, plus
`:X.Y.Z` and `:X.Y` from validated tags. It offered a main-following channel.

## Replacement decision

The next published stable release starts the stable channel. Only a published,
non-draft, non-prerelease GitHub Release with an exact `vX.Y.Z` tag without
leading zeros on main publishes `:X.Y.Z`. Only the current stable release
updates `:latest`. Existing minor and staging aliases remain frozen without
deletion. Main, staging, tag pushes, manual runs and schedules publish nothing.

Weekly security checks remain without tag refresh. Maintainers select new
releases for fixes; compatibility-neutral security fixes increment PATCH.
Version manifests are published once through the guarded workflow. Registry
errors block publication; checked native amd64/arm64 configurations and the final
manifest are verified before latest promotion.

Record the installed digest before upgrading. Container tags remain mutable
outside the workflow guards; pinning a digest selects the exact artifact. A
failed latest promotion requires explicit operator action and may promote only
the verified manifest digest of the current stable release, without rebuilding
or overwriting a version. Preserve ENV and mounts for digest rollback; financial
records and cash updates remain, with no financial restoration.

Publishing does not deploy or recreate a container. Operators retain control of
upgrades. This accepts slower security delivery in exchange for stable artifacts
and explicit releases.

## Release-candidate channel

Date: 2026-10-14.

Decision: a published GitHub prerelease with an exact `vX.Y.Z-rc.N` tag
(`N >= 1`, no leading zeros) publishes only `:X.Y.Z-rc.N`. It never moves
`:latest`, `:X.Y.Z` or `:X.Y`. When an RC exists for a version, the stable
`vX.Y.Z` tag must sit on the commit of the highest RC; the preflight enforces
this and fails otherwise. With no RC, the stable path is unchanged, which keeps
the hotfix path.

Reason: test a release in production before `:latest` moves for everyone.

Consequences: an RC number is single-use, because the registry check blocks
republishing a version. Renovate treats the suffix after `-` as a compatibility
suffix, so consumers on `X.Y.Z` are not offered RC tags. See
[release and recovery guide](../releasing.md) for the operator procedure.

Sources: [Docker image](../../README.md#docker-image),
[build guarantees](../../.github/BUILD.md),
[release and recovery guide](../releasing.md), and
[stable publishing workflow](../../.github/workflows/release-image.yml).
