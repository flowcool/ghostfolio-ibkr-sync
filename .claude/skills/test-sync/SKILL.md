---
description: Test the sync script against live data (manual / DRY_RUN); unit tests are in tests/ (pytest)
---

# Test Sync

Live-data checks: the script is stateless and idempotent (dedup on Ghostfolio side). Offline unit tests: `.venv/bin/python -m pytest -q` (see `tests/`).

## Run in existing container (production cron)

```bash
docker exec ghostfolio-ibkr-sync-individual python /app/ibkr_to_ghostfolio.py
```

## Run locally (requires env vars)

```bash
export IBKR_TOKEN=... GHOST_TOKEN=... GHOST_HOST=http://... IBKR_ACCOUNT_IDS=... IBKR_QUERY_IDS=...
python ibkr_to_ghostfolio.py
```

## Dry-run mode (preview without writing)

```bash
DRY_RUN=1 docker exec ghostfolio-ibkr-sync-individual python /app/ibkr_to_ghostfolio.py
# Or locally:
DRY_RUN=1 python ibkr_to_ghostfolio.py
```

## Verify current deployment

```bash
# Check image
docker inspect ghostfolio-ibkr-sync-individual --format '{{.Config.Image}}'

# Last cron logs
docker logs ghostfolio-ibkr-sync-individual --tail 50
```

## Validation approach

Test with real APIs — read first (`GET /api/v1/activities`), then validate import on a test account if possible. The `DRY_RUN=1` mode previews activities without writing.
