#!/bin/bash
# Isolated synthetic checks only. Never select an existing container or network.
set -euo pipefail
image=${1:?Pass the locally built test image}
probe=$(realpath "$(dirname "$0")/../tests/container_sync_probe.py")
# Inspect the immutable image configuration, without runtime ENV overrides.
identity=$(python3 - "$image" "$(dirname "$0")" <<'PY_IDENTITY'
import json
import os
import subprocess
import sys
sys.path.insert(0, sys.argv[2])
from release_image import verify_image_identity
image = json.loads(subprocess.check_output(["docker", "image", "inspect", sys.argv[1]], timeout=30))[0]
config = image["Config"]
labels = config.get("Labels") or {}
env = dict(item.split("=", 1) for item in config.get("Env", []))
version = os.environ.get("RELEASE_APP_VERSION") or labels.get("org.opencontainers.image.version")
revision = os.environ.get("RELEASE_REVISION") or labels.get("org.opencontainers.image.revision")
if version or revision:
    source = labels.get("org.opencontainers.image.source", "")
    prefix = "https://github.com/"
    assert source.startswith(prefix), "Release source label required"
    verify_image_identity({"config": config, "architecture": image["Architecture"], "os": image["Os"]},
                          "v" + (version or ""), revision, source.removeprefix(prefix), image["Architecture"])
    print(f"ghostfolio-ibkr-sync version {version} — commit {revision[:12]}")
else:
    assert env.get("APP_VERSION") == "dev" and env.get("APP_REVISION") == "unknown", "Release identity missing"
    print("ghostfolio-ibkr-sync version dev — commit unknown")
PY_IDENTITY
)
echo "Verified image identity: $identity"
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
assert not os.path.exists("/build"), "the build tree must not ship"
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
grep -Fq "$identity" <<< "$one_off_output"
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
grep -Fq "[INFO] $identity" <<< "$real_output"
grep -q 'Missing required environment variables: IBKR_TOKEN' <<< "$real_output"
scheduled_id=$(docker run -d "${real_options[@]}" -e 'CRON=* * * * *' "$image")
wait_for_log "$scheduled_id" 'Missing required environment variables: IBKR_TOKEN'
scheduled_logs=$(docker logs "$scheduled_id" 2>&1)
echo "$scheduled_logs"
grep -q 'Starting IBKR to Ghostfolio sync' <<< "$scheduled_logs"
grep -Fq "[INFO] $identity" <<< "$scheduled_logs"
grep -q 'python -m ghostfolio_ibkr_sync' <<< "$scheduled_logs"

# Keep actual scheduled application streams separate. Supercronic lifecycle
# records can share a stream, but must not wrap application timestamp/level.
docker logs "$scheduled_id" > "$mapping_dir/scheduled.stdout" 2> "$mapping_dir/scheduled.stderr"
python3 - "$mapping_dir/scheduled.stdout" "$mapping_dir/scheduled.stderr" <<'PY_STREAMS'
import re
import sys
from pathlib import Path
stdout, stderr = [Path(name).read_text() for name in sys.argv[1:]]
pattern = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d \[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\] ")
assert stdout.count("Starting IBKR to Ghostfolio sync") == 1, stdout
assert "Starting IBKR to Ghostfolio sync" not in stderr
assert "Missing required environment variables: IBKR_TOKEN" in stderr
assert "Missing required environment variables: IBKR_TOKEN" not in stdout
for stream, allowed in ((stdout, {"DEBUG", "INFO"}), (stderr, {"WARNING", "ERROR", "CRITICAL"})):
    for line in stream.splitlines():
        if match := pattern.match(line):
            assert match[1] in allowed, line
        assert not ("channel=" in line and re.search(r"\[(DEBUG|INFO|WARNING|ERROR)\]", line)), line
print("Scheduled application streams and native framing passed")
PY_STREAMS

# Exercise the installed CLI with synthetic work at every level. No network,
# credentials, financial action or alternate logging implementation is used.
docker run --rm "${real_options[@]}" --entrypoint python "$image" -c '
import logging
from ghostfolio_ibkr_sync import __main__ as cli
from ghostfolio_ibkr_sync.ibkr import log_lab_evidence
import os
os.environ["LOG_LEVEL"] = "DEBUG"
def synthetic():
    for level in (10, 20, 30, 40, 50):
        logging.getLogger("probe").log(level, "STREAM_PROBE_%s", logging.getLevelName(level))
    log_lab_evidence("window", {"escaped": "one\ntwo"})
    return 0
cli.main = synthetic
raise SystemExit(cli.run())
' > "$mapping_dir/direct.stdout" 2> "$mapping_dir/direct.stderr"
python3 - "$mapping_dir/direct.stdout" "$mapping_dir/direct.stderr" <<'PY_DIRECT'
import json
import sys
from pathlib import Path
stdout, stderr = [Path(name).read_text() for name in sys.argv[1:]]
for name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
    selected, other = (stdout, stderr) if name in ("DEBUG", "INFO") else (stderr, stdout)
    assert selected.count("STREAM_PROBE_" + name) == 1
    assert "STREAM_PROBE_" + name not in other
lines = [line for line in stdout.splitlines() if "LAB_EVIDENCE " in line]
assert len(lines) == 1 and "[DEBUG] LAB_EVIDENCE " in lines[0]
assert json.loads(lines[0].split("LAB_EVIDENCE ", 1)[1]) == {"kind": "window", "value": {"escaped": "one\ntwo"}}
print("Installed CLI levels and LAB_EVIDENCE streams passed")
PY_DIRECT

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
