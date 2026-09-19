"""Platform delivery renderer: transcodes a sealed master into a destination profile."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from .delivery import DeliveryProfile, get_delivery_profile
from .hardware import detect_hardware
from .qc import probe_media
from .render_cache import RenderCache, cache_key


class DeliveryRenderError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ffmpeg_version() -> str:
    try:
        proc = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"
    lines = (proc.stdout or "").splitlines()
    return lines[0].strip() if lines else "UNKNOWN"


def _resolved_codec(profile: DeliveryProfile) -> str:
    mode = profile.render_acceleration
    if mode not in {"cpu", "auto", "gpu"}:
        raise DeliveryRenderError(f"unknown render_acceleration mode: {mode!r}")
    caps = detect_hardware()
    if mode == "gpu" and not caps.nvenc_available:
        raise DeliveryRenderError("GPU delivery requested but NVENC is unavailable")
    return "h264_nvenc" if mode in {"auto", "gpu"} and caps.nvenc_available else "libx264"


def _validate_delivery_output(target: Path, profile: DeliveryProfile):
    probe = probe_media(target)
    errors = profile.validate_shape(
        duration_s=probe.duration_s, width=probe.width, height=probe.height
    )
    if profile.require_audio and not probe.audio_codec:
        errors.append("destination audio stream missing")
    if profile.min_video_bitrate_kbps is not None:
        measured_kbps = (probe.video_bitrate or 0) / 1000
        if measured_kbps < profile.min_video_bitrate_kbps:
            errors.append(
                f"video bitrate {measured_kbps:.0f} kbps < {profile.min_video_bitrate_kbps} kbps"
            )
    if profile.max_file_mb is not None and target.stat().st_size > profile.max_file_mb * 1024 * 1024:
        errors.append(
            f"file size {target.stat().st_size / 1024 / 1024:.1f}MB > {profile.max_file_mb}MB"
        )
    return probe, errors


def render_delivery(master: str | Path, output: str | Path, profile_id: str) -> dict:
    source = Path(master).resolve()
    target = Path(output).resolve()
    profile = get_delivery_profile(profile_id)
    if not source.is_file() or source.stat().st_size <= 0:
        raise DeliveryRenderError(f"master missing or empty: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)

    master_sha = _sha256(source)
    master_probe = probe_media(source)
    if master_probe.video_codec == "":
        raise DeliveryRenderError("master has no decodable video stream")
    duration_errors = profile.validate_shape(
        duration_s=master_probe.duration_s,
        width=profile.width,
        height=profile.height,
    )
    if duration_errors:
        raise DeliveryRenderError("; ".join(duration_errors))

    codec = _resolved_codec(profile)
    cache = RenderCache.for_project(source.parent)
    cache_key_value = cache_key({
        "schema": "SCOS_PLATFORM_DELIVERY_CACHE_R1",
        "master_sha256": master_sha,
        "profile": profile.__dict__,
        "resolved_video_codec": codec,
        "ffmpeg_version": _ffmpeg_version(),
    })

    cached = cache.lookup("delivery", cache_key_value)
    if cached is not None:
        cache.materialize(cached, target)
        probe, errors = _validate_delivery_output(target, profile)
        if errors:
            raise DeliveryRenderError("cached delivery failed current QC: " + "; ".join(errors))
        manifest = {
            "schema_version": "SCOS_PLATFORM_DELIVERY_ARTIFACT_R1",
            "master": str(source), "master_sha256": master_sha,
            "output": str(target), "output_sha256": _sha256(target),
            "delivery_profile": profile.profile_id,
            "platform": profile.platform, "purpose": profile.purpose,
            "profile": profile.__dict__,
            "resolved_video_codec": codec,
            "cache_hit": True, "cache_key": cache_key_value,
            "human_publish_gate": "NOT_APPROVED",
            "external_publish": "NOT_PERFORMED",
        }
        target.with_suffix(".delivery.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return manifest

    scale = (
        f"scale={profile.width}:{profile.height}:force_original_aspect_ratio=decrease,"
        f"pad={profile.width}:{profile.height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    video_quality = (
        ["-b:v", f"{profile.recommended_video_bitrate_kbps}k",
         "-maxrate", f"{int(profile.recommended_video_bitrate_kbps * 1.25)}k",
         "-bufsize", f"{int(profile.recommended_video_bitrate_kbps * 2)}k"]
        if profile.recommended_video_bitrate_kbps
        else ["-cq:v", "18", "-b:v", "0"]
    )
    if codec == "h264_nvenc":
        video_codec_args = ["-c:v", "h264_nvenc", *video_quality, "-preset", profile.nvenc_preset]
    else:
        video_codec_args = ["-c:v", "libx264", *video_quality, "-preset", "slow"]

    args = [
        "ffmpeg", "-y", "-i", str(source), "-vf", scale,
        *video_codec_args,
        "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
        "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-shortest", str(target),
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0 or not target.is_file() or target.stat().st_size <= 0:
        raise DeliveryRenderError((proc.stderr or proc.stdout)[-5000:])

    probe, errors = _validate_delivery_output(target, profile)
    if errors:
        raise DeliveryRenderError("; ".join(errors))

    try:
        cache.store(
            "delivery",
            cache_key_value,
            target,
            metadata={
                "master_sha256": master_sha,
                "delivery_profile": profile.profile_id,
                "resolved_video_codec": codec,
            },
        )
    except Exception as exc:
        print(f"[premium-cache] delivery artifact not cached: {exc}")

    manifest = {
        "schema_version": "SCOS_PLATFORM_DELIVERY_ARTIFACT_R1",
        "master": str(source), "master_sha256": master_sha,
        "output": str(target), "output_sha256": _sha256(target),
        "delivery_profile": profile.profile_id,
        "platform": profile.platform, "purpose": profile.purpose,
        "profile": profile.__dict__,
        "resolved_video_codec": codec,
        "cache_hit": False, "cache_key": cache_key_value,
        "human_publish_gate": "NOT_APPROVED",
        "external_publish": "NOT_PERFORMED",
    }
    target.with_suffix(".delivery.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
