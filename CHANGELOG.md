# Changelog

<a id="unreleased--v300-rc2"></a>

[GitHub Releases](https://github.com/flowcool/ghostfolio-ibkr-sync/releases) owns
the release history, migration notes and published artifacts.

For installations from 2.x, read [Upgrading to 3.0](docs/upgrading-to-3.0.md).
Current behavior and settings are in the [configuration guide](docs/configuration.md).

## Unreleased — v4.3.0

Dividend coverage and representation limits now use informational blocks and counts. They request no manual correction or required-action reminder.

Qualified Flex timestamps now use fixed EST (UTC-05:00) and EDT (UTC-04:00)
offsets. New activities get corrected UTC instants. No stored activity is rewritten.
Unknown qualified tokens fail the account before all financial writes.
Review compares calendar days in configured `TZ` and preserves stored intraday times
on the same day. Historical date repair needs the existing reviewed operation.
Keep unresolved journals intact before rollback. Qualify the exact release digest
in empty and golden labs before activation or stable promotion.

Activity correction PUTs now carry the resolved effective ISO4217 currency. A
null stored activity currency uses the proven profile currency. Unresolved
currency evidence holds the correction and sends no PUT. Pending review journals
never resend a null currency.

Each run now applies all eligible approved activity corrections without a count
cap. The fixed inter-correction delay remains 28 seconds. The measured maximum
background chain was 18.19 seconds; D includes a 1.5x margin. Stable promotion
requires PASS in both labs on the exact RC digest. Exact readback remains the
gate between PUTs. The first failed or uncertain correction stops the whole
financial run. A pending journal also blocks every account on later runs, even
if its destination account is no longer configured. Preserve journal v3 and
later approvals. No request is resent.

No ENV setting can lower the delay or add a count cap. No run duration limit is
added. Keep scheduled writers exclusive. Qualification covers connector behavior.
Record the observed Ghostfolio version as information. A destination version or
image change does not invalidate qualification. A longer background chain needs
a higher delay in a new connector release.

## Deployment example migration

The current checkout defaults to one account. Existing two-service installations
must select `compose.multi-account.yaml` before updating. Pause automatic Git
stack updates until this migration is complete. Preserve the Compose project name
and state paths. See [migration instructions](docs/getting-started.md#existing-two-service-installations).
