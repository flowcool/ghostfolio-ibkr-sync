"""Open deduplicated compatibility notices for official Ghostfolio releases."""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import yaml


class GitHubAPI:
    """Small REST client; never log tokens or upstream response bodies."""

    def __init__(self, token):
        self.token = token

    def request(self, method, path, payload=None):
        request = Request(
            "https://api.github.com/" + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "ghostfolio-ibkr-sync-release-watch",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(f"GitHub {method} {path} returned HTTP {error.code}") from None

    def list_all(self, path):
        result = []
        for page in range(1, 101):
            batch = self.request("GET", f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
            result.extend(batch)
            if len(batch) < 100:
                return result
        raise RuntimeError(f"Pagination limit exceeded for {path}")


def published_at(release):
    return datetime.fromisoformat(release["published_at"].replace("Z", "+00:00"))


def release_marker(upstream, release_id):
    return f"<!-- upstream-release:{upstream}:{release_id} -->"


def notice_body(config, release, previous_tag):
    upstream = config["upstream_repository"]
    tag = release["tag_name"]
    notes = release.get("body") or ""
    hints = [word for word in config["keywords"] if word.casefold() in notes.casefold()]
    # Upstream notes are untrusted data: link to them rather than copying their
    # markup, mentions or instructions into an automatically generated issue.
    release_url = f"https://github.com/{upstream}/releases/tag/{quote(tag, safe='')}"
    compare_url = f"https://github.com/{upstream}/compare/{quote(previous_tag, safe='')}...{quote(tag, safe='')}" if previous_tag else None
    lines = [
        release_marker(upstream, release["id"]),
        "A new stable Ghostfolio release needs a compatibility review.",
        "",
        f"Published: {release['published_at']}",
        f"[Official release notes]({release_url})",
    ]
    if compare_url:
        lines.append(f"[Upstream changes since the previous stable release]({compare_url})")
    lines.extend([
        "",
        "Release-note keyword hints: " + (", ".join(hints) if hints else "none detected"),
        "These are triage hints, not proof of compatibility or incompatibility.",
        "A release without API keywords still needs review.",
        "",
        "Review the contracts this sync relies on:",
        *[f"- [ ] {endpoint}" for endpoint in config["endpoints"]],
        "- [ ] Check authentication, errors and response field changes against upstream source.",
        "- [ ] Add or update offline contract/regression fixtures for relevant changes.",
        "- [ ] Record compatibility evidence and any follow-up work before closing.",
        "",
        "This notice does not upgrade Ghostfolio, deploy the NAS or run against real financial data.",
        "Closing it acknowledges this release review; the watcher will not reopen or duplicate it.",
    ])
    return "\n".join(lines)


def monitor(api, repository, config):
    upstream = config["upstream_repository"]
    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name) for name in [upstream, repository]):
        raise ValueError("Invalid GitHub repository name")
    baseline = api.request("GET", f"repos/{upstream}/releases/tags/{quote(config['first_release'], safe='')}")
    if baseline.get("draft") or baseline.get("prerelease"):
        raise ValueError("The first release must be a published stable release")
    since = published_at(baseline)
    releases = sorted(
        list({r["id"]: r for r in api.list_all(f"repos/{upstream}/releases")
              if not r.get("draft") and not r.get("prerelease")}.values()),
        key=lambda r: (published_at(r), r["id"]),
    )
    if not any(r["id"] == baseline["id"] for r in releases):
        raise RuntimeError("First release missing from upstream release listing")
    # Explicit state=all is essential: closed notices must remain acknowledged.
    issues = api.list_all(f"repos/{repository}/issues?state=all")
    known = {release_marker(upstream, r["id"]) for r in releases if any(
        release_marker(upstream, r["id"]) in (i.get("body") or "")
        for i in issues if "pull_request" not in i
    )}
    pending = [r for r in releases if published_at(r) >= since and release_marker(upstream, r["id"]) not in known]
    if not pending:
        print("No new stable Ghostfolio releases to report")
        return []
    labels = {label["name"] for label in api.list_all(f"repos/{repository}/labels")}
    for label in config["labels"]:
        if label not in labels:
            api.request("POST", f"repos/{repository}/labels", {"name": label, "color": "5319e7"})
    created = []
    for release in pending:
        index = next(i for i, candidate in enumerate(releases) if candidate["id"] == release["id"])
        previous_tag = releases[index - 1]["tag_name"] if index else None
        issue = api.request("POST", f"repos/{repository}/issues", {
            "title": f"Review Ghostfolio {release['tag_name']} compatibility",
            "body": notice_body(config, release, previous_tag),
            "labels": config["labels"],
        })
        created.append(issue["number"])
        print(f"Created compatibility issue #{issue['number']} for Ghostfolio {release['tag_name']}")
    return created


def main():
    config_path = Path(__file__).resolve().parents[1] / ".github/upstream-watch.yml"
    config = yaml.safe_load(config_path.read_text())
    monitor(GitHubAPI(os.environ["GITHUB_TOKEN"]), os.environ["GITHUB_REPOSITORY"], config)


if __name__ == "__main__":
    main()
