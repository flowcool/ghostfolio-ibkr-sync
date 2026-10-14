## 1. Preflight

- [ ] 1.1 Accept `vX.Y.Z-rc.N` prereleases in `release_metadata`; widen `assemble` to the RC version. Offline tests in `tests/test_release_image.py` (load the script like `tests/test_release_watch.py`). Check: `.venv/bin/python -m pytest -q tests -k 'release_candidate_metadata'`.
- [ ] 1.2 Add the stable-follows-RC commit check to the preflight as a function of tag-to-commit data, git calls stubbed in tests. Check: `.venv/bin/python -m pytest -q tests -k 'release_candidate_stable_commit'`.

## 2. Workflow

- [x] 2.1 Skip `latest` promotion explicitly for RC tags. Check: `rg -n 'rc' .github/workflows/release-image.yml` and a YAML parse of the file.

## 3. Documentation

- [ ] 3.1 Add the RC section to `docs/releasing.md` (cut, validate, promote; consumer Renovate behavior with its documentation link); update README image section and `.github/BUILD.md`. Check: `rg -n 'rc\.' docs/releasing.md README.md .github/BUILD.md`.
- [ ] 3.2 Record the RC channel in ADR 0006. Check: `rg -n 'rc\.' docs/adr/0006-latest-follows-main.md`.
