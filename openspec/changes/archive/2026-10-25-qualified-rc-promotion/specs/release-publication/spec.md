## MODIFIED Requirements

### Requirement: Stable follows the validated RC

When a tag `vX.Y.Z-rc.N` exists, stable `vX.Y.Z` SHALL use the same commit as the highest `N` and SHALL copy that RC image index without rebuilding. The resulting stable and latest digests SHALL equal the qualified RC digest. Missing or mismatched qualification evidence SHALL refuse publication. With no RC for `X.Y.Z`, stable publication SHALL proceed as before. The commit refusal SHALL name both tags.

#### Scenario: Stable commit check
- **WHEN** `.venv/bin/python -m pytest -q tests -k 'release_candidate_stable_commit'` runs the existing source checks
- **THEN** a stable commit different from the highest RC is refused.

#### Scenario: Qualified index inspection
- **WHEN** `gh run view <stable-release-run-id> --log` inspects an authorized stable promotion
- **THEN** the run copies one qualified RC index without a native build and verifies equal RC, stable and latest digests, or refuses before publication when a prerequisite is missing.


## ADDED Requirements

### Requirement: Qualified promotion evidence

Stable promotion from an RC SHALL require one maintainer-published `lab-qualification.json` asset on that published prerelease. It SHALL bind the repository, source commit, RC tag, index digest, both native manifest digests and successful stopped empty-install and golden-upgrade lab results with SHA-256 evidence hashes. The workflow SHALL verify the RC signature for its release workflow identity and source labels for both native images before publication. Qualification records SHALL contain no credentials or private host paths. They attest maintainer acceptance; they do not replace private runner evidence.

#### Scenario: Qualification refusal
- **WHEN** `python scripts/promote_release_image.py --plan` reads an otherwise valid stable event whose highest RC lacks the qualification asset
- **THEN** it exits with refusal and creates no registry tag.

### Requirement: Promotion operator instructions

Release instructions SHALL explain the qualification record, retained RC version labels, exact digest readback and tagged-workflow limitation. Tooling changes SHALL NOT imply permission to publish stable or deploy.

#### Scenario: Maintainer guidance
- **WHEN** `rg -n 'lab-qualification|APP_VERSION|tagged commit|same digest' docs/releasing.md` runs
- **THEN** the required proof and compatibility limits are explicit.
