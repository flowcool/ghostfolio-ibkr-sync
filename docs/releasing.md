# Releasing

Plain-language checklist for cutting a release. Why these choices:
[release-notes-automation.md](release-notes-automation.md).

## Before you start

1. Every PR since the last release has a label (added automatically from its
   title) and a filled **Release impact** section if it is labeled
   `breaking-change` or `compat`. Add `compat` by hand when a change can make a
   previously working setup fail or behave differently (stricter validation,
   new file format, changed limit, new required setting).
2. CI is green on `main`.
3. Record the installed image digest as the rollback target, using the running
   container's image ID and its matching repository digest. Follow the
   [Docker image guide](../README.md#docker-image); inspecting a mutable tag does
   not prove which artifact is installed. Preserve the existing ENV and mounts.

## Stable-channel cutover

The next published stable release starts the stable channel. Existing minor
`:X.Y` and staging aliases remain frozen without deletion. Only `:X.Y.Z` is
published; `:latest` follows the current stable release. Main, tag pushes, manual
runs and weekly checks never publish images. Weekly security checks remain;
maintainers ship compatibility-neutral security fixes in new PATCH releases.
Publication does not deploy or recreate a container. Operators choose upgrades.

## Choose the version

- **Major**: removes or changes something users rely on: an environment
  variable, command-line option, `mapping.yaml` format, recovery/journal file
  format, exit code, minimum Ghostfolio version, or image tag scheme.
- **Minor**: new feature, or a stricter check that can reject input that used
  to pass. List it under Breaking changes even though it is not a major.
- **Patch**: bug fix, dependency or CI maintenance with no compatibility effect.

If a removal ships in a minor, say so explicitly in the notes.

## Write the notes

Put this hand-written head in a `head.md` file outside the repo. GitHub appends
the generated PR list below it.

```markdown
## Breaking changes and migration
- <what changes, who is affected, what to do>   (write "None." if none)

## Upgrade checklist
1. <backup / dry-run / inspection steps>

## Rollback
- Previous image digest: `ghcr.io/flowcool/ghostfolio-ibkr-sync@sha256:<digest>` (<version>)
- <what rollback does NOT undo, e.g. data already written>

## Validation
- <tests, reviews, anything not tested>

## Published artifacts
- <image tags and digests, build run links, once published>
```

## Publish

```bash
git tag -a vX.Y.Z <merge-sha> -m "vX.Y.Z"
git push origin vX.Y.Z
gh release create vX.Y.Z --verify-tag --latest \
  --title "vX.Y.Z — <short summary>" --notes-file head.md --generate-notes
```

The tag push validates only. Publishing the non-draft, non-prerelease GitHub
Release triggers `release-image.yml`. It requires an exact `vX.Y.Z` tag without
leading zeros on main and refuses an existing `:X.Y.Z` or an uncertain registry
response. Select an unused version; do not replace an already published tag.

Check the release workflow logs: both native runtime checks and security gates
must pass, published configuration digests must match the tested images, and
both architectures must match the assembled manifest. Only the current stable
release advances `:latest`. Check that the release notes show the head text and
generated list. Fill in "Published artifacts" with the workflow link, version
and verified manifest digest from its `release-manifest` artifact.

## Recover a failed latest promotion

A version may exist even when its `latest` promotion failed. A workflow rerun
refuses that version; do not rebuild or overwrite it. Recovery requires explicit
operator authorization for a registry write and the original publication evidence.

1. Inspect the failed release run and download its `release-manifest` artifact.
   Require successful native checks, configuration matches and both manifest
   architecture checks. Take the verified digest from
   `release-manifest-digest.txt`; compare it with `release-manifest.json` and
   the run's `Verified stable manifest` output. If that evidence is missing or
   inconsistent, stop.
2. Inspect `ghcr.io/flowcool/ghostfolio-ibkr-sync@sha256:<verified-digest>` with
   `docker buildx imagetools inspect`. Confirm it is the verified amd64/arm64
   manifest from that release, rather than a digest resolved from `latest`.
3. Authenticate to GHCR with package write access. Immediately before promotion,
   require `gh api repos/flowcool/ghostfolio-ibkr-sync/releases/latest --jq .tag_name`
   to equal the failed release's `vX.Y.Z`. If a newer stable release exists,
   stop; do not promote the older release.
4. Promote only that verified digest, without building:

   ```bash
   docker buildx imagetools create \
     --tag ghcr.io/flowcool/ghostfolio-ibkr-sync:latest \
     ghcr.io/flowcool/ghostfolio-ibkr-sync@sha256:<verified-digest>
   ```

5. Inspect `:latest` and confirm its digest matches the verified digest. Record
   the recovery evidence in the release notes. This does not deploy anything.

## Runtime rollback

Select the previously recorded installed digest and recreate the connector with
its original ENV and mounts. This restores the runtime only: financial records
and cash updates remain. It does not restore financial data or undo imports.
Use a separately authorized Ghostfolio recovery procedure if data recovery is
needed.

## Reviewer

The maintainer cutting the tag is the final reviewer: compare the generated
list with the head text and make sure every `breaking-change` and `compat` PR is
explained.
