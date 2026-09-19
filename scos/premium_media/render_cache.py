"""Content-addressed render cache with fail-closed artifact sealing.
The cache stores derived artifacts only; authoritative project state remains source bytes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

CACHE_SCHEMA = "SCOS_RENDER_CACHE_R1"
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class CacheHit:
    namespace: str
    key: str
    artifact_path: Path
    artifact_sha256: str
    size_bytes: int
    metadata: dict[str, Any]


class RenderCacheError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_key(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()



def _safe_component(value: str) -> str:
    if not _SAFE_NAME.fullmatch(value):
        raise RenderCacheError(f"unsafe cache component: {value!r}")
    return value


class RenderCache:
    """Small content-addressed cache with atomic writes and checksum verification."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def default_root(project_dir: str | Path) -> Path:
        configured = os.environ.get("SCOS_RENDER_CACHE_DIR")
        if configured:
            return Path(configured).expanduser().resolve()
        current = Path(project_dir).resolve()
        for candidate in (current, *current.parents):
            if (candidate / ".git").exists():
                return candidate / "memory" / "runtime" / "premium-render-cache"
        return Path.home() / ".scos" / "premium-render-cache"

    @classmethod
    def for_project(cls, project_dir: str | Path) -> "RenderCache":
        return cls(cls.default_root(project_dir))

    def _entry_dir(self, namespace: str, key: str) -> Path:
        return self.root / _safe_component(namespace) / _safe_component(key)

    def _manifest_path(self, namespace: str, key: str) -> Path:
        return self._entry_dir(namespace, key) / "manifest.json"

    def lookup(self, namespace: str, key: str) -> CacheHit | None:
        manifest_path = self._manifest_path(namespace, key)
        if not manifest_path.is_file():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifact = (manifest_path.parent / str(manifest["artifact_name"])).resolve()
            if manifest.get("schema_version") != CACHE_SCHEMA:
                return None
            if manifest.get("namespace") != namespace or manifest.get("key") != key:
                return None
            if not artifact.is_file() or artifact.stat().st_size <= 0:
                return None
            expected = str(manifest["artifact_sha256"])
            actual = sha256_file(artifact)
            if actual != expected:
                return None
            size_bytes = int(manifest["size_bytes"])
            if artifact.stat().st_size != size_bytes:
                return None
            metadata = manifest.get("metadata", {})
            if not isinstance(metadata, dict):
                return None
            return CacheHit(namespace, key, artifact, expected, size_bytes, metadata)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def materialize(self, hit: CacheHit, output: str | Path) -> Path:
        target = Path(output).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            shutil.copy2(hit.artifact_path, temp_path)
            if sha256_file(temp_path) != hit.artifact_sha256:
                raise RenderCacheError("cache materialization checksum mismatch")
            os.replace(temp_path, target)
            return target
        finally:
            temp_path.unlink(missing_ok=True)



    def store(
        self,
        namespace: str,
        key: str,
        artifact: str | Path,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> CacheHit:
        source = Path(artifact).resolve()
        if not source.is_file() or source.stat().st_size <= 0:
            raise RenderCacheError(f"cannot cache missing/empty artifact: {source}")

        artifact_sha256 = sha256_file(source)
        destination = self._entry_dir(namespace, key)
        destination.parent.mkdir(parents=True, exist_ok=True)

        existing = self.lookup(namespace, key)
        if existing is not None:
            return existing

        tmp_dir: Path | None = Path(
            tempfile.mkdtemp(prefix=f".{key[:12]}-", dir=destination.parent)
        )
        try:
            cached_artifact = tmp_dir / source.name
            shutil.copy2(source, cached_artifact)
            manifest = {
                "schema_version": CACHE_SCHEMA,
                "namespace": namespace,
                "key": key,
                "artifact_name": cached_artifact.name,
                "artifact_sha256": artifact_sha256,
                "size_bytes": cached_artifact.stat().st_size,
                "metadata": dict(metadata or {}),
            }
            (tmp_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            try:
                os.replace(tmp_dir, destination)
                tmp_dir = None
            except FileExistsError:
                existing = self.lookup(namespace, key)
                if existing is not None:
                    return existing
                raise RenderCacheError("cache entry exists but failed closed validation")
            hit = self.lookup(namespace, key)
            if hit is None:
                raise RenderCacheError("cache entry failed post-write verification")
            return hit
        finally:
            if tmp_dir is not None:
                shutil.rmtree(tmp_dir, ignore_errors=True)



def fingerprint_value(value: Any, *, base_dir: Path | None = None) -> Any:
    if isinstance(value, dict):
        return {str(k): fingerprint_value(v, base_dir=base_dir) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [fingerprint_value(v, base_dir=base_dir) for v in value]
    if isinstance(value, str):
        candidates = [Path(value)]
        if base_dir is not None and not Path(value).is_absolute():
            candidates.insert(0, base_dir / value)
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved.is_file():
                return {
                    "__file__": str(resolved),
                    "sha256": sha256_file(resolved),
                    "size_bytes": resolved.stat().st_size,
                }
        return value
    return value


def source_tree_fingerprint(project_dir: str | Path) -> str:
    project = Path(project_dir).resolve()
    files: list[tuple[str, str, int]] = []
    roots = [project / "src"]
    for name in ("package.json", "package-lock.json", "remotion.config.mjs", "remotion.config.js"):
        path = project / name
        if path.is_file():
            roots.append(path)
    candidates: list[Path] = []
    for root in roots:
        if root.is_file():
            candidates.append(root)
        elif root.is_dir():
            candidates.extend(
                path for path in root.rglob("*")
                if path.is_file() and "node_modules" not in path.parts
            )
    for path in sorted(set(candidates)):
        files.append((
            path.relative_to(project).as_posix(),
            sha256_file(path),
            path.stat().st_size,
        ))
    return cache_key({"schema": "SCOS_RENDER_SOURCE_R1", "files": files})
