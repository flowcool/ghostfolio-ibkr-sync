# Tasks

All requirement references below name the delta in `specs/release-publication/spec.md`. Keep implementation in one child of the owning change item. Release publication and exact-candidate lab acceptance belong to the later release child.

## 1. Automatic image and startup identity

- [ ] 1.1 Deliver “Automatic target software identity” and “Consistent startup software identity”, including metadata derivation/refusal, both build calls, both startup paths and local fallback. Update `scripts/release_image.py`, `.github/workflows/release-image.yml`, `Dockerfile`, `entrypoint.sh`, `ghostfolio_ibkr_sync/app.py`, `scripts/check_container_runtime.sh`, relevant existing runtime/metadata tests, `README.md`, `docs/configuration.md` and `.github/BUILD.md`. Document target-version meaning in the same slice. Verify with `.venv/bin/python -m pytest -q tests/test_release_image.py tests/test_entrypoint.py tests/test_logging.py` and `bash scripts/check_container_runtime.sh "$IMAGE"` against an isolated local release image built with matching version/revision arguments and OCI labels. Expected: exact identity at startup, matching configuration, rejected malformed release identity, and unchanged cron/log semantics. Add no tests of workflow YAML or contributor tooling.

## 2. Qualified promotion and compatibility

- [ ] 2.1 Deliver “Qualified promotion evidence” and “Promotion operator instructions”. Update `scripts/promote_release_image.py` and, only if necessary for the shared verification call, `scripts/recover_release_image.py`. Extend existing release metadata/identity contract cases in `tests/test_release_image.py` with isolated native configurations. Update `docs/releasing.md` for new target identity, exact legacy recovery and tagged-workflow limits. Verify with `.venv/bin/python -m pytest -q tests/test_release_image.py -k release_identity`; expect complete new and original legacy forms to pass, and mismatched version/revision, mixed forms and missing metadata to refuse before any write. Finish with `bash scripts/check.sh` and the documented maintainer-guidance `rg` command from the delta. Preserve all existing signature, qualification, immutable-version and exact-digest checks.

After these slices pass, archive the change in the final implementation commit. Record source acceptance once in the implementation owner. Do not publish or deploy through these tasks.
