<p align="center">
  <img src="docs/assets/hero.svg" alt="Ghostfolio IBKR Sync: controlled portfolio synchronization from Interactive Brokers to self-hosted Ghostfolio" width="100%">
</p>

<p align="center">
  <a href="https://github.com/flowcool/ghostfolio-ibkr-sync/releases"><img src="https://img.shields.io/github/v/release/flowcool/ghostfolio-ibkr-sync?display_name=tag&sort=semver" alt="Latest release"></a>
  <a href="https://github.com/flowcool/ghostfolio-ibkr-sync/actions/workflows/docker-publish.yml"><img src="https://github.com/flowcool/ghostfolio-ibkr-sync/actions/workflows/docker-publish.yml/badge.svg" alt="Build and checks"></a>
  <a href="https://github.com/flowcool/ghostfolio-ibkr-sync/security"><img src="https://img.shields.io/badge/security-CodeQL-2ea44f" alt="CodeQL analysis"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT%20NON--AI-5b6f8f" alt="MIT NON-AI License"></a>
</p>

<p align="center"><strong>Your Interactive Brokers portfolio, kept current in self-hosted Ghostfolio.</strong><br>Preview every run. Import additively. Keep financial writes deliberate.</p>

<p align="center"><a href="#quick-start">Quick start</a> · <a href="#what-it-does">What it does</a> · <a href="#safety-first">Safety</a> · <a href="docs/configuration.md">Configuration</a> · <a href="docs/troubleshooting.md">Troubleshooting</a> · <a href="https://github.com/flowcool/ghostfolio-ibkr-sync/releases">Releases</a></p>

## What it does

