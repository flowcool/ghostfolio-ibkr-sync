"""Offline evidence and private-output primitives for identity maintenance.

No configuration loader, credential reader or HTTP client belongs here.
"""

import hashlib
import json
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


def require(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(path: Path) -> Path:
    require(not any(part.is_symlink() for part in (path, *path.parents)),
            "Symlink paths are not allowed")
    return path.resolve()


def read_evidence(path: Path, expected_hash: str) -> bytes:
    data = safe_path(path).read_bytes()
    require(digest(data) == expected_hash, "Evidence hash changed")
    return data


def exact_json(data: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise RuntimeError("Non-finite JSON number")

    return json.loads(data, parse_float=Decimal, parse_int=Decimal,
                      parse_constant=invalid_constant, object_pairs_hook=pairs)


def canonical_json(value: Any) -> bytes:
    """Keep exact decimal evidence as strings; runtime payloads retain numbers."""
    def default(item: Any) -> str:
        if isinstance(item, Decimal) and item.is_finite():
            return str(item)
        raise TypeError("Unsupported manifest value")

    return (json.dumps(value, default=default, sort_keys=True, ensure_ascii=True,
                       allow_nan=False, separators=(",", ":")) + "\n").encode()


def instant(value: Any) -> datetime:
    require(isinstance(value, str), "Missing timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "Timestamp needs an explicit timezone")
    return parsed


def publish_private(output: Path, files: dict[str, bytes], inputs: list[Path]) -> None:
    """Exclusive publication cannot replace an input or an earlier review."""
    target = safe_path(output)
    for path in inputs:
        source = safe_path(path)
        require(not source.is_relative_to(target) and not target.is_relative_to(source),
                "Output overlaps evidence")
    for name in files:
        require(Path(name).name == name, "Invalid output name")
    require(not target.exists(), "Output already exists")
    # Stage on the same filesystem for an atomic directory rename. Reserve the
    # destination exclusively only after every file has been written and synced.
    # Rename may replace our own empty reservation, never an earlier output.
    with tempfile.TemporaryDirectory(prefix=".identity-preview-", dir=target.parent) as staging:
        stage = Path(staging) / "review"
        stage.mkdir(mode=0o700)
        for name, data in files.items():
            descriptor = os.open(stage / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        target.mkdir(mode=0o700, parents=False, exist_ok=False)
        try:
            stage.rename(target)
        except OSError:
            target.rmdir()
            raise
