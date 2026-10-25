## ADDED Requirements

### Requirement: Legacy qualified RC publication

A maintainer-authorized recovery dispatch on main SHALL permit publication of an older qualified RC without rebuilding. It SHALL require one prepared stable draft with the highest RC source commit, complete release notes, its exact qualified digest and the expected previous latest digest. Before any tag or release write, it SHALL verify qualification, signature, native identities, main ancestry, version absence and unchanged previous stable identity. Existing stable tags, image versions and newer or equal stable releases SHALL refuse this initial-publication path. Tag and release writes SHALL use the repository GITHUB_TOKEN so the older build workflow does not run. The published release SHALL then pass the existing exact-digest promotion checks. Failures after any write attempt SHALL report possible partial state and stop dependent writes without overwrite. Publication SHALL NOT deploy.

#### Scenario: Authorized legacy publication
- **WHEN** `gh run view <recovery-run-id> --log` inspects a maintainer-authorized recovery dispatch
- **THEN** it proves the checks before publication, the actual release response, and stable/latest digests equal to the accepted RC, with no native build.

#### Scenario: Refusal or uncertain write
- **WHEN** `gh run view <recovery-run-id> --log` inspects a recovery with drifted evidence or a failed write
- **THEN** it shows a pre-publication refusal or the exact possible partial phase and performs no dependent publication.
