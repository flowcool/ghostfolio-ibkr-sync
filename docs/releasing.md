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
## What's new
<One short paragraph: what changed and why a user should care.>

## Important changes
- Breaking change or new prerequisite: <who is affected and what to do>
- Compatibility or behavior change: <details or "None.">

## Upgrade guide
1. Back up Ghostfolio.
2. Run the preview with `DRY_RUN=true` and inspect the logs.
3. <version-specific migration step, or link to a guide>

## Technical details
- Qualification scope: <image, lab scenario, and restrictions>
- Validation: <tests, reviews, and acceptance evidence>
- Known issues: <none, or link>

## Rollback
- Previous image digest: `ghcr.io/flowcool/ghostfolio-ibkr-sync@sha256:<digest>` (<version>)
- Runtime rollback does not undo activities or cash updates.

## Published artifacts
- <image tags, verified manifest digest, and build run link>

## Full changelog
<GitHub generated PR list and comparison link are appended here.>
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

Check the release workflow logs: a new build must pass both native runtime and
security gates, with published configuration digests matching the checked images.
Promotion from an RC must verify its signed artifact and accepted lab record,
then copy the exact index. The original RC run must supply the native build
checks. Both architectures must match. Only the current stable
release advances `:latest`. Check that the release notes show the head text and
generated list. Fill in "Published artifacts" with the workflow link, version
and verified manifest digest from its `release-manifest` artifact.

## Release candidate (optional)

A release candidate (RC) lets a maintainer validate an image before the stable
tag exists. Use it for risky changes; normal patch releases may skip it.

Tag format: `vX.Y.Z-rc.N`, with `N >= 1` and no leading zeros.

1. **Cut.** Tag a commit on main and publish a GitHub prerelease. The notes come
   from `.github/release.yml`, as for a stable release.

   ```bash
   git tag -a vX.Y.Z-rc.N <merge-sha> -m "vX.Y.Z-rc.N"
   git push origin vX.Y.Z-rc.N
   gh release create vX.Y.Z-rc.N --verify-tag --prerelease \
     --title "vX.Y.Z-rc.N" --generate-notes
   ```

   `release-image.yml` runs the same checks and the same single-publication
   guard as for stable, and publishes only `:X.Y.Z-rc.N`.
