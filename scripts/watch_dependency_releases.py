"""Open one deduplicated review issue per new release of a pinned dependency.

Watches the runtime closure pinned in requirements.txt (PyPI) and the
supercronic binary pinned in the Dockerfile (GitHub releases, which Dependabot
does not track). Every stable release newer than the current pin gets an issue
so breaking changes are reviewed before Dependabot proposes the bump.
"""

import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from watch_ghostfolio_releases import GitHubAPI  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LABELS = ["dependency-release"]
# A first run, or a long outage, must not flood the tracker; the rest follow
# on the next daily run.
MAX_NEW_ISSUES_PER_RUN = 10
# Final releases only: pre-, post- and dev releases are not proposed for pins.
STABLE_VERSION = re.compile(r"\d+(\.\d+){0,5}")
PACKAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
PIN = re.compile(r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^\s;#]+)")
SUPERCRONIC_PIN = re.compile(r"^ARG SUPERCRONIC_VERSION=v(?P<version>\S+)$", re.M)
# Changelog links come from untrusted package metadata: keep plain https URLs
# without markup characters, and only for changelog-like labels.
SAFE_URL = re.compile(r"https://[A-Za-z0-9.-]+(/[A-Za-z0-9._~/%#?=&+-]*)?")
CHANGELOG_LABEL = re.compile(r"change|release|history|news", re.I)
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?")


def version_key(version):
    return tuple(int(part) for part in version.split("."))


def read_pins(root=ROOT):
    """Return the watched pins: [{"ecosystem", "name", "version"}]."""
    pins = []
    for line in (root / "requirements.txt").read_text().splitlines():
        match = PIN.match(line.strip())
        if match:
            if not STABLE_VERSION.fullmatch(match["version"]):
                raise ValueError(f"Unsupported pin in requirements.txt: {match['name']}")
            pins.append({"ecosystem": "pypi", "name": match["name"].lower(), "version": match["version"]})
    supercronic = SUPERCRONIC_PIN.search((root / "Dockerfile").read_text())
    if not supercronic or not STABLE_VERSION.fullmatch(supercronic["version"]):
        raise ValueError("SUPERCRONIC_VERSION pin not found in Dockerfile")
    pins.append({"ecosystem": "github", "name": "aptible/supercronic", "version": supercronic["version"]})
    if not pins[:-1]:
        raise ValueError("No pins found in requirements.txt")
    return pins


def fetch_json(url):
    request = Request(url, headers={"Accept": "application/json",
                                    "User-Agent": "ghostfolio-ibkr-sync-dependency-watch"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"GET {url} returned HTTP {error.code}") from None


def pypi_releases(name, fetch=fetch_json):
    """Stable, non-yanked releases of a PyPI project, plus its changelog links."""
    data = fetch(f"https://pypi.org/pypi/{quote(name, safe='')}/json")
    releases = []
    for version, files in (data.get("releases") or {}).items():
        if not STABLE_VERSION.fullmatch(version) or not files or all(f.get("yanked") for f in files):
            continue
        releases.append({"version": version,
                         "published_at": min(f.get("upload_time_iso_8601") or "" for f in files)})
    links = [url for label, url in ((data.get("info") or {}).get("project_urls") or {}).items()
             if isinstance(url, str) and CHANGELOG_LABEL.search(label or "") and SAFE_URL.fullmatch(url)]
    return releases, links[:3]


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
    if pin["ecosystem"] == "pypi":
        return f"https://pypi.org/project/{quote(pin['name'], safe='')}/{quote(version, safe='')}/"
    return f"https://github.com/{pin['name']}/releases/tag/v{quote(version, safe='')}"


def notice_body(pin, release, links):
    current, new = version_key(pin["version"]), version_key(release["version"])
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
        f"- Dependency: `{pin['name']}` ({'PyPI' if pin['ecosystem'] == 'pypi' else 'GitHub release'})",
        f"- Pinned: `{pin['version']}` → released: `{release['version']}` ({level})",
        f"- Published: {published if TIMESTAMP.fullmatch(published) else 'unknown'}",
        f"- Release page: {release_page(pin, release['version'])}",
        *[f"- Changelog: {url}" for url in links],
        "",
        "Review:",
        "- [ ] Read the release notes / changelog for removals, renamed options and behaviour changes.",
        "- [ ] Check whether this sync or the notification worker uses anything that changed.",
        "- [ ] Decide: adopt (Dependabot proposes the bump after its 14-day cooldown; security fixes come at once) or hold, and record why.",
        "",
        "This notice does not change any pin, build or deployment.",
        "Closing it acknowledges the review; the watcher never reopens or duplicates it.",
    ]
    return "\n".join(lines)


def monitor(api, repository, pins, fetch_pypi=pypi_releases, limit=MAX_NEW_ISSUES_PER_RUN):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid GitHub repository name")
    pending = []
    for pin in pins:
        if pin["ecosystem"] == "pypi":
            if not PACKAGE_NAME.fullmatch(pin["name"]):
                raise ValueError("Invalid package name")
            releases, links = fetch_pypi(pin["name"])
        else:
            releases, links = github_releases(api, pin["name"])
        current = version_key(pin["version"])
        newer = {r["version"]: r for r in releases if version_key(r["version"]) > current}
        pending.extend((pin, release, links) for _, release in
                       sorted(newer.items(), key=lambda item: version_key(item[0])))
    if not pending:
        print("No new dependency releases")
        return []
    # Explicit state=all: closed notices stay acknowledged.
    bodies = [i.get("body") or "" for i in api.list_all(f"repos/{repository}/issues?state=all")
              if "pull_request" not in i]
    pending = [p for p in pending if not any(release_marker(p[0], p[1]["version"]) in b for b in bodies)]
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
