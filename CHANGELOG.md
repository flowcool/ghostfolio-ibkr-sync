# Changelog

<a id="unreleased--v300-rc2"></a>

[GitHub Releases](https://github.com/flowcool/ghostfolio-ibkr-sync/releases) owns
the release history, migration notes and published artifacts.

For installations from 2.x, read [Upgrading to 3.0](docs/upgrading-to-3.0.md).
Current behavior and settings are in the [configuration guide](docs/configuration.md).

## Deployment example migration

The current checkout defaults to one account. Existing two-service installations
must select `compose.multi-account.yaml` before updating. Pause automatic Git
stack updates until this migration is complete. Preserve the Compose project name
and state paths. See [migration instructions](docs/getting-started.md#existing-two-service-installations).
