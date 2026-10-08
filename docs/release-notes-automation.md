# Release notes automation and breaking-change policy

Status: investigation result (2026-10-08); decision: Option A (native notes).
The companion changes (labels workflow, `.github/release.yml`, PR template,
[releasing.md](releasing.md)) are listed under "Implementation" below.

## Problem

Release notes must put breaking changes, operational compatibility changes,
migration steps and rollback first. Today they are composed by hand
(`gh release create`); v2.1.0 shows the risk: the compatibility section had to
be corrected after the fact.

## Repository facts that constrain the choice

- PRs are merged with **merge commits only** (squash/rebase disabled). History
  contains `Merge pull request #N`, `Merge remote-tracking branch 'origin/main'`
  commits, and the same branch commit repeated after branch updates (e.g.
  `fix: accept legacy profiles in import responses` appears three times).
- `docker-publish.yml` publishes on `main`, `staging` and **`v*` tag pushes**
  (`:X.Y.Z`, `:X.Y`); `:latest` is main-only. A release tag therefore triggers
  an image build.
- Required checks (pytest, dependency-audit, amd64/arm64 container-check,
  CodeQL, Dependency Review) gate merges to `main`, including docs-only PRs.
- Releases are tagged manually on the merge SHA, then `gh release create`.
  No `CHANGELOG.md`, no version file: the version comes from `git describe`.
- Commits already use `fix:`/`feat:`/`refactor:`/`chore:`, but PR titles and
  merge commits are not enforced to be conventional.

## Audit of the existing history (2026-10-08)

Read-only review of git, tags, releases and PRs.

| Finding | Evidence | Consequence |
|---|---|---|
| Tags are clean | 13 annotated tags v1.0.0 to v2.1.0, each with a published release | Nothing to repair |
| Merging is disciplined | all 52 first-parent commits on `main` are PR merges | Notes can safely be PR-based |
| PR titles are conventional | 50 of 50 merged PRs use `fix:`/`feat:`/`chore:`/`docs:`/`test:` | Labels can be derived from titles automatically |
| PRs carry no release labels | 44 of 50 unlabeled (only Dependabot PRs have any); no `breaking-change` label exists | Native grouping would show nothing until labels are applied |
| Release notes are inconsistent | v2.0.4 to v2.0.7 are one-liners; v2.0.3 and earlier use Fixed/Internal; v2.0.0 has a breaking section; v2.0.8 and v2.1.0 are detailed | A reader cannot rely on a fixed place for breaking changes |
| Rollback info is rare | a previous-image digest appears only in v2.1.0 | The rollback target must be recorded at release time |
| Version rule is unwritten | v2.1.0 shipped a removal (`--resume` of JSON snapshots) and stricter validation in a minor | The policy below makes the rule explicit |
| Compatibility notes depended on memory | v2.0.0 and v2.1.0 list them; the v2.1.0 section had to be corrected after publication | A template and a label are needed, not a generator |

## Option A: GitHub generated release notes (native)

How it works: `gh release create vX.Y.Z --generate-notes` (or the UI/API
"generate notes") lists the PRs merged since the previous tag, grouped by PR
label according to `.github/release.yml` (`changelog.categories` with
`labels`, `*` catch-all, `exclude.labels`/`exclude.authors`), plus a "Full
Changelog" compare link. Hand-written text can be prepended
(`--notes-file` combined with `--generate-notes` appends the generated part).

| Aspect | Assessment |
|---|---|
| Prerequisites | One file `.github/release.yml`; a label set; label discipline |
| Cost | None; no new action, token or permission |
| Merge-commit fit | Good: PR-based, unaffected by merge noise or repeated commits |
| Workflow interaction | None: the tag/release is still created by the operator, so the `v*` image build fires as today |
| Breaking changes | A top `Breaking changes` category selected by label (`breaking-change`) is prominent, but the content is the PR title only |
| Limits | Cannot generate migration/rollback text, cannot compute the version, cannot fail if a section is missing. Quality = PR titles and labels |

## Option B: Release Please

How it works: parses Conventional Commits on `main`, maintains a release PR
(version bump, `CHANGELOG.md`, tag, GitHub Release on merge). `fix:` patch,
`feat:` minor, `!`/`BREAKING CHANGE` major. Configured with
`release-please-config.json` and `.release-please-manifest.json`; used through
`googleapis/release-please-action`.

