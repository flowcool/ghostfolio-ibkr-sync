# Contributing

Thanks for helping make IBKR imports more reliable. Keep changes focused and preserve the small runtime dependency set (`requests` and `pyyaml` for the sync; `apprise` only in the notification worker).

## Report a problem

Use [GitHub Issues](https://github.com/flowcool/ghostfolio-ibkr-sync/issues) for bugs and feature ideas. Include the sync version from the startup log, your Ghostfolio version, how you run the tool, expected behavior and a minimal reproduction.

Use synthetic transactions and sanitized logs. Remove tokens, account identifiers, private URLs and portfolio details. Never attach a real Flex XML export. Report credential leaks and security vulnerabilities through the [private reporting process](.github/SECURITY.md).

For a feature, explain the missing workflow, its impact and the smallest useful outcome. Search existing issues first. Discuss import semantics before proposing automatic edits or deletions of financial records.

## Develop and verify

The sync is the typed Python package `ghostfolio_ibkr_sync`, run only in Docker with `python -m ghostfolio_ibkr_sync`; there is no single-file launcher. Keep the functional style and strict application typing, and put new code in the module of its concern.

The local Python commands below are only for development and tests. They are not a supported sync execution interface.

```bash
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements-dev.txt
.venv/bin/python -m pytest -q
scripts/check.sh   # Ruff, strict mypy and pytest, as in CI
```

CI and the container use Python 3.14. Tests use synthetic inputs and mocked HTTP; they require neither credentials nor running IBKR/Ghostfolio services. Do not point automated tests or cleanup tools at a live portfolio. Add regression coverage for a logic change, including account isolation and repeated runs when relevant.

Open one pull request per concern and describe the problem, resulting behavior and verification. Required CI checks apply to documentation changes too. See [build and release guarantees](.github/BUILD.md) for image publishing and rollback. A compatibility notice from the upstream release watcher is a request for review, not a compatibility guarantee.

## Scope and lab gates

This project owns connector code, specifications, lab tests, PRs and releases.
Infra owns managed production deployment, image pins, schedules, host files and
production secrets. Finish connector delivery with a qualified immutable image
and its evidence. Route deployment work to Infra. A release does not approve a
production deployment or a Ghostfolio financial operation.

Before merging, test the PR image in both empty first-install and golden-copy
upgrade labs when the change affects:

- Financial logic, deduplication or activity identity.
- Ghostfolio authentication, transport or writes.
- State or journal formats.
- A major dependency or base image.

Other PRs need CI only for the lab gate. Pullfrog is the sole PR reviewer for
changes beyond documentation. Require a completed review of the final head and
resolve actionable threads. Docs-only PRs need CI only. Keep all other required
checks green. Ignore CodeRabbit and the known sticky `pullfrog-approval` status.

Retain the tested image identity, source commit, inputs, results and stopped-lab
proof. Reserve shared labs before use. Keep credentials separate from production
and retain containers, logs and evidence. Stop and verify both owned instances
after use. Lab work uses standing authority. Broker login, production access,
financial operations and stable publication keep their separate approvals.

Every release passes both scenarios on its exact digest. Promote that digest
without rebuilding. Reuse pre-merge proof only when the digest is identical.
Follow the [release process](docs/releasing.md). Infra owns the shared lab runner
and its canonical runbook in `flowcool/mylittlemess`, at
`docs/runbooks/ghostfolio-lab.md`. Report runner defects to Infra. Keep connector
behavior and fixture work here.

## Maintainer reference

- [Build and publication guarantees](.github/BUILD.md)
- [Release process, exact-image qualification and rollback](docs/releasing.md)
- [Historical release-note investigation](docs/release-notes-automation.md)
- [Architecture decisions](docs/adr/README.md)

Qualification and publication are separate from permission to deploy or write
financial data. Lab acceptance needs `LOG_LEVEL=DEBUG` for the bounded
`LAB_EVIDENCE` records. Keep raw financial evidence private.

## License

Contributions follow the repository's inherited [MIT NON-AI License](LICENSE), including its additional restrictions.