`ghostfolio-ibkr-sync` reads Interactive Brokers Flex Query reports and synchronizes supported trades, dividends, withholding tax, and base-currency cash into a self-hosted [Ghostfolio](https://ghostfol.io) instance. It runs as a Docker image, supports multiple IBKR sub-accounts, and can run once or on a schedule.

It is useful when manual activity entry has become repetitive or difficult to audit. The connector keeps the source-account identity, checks existing Ghostfolio activities before import, and makes the first run a full simulation by default.

## Key features

| User value | Supported behavior |
| --- | --- |
| **Portfolio synchronization** | Trades, dividend payments, withholding tax, and each account’s ending base-currency cash balance. Multiple IBKR accounts can run sequentially. |
| **Data integrity** | ISIN-to-Yahoo ticker mapping, duplicate detection by source identity and proximity rules, source-account isolation, currency checks, and holdings gates for sells. |
| **Controlled operations** | `DRY_RUN` simulation, explicit `DRY_RUN=false` for writes, fail-closed validation, bounded retries, structured diagnostics, and optional redacted Apprise failure summaries. |
| **Self-hosting** | Docker-only runtime, multi-architecture image (`linux/amd64` and `linux/arm64`), Compose/Portainer examples, and cron scheduling through `CRON`. |
| **Optional review** | Qualified one-to-one activity correction proposals through `ACTIVITY_REVIEW_FILE`; approval is explicit and corrections are never automatic. |

### Deliberate boundaries

Options and FX conversion trades are skipped. Flex Query data covers at most 365 days, so older positions must already exist in Ghostfolio. Stock splits and other corporate actions are outside the sync contract. Imports are additive: the connector does not delete activities, and ordinary runs do not rewrite historical records. See [limitations](#limitations) and the [activity review guide](docs/activity-review.md).

## How it works

```mermaid
flowchart LR
    A[IBKR Flex Query] --> B[Fetch and parse]
    B --> C[ISIN mapping and validation]
    D[Existing Ghostfolio activities] --> E[Deduplication and holdings gates]
    C --> E
    E --> F{DRY_RUN?}
    F -->|yes| G[Preview and diagnostics]
    F -->|false| H[Import activities]
    H --> I[Update base-currency cash]
```

The pipeline reads the existing Ghostfolio activity set before selecting imports. A simulation still authenticates, fetches reports, and evaluates the complete decision. It sends no activity, cash, platform, or correction write.

## Quick start

The fastest safe path is a Docker Compose preview. Prepare these prerequisites:

- Docker Compose, with the repository [`compose.yaml`](compose.yaml).
- Ghostfolio **2.248.0 or newer**, reachable from the Docker network.
- An IBKR account with Flex Web Service enabled.
- One Flex Query per IBKR sub-account, with a 365-day window and the fields listed in the [IBKR setup guide](docs/ibkr-setup.md).
- A private Ghostfolio access token, a valid IANA `TZ`, and a reviewed `mapping.yaml`.

1. Copy the examples and edit the private environment file:

```bash
cp .env.example .env
cp mapping.yaml.example mapping.yaml
chmod 600 .env mapping.yaml
sudo chown 10001:10001 mapping.yaml
```

2. Set the IBKR account and query IDs, Ghostfolio account names, and tokens in `.env`. Remove the unused joint service from `compose.yaml` if you have one account.
3. Validate the resolved Compose model without printing secrets:

```bash
docker compose config --quiet
```

4. Run one account in simulation and inspect the logs:

```bash
docker compose run --rm -e CRON= ibkr-sync-individual
```

5. Back up Ghostfolio. Set `DRY_RUN=false` only after the preview is understood, then run the same command once.
6. For recurring imports, set `CRON_INDIVIDUAL` and `CRON_JOINT` in `.env`, then start the services with `docker compose up -d`. The [configuration reference](docs/configuration.md) covers permissions, scheduling, Portainer deployment, and multi-account details.

The committed [`compose.yaml`](compose.yaml) and [`.env.example`](.env.example) are the canonical onboarding files. They use separate services for sub-accounts and keep credentials outside Git. The image starts with a simulation when `DRY_RUN` is absent or blank. Only `0`, `false`, `no`, or `off` request financial writes. Invalid values fail before HTTP calls. A missing or invalid `TZ` forces simulation. Read [upgrading to 3.0](docs/upgrading-to-3.0.md) before upgrading older installations.

## Docker image

Stable images are published at `ghcr.io/flowcool/ghostfolio-ibkr-sync:latest`. Use a full `:X.Y.Z` tag for a controlled upgrade, or record and pin the matching `@sha256:...` manifest digest. The `:latest` tag follows only the current stable release. A `vX.Y.Z-rc.N` image is a separate prerelease track and never moves `:latest`.

Before an upgrade, record the digest of the image that is actually running. A tag alone can move. Runtime rollback restores the selected image with its existing environment and mounts; it does not undo financial writes. See the [release and rollback procedure](docs/releasing.md).

## Safety first

Financial records can change. Back up Ghostfolio before the first import and before significant upgrades. Container rollback restores the runtime image only; it does not undo activities or cash updates.

- Simulation performs the full read and preview path without financial writes. It still contacts IBKR and Ghostfolio to obtain the evidence.
- Writes require an explicit `DRY_RUN=false`, a valid `TZ`, valid Flex prerequisites, and the normal account, mapping, currency, and holdings checks.
- Imports are additive. The connector never deletes activities during sync. Activity corrections are opt-in, one-to-one, qualified for an exact destination image, and require an explicit `yes` in the generated review file.
- Corporate actions, historical positions outside the 365-day report, options, and unsupported symbols need manual handling.
- Logs can contain financial details. Keep them private. Credentials come from environment variables and are never intended for logs or committed files.

Read [activity correction review](docs/activity-review.md) and [release qualification](docs/releasing.md#activity-review-qualification) before enabling that optional workflow.


## Configuration

The landing page keeps only the settings needed to start. The complete reference covers authentication modes, every environment variable, mapping behavior, retries, notifications, Compose hardening, and one-off execution:

- [Mapping and reconciliation](docs/configuration.md#mapping-and-reconciliation)
- [Configuration reference](docs/configuration.md)
- [IBKR Flex Query setup](docs/ibkr-setup.md)
- [Troubleshooting and exit codes](docs/troubleshooting.md)
- [Upgrade and rollback to 3.0](docs/upgrading-to-3.0.md)
- [Upgrade and rollback to 2.2](docs/upgrading-to-2.2.md)
- [Activity correction review](docs/activity-review.md)
- [Cleanup and separately authorized maintenance](docs/cleanup.md)

### Essential settings

Set the required credentials and target details in `.env`. The [full configuration reference](docs/configuration.md#configuration-reference) lists every variable, default, notification option, review setting, and operational detail.

| Variable | Purpose | Example |
| --- | --- | --- |
| `IBKR_TOKEN` | IBKR Flex Web Service token. | `replace-with-your-ibkr-flex-token` |
| `IBKR_ACCOUNT_IDS` / `IBKR_QUERY_IDS` | Comma-separated account and Flex Query IDs, in matching order. | `U1234567` / `123456` |
| `GHOST_ACCESS_TOKEN` | Recommended Ghostfolio security token. | `replace-with-your-ghostfolio-security-token` |
| `GHOST_HOST` | Ghostfolio base URL reachable by the container. | `http://ghostfolio:3333` |
| `GHOST_ACCOUNT_NAMES` | Target account names, in IBKR account order. | `IBKR Individual` |
| `MAPPING_FILE` | ISIN-to-Yahoo ticker mapping file. | `/app/mapping.yaml` |
| `TZ` | IANA timezone required for writes and scheduling. | `Europe/Paris` |
| `DRY_RUN` | Simulation by default; set `false` deliberately to request writes. | `true` |

Secrets belong in the environment or a private `.env` file with restricted permissions. Do not place them in Compose committed to Git. Use `docker compose config --quiet` for validation; resolved output can expose secrets.

## Limitations

- IBKR Flex reports cover at most 365 days. Enter older positions separately before importing newer sells.
- Options and FX conversion trades are not imported.
- Stock splits, mergers, and other corporate actions are not parsed.
- Yahoo Finance data can be delayed or incomplete for some markets.
- Cash is one ending figure in the account base currency. Ghostfolio and IBKR account currencies must match.
- Normal sync is additive. It does not automatically reconcile later broker corrections.
- The sell guard checks batch net quantity, not a chronological position ledger. A successful buy can remain when a later sell is refused.
- Concurrent runs targeting one Ghostfolio account are unsupported.

See the [detailed limitations and behavior reference](docs/configuration.md) and [troubleshooting](docs/troubleshooting.md).


## Releases and project status

The current stable release is shown by the [GitHub Releases](https://github.com/flowcool/ghostfolio-ibkr-sync/releases) badge and page. Release candidates use a separate `vX.Y.Z-rc.N` tag and image. An RC never moves `:latest`; validate it in both Ghostfolio lab scenarios before stable promotion. Stable releases publish immutable, verified multi-architecture artifacts under the repository’s existing release gates.

- [Release process and rollback](docs/releasing.md)
- [Build and publication guarantees](.github/BUILD.md)
- [Release-note automation policy](docs/release-notes-automation.md)
- [Architecture decision records](docs/adr/README.md)
- [Changelog](CHANGELOG.md)

## Development and contribution

Docker is the supported runtime. Local tests are offline and use synthetic inputs with mocked HTTP. Python 3.14+ with the pinned packages (CI and the container use Python 3.14). For a development checkout:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
# or: scripts/check.sh
```

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening an issue or pull request. Use sanitized logs and synthetic transactions. Never attach a real Flex XML export. Report security issues through [`.github/SECURITY.md`](.github/SECURITY.md).

## Credits and license

Forked from [obol89/ghostfolio-ibkr-sync](https://github.com/obol89/ghostfolio-ibkr-sync), with thanks to its contributors. See [LICENSE](LICENSE) for the inherited **MIT NON-AI License** and its additional restrictions.