| Aspect | Assessment |
|---|---|
| Prerequisites | Config + manifest files, a `release-type` (`simple` needs `version.txt` and `CHANGELOG.md`), conventional commits on every change, action pinned by SHA (repo policy), `contents`/`pull-requests`/`issues: write` |
| Cost | New third-party action in the release path (supply-chain review per `.claude/rules/security.md`), new files to maintain, a standing release PR |
| Merge-commit fit | Poor. Upstream recommends squash for clean notes; with merge commits it also reads branch commits, merge noise and the repeated commits shown above, producing duplicate or misleading entries. Squash is disabled here by design |
| Workflow interaction | Blocking. With the default `GITHUB_TOKEN`, the release PR it opens triggers no `pull_request` workflows, so required checks never run and the PR cannot merge; the tag/release it creates does not trigger `docker-publish.yml` on `v*`. A PAT or GitHub App token is required for both, adding a long-lived credential |
| Breaking changes | Strong signal in the version, but notes are commit subjects. Migration and rollback text still has to be hand-written, so the original omission risk remains |
| Limits | No publication logic; stale `autorelease: pending` labels can block new release PRs; conflicts with the manual `git tag` + `gh release create` flow documented in `CLAUDE.md` |

## Recommendation

Adopt **Option A plus a template and a check**, not Release Please. Release
Please solves version/changelog automation that this repo does not need (one
maintainer, deliberate releases), and it conflicts with merge-commit-only
merging and the tag-triggered image build. Its main benefit, enforcing a
conventional history, can be had more cheaply on PR titles.

The failure to prevent is a *missing* compatibility section, not a poorly
formatted changelog, so the control must be a reviewed template and a gate,
not a generator.

### Semver policy

- **Major**: removes or changes an operator-facing contract: env var, CLI flag,
  `mapping.yaml` schema, journal/recovery file format, exit codes, minimum
  Ghostfolio version, image tag scheme.
- **Minor**: new capability, or a stricter/fail-closed behavior that can make a
  previously accepted input fail. Must be listed under Breaking changes even
  though it is not a major bump (v2.1.0 is the model; note that its
  `--resume` JSON removal would be major under this policy, so state the
  exception explicitly in the notes when a removal ships in a minor).
- **Patch**: bug fix with no compatibility effect, dependency/CI maintenance.

### Labels and PR conventions

Labels (one release-impact label per PR): `breaking-change`, `compat`
(operational compatibility), `feature`, `fix`, `maintenance`,
`skip-release-notes`. `semver:major|minor|patch` is optional; the reviewer
decides the bump at release time.

Add to `.github/pull_request_template.md` a **Release impact** section:
bump (none/patch/minor/major), breaking or operational change (yes/no),
migration steps, rollback note. Required when the label is `breaking-change`
or `compat`.

PR titles keep the existing `fix:`/`feat:`/`refactor:`/`chore:` prefixes,
with `!` for breaking (`feat!:`). Titles, not commits, feed the notes.

### Release notes structure and ownership

Fixed order: **Breaking changes and migration**, **Upgrade checklist**,
**Rollback** (previous image digest, as v2.1.0 does), **Changes**
(generated), **Validation**, **Published artifacts**. The generated part is
appended below the hand-written head.

Ownership: the PR author fills Release impact; the **release owner (the
maintainer cutting the tag)** is the final reviewer of the full notes against
the list of merged PRs and labels, and the `/review-pr` skill checks the
Release impact section on each PR. Recording the notes in the release, not a
repo file, stays the source of truth.

### Interaction with existing controls

No change to branch protection, required checks, `docker-publish.yml` or tag
publication. Tags are still created by the operator and still trigger the
image build. Rollback of the practice: delete `.github/release.yml` and the
template section; releases revert to hand-written notes.

## Implementation

Steps 1 to 3 ship in this PR as separate commits, each revertable alone. Step
3's check is advisory (a warning annotation, never a failure, never required).

1. **Labels and `.github/release.yml`**: create the labels; configure
   categories (`breaking-change` and `compat` first, `*` catch-all,
   `skip-release-notes` and Dependabot excluded or listed under
   Maintenance). Validate with the API `generate-notes` call against the
   v2.0.8..v2.1.0 range (read-only, creates no release). Rollback: revert the
   PR; labels are harmless.
2. **PR template section** *Release impact* and a short
   `docs/releasing.md` (or an addition to `.github/BUILD.md`) with the notes
   skeleton above and the release command
   `gh release create vX.Y.Z --verify-tag --generate-notes --notes-file head.md`.
   Rollback: revert.
3. **Optional PR check** (workflow, SHA-pinned actions, `pull_request`,
   `permissions: pull-requests: read`): fail when the `breaking-change` or
   `compat` label is present and the Release impact section is empty. Use it
   as a required check only after it has run advisory for a few PRs. Rollback:
   remove it from required checks, then revert. Any change to required checks
   follows the ruleset procedure in `.github/BUILD.md`.
4. **Reconsider Release Please** only if the repo moves to squash merges and a
   GitHub App token is acceptable; until then it is not recommended.

## Sources

- GitHub Docs, [Automatically generated release notes](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes)
- [googleapis/release-please](https://github.com/googleapis/release-please) and
  [release-please-action](https://github.com/googleapis/release-please-action)
  (token and workflow-trigger limitation, squash recommendation)
