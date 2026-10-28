<p align="center">
  <img src="docs/assets/hero.svg" alt="Ghostfolio IBKR Sync: controlled portfolio synchronization from Interactive Brokers to self-hosted Ghostfolio" width="100%">
</p>

<p align="center">
  <a href="https://github.com/flowcool/ghostfolio-ibkr-sync/releases"><img src="https://img.shields.io/github/v/release/flowcool/ghostfolio-ibkr-sync?display_name=tag&sort=semver" alt="Latest release"></a>
  <a href="https://github.com/flowcool/ghostfolio-ibkr-sync/actions/workflows/docker-publish.yml"><img src="https://github.com/flowcool/ghostfolio-ibkr-sync/actions/workflows/docker-publish.yml/badge.svg" alt="Build and checks"></a>
  <a href="https://github.com/flowcool/ghostfolio-ibkr-sync/security"><img src="https://img.shields.io/badge/security-CodeQL-2ea44f" alt="CodeQL analysis"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT%20NON--AI-5b6f8f" alt="MIT NON-AI License"></a>
</p>

<p align="center"><strong>Your Interactive Brokers portfolio, kept current in self-hosted Ghostfolio.</strong><br>Preview imports. Add new activities. Review corrections or enable a bounded profile.</p>

<p align="center"><a href="#quick-start">Quick start</a> · <a href="#what-it-does">What it does</a> · <a href="#safety-first">Safety</a> · <a href="docs/configuration.md">Configuration</a> · <a href="docs/troubleshooting.md">Troubleshooting</a> · <a href="https://github.com/flowcool/ghostfolio-ibkr-sync/releases">Releases</a></p>

## What it does

Import IBKR trades, dividends, withholding tax and base-currency cash into
self-hosted [Ghostfolio](https://ghostfol.io). Run once or on a Docker schedule.
Use one Ghostfolio target per IBKR account.

## Key features

- Preview imports before you enable writes.
- Check identities, duplicates and holdings.
- Run on amd64 or arm64. Receive optional Apprise notifications.
- Review qualified one-to-one corrections, or enable a bounded reconciliation profile.

### Deliberate boundaries

Options and FX trades are excluded. Handle corporate actions and older history
manually. Unsafe BUY/SELL stay blocked. See [limitations](#limitations).

## How it works

Read Flex reports and Ghostfolio activities. Map securities and check imports.
Simulation shows the proposed result. Live mode imports activities and updates
cash separately. A cash update does not prove that all activities were imported.

## Quick start

Follow [First installation](docs/getting-started.md):

1. Configure IBKR, Ghostfolio and mapping.
2. Set the network and persistent state.
3. Run simulation and review the result.
4. Back up Ghostfolio. Enable imports, then scheduling.

You need Docker Compose, Git, Ghostfolio **2.248.0+**, IBKR Flex credentials,
a Ghostfolio Security Token and a valid IANA `TZ`. Use one Flex query per account.

[compose.yaml](compose.yaml) runs one account.
For two accounts, use [compose.multi-account.yaml](compose.multi-account.yaml).
**Existing two-service installs must switch files before updating.**
Follow the [migration steps](docs/getting-started.md#existing-two-service-installations).
Keep the project name, ENV and state paths. Do not remove orphans without review.

## Docker image

Use `ghcr.io/flowcool/ghostfolio-ibkr-sync:latest` for the stable image.
Pin `@sha256:...` for controlled upgrades. RC tags use `vX.Y.Z-rc.N`.
They never replace `:latest`.

Startup reports `ghostfolio-ibkr-sync version X.Y.Z — commit <12-character SHA>`.
The build sets this metadata. An RC can report the target version before release.
See [GitHub Releases](https://github.com/flowcool/ghostfolio-ibkr-sync/releases).

## Safety first

- Back up before the first import and significant upgrades. Image rollback does not undo writes.
- `DRY_RUN` defaults to simulation. Writes need an explicit false value and valid `TZ`.
  Account, currency, mapping and evidence checks still apply.
- Simulation reads services and maintains local evidence. It sends no financial writes.
- Keep `CORPORATE_ACTION_STATE_FILE` in a private persistent directory.
  Initialize it in simulation. Review the inventory before live mode.
  Missing state, bad permissions or active holds can cause exit 1 in simulation.
- Imports never delete activities. Corrections need exact-image qualification and explicit `yes`.
- Follow recovery after an uncertain write. Do not resend or delete state to clear a hold.
- Keep logs and tokens private. Keep credentials outside Git.
  Use `docker compose config --quiet` to avoid printing secrets.

For blocked trades, read [corporate-action safety](docs/corporate-actions.md).
For corrections, read [activity review](docs/activity-review.md).

## Configuration

- [IBKR Flex fields](docs/ibkr-setup.md)
- [Authentication and ENV](docs/configuration.md)
- [Mapping](docs/configuration.md#mapping-and-reconciliation)
- [Troubleshooting](docs/troubleshooting.md)
- [3.0 upgrade and rollback](docs/upgrading-to-3.0.md)
- [2.2 upgrade and rollback](docs/upgrading-to-2.2.md)
- [Maintenance](docs/maintenance.md) · [Older cleanup links](docs/cleanup.md)

### Essential settings

Use [.env.example](.env.example) for Compose.
See the [ENV reference](docs/configuration.md#configuration-reference) for all settings.
Standalone Docker uses a [separate ENV file](docs/configuration.md#single-account-one-off-run).

## Operational results

`Cycle result` reports success, required action or failure.
Configured notifications repeat required actions after each completed run, including simulation.
Clean success sends no heartbeat.

Check imports, cash, holds and delivery separately.
`sent` confirms transport success, not device receipt.
See [required actions](docs/configuration.md#user-action-required),
[delivery](docs/configuration.md#notification-result) and
[cycle results](docs/configuration.md#cycle-result).

## Corporate-action safety

Include Corporate Actions in Flex, even when empty.
The [guide](docs/corporate-actions.md) covers holds, state loss and evidence retention.
Ordinary reports rotate after 30 days. Required safety evidence stays retained.
Report windows cannot prove lifetime history. Manual acknowledgment cannot release a hold.

### Official effective-date evidence

Follow the [dated-evidence procedure](docs/corporate-actions.md#official-effective-date-evidence).
A date supplies evidence. It does not approve a financial write.

### Native splits, notifications and recovery

See [native evidence and recovery](docs/corporate-actions.md#native-splits-notifications-and-recovery).
Native split evidence needs qualified Ghostfolio **3.91.0+**.
This does not authorize split writes or historical conversion.

## Limitations

- Flex covers at most 365 days. Reports update daily.
  Add older positions before newer sells need them.
- No options, FX trades or automatic corporate-action treatment.
- Account currencies must match. Cash is not converted.
- Holdings checks use net quantities, not chronological balances.
  A successful buy can remain after a later failure.
- No concurrent runs against one target account.
- Yahoo prices and metadata can be delayed or incomplete.

Read the [full limits](docs/configuration.md#limitations) before recovery.

## Releases and project status

[GitHub Releases](https://github.com/flowcool/ghostfolio-ibkr-sync/releases) contains
release history and artifacts. [Changelog](CHANGELOG.md) links there too.

## Development and contribution

See [Contributing](CONTRIBUTING.md) for development, architecture and releases.
Docker is the supported runtime.
Local development requires Python 3.14+ with the pinned packages
(CI and the container use Python 3.14).

## Credits and license

Forked from [obol89/ghostfolio-ibkr-sync](https://github.com/obol89/ghostfolio-ibkr-sync).
See [LICENSE](LICENSE) for the **MIT NON-AI License** and restrictions.
