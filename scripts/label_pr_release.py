"""Label a pull request for release notes from its conventional title.

Advisory only: never fails the PR. Warns when a breaking or compat PR has no
filled "Release impact" section.
"""

import json
import os
import re
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

TITLE = re.compile(r"^(?P<type>[a-z]+)(\([^)]*\))?(?P<bang>!)?:\s")
TYPE_LABELS = {
    "feat": "feature",
    "fix": "fix",
    "docs": "documentation",
    "chore": "maintenance",
    "refactor": "maintenance",
    "test": "maintenance",
    "ci": "maintenance",
    "build": "maintenance",
}
LABEL_COLORS = {
    "breaking-change": "b60205",
    "compat": "d93f0b",
    "feature": "0e8a16",
    "fix": "1d76db",
    "documentation": "0075ca",
    "maintenance": "cfd3d7",
    "skip-release-notes": "ffffff",
}
IMPACT_LABELS = {"breaking-change", "compat"}
IMPACT_SECTION = re.compile(r"^## Release impact\s*\n(?P<body>.*?)(?=^## |\Z)", re.M | re.S)
PLACEHOLDER = re.compile(r"<!--.*?-->|[\s\-*_]|none|n/a", re.I | re.S)


def labels_for_title(title):
    """Return the release-notes labels implied by a conventional PR title."""
    match = TITLE.match(title or "")
    if not match:
        return set()
    labels = set()
    if match.group("type") in TYPE_LABELS:
        labels.add(TYPE_LABELS[match.group("type")])
    if match.group("bang"):
        labels.add("breaking-change")
    return labels


def impact_section_filled(body):
    """True when the Release impact section holds real text, not just a template."""
    match = IMPACT_SECTION.search(body or "")
    if not match:
        return False
    text = re.sub(r"\[[ xX]\]", "", match.group("body"))
    return bool(PLACEHOLDER.sub("", text))


def api(token, method, path, payload=None):
    request = Request(
        "https://api.github.com/" + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "ghostfolio-ibkr-sync-release-labels",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    event = json.load(open(os.environ["GITHUB_EVENT_PATH"]))
    pr = event["pull_request"]
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    current = {label["name"] for label in pr["labels"]}
    wanted = labels_for_title(pr["title"]) - current
    if "dependencies" in current:
        wanted.discard("maintenance")
    try:
        for name in sorted(wanted):
            try:
                api(token, "POST", f"repos/{repo}/labels", {"name": name, "color": LABEL_COLORS[name]})
            except HTTPError as error:
                if error.code != 422:  # 422 = label already exists
                    raise
        if wanted:
            api(token, "POST", f"repos/{repo}/issues/{pr['number']}/labels", {"labels": sorted(wanted)})
    except HTTPError as error:
        # Fork and Dependabot PRs get a read-only token; labeling is best effort.
        print(f"::warning::could not label PR (HTTP {error.code}); add labels by hand")
    if (current | wanted) & IMPACT_LABELS and not impact_section_filled(pr.get("body")):
        print("::warning::breaking-change/compat PR needs a filled 'Release impact' section "
              "(bump, migration, rollback) before release notes are written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
