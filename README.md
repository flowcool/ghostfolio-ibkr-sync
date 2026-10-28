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

Import supported Interactive Brokers trades, dividends, withholding tax and
base-currency cash into self-hosted [Ghostfolio](https://ghostfol.io). Run once
or on a schedule with Docker. Each IBKR account has its own Ghostfolio target.

## Key features

- Preview the complete selection before enabling financial writes.
- Keep imports additive, with source identity, duplicate and holdings checks.
- Run hardened Docker images on amd64 or arm64, with optional Apprise notices.
- Review exact one-to-one corrections through a separate qualified opt-in flow.

### Deliberate boundaries

Options and FX trades are excluded. Corporate actions and older history need
manual handling. Detection holds unsafe BUY/SELL; it never performs an automatic
split or historical repair. See [limitations](#limitations).

## How it works

Read IBKR Flex reports and existing Ghostfolio activities. Map securities, check
identity and holdings, then select imports. Simulation previews the result.
Live runs import activities and independently update base-currency cash.
Cash success does not prove that every activity was imported.

## Quick start

Use the [first-install guide](docs/getting-started.md) for one complete path:

1. Obtain the files, prepare the Flex query and Ghostfolio target, and review mapping.
2. Choose the existing Ghostfolio network and prepare private persistent state.
3. Run simulation. Review proposed, skipped and held events and required actions.
4. Back up Ghostfolio. Explicitly enable one import, then scheduling.

You need Docker Compose, reachable Ghostfolio **2.248.0 or newer**, an IBKR Flex
Web Service token, one query per source account, a Ghostfolio Security Token and
a valid IANA `TZ`. The guide includes file acquisition with Git.

The canonical [compose.yaml](compose.yaml) starts one account. For more accounts,
use [compose.multi-account.yaml](compose.multi-account.yaml) and its
[migration instructions](docs/getting-started.md#existing-two-service-installations).
Existing two-service users must select that file before updating their deployment.
Keep the same project identity, ENV and state paths. Do not remove orphans blindly.

## Docker image

Use `ghcr.io/flowcool/ghostfolio-ibkr-sync:latest` for the current stable image.
For controlled upgrades, record and pin its immutable `@sha256:...` digest.
Release candidates use separate `vX.Y.Z-rc.N` tags and never move `:latest`.

New images report `ghostfolio-ibkr-sync version X.Y.Z — commit <12-character SHA>`.
The build sets version metadata automatically. An RC can report its target
software version before stable publication. Published artifacts and upgrade notes
are in [GitHub Releases](https://github.com/flowcool/ghostfolio-ibkr-sync/releases).

## Safety first

Back up Ghostfolio before the first import and significant upgrades. Runtime
rollback never undoes financial writes.

- `DRY_RUN` defaults to simulation. Only explicit false values request writes.
  A valid `TZ` and all account, currency, mapping and evidence guards still apply.
- Simulation authenticates and reads services. It can initialize and maintain
  local evidence, but sends no activity, cash, platform or correction write.
- Set `CORPORATE_ACTION_STATE_FILE` in a private persistent mounted directory.
  Initialize it in simulation and review its bounded inventory before live mode.
  Missing or unwritable state and active holds can make simulation exit 1.
- Imports never delete activities. Optional corrections require exact-image
  qualification and explicit `yes`. Pending or uncertain writes require their
  recovery procedure. Do not resend automatically or delete state to clear a hold.
- Logs contain financial details. Keep them private. Keep tokens in private ENV,
  outside Git. Validate Compose with `docker compose config --quiet` to avoid
  printing resolved credentials.

Read [corporate-action safety and recovery](docs/corporate-actions.md) and
[activity correction review](docs/activity-review.md) when those conditions apply.

## Configuration

Start with [installation](docs/getting-started.md). Use these guides as needed:

- [IBKR Flex setup and required fields](docs/ibkr-setup.md)
- [Authentication, ENV and operations](docs/configuration.md)
- [Mapping and reconciliation](docs/configuration.md#mapping-and-reconciliation)
- [Troubleshooting and exit codes](docs/troubleshooting.md)
- [Upgrade and rollback to 3.0](docs/upgrading-to-3.0.md)
- [Upgrade and rollback to 2.2](docs/upgrading-to-2.2.md)
- [Maintenance index](docs/maintenance.md) and [existing cleanup entry point](docs/cleanup.md)

### Essential settings

The [ENV reference](docs/configuration.md#configuration-reference) lists required
credentials, account/query IDs, target names, mapping, state, `TZ` and `DRY_RUN`.
Compose uses the suffixed values from [.env.example](.env.example).
Autonomous Docker runs use a [separate container ENV file](docs/configuration.md#single-account-one-off-run).

## Operational results

`Cycle result` distinguishes success, success with user action required, and
failure. Required actions repeat once per completed run in one configured
notification, including simulation. Clean success sends no heartbeat.

Cash, imports, holds and notification delivery remain separate outcomes.
`sent` means transport success, not device receipt. Read
[User action required](docs/configuration.md#user-action-required),
[Notification result](docs/configuration.md#notification-result) and
[Cycle result](docs/configuration.md#cycle-result).

## Corporate-action safety

Select Corporate Actions in the Flex query, including an empty section.
The [full guide](docs/corporate-actions.md) covers holds, retained private reports,
fixed 30-day ordinary-report rotation, safety exceptions and state loss.
Available windows cannot prove lifetime history. Manual acknowledgment cannot release a hold.

### Official effective-date evidence

Use the [dated-evidence procedure](docs/corporate-actions.md#official-effective-date-evidence).
It supplies a fact, never financial approval.

### Native splits, notifications and recovery

See [native evidence and recovery](docs/corporate-actions.md#native-splits-notifications-and-recovery).
A qualified stable Ghostfolio **3.91.0+** is a separate prerequisite for native
split evidence. This does not authorize native split writes or historical conversion.

## Limitations

- Flex reports cover at most 365 days and update daily. Older positions must
  already exist before newer sells need them.
- Options, FX conversion trades and automatic corporate-action treatment are excluded.
- Account currencies must match; cash is not converted.
- The holdings gate checks net quantity, not chronological balances. Buy and sell
  requests are separate; successful buys can remain after a later failure.
- Concurrent runs against one target account are unsupported.
- Yahoo prices and metadata can be delayed or incomplete.

See the [full limits](docs/configuration.md#limitations) before historical recovery.

## Releases and project status

[GitHub Releases](https://github.com/flowcool/ghostfolio-ibkr-sync/releases) owns
release history and artifacts. [Changelog](CHANGELOG.md) remains an entry point.

## Development and contribution

Use [Contributing](CONTRIBUTING.md) for offline development, architecture decisions,
release qualification and publication procedures. Docker is the supported runtime.

## Credits and license

Forked from [obol89/ghostfolio-ibkr-sync](https://github.com/obol89/ghostfolio-ibkr-sync).
See [LICENSE](LICENSE) for the inherited **MIT NON-AI License** and restrictions.
