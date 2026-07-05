"""test_manifest_tools.py - SCOS Stage 4.18 manifest / checksum tool suite.

Plain executable script (no pytest). Covers stable JSON determinism, UTF-8/LF
writes, SHA-256 digests (known vectors), artifact / manifest-metadata record
builders, and the in-memory ChecksumCache lifecycle. Every write lives under a
TemporaryDirectory.

Run: python scos/commercial/tests/test_manifest_tools.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COMMERCIAL = _HERE.parent

sys.path.insert(0, str(_COMMERCIAL))

from manifest_tools import (  # noqa: E402
    COMMERCIAL_MANIFEST_TOOLS_SCHEMA_VERSION,
    ChecksumCache,
    build_artifact_record,
    build_manifest_metadata,
    sha256_file,
    sha256_text,
    stable_json_dumps,
    write_stable_json,
)

_PASS = 0
_FAIL = 0


def check(name: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def test_stable_json_dumps() -> None:
    print("\n[1] stable_json_dumps")
    text = stable_json_dumps({"b": 1, "a": {"y": 2, "x": [3, 4]}})
    check("keys sorted", text == json.dumps(
        {"b": 1, "a": {"y": 2, "x": [3, 4]}}, sort_keys=True, indent=2) + "\n")
    check("trailing newline", text.endswith("}\n"))
    check("deterministic across key insertion order",
          stable_json_dumps({"a": 1, "b": 2}) == stable_json_dumps({"b": 2, "a": 1}))
    check("unicode survives round-trip",
          json.loads(stable_json_dumps({"note": "ยืนยัน"})) == {"note": "ยืนยัน"})


def test_write_stable_json(tmp: Path) -> None:
    print("\n[2] write_stable_json")
    target = tmp / "manifest.json"
    returned = write_stable_json(target, {"b": 1, "a": "ยืนยัน"})
    check("returns string path", returned == str(target))
    raw = target.read_bytes()
    check("unicode round-trips through file",
          json.loads(target.read_text(encoding="utf-8")) == {"a": "ยืนยัน", "b": 1})
    check("LF only (no CRLF)", b"\r\n" not in raw and raw.endswith(b"\n"))
    write_stable_json(target, {"a": "ยืนยัน", "b": 1})
    check("byte-identical rewrite", target.read_bytes() == raw)
    check("content matches stable_json_dumps",
          target.read_text(encoding="utf-8") == stable_json_dumps({"a": "ยืนยัน", "b": 1}))


def test_sha256(tmp: Path) -> None:
    print("\n[3] sha256_text / sha256_file")
    check("known vector: empty string",
          sha256_text("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    check("known vector: 'abc'",
          sha256_text("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    blob = tmp / "blob.bin"
    payload = b"x" * 200_000  # forces multiple 64 KiB chunks
    blob.write_bytes(payload)
    check("file digest matches hashlib", sha256_file(blob) == hashlib.sha256(payload).hexdigest())
    abc_file = tmp / "abc.txt"
    abc_file.write_bytes(b"abc")
    check("text digest matches file digest of same bytes", sha256_text("abc") == sha256_file(abc_file))


def test_build_artifact_record(tmp: Path) -> None:
    print("\n[4] build_artifact_record")
    artifact = tmp / "artifact.json"
    artifact.write_text("{}\n", encoding="utf-8")
    record = build_artifact_record(
        artifact_id="A-001", artifact_type="manifest", path=artifact,
        metadata={"stage": "4.18"},
    )
    check("deterministic key order",
          list(record) == ["artifact_id", "artifact_type", "path", "sha256", "required", "metadata"])
    check("sha256 computed for existing file", record["sha256"] == sha256_file(artifact))
    check("required defaults True", record["required"] is True)
    check("metadata copied", record["metadata"] == {"stage": "4.18"})
    no_sha = build_artifact_record(
        artifact_id="A-002", artifact_type="report", path=artifact, include_sha256=False)
    check("include_sha256=False -> None", no_sha["sha256"] is None)
    missing = build_artifact_record(
        artifact_id="A-003", artifact_type="report", path=tmp / "missing.json")
    check("missing file -> sha256 None", missing["sha256"] is None)
    check("path serialized as string", isinstance(record["path"], str))


def test_build_manifest_metadata() -> None:
    print("\n[5] build_manifest_metadata")
    block = build_manifest_metadata(
        schema_version=1, created_at="2026-07-05T00:00:00Z",
        generator="scos.commercial.manifest_tools",
    )
    check("deterministic key order",
          list(block) == ["schema_version", "created_at", "generator", "source_hash", "metadata"])
    check("source_hash defaults None", block["source_hash"] is None)
    check("metadata defaults empty dict", block["metadata"] == {})
    check("created_at is caller-supplied verbatim", block["created_at"] == "2026-07-05T00:00:00Z")
    check("schema_version coerced to int",
          build_manifest_metadata(schema_version="2", created_at="t", generator="g")["schema_version"] == 2)


def test_checksum_cache(tmp: Path) -> None:
    print("\n[6] ChecksumCache")
    cache = ChecksumCache()
    target = tmp / "cached.bin"
    target.write_bytes(b"version-one")
    first = cache.get_file_sha256(target)
    check("first read is a miss", cache.stats() == {"entries": 1, "hits": 0, "misses": 1})
    second = cache.get_file_sha256(target)
    check("unchanged file is a hit", second == first
          and cache.stats() == {"entries": 1, "hits": 1, "misses": 1})

    target.write_bytes(b"version-two-different-length")
    os.utime(target)  # ensure metadata reflects the rewrite
    refreshed = cache.get_file_sha256(target)
    check("changed file refreshes checksum",
          refreshed != first and refreshed == hashlib.sha256(b"version-two-different-length").hexdigest())
    check("stale entry replaced, not accumulated", cache.stats()["entries"] == 1)

    cache.clear()
    check("clear resets stats", cache.stats() == {"entries": 0, "hits": 0, "misses": 0})
    check("stats keys deterministic", list(cache.stats()) == ["entries", "hits", "misses"])
    check("schema version is 1", COMMERCIAL_MANIFEST_TOOLS_SCHEMA_VERSION == 1)


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_stable_json_dumps()
        test_write_stable_json(tmp)
        test_sha256(tmp)
        test_build_artifact_record(tmp)
        test_build_manifest_metadata()
        test_checksum_cache(tmp)
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
