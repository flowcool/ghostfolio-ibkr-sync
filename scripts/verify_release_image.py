"""Verify the native config in an attested published index against the tested image."""
import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path


def native_manifest_digest(index, arch):
    matches = [entry.get("digest") for entry in index.get("manifests", [])
        if entry.get("platform", {}).get("os") == "linux"
        and entry.get("platform", {}).get("architecture") == arch]
    if len(matches) != 1 or not re.fullmatch(r"sha256:[0-9a-f]{64}", matches[0] or ""):
        raise RuntimeError("Exactly one native image manifest is required")
    return matches[0]


def verify(image, digest, arch):
    if (not re.fullmatch(r"ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+", image)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
            or arch not in ("amd64", "arm64")):
        raise RuntimeError("Invalid publication reference")
    def inspect(ref):
        return json.loads(subprocess.check_output(
            ["docker", "buildx", "imagetools", "inspect", "--raw", ref],
            text=True, timeout=60))
    index = inspect(image + "@" + digest)
    manifest = inspect(image + "@" + native_manifest_digest(index, arch))
    # Image IDs depend on Docker's storage backend. Hash the saved config bytes.
    with tempfile.TemporaryDirectory() as directory:
        saved = Path(directory, "checked-image.tar")
        subprocess.run(["docker", "image", "save", "--output", str(saved),
                        "ibkr-release:check"], check=True, timeout=120)
        with tarfile.open(saved) as archive:
            entries = json.load(archive.extractfile("manifest.json"))
            if len(entries) != 1:
                raise RuntimeError("Exactly one checked local image is required")
            config = archive.extractfile(entries[0]["Config"]).read()
        local = "sha256:" + hashlib.sha256(config).hexdigest()
    if manifest.get("config", {}).get("digest") != local:
        raise RuntimeError("Published native configuration differs from the tested image")
    print(f"Verified linux/{arch} configuration {local} in published {digest}")
    return digest


def assemble(image, version):
    if (not re.fullmatch(r"ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+", image)
            or not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-rc\.[1-9][0-9]*)?", version)):
        raise RuntimeError("Invalid release publication reference")
    sources = []
    expected = {}
    for arch in ("amd64", "arm64"):
        digest = Path("digests", arch + ".txt").read_text()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise RuntimeError("Invalid checked image digest")
        source = image + "@" + digest
        index = json.loads(subprocess.check_output(
            ["docker", "buildx", "imagetools", "inspect", "--raw", source], timeout=60))
        expected[arch] = native_manifest_digest(index, arch)
        sources.append(source)
    subprocess.run(["docker", "buildx", "imagetools", "create", "--tag",
                    image + ":" + version, *sources], check=True, timeout=120)
    raw = subprocess.check_output(
        ["docker", "buildx", "imagetools", "inspect", "--raw", image + ":" + version], timeout=60)
    manifest = json.loads(raw)
    for arch, digest in expected.items():
        if native_manifest_digest(manifest, arch) != digest:
            raise RuntimeError("Version manifest differs from the checked native image")
        print(f"Version {version}: verified linux/{arch} manifest {digest}")
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    Path("release-manifest.json").write_bytes(raw)
    Path("release-manifest-digest.txt").write_text(digest)
    print(f"Verified stable manifest {image}@{digest}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--digest")
    parser.add_argument("--arch", choices=("amd64", "arm64"))
    parser.add_argument("--assemble", metavar="VERSION")
    args = parser.parse_args()
    if args.assemble:
        if args.digest or args.arch:
            parser.error("--assemble cannot be combined with --digest or --arch")
        assemble(args.image, args.assemble)
    else:
        if not args.digest or not args.arch:
            parser.error("--digest and --arch are required for native verification")
        digest = verify(args.image, args.digest, args.arch)
        Path("digests").mkdir(exist_ok=True)
        Path("digests", args.arch + ".txt").write_text(digest)


if __name__ == "__main__":
    main()
