"""Read-only deterministic media asset indexing and acquisition intelligence.

The index is a disposable read model. It never copies, mutates, publishes, or
downloads assets and never becomes project-state authority. Content SHA-256 is
the stable identity; metadata is derived from the current bytes via ffprobe.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from scos.media_binaries import resolve_ffprobe

INDEX_SCHEMA_VERSION = 1
INDEX_ALGORITHM = "sha256+ffprobe"

MEDIA_EXTENSIONS = frozenset({
    ".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".wmv",
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
})

STATE_READY = "READY"
STATE_CHANGED = "CHANGED"
STATE_MISSING = "MISSING"
STATE_UNSUPPORTED = "UNSUPPORTED"
STATE_ERROR = "ERROR"


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _safe_file(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
        return resolved.is_file()
    except (OSError, ValueError):
        return False


def _probe(path: Path, ffprobe: str, timeout_s: float) -> dict[str, Any]:
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries",
        "format=format_name,duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
        "-of", "json",
        str(path),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[-500:] or "ffprobe failed")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = data.get("format") or {}
    fps = None
    if video and video.get("r_frame_rate"):
        try:
            num, den = str(video["r_frame_rate"]).split("/", 1)
            fps = round(float(num) / float(den), 6) if float(den) else None
        except (ValueError, ZeroDivisionError):
            fps = None
    duration = None
    try:
        if fmt.get("duration") is not None:
            duration = round(float(fmt["duration"]), 6)
    except (TypeError, ValueError):
        duration = None
    return {
        "format": fmt.get("format_name"),
        "duration_sec": duration,
        "width": video.get("width") if video else None,
        "height": video.get("height") if video else None,
        "fps": fps,
        "video_codec": video.get("codec_name") if video else None,
        "audio_codec": audio.get("codec_name") if audio else None,
        "audio_sample_rate": int(audio["sample_rate"]) if audio and str(audio.get("sample_rate") or "").isdigit() else None,
        "audio_channels": int(audio["channels"]) if audio and str(audio.get("channels") or "").isdigit() else None,
        "has_video": video is not None,
        "has_audio": audio is not None,
    }


@dataclass(frozen=True)
class AssetIndexEntry:
    relative_path: str
    name: str
    extension: str
    size_bytes: int
    sha256: str | None
    kind: str
    state: str
    duplicate_of: str | None
    metadata: dict[str, Any]
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AssetIndex:
    schema_version: int
    algorithm: str
    roots: tuple[str, ...]
    entries: tuple[AssetIndexEntry, ...]
    unique_sha256_count: int
    duplicate_group_count: int
    index_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "algorithm": self.algorithm,
            "roots": list(self.roots),
            "entries": [entry.to_dict() for entry in self.entries],
            "unique_sha256_count": self.unique_sha256_count,
            "duplicate_group_count": self.duplicate_group_count,
            "index_hash": self.index_hash,
        }


def _iter_media_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix().casefold()):
        if path.is_file() and path.suffix.casefold() in MEDIA_EXTENSIONS:
            yield path


def build_asset_index(
    roots: Iterable[Path | str],
    *,
    ffprobe: str | None = None,
    max_files: int = 5000,
    max_total_bytes: int = 20 * 1024 * 1024 * 1024,
    probe_timeout_s: float = 20.0,
    previous: AssetIndex | None = None,
) -> AssetIndex:
    normalized_roots = tuple(
        str(Path(root).resolve()) for root in sorted({str(Path(r).resolve()) for r in roots})
    )
    if not normalized_roots:
        raise ValueError("at least one asset root is required")
    if max_files <= 0 or max_total_bytes <= 0:
        raise ValueError("max_files and max_total_bytes must be positive")

    probe_bin = ffprobe or resolve_ffprobe()
    previous_map = {
        item.relative_path: item
        for item in (previous.entries if previous else ())
    }

    entries: list[AssetIndexEntry] = []
    total_bytes = 0
    seen_sha: dict[str, str] = {}
    for root_text in normalized_roots:
        root = Path(root_text)
        if not root.is_dir():
            entries.append(
                AssetIndexEntry(
                    relative_path="",
                    name=root.name,
                    extension="",
                    size_bytes=0,
                    sha256=None,
                    kind="root",
                    state=STATE_MISSING,
                    duplicate_of=None,
                    metadata={"root": root_text},
                    error="root does not exist",
                )
            )
            continue

        for path in _iter_media_files(root):
            if len(entries) >= max_files:
                break
            try:
                size = path.stat().st_size
            except OSError as exc:
                entries.append(AssetIndexEntry(
                    relative_path=_canonical_rel(path, root),
                    name=path.name,
                    extension=path.suffix.casefold(),
                    size_bytes=0,
                    sha256=None,
                    kind="media",
                    state=STATE_ERROR,
                    duplicate_of=None,
                    metadata={},
                    error=f"stat:{type(exc).__name__}",
                ))
                continue

            total_bytes += size
            if total_bytes > max_total_bytes:
                raise RuntimeError(
                    f"asset scan byte budget exceeded: {total_bytes} > {max_total_bytes}"
                )

            rel = _canonical_rel(path, root)
            previous_entry = previous_map.get(rel)
            current_sha: str | None = None
            state = STATE_READY
            error: str | None = None
            metadata: dict[str, Any] = {}

            try:
                current_sha = _sha256(path)
                if previous_entry is not None and previous_entry.sha256 != current_sha:
                    state = STATE_CHANGED
                metadata = _probe(path, probe_bin, probe_timeout_s)
            except Exception as exc:
                state = STATE_ERROR
                error = f"{type(exc).__name__}:{str(exc)[-400:]}"

            duplicate_of = (
                seen_sha.get(current_sha)
                if current_sha is not None
                else None
            )
            if current_sha is not None and current_sha not in seen_sha:
                seen_sha[current_sha] = f"{root_text}:{rel}"

            kind = "video" if metadata.get("has_video") else (
                "audio" if metadata.get("has_audio") else "image"
            )
            entries.append(
                AssetIndexEntry(
                    relative_path=rel,
                    name=path.name,
                    extension=path.suffix.casefold(),
                    size_bytes=size,
                    sha256=current_sha,
                    kind=kind,
                    state=state,
                    duplicate_of=duplicate_of,
                    metadata=metadata,
                    error=error,
                )
            )

    entries.sort(key=lambda item: (item.relative_path.casefold(), item.name.casefold()))
    unique = {item.sha256 for item in entries if item.sha256}
    duplicate_groups = sum(
        1
        for sha in unique
        if sum(1 for item in entries if item.sha256 == sha) > 1
    )
    content = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "algorithm": INDEX_ALGORITHM,
        "roots": list(normalized_roots),
        "entries": [entry.to_dict() for entry in entries],
    }
    index_hash = hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    return AssetIndex(
        schema_version=INDEX_SCHEMA_VERSION,
        algorithm=INDEX_ALGORITHM,
        roots=normalized_roots,
        entries=tuple(entries),
        unique_sha256_count=len(unique),
        duplicate_group_count=duplicate_groups,
        index_hash=index_hash,
    )


__all__ = [
    "AssetIndex",
    "AssetIndexEntry",
    "INDEX_ALGORITHM",
    "INDEX_SCHEMA_VERSION",
    "STATE_CHANGED",
    "STATE_ERROR",
    "STATE_MISSING",
    "STATE_READY",
    "STATE_UNSUPPORTED",
    "build_asset_index",
]
