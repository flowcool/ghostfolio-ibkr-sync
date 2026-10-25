"""Publish a prepared legacy-RC release with the qualified bytes, without a build."""
import json
import os
from pathlib import Path
import re
import subprocess

import promote_release_image as promotion
from release_image import (STABLE_TAG, release_candidate_commits,
                           registry_version_absent)


def api(*args):
    return json.loads(promotion.output("gh", "api", *args))


def recover():
    progress = {"phase": "recovery authority", "publication_attempted": False}
    root = Path.cwd()
    try:
        if (os.environ["GITHUB_EVENT_NAME"] != "workflow_dispatch"
                or os.environ["GITHUB_REF"] != "refs/heads/main"):
            raise RuntimeError("Recovery requires an explicit dispatch on main")
        repository = os.environ["GITHUB_REPOSITORY"].lower()
        tag = os.environ["RECOVERY_TAG"]
        expected = os.environ["RECOVERY_DIGEST"]
        previous = os.environ["RECOVERY_PREVIOUS_DIGEST"]
        if (not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", repository)
                or not STABLE_TAG.fullmatch(tag)
                or not promotion.DIGEST.fullmatch(expected)
                or not promotion.DIGEST.fullmatch(previous)):
            raise RuntimeError("Invalid recovery identity")
        commits = release_candidate_commits(tag)
        candidates = [n for n in commits if promotion.RC_TAG.fullmatch(n)]
        candidate = max(candidates, key=lambda n: int(promotion.RC_TAG.fullmatch(n).group(4)))
        commit = commits[candidate]
        subprocess.run(["git", "merge-base", "--is-ancestor", commit, "origin/main"], check=True, timeout=15)
        if promotion.output("git", "tag", "--list", tag).strip():
            raise RuntimeError("Recovery requires an unpublished stable tag")
        records = api(f"repos/{repository}/releases?per_page=20")
        drafts = [r for r in records if r.get("tag_name") == tag]
        if len(drafts) != 1:
            raise RuntimeError("One prepared draft is required")
        draft = drafts[0]
        if (draft.get("draft") is not True or draft.get("prerelease") is not False
                or draft.get("published_at") is not None
                or draft.get("target_commitish") != commit or not draft.get("body")):
            raise RuntimeError("Draft source or state mismatch")
        previous_release = api(f"repos/{repository}/releases/latest")
        previous_tag = previous_release.get("tag_name", "")
        if (not STABLE_TAG.fullmatch(previous_tag)
                or tuple(map(int, previous_tag[1:].split("."))) >= tuple(map(int, tag[1:].split(".")))):
            raise RuntimeError("Recovery cannot replace a newer or equal stable release")
        progress["phase"] = "qualification and rollback verification"
        record = promotion.candidate_qualification(repository, candidate, commit)
        if record["digest"] != expected:
            raise RuntimeError("Qualified digest differs from the authorized digest")
        image = "ghcr.io/" + repository
        promotion.same_digest(image + ":latest", previous)
        registry_version_absent(repository, tag[1:], os.environ["GITHUB_ACTOR"], os.environ["GH_TOKEN"])
        promotion.promote((tag, tag[1:], candidate, record), progress, verify_only=True)
        proof = root / "tmp/recovery"
        proof.mkdir(parents=True, exist_ok=True)
        (proof / "preflight.json").write_text(json.dumps({"tag": tag, "candidate": candidate,
            "commit": commit, "digest": expected, "previous_latest": previous}, indent=2))
        if api(f"repos/{repository}/releases/latest").get("id") != previous_release.get("id"):
            raise RuntimeError("Current stable release changed during verification")
        current_draft = api(f"repos/{repository}/releases/{draft['id']}")
        if any(current_draft.get(key) != draft.get(key) for key in (
                "id", "tag_name", "target_commitish", "body", "name", "draft", "prerelease", "published_at")):
            raise RuntimeError("Prepared draft changed during verification")
        # Use the repository GITHUB_TOKEN. Its writes do not trigger release/tag
        # workflows; the legacy release build must not rebuild accepted bytes.
        progress["phase"] = "stable annotated tag creation"
        progress["publication_attempted"] = True
        annotation = api(f"repos/{repository}/git/tags", "-X", "POST", "-f", "tag=" + tag,
            "-f", "message=" + tag, "-f", "object=" + commit, "-f", "type=commit")
        api(f"repos/{repository}/git/refs", "-X", "POST", "-f", "ref=refs/tags/" + tag,
            "-f", "sha=" + annotation["sha"])
        progress["phase"] = "prepared release publication"
        published = api(f"repos/{repository}/releases/{draft['id']}", "-X", "PATCH",
            "-F", "draft=false", "-F", "prerelease=false", "-f", "make_latest=true")
        (proof / "published-release.json").write_text(json.dumps(published, indent=2))
        if (published.get("draft") is not False or published.get("prerelease") is not False
                or published.get("tag_name") != tag or not published.get("published_at")):
            raise RuntimeError("Published release readback mismatch")
        subprocess.run(["git", "fetch", "origin", "--tags"], check=True, timeout=60)
        source = proof / "source"
        subprocess.run(["git", "worktree", "add", "--detach", str(source), commit], check=True, timeout=60)
        event = proof / "release-event.json"
        event.write_text(json.dumps({"action": "published", "release": published}))
        os.environ["GITHUB_EVENT_NAME"] = "release"
        os.environ["GITHUB_EVENT_PATH"] = str(event)
        os.environ["GITHUB_OUTPUT"] = str(proof / "promotion-output.txt")
        os.chdir(source)
        progress["phase"] = "qualified stable promotion"
        selected = promotion.plan()
        if selected != (tag, tag[1:], candidate, record):
            raise RuntimeError("Published plan differs from accepted preflight")
        promotion.promote(selected, progress)
        if api(f"repos/{repository}/releases/latest").get("tag_name") != tag:
            raise RuntimeError("Publication is no longer the current stable release")
        promotion.same_digest(image + ":latest", expected)
        (proof / "result.json").write_text(json.dumps({"status": "PASS", "tag": tag,
            "digest": expected, "source": commit, "previous_latest": previous}, indent=2))
    except Exception:
        state = ("GitHub or registry writes may be partial; inspect evidence and never overwrite"
                 if progress["publication_attempted"] else "Recovery refused before publication")
        raise SystemExit(f"{state}; failed at {progress['phase']}") from None
    finally:
        os.chdir(root)


if __name__ == "__main__":
    recover()
