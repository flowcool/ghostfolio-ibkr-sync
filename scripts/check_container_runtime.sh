#!/bin/bash
# Isolated synthetic checks only. Never select an existing container or network.
set -euo pipefail
image=${1:?Pass the locally built test image}
probe=$(realpath "$(dirname "$0")/../tests/container_sync_probe.py")
scheduled_id=''
cleanup() {
    if [ -n "$scheduled_id" ]; then
        docker rm -f "$scheduled_id" >/dev/null
    fi
}
trap cleanup EXIT
docker run --rm --read-only --network none --cap-drop ALL \
    --security-opt no-new-privileges:true --entrypoint python "$image" -c '
import os
for name in ("/app/ibkr_to_ghostfolio.py", "/app/entrypoint.sh"):
    assert os.stat(name).st_uid == 0
    assert not os.stat(name).st_mode & 0o222
    assert not os.access(name, os.W_OK)
'
options=(--read-only --network none --cap-drop ALL
    --security-opt no-new-privileges:true --tmpfs /tmp:rw,noexec,nosuid,size=16m,mode=1777
    --mount "type=bind,src=$probe,dst=/app/ibkr_to_ghostfolio.py,readonly")

docker run --rm "${options[@]}" "$image" | grep -q 'Synthetic read-only sync passed'
scheduled_id=$(docker run -d "${options[@]}" -e 'CRON=* * * * *' "$image")
# A real supercronic tick must run the synthetic Python payload successfully.
for attempt in {1..75}; do
    if docker logs "$scheduled_id" 2>&1 | grep -q 'Synthetic read-only sync passed'; then
        echo 'Read-only one-off and scheduled modes passed'
        exit 0
    fi
    if [ "$(docker inspect -f '{{.State.Running}}' "$scheduled_id")" != true ]; then
        echo 'Synthetic scheduled container stopped unexpectedly' >&2
        exit 1
    fi
    sleep 1
done
echo 'Synthetic scheduled tick did not complete' >&2
exit 1
