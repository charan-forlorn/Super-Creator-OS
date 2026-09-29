"""Deterministic local video-encoder discovery and bounded GPU-aware routing.

This module only decides the encoder for SCOS intermediate render work. It never
changes the final video-use engine contract. AUTO prefers a known hardware
encoder only when FFmpeg advertises it; unavailable forced hardware paths fail
closed instead of silently falling back.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

HardwareMode = Literal["auto", "off", "required"]


@dataclass(frozen=True)
class EncoderPlan:
    backend_id: str
    ffmpeg_encoder: str
    args: tuple[str, ...]
    hardware: bool
    accelerator: str
    reason: str

    @property
    def signature(self) -> str:
        return "|".join(
            (
                self.backend_id,
                self.ffmpeg_encoder,
                "hw" if self.hardware else "cpu",
                self.accelerator,
                *self.args,
            )
        )


_PREFERENCES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "nvenc",
        "h264_nvenc",
        "nvidia",
        ("-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0"),
    ),
    (
        "qsv",
        "h264_qsv",
        "intel-qsv",
        ("-preset", "medium", "-global_quality", "23"),
    ),
    (
        "amf",
        "h264_amf",
        "amd-amf",
        ("-quality", "quality", "-qp_i", "22", "-qp_p", "23"),
    ),
    (
        "vaapi",
        "h264_vaapi",
        "vaapi",
        ("-qp", "23"),
    ),
)

_CPU = EncoderPlan(
    backend_id="libx264",
    ffmpeg_encoder="libx264",
    args=("-preset", "fast", "-crf", "20"),
    hardware=False,
    accelerator="cpu",
    reason="CPU fallback",
)


def _parse_mode(value: str | None) -> HardwareMode:
    mode = (value or "auto").strip().lower()
    if mode not in {"auto", "off", "required"}:
        raise ValueError("SCOS_RENDER_GPU_MODE must be auto, off, or required")
    return mode  # type: ignore[return-value]


@lru_cache(maxsize=4)
def available_encoders(ffmpeg_bin: str = "ffmpeg") -> frozenset[str]:
    proc = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg encoder discovery failed: {proc.stderr.strip()[-400:]}")
    names: set[str] = set()
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        stripped = line.strip()
        for candidate in (
            "h264_nvenc",
            "h264_qsv",
            "h264_amf",
            "h264_vaapi",
        ):
            if candidate in stripped:
                names.add(candidate)
    return frozenset(names)


@lru_cache(maxsize=16)
def encoder_runtime_ok(
    ffmpeg_bin: str,
    encoder: str,
    args: tuple[str, ...],
) -> bool:
    """Verify that the advertised encoder can actually initialize at runtime."""
    probe = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=256x144:r=1",
        "-frames:v",
        "1",
        "-c:v",
        encoder,
        *args,
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(
        probe,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return proc.returncode == 0


def choose_encoder(
    *,
    ffmpeg_bin: str = "ffmpeg",
    mode: HardwareMode | None = None,
) -> EncoderPlan:
    selected_mode = _parse_mode(mode or os.environ.get("SCOS_RENDER_GPU_MODE"))
    if selected_mode == "off":
        return EncoderPlan(
            **{**_CPU.__dict__, "reason": "CPU fallback; GPU routing disabled by operator mode"}
        )

    encoders = available_encoders(ffmpeg_bin)
    for backend_id, encoder, accelerator, args in _PREFERENCES:
        if encoder in encoders and encoder_runtime_ok(ffmpeg_bin, encoder, args):
            return EncoderPlan(
                backend_id=backend_id,
                ffmpeg_encoder=encoder,
                args=args,
                hardware=True,
                accelerator=accelerator,
                reason=f"FFmpeg advertises {encoder} and runtime probe passed",
            )

    if selected_mode == "required":
        raise RuntimeError("GPU-required render mode requested but no supported hardware encoder is available")
    return _CPU


__all__ = [
    "EncoderPlan",
    "HardwareMode",
    "available_encoders",
    "choose_encoder",
    "encoder_runtime_ok",
]
