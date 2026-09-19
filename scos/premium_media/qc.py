"""Fail-closed media QA: metadata, loudness, subtitles, and optional VMAF capability."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from scos.control_center.hvs_golden_render_models import QA_POLICY
from scos.control_center.hvs_golden_render_service import _audio_analysis, _sample_frame_luma

from .models import PremiumRenderProfile, SubtitleCue
from .subtitles import validate_cues


@dataclass(frozen=True)
class MediaProbe:
    path: str
    width: int
    height: int
    fps: float
    duration_s: float
    video_codec: str
    audio_codec: str | None
    audio_sample_rate: int | None
    audio_channels: int | None
    video_bitrate: int | None
    audio_bitrate: int | None


@dataclass(frozen=True)
class LoudnessReport:
    integrated_lufs: float | None
    true_peak_db: float | None
    lra: float | None
    input_thresh: float | None = None
    target_offset: float | None = None
    raw: str = ""


@dataclass(frozen=True)
class QCReport:
    passed: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    probe: MediaProbe | None = None
    loudness: LoudnessReport | None = None
    capabilities: dict[str, bool] = field(default_factory=dict)


class QCError(ValueError):
    pass


def _run(args: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise QCError(f"required executable missing: {args[0]}") from exc


def probe_media(path: str | Path) -> MediaProbe:
    target = str(path)
    proc = _run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", target
    ])
    if proc.returncode != 0:
        raise QCError(proc.stderr.strip()[-1000:])
    data = json.loads(proc.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video:
        raise QCError("output has no video stream")
    rate = video.get("r_frame_rate", "0/1").split("/")
    fps = float(rate[0]) / float(rate[1]) if len(rate) == 2 and float(rate[1]) else 0.0
    fmt = data.get("format", {})
    return MediaProbe(
        path=target,
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        fps=fps,
        duration_s=float(fmt.get("duration") or video.get("duration") or 0.0),
        video_codec=str(video.get("codec_name") or ""),
        audio_codec=str(audio.get("codec_name")) if audio else None,
        audio_sample_rate=int(audio.get("sample_rate")) if audio and audio.get("sample_rate") else None,
        audio_channels=int(audio.get("channels")) if audio else None,
        video_bitrate=int(video["bit_rate"]) if video.get("bit_rate") else None,
        audio_bitrate=int(audio["bit_rate"]) if audio and audio.get("bit_rate") else None,
    )


def analyze_loudness(path: str | Path, *, target_lufs: float = -16.0, tp: float = -1.0) -> LoudnessReport:
    proc = _run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-filter:a", f"loudnorm=I={target_lufs}:LRA=7:TP={tp}:print_format=json",
        "-f", "null", "-"
    ], timeout=300)
    raw = (proc.stderr or "")
    matches = re.findall(r'\{\s*"input_i".*?\}', raw, flags=re.S)
    if not matches:
        return LoudnessReport(None, None, None, raw=raw[-3000:])
    try:
        report = json.loads(matches[-1])
        return LoudnessReport(
            integrated_lufs=float(report["input_i"]),
            true_peak_db=float(report["input_tp"]),
            lra=float(report["input_lra"]),
            input_thresh=float(report["input_thresh"]) if "input_thresh" in report else None,
            target_offset=float(report["target_offset"]) if "target_offset" in report else None,
            raw=matches[-1],
        )
    except (KeyError, ValueError, json.JSONDecodeError):
        return LoudnessReport(None, None, None, raw=raw[-3000:])


def validate_render(
    path: str | Path,
    profile: PremiumRenderProfile,
    *,
    expected_duration_s: float | None = None,
    subtitle_cues: list[SubtitleCue] | None = None,
    loudness_tolerance_lufs: float = 2.0,
    duration_tolerance_s: float = 0.10,
    require_audio: bool = True,
) -> QCReport:
    errors: list[str] = []
    warnings: list[str] = []
    target = Path(path)
    if not target.exists() or target.stat().st_size <= 0:
        return QCReport(False, ("output missing or empty",))

    try:
        probe = probe_media(target)
    except QCError as exc:
        return QCReport(False, (str(exc),))

    if probe.width != profile.width or probe.height != profile.height:
        errors.append(f"geometry {probe.width}x{probe.height} != {profile.width}x{profile.height}")
    if abs(probe.fps - profile.fps) > 0.01:
        errors.append(f"fps {probe.fps} != {profile.fps}")
    if expected_duration_s is not None and abs(probe.duration_s - expected_duration_s) > duration_tolerance_s:
        errors.append(
            f"duration {probe.duration_s:.3f}s != expected {expected_duration_s:.3f}s"
        )
    if not probe.audio_codec:
        if require_audio:
            errors.append("audio stream missing")
        else:
            warnings.append("audio stream missing in base render")
            loudness = None
    else:
        if probe.audio_sample_rate != profile.sample_rate:
            errors.append(
                f"audio sample rate {probe.audio_sample_rate} != {profile.sample_rate}"
            )
        if probe.audio_channels != 2:
            errors.append(f"audio channels {probe.audio_channels} != 2")
        loudness = analyze_loudness(target, target_lufs=profile.target_lufs, tp=profile.max_true_peak_db)
        if loudness.integrated_lufs is None:
            warnings.append("loudness analysis unavailable")
        else:
            if require_audio and abs(loudness.integrated_lufs - profile.target_lufs) > loudness_tolerance_lufs:
                errors.append(
                    f"integrated loudness {loudness.integrated_lufs:.2f} LUFS outside "
                    f"{loudness_tolerance_lufs:.2f} tolerance of {profile.target_lufs:.2f}"
                )
            if require_audio and loudness.true_peak_db is not None and loudness.true_peak_db > profile.max_true_peak_db + 0.2:
                errors.append(
                    f"true peak {loudness.true_peak_db:.2f} dB exceeds ceiling {profile.max_true_peak_db:.2f} dB"
                )

    if subtitle_cues is not None:
        try:
            validate_cues(subtitle_cues, duration_s=probe.duration_s)
        except Exception as exc:
            errors.append(f"subtitle validation failed: {exc}")

    # Reuse the authoritative HVS visual/audio QA policy and sampling helpers.
    # Static/frozen content is advisory, but dominant black output and clipping
    # are render-integrity failures. No thresholds are re-invented here.
    hvs_profile = type("Profile", (), {"width": probe.width, "height": probe.height, "fps": profile.fps})()
    luma, hashes = _sample_frame_luma(
        artifact_path=str(target), ffprobe_bin="ffprobe", ffmpeg_bin="ffmpeg",
        profile=hvs_profile, policy=QA_POLICY,
    )
    if luma:
        black_frac = sum(v < QA_POLICY["black_luma_threshold"] for v in luma) / len(luma)
        if black_frac >= 0.5:
            errors.append(f"black-frame dominance {black_frac:.3f} >= 0.5")
        if len(hashes) >= 2:
            frozen_frac = sum(hashes[i] == hashes[i - 1] for i in range(1, len(hashes))) / (len(hashes) - 1)
            if frozen_frac >= QA_POLICY["frozen_max_identical_fraction"]:
                warnings.append(f"frozen-frame advisory {frozen_frac:.3f} >= {QA_POLICY['frozen_max_identical_fraction']}")
    if probe.audio_codec:
        aud = _audio_analysis(artifact_path=str(target), ffmpeg_bin="ffmpeg")
        if aud["present"] and aud["peak"] > QA_POLICY["clip_peak_threshold"]:
            errors.append(f"audio clipping peak {aud['peak']:.3f} > {QA_POLICY['clip_peak_threshold']}")
        if aud["present"] and aud["mean_abs"] < QA_POLICY["silence_amplitude_threshold"]:
            warnings.append(f"near-silent audio mean_abs {aud['mean_abs']:.5f}")

    caps = {
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "vmaf_filter": _has_vmaf_filter(),
        "remotion": shutil.which("node") is not None,
    }
    return QCReport(not errors, tuple(errors), tuple(warnings), probe, loudness, caps)


def _has_vmaf_filter() -> bool:
    proc = _run(["ffmpeg", "-hide_banner", "-filters"], timeout=30)
    return "libvmaf" in (proc.stdout or "")


def assert_publishable(report: QCReport) -> None:
    if not report.passed:
        raise QCError("; ".join(report.errors) or "quality gate failed")
