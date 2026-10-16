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
import glob
import importlib.util
assert importlib.util.find_spec("pip") is None, "pip must not ship in the image"
print("CPython", platform.python_version(), flush=True)
assert importlib.util.find_spec("ghostfolio_ibkr_sync") is not None
assert not os.path.exists("/app/ibkr_to_ghostfolio.py"), "the legacy launcher must not ship"
assert not glob.glob("/app/*.py"), "no source file may ship in /app"
'
# The installed package, not a mounted source tree, is what the image runs:
# the probe replaces only its __main__.py, and the checks below that must see
# the real program run without the mount.
package_main=$(docker run --rm --entrypoint python "$image" -I -c '
import importlib.util
spec = importlib.util.find_spec("ghostfolio_ibkr_sync")
print(spec.origin.removesuffix("__init__.py") + "__main__.py")')
case "$package_main" in
    */site-packages/ghostfolio_ibkr_sync/__main__.py) ;;
    *) echo "Package is not installed in site-packages: $package_main" >&2; exit 1 ;;
esac
options=(--read-only --network none --cap-drop ALL
    --security-opt no-new-privileges:true --tmpfs /tmp:rw,noexec,nosuid,size=16m,mode=1777
    --mount "type=bind,src=$probe,dst=$package_main,readonly")

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

# Wait for a pattern in a scheduled container's log; fail if it stops first.
wait_for_log() {
    local id=$1 pattern=$2 attempt logs
    for attempt in {1..120}; do
        logs=$(docker logs "$id" 2>&1)
        if grep -q "$pattern" <<< "$logs"; then
            return 0
        fi
        if [ "$(docker inspect -f '{{.State.Running}}' "$id")" != true ]; then
            echo "Scheduled container stopped unexpectedly (waiting for: $pattern)" >&2
            return 1
        fi
        sleep 1
    done
    echo "Scheduled tick did not complete (waiting for: $pattern)" >&2
    return 1
}

# Synthetic payload mounted over the package __main__: proves the entrypoint
# starts `python -m ghostfolio_ibkr_sync` from site-packages under the hardened
# profile, one-off and scheduled.
one_off_output=$(docker run --rm "${options[@]}" "$image")
grep -q 'Synthetic read-only sync passed' <<< "$one_off_output"
scheduled_id=$(docker run -d "${options[@]}" -e 'CRON=* * * * *' "$image")
# A real supercronic tick must run the synthetic Python payload successfully.
wait_for_log "$scheduled_id" 'Synthetic read-only sync passed'
docker rm -f "$scheduled_id" >/dev/null
scheduled_id=''

# Real installed program, no credentials and no network: it must start through
# the entrypoint and stop at configuration validation, one-off and scheduled.
real_options=(--read-only --network none --cap-drop ALL
    --security-opt no-new-privileges:true --tmpfs /tmp:rw,noexec,nosuid,size=16m,mode=1777)
status=0
real_output=$(docker run --rm "${real_options[@]}" "$image" 2>&1) || status=$?
echo "$real_output"
[ "$status" -eq 1 ]
grep -q 'Starting IBKR to Ghostfolio sync' <<< "$real_output"
grep -q 'Missing required environment variables: IBKR_TOKEN' <<< "$real_output"
scheduled_id=$(docker run -d "${real_options[@]}" -e 'CRON=* * * * *' "$image")
wait_for_log "$scheduled_id" 'Missing required environment variables: IBKR_TOKEN'
scheduled_logs=$(docker logs "$scheduled_id" 2>&1)
echo "$scheduled_logs"
grep -q 'Starting IBKR to Ghostfolio sync' <<< "$scheduled_logs"
grep -q 'python -m ghostfolio_ibkr_sync' <<< "$scheduled_logs"

# Notification worker with its production argv, from a directory that holds no
# source: -I leaves the current directory and PYTHON* variables out of module
# lookup, so only the installed package can answer. Malformed stdin must exit 10
# before Apprise loads, with an empty environment (no credentials) and no network.
worker_output=$(docker run --rm -w / "${real_options[@]}" --entrypoint python "$image" -c '
import subprocess
import sys
from ghostfolio_ibkr_sync.notify import _notify_worker_argv
argv = _notify_worker_argv()
assert argv == [sys.executable, "-I", "-m", "ghostfolio_ibkr_sync", "--notify-worker"], argv
proc = subprocess.run(argv, input=b"not json", env={}, capture_output=True, timeout=30)
assert proc.returncode == 10, (proc.returncode, proc.stderr)
assert proc.stdout == b"" and proc.stderr == b"", (proc.stdout, proc.stderr)
print("Installed notification worker exit 10 passed", flush=True)
')
grep -q 'Installed notification worker exit 10 passed' <<< "$worker_output"
echo 'Read-only one-off, scheduled and installed worker modes passed'
