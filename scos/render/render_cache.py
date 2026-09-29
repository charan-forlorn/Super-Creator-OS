"""Content-addressed render cache for SCOS.

The cache stores only derived render artifacts. It is disposable acceleration
state, never canonical project state, approval state, provenance authority, or
evidence authority. Cache hits are fail-closed: a manifest mismatch, missing
file, size/mtime drift, or SHA-256 mismatch is treated as a miss.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from scos.render.base import RenderError, RenderProfile, RenderRequest, ShotSpec

CACHE_SCHEMA_VERSION = 1
CACHE_BACKEND_ID = "scos.render-cache.v1"


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class RenderCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self._checksum_memo: dict[tuple[str, int, int], str] = {}
        self._hits = 0
        self._misses = 0
        self._invalid = 0
        self._stores = 0

    @property
    def stats(self) -> dict[str, int]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "invalid": self._invalid,
            "stores": self._stores,
        }

    def _sha256(self, path: Path) -> str:
        # Cache correctness is content-addressed: a stat-only memo can become
        # stale on filesystems with coarse timestamp resolution. Always hash the
        # current bytes so a changed asset can never produce a false cache hit.
        path = path.resolve()
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def source_digest(self, path: Path) -> str:
        target = Path(path)
        if not target.is_file() or target.stat().st_size <= 0:
            raise RenderError(f"source asset missing or empty: {target}")
        return self._sha256(target)

    def clip_fingerprint(
        self,
        clip: ShotSpec,
        profile: RenderProfile,
        encoder_signature: str,
    ) -> str:
        payload = {
            "schema": CACHE_SCHEMA_VERSION,
            "kind": "scene",
            "backend": CACHE_BACKEND_ID,
            "scene_id": clip.scene_id,
            "duration_s": round(clip.duration_s, 6),
            "visual_sha256": self.source_digest(clip.visual_path),
            "audio_sha256": self.source_digest(clip.audio_path)
            if clip.audio_path is not None
            else "SILENCE",
            "motion": clip.motion,
            "motion_strength": round(clip.motion_strength, 6),
            "camera": clip.camera,
            "action": clip.action,
            "environment": clip.environment,
            "lighting": clip.lighting,
            "style": clip.style,
            "prompt": clip.prompt,
            "references": list(clip.references),
            "start_frame": self.source_digest(clip.start_frame)
            if clip.start_frame is not None
            else None,
            "end_frame": self.source_digest(clip.end_frame)
            if clip.end_frame is not None
            else None,
            "generation_backend": clip.generation_backend,
            "continuity_group": clip.continuity_group,
            "profile": asdict(profile),
            "encoder_signature": encoder_signature,
        }
        return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()

    def scene_fingerprints(
        self,
        request: RenderRequest,
        encoder_signature: str,
    ) -> list[str]:
        return [
            self.clip_fingerprint(clip, request.profile, encoder_signature)
            for clip in request.clips
        ]

    def request_fingerprint(
        self,
        request: RenderRequest,
        scene_fingerprints: list[str],
        backend_signature: str,
        encoder_signature: str,
    ) -> str:
        payload = {
            "schema": CACHE_SCHEMA_VERSION,
            "kind": "final",
            "backend": CACHE_BACKEND_ID,
            "render_backend_signature": backend_signature,
            "encoder_signature": encoder_signature,
            "profile": asdict(request.profile),
            "scenes": scene_fingerprints,
        }
        return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()

    def _paths(self, kind: str, key: str) -> tuple[Path, Path]:
        if kind not in {"scene", "final"}:
            raise ValueError("cache kind must be scene or final")
        directory = self.root / kind
        return directory / f"{key}.mp4", directory / f"{key}.json"

    def _lookup(
        self,
        *,
        kind: str,
        key: str,
        expected_fingerprint: str,
    ) -> Path | None:
        artifact, manifest = self._paths(kind, key)
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("schema_version") != CACHE_SCHEMA_VERSION:
                raise ValueError("schema mismatch")
            if data.get("fingerprint") != expected_fingerprint:
                raise ValueError("fingerprint mismatch")
            if not artifact.is_file() or artifact.stat().st_size <= 0:
                raise ValueError("artifact missing or empty")
            expected_sha = str(data.get("sha256") or "")
            if not expected_sha or self._sha256(artifact) != expected_sha:
                raise ValueError("artifact SHA-256 mismatch")
        except (OSError, ValueError, json.JSONDecodeError):
            self._misses += 1
            if manifest.exists() or artifact.exists():
                self._invalid += 1
            return None
        self._hits += 1
        return artifact

    def lookup_scene(self, fingerprint: str) -> Path | None:
        return self._lookup(kind="scene", key=fingerprint, expected_fingerprint=fingerprint)

    def lookup_final(self, fingerprint: str) -> Path | None:
        return self._lookup(kind="final", key=fingerprint, expected_fingerprint=fingerprint)

    def store(
        self,
        *,
        kind: str,
        key: str,
        source: Path,
        fingerprint: str,
        metadata: dict[str, Any],
    ) -> Path:
        artifact, manifest = self._paths(kind, key)
        artifact.parent.mkdir(parents=True, exist_ok=True)
        temp_artifact = artifact.with_suffix(f".tmp.{os.getpid()}.mp4")
        temp_manifest = manifest.with_suffix(f".tmp.{os.getpid()}.json")
        shutil.copy2(source, temp_artifact)
        sha = self._sha256(temp_artifact)
        envelope = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "cache_backend": CACHE_BACKEND_ID,
            "kind": kind,
            "fingerprint": fingerprint,
            "sha256": sha,
            "size_bytes": temp_artifact.stat().st_size,
            "metadata": metadata,
        }
        temp_manifest.write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        with temp_artifact.open("rb") as handle:
            handle.read(1)
        os.replace(temp_artifact, artifact)
        os.replace(temp_manifest, manifest)
        self._stores += 1
        return artifact

    def materialize(self, cached: Path, target: Path) -> Path:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if cached.resolve() == target.resolve():
            return target
        temporary = target.with_suffix(f".tmp.{os.getpid()}{target.suffix}")
        shutil.copy2(cached, temporary)
        os.replace(temporary, target)
        return target

    def invalidate(self, *, kind: str, key: str) -> None:
        artifact, manifest = self._paths(kind, key)
        for path in (artifact, manifest):
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def clear(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)
        self._checksum_memo.clear()
        self._hits = self._misses = self._invalid = self._stores = 0


__all__ = ["CACHE_BACKEND_ID", "CACHE_SCHEMA_VERSION", "RenderCache"]
