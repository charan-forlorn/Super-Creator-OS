"""Platform delivery renderer: transcodes a sealed master into a destination profile."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .delivery import DeliveryProfile, get_delivery_profile
from .qc import probe_media


class DeliveryRenderError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def render_delivery(master: str | Path, output: str | Path, profile_id: str) -> dict:
    source = Path(master).resolve()
    target = Path(output).resolve()
    profile = get_delivery_profile(profile_id)
    if not source.is_file() or source.stat().st_size <= 0:
        raise DeliveryRenderError(f"master missing or empty: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)

    master_probe = probe_media(source)
    if master_probe.video_codec == "":
        raise DeliveryRenderError("master has no decodable video stream")
    # Geometry can legitimately change at delivery time; duration constraints remain binding.
    duration_errors = profile.validate_shape(
        duration_s=master_probe.duration_s,
        width=profile.width,
        height=profile.height,
    )
    if duration_errors:
        raise DeliveryRenderError("; ".join(duration_errors))
    scale = f"scale={profile.width}:{profile.height}:force_original_aspect_ratio=decrease,pad={profile.width}:{profile.height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    video_quality = (
        ["-b:v", f"{profile.recommended_video_bitrate_kbps}k",
         "-maxrate", f"{int(profile.recommended_video_bitrate_kbps * 1.25)}k",
         "-bufsize", f"{int(profile.recommended_video_bitrate_kbps * 2)}k"]
        if profile.recommended_video_bitrate_kbps
        else ["-crf", "14"]
    )
    args = [
        "ffmpeg", "-y", "-i", str(source), "-vf", scale,
        "-c:v", "libx264", *video_quality, "-preset", "slow",
        "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
        "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-shortest", str(target),
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0 or not target.is_file() or target.stat().st_size <= 0:
        raise DeliveryRenderError((proc.stderr or proc.stdout)[-5000:])

    probe = probe_media(target)
    errors = profile.validate_shape(duration_s=probe.duration_s, width=probe.width, height=probe.height)
    if profile.require_audio and not probe.audio_codec:
        errors.append("destination audio stream missing")
    if profile.min_video_bitrate_kbps is not None:
        measured_kbps = (probe.video_bitrate or 0) / 1000
        if measured_kbps < profile.min_video_bitrate_kbps:
            errors.append(f"video bitrate {measured_kbps:.0f} kbps < {profile.min_video_bitrate_kbps} kbps")
    if profile.max_file_mb is not None and target.stat().st_size > profile.max_file_mb * 1024 * 1024:
        errors.append(f"file size {target.stat().st_size / 1024 / 1024:.1f}MB > {profile.max_file_mb}MB")
    if errors:
        raise DeliveryRenderError("; ".join(errors))
    manifest = {
        "schema_version": "SCOS_PLATFORM_DELIVERY_ARTIFACT_R1",
        "master": str(source), "master_sha256": _sha256(source),
        "output": str(target), "output_sha256": _sha256(target),
        "delivery_profile": profile.profile_id,
        "platform": profile.platform, "purpose": profile.purpose,
        "profile": profile.__dict__,
        "human_publish_gate": "NOT_APPROVED",
        "external_publish": "NOT_PERFORMED",
    }
    target.with_suffix(".delivery.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
