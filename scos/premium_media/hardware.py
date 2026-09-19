"""Local hardware capability detection and deterministic encoder selection."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, replace

from .models import PremiumRenderProfile


@dataclass(frozen=True)
class HardwareCapabilities:
    ffmpeg_path: str | None
    encoders: tuple[str, ...]
    gpu_name: str | None = None
    gpu_memory_mb: int | None = None

    @property
    def nvenc_available(self) -> bool:
        return any(name.endswith("_nvenc") for name in self.encoders)


def _run_text(args: list[str]) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout or ""


def detect_hardware() -> HardwareCapabilities:
    ffmpeg = shutil.which("ffmpeg")
    encoders: list[str] = []
    if ffmpeg:
        output = _run_text([ffmpeg, "-hide_banner", "-encoders"])
        for codec in ("h264_nvenc", "hevc_nvenc", "av1_nvenc"):
            if codec in output:
                encoders.append(codec)
    gpu_name = None
    gpu_memory_mb = None
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        output = _run_text(
            [
                nvidia_smi,
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ]
        ).strip()
        if output:
            first = output.splitlines()[0]
            pieces = [part.strip() for part in first.split(",", 1)]
            gpu_name = pieces[0] or None
            if len(pieces) == 2:
                try:
                    gpu_memory_mb = int(float(pieces[1]))
                except ValueError:
                    gpu_memory_mb = None
    return HardwareCapabilities(
        ffmpeg_path=ffmpeg,
        encoders=tuple(encoders),
        gpu_name=gpu_name,
        gpu_memory_mb=gpu_memory_mb,
    )


def resolve_finish_profile(
    profile: PremiumRenderProfile,
    *,
    capabilities: HardwareCapabilities | None = None,
) -> PremiumRenderProfile:
    caps = capabilities or detect_hardware()
    mode = profile.render_acceleration
    if mode not in {"cpu", "auto", "gpu"}:
        raise ValueError(f"unknown render_acceleration mode: {mode!r}")
    if mode == "cpu":
        return profile
    if not caps.nvenc_available:
        if mode == "gpu":
            raise RuntimeError("GPU render requested but NVENC is unavailable")
        return profile
    if profile.video_codec not in {"libx264", "h264_nvenc"}:
        return profile
    return replace(
        profile,
        video_codec="h264_nvenc",
        video_preset=profile.nvenc_preset,
    )



def encoder_args(profile: PremiumRenderProfile) -> list[str]:
    """Return codec-specific FFmpeg video-rate arguments."""
    if profile.video_codec == "h264_nvenc":
        cq = profile.nvenc_cq if profile.nvenc_cq is not None else profile.video_crf
        return [
            "-c:v", "h264_nvenc",
            "-rc:v", "vbr",
            "-cq:v", str(cq),
            "-b:v", "0",
            "-preset", profile.video_preset,
        ]
    return [
        "-c:v", profile.video_codec,
        "-crf", str(profile.video_crf),
        "-preset", profile.video_preset,
    ]
