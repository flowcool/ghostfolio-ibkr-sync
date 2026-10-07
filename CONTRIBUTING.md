# Contributing

Thanks for helping make IBKR imports more reliable. Keep changes focused and preserve the small runtime dependency set (`requests` and `pyyaml`).

## Report a problem

Use [GitHub Issues](https://github.com/flowcool/ghostfolio-ibkr-sync/issues) for bugs and feature ideas. Include the sync version from the startup log, your Ghostfolio version, how you run the tool, expected behavior and a minimal reproduction.

Use synthetic transactions and sanitized logs. Remove tokens, account identifiers, private URLs and portfolio details. Never attach a real Flex XML export. Report credential leaks and security vulnerabilities through the [private reporting process](.github/SECURITY.md).

For a feature, explain the missing workflow, its impact and the smallest useful outcome. Search existing issues first. Discuss import semantics before proposing automatic edits or deletions of financial records.

## Develop and verify

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

CI and the container use Python 3.12. Tests use synthetic inputs and mocked HTTP; they require neither credentials nor running IBKR/Ghostfolio services. Do not point automated tests or cleanup tools at a live portfolio. Add regression coverage for a logic change, including account isolation and repeated runs when relevant.

Open one pull request per concern and describe the problem, resulting behavior and verification. Required CI checks apply to documentation changes too. See [build and release guarantees](.github/BUILD.md) for image publishing and rollback. A compatibility notice from the upstream release watcher is a request for review, not a compatibility guarantee.

## License

Contributions follow the repository's inherited [MIT NON-AI License](LICENSE), including its additional restrictions.
