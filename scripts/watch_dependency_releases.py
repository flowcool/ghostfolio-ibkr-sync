"""Open deduplicated review issues for the pinned Supercronic binary.

Python dependency updates belong to Renovate. Supercronic requires a manual
version bump together with both architecture checksums in the Dockerfile.
"""

import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from watch_ghostfolio_releases import GitHubAPI  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LABELS = ["dependency-release"]
# A first run, or a long outage, must not flood the tracker; the rest follow
# on the next daily run.
MAX_NEW_ISSUES_PER_RUN = 10
# Final releases only: pre-, post- and dev releases are not proposed for pins.
STABLE_VERSION = re.compile(r"\d+(\.\d+){0,5}")
MARKER = re.compile(r"<!-- dependency-release:(?P<ecosystem>[a-z]+):(?P<name>[^:\s]+):(?P<version>\d+(\.\d+)*) -->")
SUPERCRONIC_PIN = re.compile(r"^ARG SUPERCRONIC_VERSION=v(?P<version>\S+)$", re.M)
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?")


def version_key(version):
    """Comparable key; trailing zeros dropped so 2.34.2.0 equals 2.34.2 (PEP 440)."""
    parts = [int(part) for part in version.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def read_pins(root=ROOT):
    """Return the watched pins: [{"ecosystem", "name", "version"}]."""
    supercronic = SUPERCRONIC_PIN.search((root / "Dockerfile").read_text())
    if not supercronic or not STABLE_VERSION.fullmatch(supercronic["version"]):
        raise ValueError("SUPERCRONIC_VERSION pin not found in Dockerfile")
    return [{"ecosystem": "github", "name": "aptible/supercronic", "version": supercronic["version"]}]


def github_releases(api, repository):
    releases = []
    for release in api.list_all(f"repos/{repository}/releases"):
        version = (release.get("tag_name") or "").removeprefix("v")
        if release.get("draft") or release.get("prerelease") or not STABLE_VERSION.fullmatch(version):
            continue
        releases.append({"version": version, "published_at": release.get("published_at") or ""})
    return releases, []


def release_marker(pin, version):
    return f"<!-- dependency-release:{pin['ecosystem']}:{pin['name']}:{version} -->"


def release_page(pin, version):
    return f"https://github.com/{pin['name']}/releases/tag/v{quote(version, safe='')}"


def notice_body(pin, release, links):
    current, new = version_key(pin["version"]) + (0, 0), version_key(release["version"]) + (0, 0)
    if new[0] != current[0]:
        level = "major version change: breaking changes are likely"
    elif new[:2] != current[:2]:
        level = "minor version change"
    else:
        level = "patch version change"
    published = release.get("published_at") or ""
    lines = [
        release_marker(pin, release["version"]),
        "A new release of a pinned dependency needs a breaking-change review before it is adopted.",
        "",
        f"- Dependency: `{pin['name']}` (GitHub release)",
        f"- Pinned: `{pin['version']}` → released: `{release['version']}` ({level})",
        f"- Published: {published if TIMESTAMP.fullmatch(published) else 'unknown'}",
        f"- Release page: {release_page(pin, release['version'])}",
        *[f"- Changelog: {url}" for url in links],
        "",
        "Review:",
        "- [ ] Read the release notes / changelog for removals, renamed options and behaviour changes.",
        "- [ ] Check whether the scheduler uses anything that changed.",
        "- [ ] Decide: adopt (update SUPERCRONIC_VERSION and both architecture SHA256 pins together in a reviewed PR) or hold, and record why.",
        "",
        "This notice does not change any pin, build or deployment.",
        "Closing it acknowledges the review; the watcher never reopens or duplicates it.",
    ]
    return "\n".join(lines)


def monitor(api, repository, pins, limit=MAX_NEW_ISSUES_PER_RUN):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid GitHub repository name")
    pending = []
    for pin in pins:
        # Ignore Python and unrelated binaries even if a caller supplies them.
        if (pin["ecosystem"], pin["name"]) != ("github", "aptible/supercronic"):
            continue
        releases, links = github_releases(api, pin["name"])
        current = version_key(pin["version"])
        # Keyed by version_key: equivalent spellings (3.11, 3.11.0) get one issue.
        newer = {version_key(r["version"]): r for r in releases if version_key(r["version"]) > current}
        pending.extend((pin, newer[key], links) for key in sorted(newer))
    if not pending:
        print("No new dependency releases")
        return []
    # Explicit state=all: closed notices stay acknowledged.
    bodies = [i.get("body") or "" for i in api.list_all(f"repos/{repository}/issues?state=all")
              if "pull_request" not in i]
    # Compared by version_key so a marker written as 2.35 also covers 2.35.0.
    seen = {(m["ecosystem"], m["name"], version_key(m["version"])) for b in bodies for m in MARKER.finditer(b)}
    pending = [p for p in pending
               if (p[0]["ecosystem"], p[0]["name"], version_key(p[1]["version"])) not in seen]
    if not pending:
        print("Every new dependency release already has a review issue")
        return []
    labels = {label["name"] for label in api.list_all(f"repos/{repository}/labels")}
    for label in LABELS:
        if label not in labels:
            api.request("POST", f"repos/{repository}/labels", {"name": label, "color": "c5def5"})
    created = []
    for pin, release, links in pending[:limit]:
        issue = api.request("POST", f"repos/{repository}/issues", {
            "title": f"Review {pin['name']} {release['version']} (pinned {pin['version']})",
            "body": notice_body(pin, release, links),
            "labels": LABELS,
        })
        created.append(issue["number"])
        print(f"Created review issue #{issue['number']} for {pin['name']} {release['version']}")
    if len(pending) > limit:
        print(f"{len(pending) - limit} more release(s) left for the next run")
    return created


def main():
    monitor(GitHubAPI(os.environ["GITHUB_TOKEN"]), os.environ["GITHUB_REPOSITORY"], read_pins())


if __name__ == "__main__":
    main()
