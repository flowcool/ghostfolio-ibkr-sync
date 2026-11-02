# Changelog

<a id="unreleased--v300-rc2"></a>

[GitHub Releases](https://github.com/flowcool/ghostfolio-ibkr-sync/releases) owns
the release history, migration notes and published artifacts.

For installations from 2.x, read [Upgrading to 3.0](docs/upgrading-to-3.0.md).
Current behavior and settings are in the [configuration guide](docs/configuration.md).

## Unreleased — minor release

Qualified Flex timestamps now use fixed EST (UTC-05:00) and EDT (UTC-04:00)
offsets. New activities get corrected UTC instants. No stored activity is rewritten.
Unknown qualified tokens fail the account before all financial writes.
Review compares calendar days in configured `TZ` and preserves stored intraday times
on the same day. Historical date repair needs the existing reviewed operation.
Keep unresolved journals intact before rollback. Qualify the exact release digest
in empty and golden labs before activation or stable promotion.

## Deployment example migration

The current checkout defaults to one account. Existing two-service installations
must select `compose.multi-account.yaml` before updating. Pause automatic Git
stack updates until this migration is complete. Preserve the Compose project name
and state paths. See [migration instructions](docs/getting-started.md#existing-two-service-installations).
