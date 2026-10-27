#!/bin/bash
set -e

revision=${APP_REVISION:-unknown}
if [[ ! "$revision" =~ ^[0-9a-f]{40}$ ]]; then revision=unknown; fi
printf 'ghostfolio-ibkr-sync version %s — commit %s\n' "${APP_VERSION:-dev}" "${revision:0:12}"

if [ -n "$CRON" ]; then
    # Five numeric cron fields only; never interpolate an environment command.
    if [[ ! "$CRON" =~ ^[0-9*/,-]+([[:blank:]][0-9*/,-]+){4}$ ]]; then
        echo 'Invalid CRON: expected five numeric schedule fields' >&2
        exit 1
    fi
    if ! crontab_path=$(
        umask 077
        mktemp /tmp/ibkr-crontab.XXXXXX 2>/dev/null
    ); then
        echo 'Could not create runtime crontab' >&2
        exit 1
    fi
    printf '%s python -m ghostfolio_ibkr_sync\n' "$CRON" > "$crontab_path"
    if ! supercronic -test "$crontab_path" > /dev/null 2>&1; then
        echo 'Invalid CRON: schedule validation failed' >&2
        exit 1
    fi
    echo 'Running with validated cron schedule'
    exec supercronic -passthrough-logs -split-logs "$crontab_path"
else
    echo "Running once (no CRON schedule set)"
    exec python -m ghostfolio_ibkr_sync
fi
