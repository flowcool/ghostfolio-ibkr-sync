"""Fail-closed release and registry guards; version tags are single publication."""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests


STABLE_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
RC_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-rc\.([1-9][0-9]*)")


def release_identity(tag, commit):
    """Derive immutable software identity from an exact release tag and Git commit."""
    match = STABLE_TAG.fullmatch(tag) or RC_TAG.fullmatch(tag)
    if not match or not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("Exact release tag and full source commit required")
    return ".".join(match.group(1, 2, 3)), commit


def verify_image_identity(config, tag, commit, repository, arch, allow_legacy=False):
    """Verify runtime and OCI identity before publication; allow exact legacy RCs only on promotion."""
    version, revision = release_identity(tag, commit)
    image_config = config.get("config", {})
    labels = image_config.get("Labels", {})
    if (config.get("architecture") != arch or config.get("os") != "linux"
            or labels.get("org.opencontainers.image.revision") != revision
            or labels.get("org.opencontainers.image.source") != "https://github.com/" + repository):
        raise RuntimeError("Native source identity mismatch")
    runtime = {}
    for entry in image_config.get("Env", []):
        key, separator, value = entry.partition("=")
        if key in ("APP_VERSION", "APP_REVISION"):
            if not separator or key in runtime:
                raise RuntimeError("Ambiguous runtime image identity")
            runtime[key] = value
    label_version = labels.get("org.opencontainers.image.version")
    if (runtime.get("APP_VERSION") == version and runtime.get("APP_REVISION") == revision
            and label_version == version):
        return "target"
    if (allow_legacy and RC_TAG.fullmatch(tag) and runtime.get("APP_VERSION") == tag
            and "APP_REVISION" not in runtime and label_version == tag):
        return "legacy"
    raise RuntimeError("Runtime and OCI image identity mismatch")


def release_metadata(event):
    release = event.get("release", {})
    tag = release.get("tag_name", "")
    prerelease = release.get("prerelease")
    if (event.get("action") != "published" or release.get("draft") is not False
            or not isinstance(tag, str)
            or not ((prerelease is False and STABLE_TAG.fullmatch(tag))
                    or (prerelease is True and RC_TAG.fullmatch(tag)))):
        raise RuntimeError("A published stable vX.Y.Z release or vX.Y.Z-rc.N prerelease is required")
    return tag, tag[1:]


def stable_follows_release_candidate(tag, tag_commits, stable_commit):
    """A stable vX.Y.Z must sit on the commit of its highest vX.Y.Z-rc.N, when one exists."""
    if not STABLE_TAG.fullmatch(tag):
        return
    best = None
    for name in tag_commits:
        match = RC_TAG.fullmatch(name)
        if match and name.startswith(tag + "-rc.") and (best is None or int(match.group(4)) > best[0]):
            best = (int(match.group(4)), name)
    if best and tag_commits[best[1]] != stable_commit:
        raise RuntimeError(f"Stable tag {tag} must point to the commit of {best[1]}")


def release_candidate_commits(tag):
    """Map each vX.Y.Z-rc.* tag of a stable tag to its commit; the git wrapper for the pure check."""
    names = subprocess.check_output(["git", "tag", "--list", tag + "-rc.*"], text=True, timeout=15).split()
    return {name: subprocess.check_output(["git", "rev-parse", name + "^{commit}"], text=True,
                                          timeout=15).strip() for name in names}


def registry_version_absent(repository, tag, username, password):
    """Only an authenticated missing manifest or repository allows initial publication."""
    if not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", repository):
        raise RuntimeError("Invalid release repository")
    with requests.Session() as session:
        session.trust_env = False
        response = session.get("https://ghcr.io/token", params={"service": "ghcr.io",
            "scope": f"repository:{repository}:pull"}, auth=(username, password),
            timeout=(10, 30), allow_redirects=False)
        print(f"Registry token endpoint HTTP {response.status_code}", file=sys.stderr)
        if response.status_code != 200:
            raise RuntimeError("Registry authorization failed")
        token = response.json().get("token")
        if not isinstance(token, str) or not token or any(char.isspace() for char in token):
            raise RuntimeError("Registry authorization failed")
        response = session.get(f"https://ghcr.io/v2/{repository}/manifests/{tag}",
            headers={"Authorization": "Bearer " + token,
                "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"},
            timeout=(10, 30), allow_redirects=False)
        print(f"Registry version manifest HTTP {response.status_code}", file=sys.stderr)
        if response.status_code == 200:
            raise RuntimeError("Version image already exists; publication refused")
        body = response.json()
        errors = body.get("errors", []) if isinstance(body, dict) else []
        if response.status_code != 404 or not isinstance(errors, list) or not errors or any(
                not isinstance(error, dict) or error.get("code") not in ("MANIFEST_UNKNOWN", "NAME_UNKNOWN") for error in errors):
            raise RuntimeError("Registry absence could not be proven")


def registry_login(username, password):
    """Authenticate before builds without reading a package that may not exist yet."""
    with requests.Session() as session:
        session.trust_env = False
        response = session.get("https://ghcr.io/token", params={"service": "ghcr.io"},
            auth=(username, password), timeout=(10, 30), allow_redirects=False)
        print(f"Registry login token endpoint HTTP {response.status_code}", file=sys.stderr)
        if response.status_code != 200:
            raise RuntimeError("Registry authorization failed")
        token = response.json().get("token")
        if not isinstance(token, str) or not token or any(char.isspace() for char in token):
            raise RuntimeError("Registry authorization failed")
        response = session.get("https://ghcr.io/v2/",
            headers={"Authorization": "Bearer " + token}, timeout=(10, 30), allow_redirects=False)
        print(f"Registry login API HTTP {response.status_code}", file=sys.stderr)
        if response.status_code != 200:
            raise RuntimeError("Registry authorization failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", action="store_true")
    parser.add_argument("--registry-login", action="store_true")
    args = parser.parse_args()
    phase = "release metadata"
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        tag, version = release_metadata(event)
        phase = "release Git ancestry and tag"
        subprocess.run(["git", "merge-base", "--is-ancestor", "HEAD", "origin/main"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        # Checkout must resolve this release tag, not an arbitrary workflow ref.
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, timeout=15).strip()
        tagged = subprocess.check_output(["git", "rev-parse", tag + "^{commit}"], text=True, timeout=15).strip()
        if head != tagged:
            raise RuntimeError("Release checkout does not match tag")
        app_version, revision = release_identity(tag, head)
        if STABLE_TAG.fullmatch(tag):
            stable_follows_release_candidate(tag, release_candidate_commits(tag), tagged)
        print(f"Release {tag}: version={version}, commit={head}, ancestor of origin/main")
        if args.registry_login:
            phase = "registry login"
            registry_login(os.environ["GITHUB_ACTOR"], os.environ["GH_TOKEN"])
        if args.registry:
            phase = "registry authorization and version absence"
            registry_version_absent(os.environ["GITHUB_REPOSITORY"].lower(), version,
                                    os.environ["GITHUB_ACTOR"], os.environ["GH_TOKEN"])
            print(f"Authenticated version absence confirmed: {version}")
        phase = "workflow output"
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"tag={tag}\nversion={version}\napp_version={app_version}\nrevision={revision}\n")
    except Exception:
        raise SystemExit(f"Release preflight failed at {phase}; version publication refused") from None


if __name__ == "__main__":
    main()
