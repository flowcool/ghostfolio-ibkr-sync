#!/bin/bash
# Isolated synthetic checks only. Never select an existing container or network.
set -euo pipefail
image=${1:?Pass the locally built test image}
probe=$(realpath "$(dirname "$0")/../tests/container_sync_probe.py")
# Hold the mapping file inside an operator-owned temp dir. The file itself is
# chowned to 10001 below, but unlinking it needs write access on the parent dir
# (which the operator owns, non-sticky), not file ownership. So cleanup needs no
# sudo and cannot hang on a sudo prompt inside the EXIT trap.
mapping_dir=$(mktemp -d)
mapping="$mapping_dir/mapping.yaml"
scheduled_id=''
cleanup() {
    if [ -n "$scheduled_id" ]; then
        docker rm -f "$scheduled_id" >/dev/null
    fi
    rm -rf "$mapping_dir"
}
trap cleanup EXIT
docker run --rm --read-only --network none --cap-drop ALL \
    --security-opt no-new-privileges:true --entrypoint python "$image" -c '
import os
import platform
import sys
assert platform.python_implementation() == "CPython"
assert sys.version_info[:2] == (3, 14), sys.version
print("CPython", platform.python_version(), flush=True)
for name in ("/app/ibkr_to_ghostfolio.py", "/app/entrypoint.sh"):
    assert os.stat(name).st_uid == 0
    assert not os.stat(name).st_mode & 0o222
    assert not os.access(name, os.W_OK)
'
options=(--read-only --network none --cap-drop ALL
    --security-opt no-new-privileges:true --tmpfs /tmp:rw,noexec,nosuid,size=16m,mode=1777
    --mount "type=bind,src=$probe,dst=/app/ibkr_to_ghostfolio.py,readonly")

# Owner-only mapping access must work with the documented hardened profile,
# without DAC capabilities or a live NAS.
printf 'symbol_mapping:\n  TEST: TEST\n' > "$mapping"
chmod 0600 "$mapping"
sudo chown 10001:10001 "$mapping"
mapping_output=$(docker run --rm "${options[@]}" \
    --mount "type=bind,src=$mapping,dst=/tmp/mapping.yaml,readonly" \
    -e MAPPING_FILE=/tmp/mapping.yaml --entrypoint python "$image" -c '
import os
from pathlib import Path
import yaml
assert os.getuid() == 10001 and os.getgid() == 10001
assert yaml.safe_load(Path(os.environ["MAPPING_FILE"]).read_text()) == {
    "symbol_mapping": {"TEST": "TEST"}}
print("Owner-only mapping bind mount passed", flush=True)
')
grep -q 'Owner-only mapping bind mount passed' <<< "$mapping_output"

one_off_output=$(docker run --rm "${options[@]}" "$image")
grep -q 'Synthetic read-only sync passed' <<< "$one_off_output"
scheduled_id=$(docker run -d "${options[@]}" -e 'CRON=* * * * *' "$image")
# A real supercronic tick must run the synthetic Python payload successfully.
for attempt in {1..120}; do
    scheduled_output=$(docker logs "$scheduled_id" 2>&1)
    if grep -q 'Synthetic read-only sync passed' <<< "$scheduled_output"; then
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