2. **Validate.** Before an RC digest proceeds to production or stable
   promotion, require it to pass the versioned infra `lab.py` runner in both
   isolated scenarios: empty first install and golden-copy upgrade. A failed or
   incomplete digest cannot proceed; publish a new RC for its fix and run both
   scenarios for that new digest. Stop both lab instances after the run. Lab
   credentials remain separate from production credentials. Production validation
   is a separate operator-validated operation. Users can try a candidate with the
   [user procedure](upgrading-to-3.0.md#try-a-release-candidate). A fix creates a
   new RC (`N + 1`); never replace a published RC tag.

   There is no mandatory soak or waiting period. Reuse accepted evidence for the
   exact RC digest. Retagging identical bytes does not require another lab run.
   Repeat affected checks after a relevant source, configuration or destination change.

3. **Promote.** On the operator's GO, tag stable `vX.Y.Z` on the same commit as the highest RC, then
   follow [Publish](#publish). Pass `--notes-start-tag <previous stable>` to
   `gh release create` so the generated notes cover the whole version, not only
   the changes since the last RC.

   ```bash
   gh release create vX.Y.Z --verify-tag --latest --notes-start-tag <previous-stable-tag> \
     --title "vX.Y.Z — <short summary>" --notes-file head.md --generate-notes
   ```

### Preserve the qualified digest

For stable publication with an RC, the workflow copies the highest RC index.
Stable and latest must have the same digest as that qualified RC. It does not
rebuild either architecture. The build derives the target software version
`X.Y.Z` from the validated tag. `APP_VERSION` and the OCI version label contain
that target software version. `APP_REVISION` and the OCI revision label contain
the full source commit. Startup reports
`ghostfolio-ibkr-sync version X.Y.Z — commit <12-character SHA>`.
These values are automatic and do not change on promotion. An RC reports its
target software version before stable publication. Candidate registry tags and
cosign certificate identities retain the full RC identity.

Older qualified images retain their original exact RC `APP_VERSION` and OCI
version label, and their old startup text. The shared promotion/recovery verifier
accepts that original form only without `APP_REVISION`. It rejects mixed metadata
or conflicting runtime/OCI versions and commits, including disagreement between
architectures. Both forms still require the same qualification, signature,
source and exact-digest checks. Changing image metadata would change its bytes;
never rebuild or overwrite an already qualified candidate to change its display.

Before publishing stable, a maintainer reviews both lab result files and attaches
one `lab-qualification.json` asset to the RC prerelease. This record attests the
maintainer's acceptance. The workflow can verify the record and its binding to
the signed image. It cannot independently prove that a lab run occurred. Keep the
private runner evidence. Use this exact schema; replace every placeholder:

```json
{
  "schema": 1,
  "repository": "flowcool/ghostfolio-ibkr-sync",
  "rc_tag": "vX.Y.Z-rc.N",
  "commit": "<40-character release commit>",
  "digest": "sha256:<qualified index hash>",
  "native": {
    "amd64": "sha256:<amd64 manifest hash>",
    "arm64": "sha256:<arm64 manifest hash>"
  },
  "labs": {
    "empty": {"status": "PASS", "cleanup": "stopped", "evidence_sha256": "<result.json SHA-256>"},
    "golden": {"status": "PASS", "cleanup": "stopped", "evidence_sha256": "<result.json SHA-256>"}
  }
}
```

Hash the retained final `result.json` from each versioned lab runner invocation.
Require both results to name this image digest, report successful acceptance,
and confirm stopped cleanup. Do not attest a failed or incomplete run. Copy the
native manifest hashes from the signed index. Do not include credentials,
private paths or host names. Under the recorded release authorization, attach it:

```bash
gh release upload vX.Y.Z-rc.N lab-qualification.json
```

The stable workflow rejects a missing, malformed or mismatched record. It checks
the RC signature, both native source revisions and version labels, the immutable
index and the RC tag digest before writing. It rechecks the qualification record
and the one-time stable tag guard, then reads back stable and latest digests.
A partial write stops promotion. Do not overwrite a version to recover it.

The workflow in the **tagged commit** controls release publication. Merging new
tooling does not change an older RC's workflow. Such an RC needs a separately
authorized recovery operation, or a new RC that includes this tooling and passes
both labs. This preparation grants no stable publication or deployment authority.

What the workflow refuses:

- Any prerelease tag that is not an exact `vX.Y.Z-rc.N` (for example `-beta.1`,
  `-rc.0`, `-rc.01`), a stable tag flagged prerelease, drafts and tag pushes.
- A stable `vX.Y.Z` when a `vX.Y.Z-rc.N` tag exists and the stable tag is not on
  the commit of the highest `N`. The error names both tags. With no RC, stable
  publication is unchanged.

An RC never creates or moves `:latest`, `:X.Y.Z` or `:X.Y`. The workflow skips
`latest` promotion for RC tags.

### Consumer Renovate

A consumer pinned to `X.Y.Z` is not expected to be offered `X.Y.Z-rc.N`. The
[Renovate docker versioning documentation](https://docs.renovatebot.com/modules/versioning/docker/)
states: "Renovate treats the text after the first hyphen as a type of
platform/compatibility indicator", and gives the example that users on
`-alpine` do not want updates to `12.16.0` or `12.16.0-stretch`. So `-rc.N` is a
suffix that marks a separate compatibility track. The page does not mention
prereleases or `-rc.` tags, and does not say explicitly that a plain `X.Y.Z` is
not offered a suffixed variant. This is an inference from the suffix rule;
consumers who need certainty should check their Renovate dry-run output.

## Publish an older qualified RC

An RC can predate the workflow that copies its digest. Under an explicit stable
publication GO, use `recover-release-image.yml` from main. This operation does
not rebuild or deploy. The exact accepted digest keeps its existing lab proof.

1. Verify the retained RC build, signature, native manifests and both successful
   stopped lab runs. Attach the qualification record described above.
2. Record the current latest digest as the expected rollback target. Prepare one
   non-prerelease draft named `vX.Y.Z`, with `--target` set to the exact highest
   RC commit. Include the complete stable changelog, accepted digest, retained
   embedded APP_VERSION, APP_REVISION (when present) and qualification limits. Do not create the stable tag yet.
3. Dispatch the reviewed executor on main:

   ```bash
   gh workflow run recover-release-image.yml --ref main \
     -f tag=vX.Y.Z -f digest=sha256:<qualified-index> \
     -f previous_digest=sha256:<current-latest>
   ```

The executor verifies all image evidence before writes. It refuses an existing
stable tag/version, a changed latest digest, a changed current stable release or
a newer/equal stable version. It creates the annotated stable tag and publishes
the prepared draft with the repository GITHUB_TOKEN. GitHub does not trigger
other workflows from these token-originated writes, so the older release build
cannot run. It then uses the real published release response and the accepted
source checkout for the existing promotion guards. It reads back stable/latest
and retains a `qualified-release-recovery` artifact. Inspect that proof and the
public release notes. This workflow is for the initial publication only.

After a failed or uncertain write, stop and inspect actual tag, release and
registry state. Do not rerun this initial-publication workflow or overwrite a
version. A partially published version uses the explicit digest recovery below.

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

After any imported or converted v2 activity exists, stop writers and set
`DRY_RUN=true`. Keep rc.5 or a newer qualified dual reader. Never run pre-rc.5
code against that history. Reader rollback retains rows and can still refuse
partial dividend coverage. Comment reversal restores only unchanged journal-owned
comments; it retains new v2 imports. See [guarded rollback](cleanup.md#guarded-comment-rollback-and-resume-inspection).

Select the previously recorded installed digest and recreate the connector with
its original ENV and mounts. This restores the runtime only: financial records
and cash updates remain. It does not restore financial data or undo imports.
Use a separately authorized Ghostfolio recovery procedure if data recovery is
needed.

## V2 writer qualification and release order

Offline tests prove the implemented rules on their fixed inputs. They do not
qualify IBKR ID lifetime or deployed Ghostfolio behavior. Record each gate's
evidence, scope, missing cases and verdict before enabling the affected writes.
Do not infer a vendor guarantee from nearby captures.

| Gate | Required evidence |
|---|---|
| G1: bounded stability | Capture hashes, selected Flex fields, report windows and event counts. Match overlapping payments independently of actionID. Record retained, replaced and reused IDs, revisions, reversals and repayments. Qualify trade overlaps and corrections too. Missing cases block the affected capability. |
| G2: account scope | Test equal tradeIDs/actionIDs in two source accounts. Retain the source-account segment in every identity. Record saved multi-account evidence when available; unknown global uniqueness is informational. |
| G3: complete partition | Prove complete payment, PIL, signed tax/refund and accrual association for each qualified window. Conserve exact cash before fee clamping. A stable ID does not prove a complete window. |
| G4: destination comments | Confirm the current version and immutable image against the inspected source. On that image, import and read back exact comments, punctuation, realistic lengths and otherwise identical payloads from two accounts. Offline tests cover 1999/2000/2001 characters; the source-backed maximum is 2000. |
| G5: comment preservation | On the qualified image, prove whitelisted full PUT and reverse PUT preserve ownership, financial values, UTC instant, tags and profiles. Measure background effects, batch sizes and pacing. Synthetic HTTP does not prove these effects. |
| G6: reader rollback | Use the actual rc.5 image with complete and partial v2 action sets and mixed historical generations. Prove row preservation, simulation and partial-coverage refusal. Current-source tests cannot substitute for this image. |
| G7: sibling compatibility | Compare readers and import/cash/request helpers at pinned revisions. Keep sibling generations and pins unchanged. Flag changed shared helpers for a separate DEGIRO change under [ADR 0007](adr/0007-pinned-degiro-core.md). |

The destination source reference is Ghostfolio 3.86.0, commit
`ef47c0d1b2c48fa4e97fb381561b514e657928cf`. Saved deployment evidence binds it to
`sha256:929a54a1972c48f3cfb30af2db6f9f2aaeb610a9cc5f53264f1df1629eb43078`.
This is not a current runtime observation. A mutable `latest` tag cannot confirm
the installed image. Version drift requires renewed qualification.

Use this order for the v2 writer:

1. Complete offline implementation and review. Archive the approved change and
   replay acceptance on main. Replay complete saved migration inputs, including
   the full configured source-account inventory and destination snapshot.
   Diagnostic section captures without AccountInformation cannot supply that proof.
2. Obtain a separate operator GO for an unused immutable RC numbered rc.6 or later.
   Publish its digest before lab validation. Publication does not enable writes.
3. Pass both empty first-install and golden-copy upgrade scenarios on that same
   digest through the versioned infra runner. Include new v2 imports, repeat runs,
   mixed history, partial acceptance, bounded recovery, maintenance and rollback.
   Derive expected sets from each fixed report/snapshot pair. Do not reuse reader
   counts as writer expectations. Keep lab credentials separate. Stop both instances.
4. Complete G1–G7 and confirm the current destination image. Obtain separate GO
   for production activation. A failed or incomplete digest cannot proceed;
   publish a new RC and rerun both lab scenarios.
5. Historical conversion needs its own reviewed preview, operation plan and GO.
   Stable promotion needs a new GO. Neither follows from offline tests or RC publication.

The reader floor is rc.5, commit `246b890d8cf2b6a58e99bbbf0169aa5f846c23bc`,
image `sha256:32a034c96c2a675329e0aa38a3003a0352db8cec013ea74b6d04ac04cc8a9369`.
Keep existing pair cleanup tools outside the runtime image and do not run them
against v2 history until separately qualified. Use the distinct
[recovery and maintenance tools](cleanup.md) only within their approved operations.

## Reviewer

The maintainer cutting the tag is the final reviewer: compare the generated
list with the head text and make sure every `breaking-change` and `compat` PR is
explained.

## Activity review qualification

Review is opt-in. `activity_review.QUALIFIED_EXECUTION` binds the initial
execution budget to Ghostfolio image
`sha256:929a54a1972c48f3cfb30af2db6f9f2aaeb610a9cc5f53264f1df1629eb43078`:
one correction per complete connector run, across all configured accounts.
Remaining approvals and import holds stay pending for the next run. No ENV
setting bypasses this boundary. Operators must verify that destination image;
the connector cannot discover a server's Docker image through its activity API.
Image drift requires renewed qualification.

The 2026-10-23 isolated proof used the published v3.1.0-rc.1 package against that
Ghostfolio image. Six TRADE/DIVIDEND full-update/reverse cases covered exact
numeric values, UTC dates, tags, ownership, unchanged profiles and Unicode notes
at 1999/2000 UTF-16 units. Thirteen observed PUTs each had exact financial
readback and independently attributed new market-data and later portfolio-cache
job completion. One matrix run stopped when its observer became unavailable;
its FAIL is retained. A separately authorized, journal-bound inverse completed
the final case and restored the original financial state. These observations
qualify isolated corrections; they do not qualify a burst of corrections.

The finite limit is therefore one. The configured minimum inter-correction
delay is zero because no second correction can dispatch in that run. This does
not certify a safe interval between separate runs, background completion at HTTP
readback, or production throughput. Observed background chains of 6.708-9.839
seconds are samples, not a safe-delay guarantee. Do not use repeated immediate
runs to drain approvals. Larger limits need separate isolated qualification.
The installed RC also passed network-denied normal-run budget/deferred-approval,
interruption/restart, no-resend, duplicate-reference and notes-compatible-reader
replays. Those tests prove connector behavior, not live background timing.
Private native evidence stays outside this public repository.

Prove full/reverse PUT preservation, exact numeric/date readback, notes (Unicode
length/trimming), tags, ownership, profile/background effects, duplicate references,
interruption at each journal transition, restart recovery and no repeat logical
request. Failed preservation keeps affected corrections unavailable. Changed
security profiles currently require separate preservation evidence. Current
report windows cannot qualify historical legacy-global reference upgrades.

Publication requires its recorded GO. Both versioned empty/golden lab scenarios
must pass on the same immutable candidate digest before activation/stable
promotion. No duration or cycle count is added. Production activation, historical
conversion and stable publication retain separate GO. After notes-bearing writes,
retain a qualified extended reader; bare-v2 rc.5 alone is insufficient. Software
rollback preserves rows and does not restore data.

Downstream impact under ADR 0007: exact Ghostfolio response capture, comment
identity reading and a whitelisted update helper changed. DEGIRO stays pinned;
adoption needs a separate downstream change. No sibling writer or pin changes.

## Lab logging

Lab acceptance needs `LOG_LEVEL=DEBUG` for the bounded `LAB_EVIDENCE` records.
INFO logs do not include them. This setting does not authorize any live operation.
