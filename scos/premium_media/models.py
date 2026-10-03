"""Premium media contracts: rights-aware assets, layered audio, captions, and render profiles.
The module is dependency-light so it can be reused by SCOS, Remotion, and FFmpeg paths.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RightsClass(str, Enum):
    COMMERCIAL_CLEARED = "commercial_cleared"
    CC0 = "cc0"
    CC_BY = "cc_by"
    PLATFORM_SCOPED = "platform_scoped"
    NONCOMMERCIAL = "noncommercial"
    UNKNOWN = "unknown"
    PROHIBITED = "prohibited"


class RenderBackendKind(str, Enum):
    REMOTION = "remotion"
    FFMPEG = "ffmpeg"
    VIDEO_USE = "video_use"


class AudioRole(str, Enum):
    VOICE = "voice"
    MUSIC = "music"
    SFX = "sfx"
    AMBIENCE = "ambience"


@dataclass(frozen=True)
class AssetRights:
    source_url: str
    license_name: str
    rights_class: RightsClass
    commercial_ok: bool
    allowed_platforms: tuple[str, ...] = ()
    attribution_required: bool = False
    attribution_text: str = ""
    evidence_url: str = ""
    license_version: str = ""
    expires_at: str | None = None
    notes: str = ""

    def allows(self, platform: str, for_ad: bool = False) -> bool:
        if self.rights_class in {RightsClass.UNKNOWN, RightsClass.PROHIBITED, RightsClass.NONCOMMERCIAL}:
            return False
        if not self.commercial_ok and for_ad:
            return False
        if self.allowed_platforms and platform not in self.allowed_platforms:
            return False
        return True


@dataclass(frozen=True)
class MediaAsset:
    asset_id: str
    path: str
    media_type: str
    duration_s: float | None = None
    tags: tuple[str, ...] = ()
    language: str | None = None
    sha256: str = ""
    rights: AssetRights | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AudioStem:
    asset_id: str
    role: AudioRole
    start_s: float = 0.0
    gain_db: float = 0.0
    trim_start_s: float = 0.0
    trim_end_s: float | None = None
    duck_group: str | None = None
    pan: float = 0.0
    enabled: bool = True


@dataclass(frozen=True)
class SubtitleCue:
    start_s: float
    end_s: float
    text: str
    language: str = "und"
    speaker: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class SubtitleStyle:
    font_family: str = "Tahoma"
    font_size_px: int = 56
    primary_color: str = "&H00FFFFFF"
    outline_color: str = "&H00101010"
    outline_px: int = 3
    shadow_px: int = 1
    margin_v: int = 120
    max_chars_per_line: int = 26
    position: str = "bottom_center"


@dataclass(frozen=True)
class PremiumRenderProfile:
    name: str
    platform: str
    width: int = 1080
    height: int = 1920
    fps: int = 30
    video_codec: str = "libx264"
    video_crf: int = 18
    video_preset: str = "slow"
    pix_fmt: str = "yuv420p"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    sample_rate: int = 48000
    target_lufs: float = -16.0
    max_true_peak_db: float = -1.0
    single_screen: bool = True
    burn_in_subtitles: bool = True
    faststart: bool = True
    for_ad: bool = False
    render_acceleration: str = "cpu"
    nvenc_preset: str = "p5"
    nvenc_cq: int | None = None


@dataclass(frozen=True)
class PremiumRenderSpec:
    project_id: str
    duration_s: float
    profile: PremiumRenderProfile
    backend: RenderBackendKind = RenderBackendKind.REMOTION
    composition_id: str = ""
    remotion_project_dir: str = ""
    visual_manifest_path: str = ""
    assets: tuple[MediaAsset, ...] = ()
    audio_stems: tuple[AudioStem, ...] = ()
    subtitles: tuple[SubtitleCue, ...] = ()
    subtitle_style: SubtitleStyle = field(default_factory=SubtitleStyle)
    output_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
