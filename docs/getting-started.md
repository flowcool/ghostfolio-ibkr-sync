# First installation

Use this guide for one IBKR account.
You need Git, Docker Compose and reachable Ghostfolio **2.248.0+**.
Native split evidence has [separate requirements](corporate-actions.md).
You do not need to enable it for setup.

## 1. Obtain and configure the files

```bash
git clone --depth 1 https://github.com/flowcool/ghostfolio-ibkr-sync.git
cd ghostfolio-ibkr-sync
cp .env.example .env
cp mapping.yaml.example mapping.yaml
chmod 600 .env mapping.yaml
```

This checkout supports stable 3.3.0+ ENV settings.
Keep guides, Compose and ENV examples from the same revision.
For an older release archive, use its own guide.
The image `ghcr.io/flowcool/ghostfolio-ibkr-sync:latest` tracks stable releases.
Pin a qualified digest for controlled upgrades.

Configure these files:

- **IBKR:** enable Flex Web Service. Create one query for this account only.
  Follow the [field checklist](ibkr-setup.md#2-create-a-flex-query).
  Select XML, 365 days, the required time format and Corporate Actions.
- **Ghostfolio:** get a Security Token. Create the target account.
  Its currency must match the IBKR base currency.
  See [authentication and accounts](configuration.md#ghostfolio-setup).
- **`.env`:** set the tokens, individual account/query IDs and target account name.
  Set an IANA `TZ`, such as `Europe/Paris`. Keep `DRY_RUN=true`.
- **`mapping.yaml`:** edit it before changing ownership.
  Examples are optional. Keep the `symbol_mapping` structure.
  Unmapped ISINs use the IBKR symbol. Verify the destination before live import.
  See [mapping](configuration.md#mapping-and-reconciliation).

### Choose the existing Docker network

Find the Ghostfolio container's network.
Replace `<ghostfolio-container>` with its name:

```bash
docker inspect <ghostfolio-container> --format '{{json .NetworkSettings.Networks}}'
```

In `.env`, set:

- `GHOST_DOCKER_NETWORK`: the existing network name, such as `your-stack_default`.
- `GHOST_HOST`: a service name or DNS alias on that network, with its port.
  The default `http://ghostfolio:3333` needs a working `ghostfolio` alias.

Use HTTPS outside the trusted Docker network.
Compose does not create the network or attach Ghostfolio.
An empty network cannot reach the server.
Use the network managed by the Ghostfolio deployment.
A manual `docker network connect` attachment can disappear when the container is recreated.

### Prepare private persistent state

After editing the mapping, set its final ownership and create the state directory:

```bash
mkdir -p state/individual
chmod 700 state/individual
sudo chown 10001:10001 mapping.yaml state/individual
```

The image runs as `10001:10001`.
Mapping uses mode `0600` and a read-only mount.
State uses mode `0700` and a writable mount at `/state`.
Later mapping edits can need sudo.
Only your operator user must own and read `.env`.
Back up state, companion files and evidence together.
Never delete state to clear a hold.

Validate the model without printing resolved secrets:

```bash
docker compose config --quiet
```

## 2. Run and review a simulation

Before the first scheduled start, run:

```bash
docker compose run --rm -e DRY_RUN=true -e CRON= ibkr-sync-individual
```

For an existing installation, pause the scheduled service before a manual run:

```bash
docker compose stop ibkr-sync-individual
```

For two accounts, use `docker compose -f compose.multi-account.yaml stop` before
manual previews.
Do not run two processes against the same account.
Simulation logs in and reads reports.
A valid report initializes state. Simulation can retain or rotate local evidence.
It sends no activity, correction, cash or platform write.

Review the private logs and the final `Cycle result`:

- **Proposed:** check account, security, currency, quantity, fees and cash.
  Preview does not prove server acceptance.
- **Skipped:** check proximity matches manually. Proximity does not prove identity.
  Identity and duplicate checks prevent reimport.
- **Held:** read each required action and check its file.
  State errors, missing evidence and active holds can cause exit 1 in simulation.
- **Result:** clean success needs no action.
  Otherwise, complete the named check or fix the failure.
  A cash update does not release held activities.

See [results](configuration.md#cycle-result) or [troubleshooting](troubleshooting.md).
Apprise can notify required actions in simulation.
Clean success sends no heartbeat. `sent` confirms transport, not device receipt.

Reports do not prove lifetime history.
Add older positions before newer sells need them.
Handle corporate events manually. BUY/SELL can stay blocked until proof is complete.
Do not force a write through acknowledgment, state deletion or invented mapping.

## 3. Enable one import, then scheduling

Back up Ghostfolio with a verified procedure.
Keep the image digest, ENV, mapping and state.
Review the preview and resolve unsafe holds before enabling writes.

For one deliberately enabled run, with the schedule still stopped:

```bash
docker compose run --rm -e DRY_RUN=false -e CRON= ibkr-sync-individual
```

After the first import, [add missing currency pairs](configuration.md#4-add-currencies)
and run [Gather All Data](configuration.md#5-after-your-first-import).
Check the result. A successful buy can remain if a later sell fails.
Do not resend an uncertain operation. Follow its recovery guide and keep journals.
Image rollback does not undo financial writes.

For recurring imports, set `DRY_RUN=false` and the five-field numeric
`CRON_INDIVIDUAL` in `.env`, then start the scheduled service:

```bash
docker compose up -d
```

Missing or invalid `TZ` forces simulation. Other guards still apply.
Before using an older image, set `DRY_RUN=true` explicitly.
An absent value can select live mode on older images.
See [upgrade and rollback](upgrading-to-3.0.md).

## Multiple accounts

Use the root-level [compose.multi-account.yaml](../compose.multi-account.yaml).
Add these values to your private `.env` for the second account:

```dotenv
IBKR_ACCOUNT_IDS_JOINT=U7654321
IBKR_QUERY_IDS_JOINT=654321
GHOST_ACCOUNT_NAME_JOINT=IBKR Joint
CRON_JOINT=5 6 * * *
```

Use one verified Flex query and one Ghostfolio target per account.
Prepare `state/joint`: mode `0700`, owner `10001:10001`.
Never share state directories between services.
Both services use the same `.env` `DRY_RUN` value.
Schedules are staggered. Both root-level examples use the same mapping and state paths.

Set `COMPOSE_FILE=compose.multi-account.yaml` in private `.env`.
Plain Compose commands will then include both services.
If you select files explicitly, use `-f compose.multi-account.yaml` on **every** command:

```bash
docker compose -f compose.multi-account.yaml config --quiet
docker compose -f compose.multi-account.yaml run --rm -e DRY_RUN=true -e CRON= ibkr-sync-individual
docker compose -f compose.multi-account.yaml run --rm -e DRY_RUN=true -e CRON= ibkr-sync-joint
```

### Existing two-service installations

**Switch to `compose.multi-account.yaml` before updating.**
The default `compose.yaml` now has one service.

1. Pause Portainer Git auto-update, if used.
2. Keep the project/stack name, working directory, `.env`, service names and state paths.
3. Select the multi-account file. Check both services in the resolved model.
4. For Portainer, verify that your version can change the stack's Compose path.
   Otherwise, plan the stack migration before updating.
   Keep the stack name, bind paths and state.
   `.env` file selection does not control Portainer.
5. After updating, run `docker compose -f compose.multi-account.yaml ps --all`.
   Check both services and their intended image.

A missing joint service can remain as an orphan, then disappear on recreation.
Do not remove orphans without review.
Do not switch files while a financial result is uncertain.
A normal pull or automatic update cannot perform this migration.
No financial data conversion is needed.

## Further operations

[Configuration](configuration.md) · [Activity review](activity-review.md) · [Maintenance](maintenance.md)
