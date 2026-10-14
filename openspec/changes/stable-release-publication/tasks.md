# Tasks

## 1. Native validation

- [x] 1.1 Move `docker-publish.yml` container checks to native amd64/arm64 runners; retain weekly scans, remove publication, update BUILD guarantees. Verify `gh run view <PR-run-id> --log`: both isolated runtime checks/scans pass, no publishing.

## 2. Stable publication

- [x] 2.1 Add `release-image.yml`, `scripts/release_image.py` and `scripts/verify_release_image.py` using the design's sibling mechanisms. Deliver metadata/ancestry, registry, configuration/manifest and latest guards. Verify `gh run view <release-run-id> --log` scenarios; real publication requires explicit operator authorization.

## 3. Operator migration

- [x] 3.1 Update README, BUILD, releasing guide and ADR 0006 coherently. Verify the spec's operator-guidance command shows frozen aliases, next-release cutover, security releases and digest recovery.
