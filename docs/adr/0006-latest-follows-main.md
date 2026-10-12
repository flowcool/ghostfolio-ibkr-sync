# Publish latest from main and leave upgrade control to the operator

Date: 2026-10-12. Status: accepted (existing behavior).

The publishing workflow selects `:latest` only for `main`, including its weekly
rebuild; it is not restricted to tagged releases. A validated `vX.Y.Z` release
also publishes `:X.Y.Z` and `:X.Y`. This gives operators a main-following channel
and version-specific upgrade choices without changing their selected policy.

Container tags, including full versions, are mutable. Pinning an image digest
provides exact artifact selection and a reproducible rollback; a full version is
useful for controlled upgrades but is not an immutable artifact identifier.
Do not silently switch an operator away from `:latest`. Publishing an image does
not deploy it or recreate a running container.

Sources: [Docker image](../../README.md#docker-image),
[build guarantees](../../.github/BUILD.md), and
[publishing workflow](../../.github/workflows/docker-publish.yml).
