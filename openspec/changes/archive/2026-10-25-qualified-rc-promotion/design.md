## Context

`release_image.release_metadata`, `stable_follows_release_candidate` and `registry_version_absent` already guard release authority, source and one-time publication. `verify_release_image.native_manifest_digest` validates native descriptors. Reuse them.

## Decisions

For stable with an RC, select the highest numeric RC and require its published prerelease to expose one `lab-qualification.json` asset. A maintainer publishes this record only after reviewing both stopped lab runs. The record binds the repository, RC tag, commit, index digest, native manifest digests and hashes of both private result files. It is a maintainer attestation, not an independent proof of lab execution. GitHub release write access is the trust boundary.

Before any registry write, verify the RC keyless signature for the exact release workflow/tag identity. Inspect the immutable index and both native configs, including source revision and version labels. Recheck event authority, Git ancestry, highest RC and version absence. Copy one index source with Docker imagetools; compare the final raw index digest. Only the current stable may then move latest, followed by a digest readback. Preserve RC version labels because changing them changes bytes.

RC and stable-without-RC builds retain the current native runtime/security gates. The workflow at the tagged commit controls publication. An older RC requires a separately authorized recovery operation or a new RC carrying this tooling; merging this change cannot alter its release workflow.

## Verification and recovery

Use existing release tests and offline synthetic boundary checks without registry writes. Profile the endurance test before and after a test-local C YAML codec substitution; preserve every iteration, custom node validation, real files and fsyncs. Other tests retain the production codec. Review workflow job conditions and permissions. Revert these scoped commits to recover tooling. A partial registry write stops dependent actions; never overwrite an existing version. No stable publication occurs in this task.
