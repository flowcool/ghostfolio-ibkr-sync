"""Promote the highest qualified RC index without changing its bytes."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from release_image import (RC_TAG, STABLE_TAG, release_candidate_commits,
                           release_metadata, stable_follows_release_candidate)
from verify_release_image import native_manifest_digest

DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeError("Duplicate qualification key")
        result[key] = value
    return result


def output(*args):
    return subprocess.check_output(args, timeout=90)


def qualification(record, repository, candidate, commit):
    """Release writers attest acceptance; private runner evidence stays private."""
    if (not isinstance(record, dict) or set(record) != {
            "schema", "repository", "rc_tag", "commit", "digest", "native", "labs"}
            or type(record["schema"]) is not int or record["schema"] != 1
            or record["repository"] != repository or record["rc_tag"] != candidate
            or record["commit"] != commit
            or not isinstance(record["digest"], str) or not DIGEST.fullmatch(record["digest"])):
        raise RuntimeError("Qualification identity mismatch")
    native = record["native"]
    if (not isinstance(native, dict) or set(native) != {"amd64", "arm64"}
            or any(not isinstance(d, str) or not DIGEST.fullmatch(d) for d in native.values())
            or len(set(native.values())) != 2):
        raise RuntimeError("Qualification native manifests missing")
    labs = record["labs"]
    if not isinstance(labs, dict) or set(labs) != {"empty", "golden"}:
        raise RuntimeError("Both lab acceptances are required")
    for lab in labs.values():
        if (not isinstance(lab, dict) or set(lab) != {"status", "cleanup", "evidence_sha256"}
                or lab["status"] != "PASS" or lab["cleanup"] != "stopped"
                or not isinstance(lab["evidence_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", lab["evidence_sha256"])):
            raise RuntimeError("Successful stopped lab evidence is required")
    return record


def plan():
    if os.environ.get("GITHUB_EVENT_NAME") != "release":
        raise RuntimeError("A release publication event is required")
    tag, version = release_metadata(json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()))
    repository = os.environ["GITHUB_REPOSITORY"].lower()
    if not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", repository):
        raise RuntimeError("Invalid repository")
    if not STABLE_TAG.fullmatch(tag):
        return None
    commits = release_candidate_commits(tag)
    candidates = [name for name in commits if RC_TAG.fullmatch(name)]
    if not candidates:
        return None
    candidate = max(candidates, key=lambda name: int(RC_TAG.fullmatch(name).group(4)))
    commit = output("git", "rev-parse", "HEAD").decode().strip()
    stable_follows_release_candidate(tag, commits, commit)
    return tag, version, candidate, candidate_qualification(repository, candidate, commit)


def candidate_qualification(repository, candidate, commit):
    release = json.loads(output("gh", "api", f"repos/{repository}/releases/tags/{candidate}"))
    if (release.get("draft") is not False or release.get("prerelease") is not True
            or release.get("tag_name") != candidate or not release.get("published_at")):
        raise RuntimeError("Published RC prerelease required")
    assets = [a for a in release.get("assets", []) if a.get("name") == "lab-qualification.json"]
    if (len(assets) != 1 or type(assets[0].get("id")) is not int
            or assets[0].get("state") != "uploaded" or not 0 < assets[0].get("size", 0) <= 16384):
        raise RuntimeError("One bounded lab-qualification.json asset is required")
    data = output("gh", "api", "-H", "Accept: application/octet-stream",
                  f"repos/{repository}/releases/assets/{assets[0]['id']}")
    if len(data) > 16384:
        raise RuntimeError("Qualification record is too large")
    record = qualification(json.loads(data, object_pairs_hook=unique_object), repository, candidate, commit)
    return record


def inspect(reference):
    return output("docker", "buildx", "imagetools", "inspect", "--raw", reference)


def same_digest(reference, expected):
    raw = inspect(reference)
    if "sha256:" + hashlib.sha256(raw).hexdigest() != expected:
        raise RuntimeError("Index digest mismatch; stop dependent publication")
    return raw


def promote(selected, progress=None, verify_only=False):
    if progress is None:
        progress = {}
    progress["phase"] = "signature verification"
    tag, version, candidate, record = selected
    image = "ghcr.io/" + record["repository"]
    source = image + "@" + record["digest"]
    # Verify before writes. The RC already passed native security/runtime gates.
    subprocess.run(["cosign", "verify", "--certificate-identity",
        f"https://github.com/{record['repository']}/.github/workflows/release-image.yml@refs/tags/{candidate}",
        "--certificate-oidc-issuer", "https://token.actions.githubusercontent.com", source],
        check=True, stdout=subprocess.DEVNULL, timeout=120)
    progress["phase"] = "qualified index verification"
    raw = same_digest(source, record["digest"])
    same_digest(image + ":" + candidate[1:], record["digest"])
    index = json.loads(raw)
    progress["phase"] = "native source identity verification"
    for arch in ("amd64", "arm64"):
        digest = native_manifest_digest(index, arch)
        if digest != record["native"][arch]:
            raise RuntimeError("Native manifest mismatch")
        config = json.loads(output("docker", "buildx", "imagetools", "inspect",
            "--format", "{{json .Image}}", image + "@" + digest))
        labels = config.get("config", {}).get("Labels", {})
        if (config.get("architecture") != arch or config.get("os") != "linux"
                or labels.get("org.opencontainers.image.revision") != record["commit"]
                or labels.get("org.opencontainers.image.source") != "https://github.com/" + record["repository"]
                or labels.get("org.opencontainers.image.version") != candidate):
            raise RuntimeError("Native source identity mismatch")
    if verify_only:
        return raw
    # Re-read release authority, main ancestry, exact tag and version absence.
    progress["phase"] = "release and qualification recheck"
    subprocess.run([sys.executable, "scripts/release_image.py", "--registry"],
                   check=True, timeout=120)
    if plan() != selected:
        raise RuntimeError("Qualification changed during verification")
    progress["phase"] = "version write and readback"
    progress["publication_attempted"] = True
    subprocess.run(["docker", "buildx", "imagetools", "create", "--tag",
                    image + ":" + version, source], check=True, timeout=120)
    same_digest(image + ":" + version, record["digest"])
    Path("release-manifest.json").write_bytes(raw)
    Path("release-manifest-digest.txt").write_text(record["digest"])
    progress["phase"] = "current stable release check"
    current = output("gh", "api", f"repos/{record['repository']}/releases/latest", "--jq", ".tag_name").decode().strip()
    if current == tag:
        progress["phase"] = "latest write and readback"
        subprocess.run(["docker", "buildx", "imagetools", "create", "--tag", image + ":latest", source],
                       check=True, timeout=120)
        same_digest(image + ":latest", record["digest"])
        print(f"Verified latest uses the same digest: {record['digest']}")
    else:
        print("Skip latest: publication is not the current stable release")
    print(f"Verified stable uses the same digest as {candidate}: {record['digest']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="Read qualification metadata; no registry writes")
    mode.add_argument("--publish", action="store_true", help="Release workflow only; requires publication authority")
    args = parser.parse_args()
    progress = {"phase": "qualification record", "publication_attempted": False}
    try:
        selected = plan()
        if args.publish:
            if selected is None:
                raise RuntimeError("Qualified RC required")
            promote(selected, progress)
        else:
            with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
                stream.write("candidate=" + (selected[2] if selected else "") + "\n")
            print("Qualified RC promotion selected" if selected else "Native release build selected")
    except Exception:
        if progress["publication_attempted"]:
            outcome = "Publication may be partial; stop, inspect registry evidence and never overwrite the version"
        else:
            outcome = "Promotion refused before publication"
        raise SystemExit(f"{outcome}; failed at {progress['phase']}") from None


if __name__ == "__main__":
    main()
