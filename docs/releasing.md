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
3. Record the currently published image as the rollback target: run
   `docker buildx imagetools inspect ghcr.io/flowcool/ghostfolio-ibkr-sync:<previous version>`
   and copy the `sha256:` digest.

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

The tag push builds and publishes `:X.Y.Z` and `:X.Y`; `:latest` stays
main-only. The build refuses a tag that is not exactly `vX.Y.Z` or whose commit
is not on `main` (fix: delete the tag locally and on origin, then re-tag). Afterwards, check that the published release shows the head text and
the generated list, and fill in "Published artifacts".

## Reviewer

The maintainer cutting the tag is the final reviewer: compare the generated
list with the head text and make sure every `breaking-change` and `compat` PR is
explained.
