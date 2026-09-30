#!/bin/bash
set -e

echo "ghostfolio-ibkr-sync version ${APP_VERSION:-dev}"

if [ -n "$CRON" ]; then
    echo "Running with cron schedule: $CRON"
    echo "$CRON python /app/ibkr_to_ghostfolio.py" > /app/crontab
    exec supercronic /app/crontab
else
    echo "Running once (no CRON schedule set)"
    exec python /app/ibkr_to_ghostfolio.py
fi
