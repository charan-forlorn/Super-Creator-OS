"""Typed data model for the Module 3 Asset Builder.

All encode/format constants live on `AssetConfig` (single source of truth) — no
magic values scattered across the generators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AssetConfig:
    """Output format for generated scene assets."""

    # Visual (vertical 9:16)
    width: int = 1080
    height: int = 1920

    # Audio
    sample_rate: int = 48000
    channels: int = 1                 # mono
    sample_width_bytes: int = 2       # 16-bit PCM
    # Deterministic voiceover-stub tone is mapped into this band (Hz).
    freq_min: float = 180.0
    freq_max: float = 420.0
    fade_s: float = 0.02              # click-free edges

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"


@dataclass(frozen=True)
class Asset:
    """One scene's generated media."""

    scene_id: str
    image_path: Path
    audio_path: Path
    duration: float

    def to_dict(self, relative_to: Path | None = None) -> dict:
        """Serialize for the manifest / downstream agents.

        Emits `asset_path` as an alias of `image_path` so the existing
        EditComposer (which reads `asset_path`) consumes the bundle unmodified.
        Paths are repo-relative POSIX strings when `relative_to` is given.
        """
        def fmt(p: Path) -> str:
            if relative_to is not None:
                try:
                    return p.resolve().relative_to(relative_to.resolve()).as_posix()
                except ValueError:
                    return p.as_posix()
            return p.as_posix()

        image = fmt(self.image_path)
        return {
            "scene_id": self.scene_id,
            "image_path": image,
            "asset_path": image,          # alias for EditComposer compatibility
            "audio_path": fmt(self.audio_path),
            "duration": round(self.duration, 3),
        }


@dataclass
class AssetBuildResult:
    """Outcome of a build: the per-scene assets + manifest location."""

    run_id: str
    assets: list[Asset] = field(default_factory=list)
    manifest_path: Path | None = None
    total_duration: float = 0.0
