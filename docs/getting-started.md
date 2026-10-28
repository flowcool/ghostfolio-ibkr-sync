# First installation

This guide uses one IBKR account. Use Docker Compose and a reachable self-hosted
Ghostfolio **2.248.0 or newer**. Git is needed for the file acquisition below.
Native split evidence has a separate qualified-version gate; ordinary installation
does not require enabling it. Read [corporate-action safety](corporate-actions.md)
when a hold names an event or missing evidence.

## 1. Obtain and configure the files

```bash
git clone --depth 1 https://github.com/flowcool/ghostfolio-ibkr-sync.git
cd ghostfolio-ibkr-sync
cp .env.example .env
cp mapping.yaml.example mapping.yaml
chmod 600 .env mapping.yaml
```

These commands obtain the current documentation checkout. Its examples use the
ENV interface supported by stable 3.3.0 and newer. Keep the guides, Compose and
ENV examples from one checkout together. If you choose an older release archive,
follow that archive's guide; do not mix examples from different revisions.
The image `ghcr.io/flowcool/ghostfolio-ibkr-sync:latest` follows stable releases.
For a controlled upgrade, record and pin a qualified image digest.

Prepare these values before editing `.env`:

- Enable IBKR Flex Web Service. Create one query selecting only this source
  account. Use the [single required-field checklist](ibkr-setup.md#2-create-a-flex-query).
  Use XML, a 365-day window, the required time format and Corporate Actions.
- Obtain a Ghostfolio Security Token for `GHOST_ACCESS_TOKEN`. Create the target
  account in Ghostfolio, with its currency equal to the IBKR base currency.
  See [authentication and accounts](configuration.md#ghostfolio-setup).
- Set `IBKR_TOKEN`, the individual source account/query IDs and target account name
  in `.env`. Set an IANA `TZ`, for example `Europe/Paris`. Keep `DRY_RUN=true`.
- Review and edit `mapping.yaml` now. Example entries are optional; retain the
  `symbol_mapping` structure. An unmapped ISIN falls back to the IBKR symbol;
  verify the destination security before live import. See [mapping](configuration.md#mapping-and-reconciliation).

### Choose the existing Docker network

Find the network containing your Ghostfolio container. For an existing local
Docker deployment, replace `<ghostfolio-container>` with its container name:

```bash
docker inspect <ghostfolio-container> --format '{{json .NetworkSettings.Networks}}'
```

Set `GHOST_DOCKER_NETWORK` in `.env` to that network's actual name, such as
`your-stack_default`. Set `GHOST_HOST` to a service name or DNS alias available
on that network, with the correct port. The default `http://ghostfolio:3333`
works only when `ghostfolio` resolves there. Use HTTPS when traffic leaves the
trusted Docker network.

Compose references an external network; it does not create or attach Ghostfolio.
Creating an empty network alone will not make the server reachable. Prefer the
network managed by Ghostfolio's deployment. A manual `docker network connect`
attachment can disappear when that deployment recreates the container.

### Prepare private persistent state

After editing the mapping, set its final ownership and create the state directory:

```bash
mkdir -p state/individual
chmod 700 state/individual
sudo chown 10001:10001 mapping.yaml state/individual
```

The image runs as UID/GID `10001:10001`. Mapping stays mode `0600` and read-only
in the container. State stays mode `0700`, writable by that user, at `/state`.
Later host edits of the mapping can require sudo. Keep `.env` owned and readable
only by your operator user. Back up the state directory with its companions and
evidence; never delete it to clear a hold.

Validate the model without printing resolved secrets:

```bash
docker compose config --quiet
```

## 2. Run and review a simulation

Before the first scheduled start, run:

```bash
docker compose run --rm -e DRY_RUN=true -e CRON= ibkr-sync-individual
```

For an existing installation, pause the scheduled service before a manual run.
Do not run two connector processes against the same account at once.
Simulation still logs in and reads reports. It initializes corporate state after
valid source acquisition and can retain or rotate local evidence. It sends no
activity, correction, cash or platform write.

Review the private logs and the final `Cycle result`:

- **Proposed:** inspect the simulated imports and cash, including the destination
  account, security, currency, quantity and fees. Preview cannot prove server acceptance.
- **Skipped:** existing identities and supported duplicate checks avoid reimport.
  A proximity skip can require manual checking; it does not prove event identity.
- **Held:** inspect each required action and configured file. State or evidence
  problems and active corporate holds can cause exit 1 even in simulation.
- **Result:** clean success needs no intervention. Success with user action
  required still needs the named check. Failure needs the stated resolution.
  Cash success does not prove that held activities were imported.

Use [operational results](configuration.md#cycle-result) and
[troubleshooting](troubleshooting.md) for the reason and safe next step. Required
actions can notify in simulation when Apprise is configured. Clean success sends
no heartbeat. A `sent` delivery status is transport success, not device receipt.

Available reports cover bounded history, not lifetime completeness. Add older
positions separately before newer sells require them. Corporate events remain
manual and can hold BUY/SELL until evidence proves safety. Do not acknowledge,
delete state or invent a mapping to force a financial operation.

## 3. Enable one import, then scheduling

Back up Ghostfolio with your deployment's verified backup procedure. Keep the
current image digest, ENV, mapping and state for recovery. Enable writes only
after understanding the preview and resolving unsafe holds.

For one deliberately enabled run, with the schedule still stopped:

```bash
docker compose run --rm -e DRY_RUN=false -e CRON= ibkr-sync-individual
```

Review the observed result. Imports are additive; a buy can remain if a later sell
fails. Do not resend an uncertain operation automatically. Follow its recovery
guide and keep journals. Restoring an image never undoes financial writes.

For recurring imports, set `DRY_RUN=false` and the five-field numeric
`CRON_INDIVIDUAL` in `.env`, then start the scheduled service:

```bash
docker compose up -d
```

Missing or invalid `TZ` still forces simulation. Other guards remain active.
For old-image rollback, set `DRY_RUN=true` explicitly before preview: older
images can interpret an absent value as live mode. See [upgrade and rollback](upgrading-to-3.0.md).

## Multiple accounts

Use the root-level [compose.multi-account.yaml](../compose.multi-account.yaml).
Add these values to your private `.env` for the second account:

```dotenv
IBKR_ACCOUNT_IDS_JOINT=U7654321
IBKR_QUERY_IDS_JOINT=654321
GHOST_ACCOUNT_NAME_JOINT=IBKR Joint
CRON_JOINT=5 6 * * *
```

Create and qualify one Flex query and one distinct Ghostfolio target per account.
Prepare `state/joint` with mode `0700`, owned by `10001:10001`, as above. Never
share one state directory between services. Both services use the same `DRY_RUN`
value from `.env`; schedules are staggered to reduce overlap. Root-level examples
resolve the same mapping and state paths.

Use `-f compose.multi-account.yaml` on **every** Compose command for this setup:

```bash
docker compose -f compose.multi-account.yaml config --quiet
docker compose -f compose.multi-account.yaml run --rm -e DRY_RUN=true -e CRON= ibkr-sync-individual
docker compose -f compose.multi-account.yaml run --rm -e DRY_RUN=true -e CRON= ibkr-sync-joint
```

### Existing two-service installations

Before updating a checkout or Git-backed Portainer stack, select
`compose.multi-account.yaml` instead of the now single-account `compose.yaml`.
Retain the existing Compose project/stack name, working directory, `.env`, service
names and state paths. Check both services in the resolved model before recreating
anything. In Portainer, change the stack's Compose file selection and retain its
existing bind-mount layout; do not recreate the stack under another name.
An omitted joint service can remain as an orphan and disappear on a later recreate.
Do not remove orphans blindly or switch files while a financial run is uncertain.
This file-selection step is a deployment migration, not a financial conversion.

## Further operations

Use [configuration](configuration.md) for autonomous Docker runs, settings and
notifications. Use [activity review](activity-review.md) only for qualified,
explicit corrections, and [maintenance](maintenance.md) for historical procedures.
