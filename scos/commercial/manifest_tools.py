"""SCOS Stage 4.18 stable manifest / checksum tools.

Shared helpers for commercial artifact integrity: stable JSON serialization
(byte-identical across runs), SHA-256 digests, deterministic manifest record
builders, and a tiny in-memory checksum cache. These consolidate the private
``_json_text`` / ``_sha256_of`` helpers duplicated across Stage 4 modules and
preserve their exact output format (``sort_keys=True, indent=2`` + trailing
newline; streaming 64 KiB chunked SHA-256).

No signing, no provenance implementation, no persistence, no hidden writes.
Local-first, deterministic, stdlib-only. ``created_at`` values are always
caller-supplied — this module never reads a real clock.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

COMMERCIAL_MANIFEST_TOOLS_SCHEMA_VERSION = 1

_CHUNK_SIZE = 65536


def stable_json_dumps(payload: dict) -> str:
    """Serialize ``payload`` deterministically: sorted keys, 2-space indent, trailing newline."""
    return json.dumps(payload, sort_keys=True, indent=2) + "\n"


def write_stable_json(path, payload: dict) -> str:
    """Write ``payload`` as stable JSON (UTF-8, LF line endings). Returns the string path."""
    target = Path(path)
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(stable_json_dumps(payload))
    return str(target)


def sha256_text(text: str) -> str:
    """SHA-256 hex digest of ``text`` encoded as UTF-8."""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    """SHA-256 hex digest of the file bytes at ``path`` (deterministic chunked read)."""
    digest = hashlib.sha256()
    with open(Path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_artifact_record(
    *,
    artifact_id: str,
    artifact_type: str,
    path,
    required: bool = True,
    include_sha256: bool = True,
    metadata=None,
) -> dict:
    """Build a deterministic artifact record dict.

    ``sha256`` is computed only when ``include_sha256`` is True and the path is
    an existing file; otherwise it is ``None``.
    """
    target = Path(path)
    sha256 = None
    if include_sha256 and target.is_file():
        sha256 = sha256_file(target)
    return {
        "artifact_id": str(artifact_id),
        "artifact_type": str(artifact_type),
        "path": str(target),
        "sha256": sha256,
        "required": bool(required),
        "metadata": dict(metadata or {}),
    }


def build_manifest_metadata(
    *,
    schema_version: int,
    created_at: str,
    generator: str,
    source_hash: str | None = None,
    metadata=None,
) -> dict:
    """Build the deterministic metadata block shared by commercial manifests.

    ``created_at`` must be supplied by the caller — never derived from a clock.
    """
    return {
        "schema_version": int(schema_version),
        "created_at": str(created_at),
        "generator": str(generator),
        "source_hash": None if source_hash is None else str(source_hash),
        "metadata": dict(metadata or {}),
    }


class ChecksumCache:
    """Tiny in-memory SHA-256 cache keyed by (resolved path, size, mtime_ns).

    If the file changes (size or mtime), the checksum is recomputed. No
    persistence, no database, no hidden writes.
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[str, int, int], str] = {}
        self._hits = 0
        self._misses = 0

    def get_file_sha256(self, path) -> str:
        target = Path(path).resolve()
        stat = os.stat(target)
        mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
        key = (str(target), stat.st_size, mtime_ns)
        cached = self._entries.get(key)
        if cached is not None:
            self._hits += 1
            return cached
        self._misses += 1
        digest = sha256_file(target)
        # Drop stale entries for the same path so the cache tracks file changes
        # without growing per rewrite.
        stale = [entry for entry in self._entries if entry[0] == key[0]]
        for entry in stale:
            del self._entries[entry]
        self._entries[key] = digest
        return digest

    def clear(self) -> None:
        self._entries.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict:
        return {
            "entries": len(self._entries),
            "hits": self._hits,
            "misses": self._misses,
        }
