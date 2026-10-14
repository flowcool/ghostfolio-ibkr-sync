## 1. Preflight

- [ ] 1.1 Accept `vX.Y.Z-rc.N` prereleases in `release_metadata`; widen `assemble` to the RC version. Check: run the five synthetic events of the "RC validation offline" scenario with `GITHUB_EVENT_PATH` set in a scratch clone.
- [ ] 1.2 Add the stable-follows-RC commit check to the preflight. Check: the scratch repository run of the "Stable commit check" scenario.

## 2. Workflow

- [ ] 2.1 Skip `latest` promotion explicitly for RC tags. Check: `rg -n 'rc' .github/workflows/release-image.yml` and a YAML parse of the file.

## 3. Documentation

- [ ] 3.1 Add the RC section to `docs/releasing.md` (cut, validate, promote, consumer Renovate rule); update README image section and `.github/BUILD.md`. Check: `rg -n 'rc\.' docs/releasing.md README.md .github/BUILD.md`.
- [ ] 3.2 Record the RC channel in ADR 0006. Check: `rg -n 'rc\.' docs/adr/0006-latest-follows-main.md`.
- [ ] 3.3 Verify the consumer Renovate rule on a scratch config with the Renovate local dry run. Check: the dry-run output, recorded in the item note.
