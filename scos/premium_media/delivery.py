"""Canonical separation between platform-neutral masters and destination delivery renders."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DeliveryProfile:
    profile_id: str
    platform: str
    purpose: str
    width: int
    height: int
    fps: int = 30
    min_duration_s: float | None = None
    max_duration_s: float | None = None
    recommended_duration_range_s: tuple[float, float] | None = None
    min_video_bitrate_kbps: int | None = None
    recommended_video_bitrate_kbps: int | None = None
    max_file_mb: int | None = None
    require_audio: bool = True
    require_916: bool = False
    safe_zone_required: bool = True
    render_acceleration: str = "auto"
    nvenc_preset: str = "p5"
    source_urls: tuple[str, ...] = ()
    evidence_note: str = ""

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height

    @property
    def is_platform_delivery(self) -> bool:
        return self.platform != "master"

    def validate_shape(self, *, duration_s: float, width: int, height: int) -> list[str]:
        errors: list[str] = []
        if width != self.width or height != self.height:
            errors.append(f"geometry {width}x{height} != {self.width}x{self.height}")
        if self.min_duration_s is not None and duration_s < self.min_duration_s:
            errors.append(f"duration {duration_s:.3f}s < minimum {self.min_duration_s:.3f}s")
        if self.max_duration_s is not None and duration_s > self.max_duration_s:
            errors.append(f"duration {duration_s:.3f}s > maximum {self.max_duration_s:.3f}s")
        return errors


MASTER_VERTICAL = DeliveryProfile(
    profile_id="master_vertical_1080", platform="master", purpose="master",
    width=1080, height=1920, fps=30, require_audio=True, safe_zone_required=True,
    render_acceleration="cpu",
    evidence_note="Platform-neutral production master; destination-specific delivery requirements are applied later.",
)

MASTER_ARCHIVE_VERTICAL = DeliveryProfile(
    profile_id="master_vertical_2160", platform="master", purpose="archive-master",
    width=2160, height=3840, fps=30, require_audio=True, safe_zone_required=True,
    render_acceleration="cpu",
    evidence_note="Optional high-resolution archival master target; not a platform delivery artifact.",
)

TIKTOK_ADS_GLOBAL = DeliveryProfile(
    profile_id="tiktok_ads_global_app_bundle", platform="tiktok", purpose="ads",
    width=1080, height=1920, fps=30, min_duration_s=5, max_duration_s=60,
    recommended_duration_range_s=(21, 30), min_video_bitrate_kbps=516,
    recommended_video_bitrate_kbps=1800, max_file_mb=500,
    require_audio=True, require_916=True, safe_zone_required=True,
    source_urls=("https://ads.tiktok.com/resources/help/article/global-app-bundle-video-ad-specifications?lang=th",),
    evidence_note="TikTok global app-bundle video ad specification: 9:16 recommended, 5–60s, 516 kbps+ recommended, 500 MB max.",
)

META_REELS_ADS = DeliveryProfile(
    profile_id="meta_reels_ads", platform="meta_reels", purpose="ads",
    width=1080, height=1920, fps=30, require_audio=True, require_916=True,
    safe_zone_required=True,
    source_urls=("https://www.facebook.com/business/ads/facebook-instagram-reels-ads",),
    evidence_note="Meta Reels ads guidance emphasizes 9:16 video, audio, and key messages inside the safe zone; exact timing/file limits should be read from the live destination spec at delivery time.",
)

YOUTUBE_UPLOAD_1080P = DeliveryProfile(
    profile_id="youtube_upload_1080p", platform="youtube", purpose="shorts-upload",
    width=1080, height=1920, fps=30, require_audio=True, require_916=True,
    safe_zone_required=True,
    recommended_video_bitrate_kbps=8000,
    source_urls=("https://support.google.com/youtube/answer/1722171?hl=en",),
    evidence_note="Vertical 1080p YouTube delivery profile for short-form output. Live destination requirements remain authoritative at delivery time.",
)

YOUTUBE_UPLOAD_1080P_LANDSCAPE = DeliveryProfile(
    profile_id="youtube_upload_1080p_landscape", platform="youtube", purpose="upload",
    width=1920, height=1080, fps=30, require_audio=True, require_916=False,
    safe_zone_required=True,
    recommended_video_bitrate_kbps=12000,
    source_urls=("https://support.google.com/youtube/answer/1722171?hl=en",),
    evidence_note="Horizontal 1920x1080 YouTube delivery profile. Live destination requirements remain authoritative at delivery time.",
)

MASTER_HORIZONTAL_1080 = DeliveryProfile(
    profile_id="master_horizontal_1080", platform="master", purpose="master",
    width=1920, height=1080, fps=30, require_audio=True, safe_zone_required=True,
    render_acceleration="cpu",
    evidence_note="Platform-neutral 16:9 production master for horizontal delivery.",
)

MASTER_SQUARE_1080 = DeliveryProfile(
    profile_id="master_square_1080", platform="master", purpose="master",
    width=1080, height=1080, fps=30, require_audio=True, safe_zone_required=True,
    render_acceleration="cpu",
    evidence_note="Platform-neutral 1:1 production master for square feeds.",
)

MASTER_PORTRAIT_4X5 = DeliveryProfile(
    profile_id="master_portrait_4x5_1080", platform="master", purpose="master",
    width=1080, height=1350, fps=30, require_audio=True, safe_zone_required=True,
    render_acceleration="cpu",
    evidence_note="Platform-neutral 4:5 production master for portrait feeds.",
)

DELIVERY_PROFILES: dict[str, DeliveryProfile] = {
    p.profile_id: p for p in (
        MASTER_VERTICAL,
        MASTER_ARCHIVE_VERTICAL,
        MASTER_HORIZONTAL_1080,
        MASTER_SQUARE_1080,
        MASTER_PORTRAIT_4X5,
        TIKTOK_ADS_GLOBAL,
        META_REELS_ADS,
        YOUTUBE_UPLOAD_1080P,
        YOUTUBE_UPLOAD_1080P_LANDSCAPE,
    )
}


def get_delivery_profile(profile_id: str) -> DeliveryProfile:
    try:
        return DELIVERY_PROFILES[profile_id]
    except KeyError as exc:
        raise KeyError(f"unknown delivery profile: {profile_id}") from exc


def delivery_manifest(profile_ids: list[str] | tuple[str, ...]) -> dict[str, Any]:
    profiles = [get_delivery_profile(pid) for pid in profile_ids]
    return {
        "schema_version": "SCOS_PLATFORM_DELIVERY_R1",
        "profiles": [
            {
                "profile_id": p.profile_id,
                "platform": p.platform,
                "purpose": p.purpose,
                "width": p.width,
                "height": p.height,
                "fps": p.fps,
                "duration": [p.min_duration_s, p.max_duration_s],
                "recommended_duration_range_s": p.recommended_duration_range_s,
                "min_video_bitrate_kbps": p.min_video_bitrate_kbps,
                "recommended_video_bitrate_kbps": p.recommended_video_bitrate_kbps,
                "max_file_mb": p.max_file_mb,
                "require_audio": p.require_audio,
                "require_916": p.require_916,
                "safe_zone_required": p.safe_zone_required,
                "render_acceleration": p.render_acceleration,
                "nvenc_preset": p.nvenc_preset,
                "source_urls": list(p.source_urls),
                "evidence_note": p.evidence_note,
            }
            for p in profiles
        ],
    }
