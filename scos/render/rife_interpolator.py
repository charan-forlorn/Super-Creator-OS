from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from fractions import Fraction
from pathlib import Path
from typing import Any

from scos.media_binaries import resolve_ffmpeg
from scos.media_analysis.source_probe import probe_source

DEFAULT_RIFE_ROOT = Path(os.getenv(
    "SCOS_RIFE_ROOT",
    r"C:\Workspace\super-creator-os\tools\rife\rife-ncnn-vulkan-20221029-windows\rife-ncnn-vulkan-20221029-windows",
))


def resolve_rife_exe() -> Path:
    exe = Path(os.getenv("SCOS_RIFE_EXE", str(DEFAULT_RIFE_ROOT / "rife-ncnn-vulkan.exe"))).resolve()
    if not exe.is_file():
        raise FileNotFoundError(f"RIFE executable not found: {exe}")
    return exe


def resolve_model(name: str = "rife-v4.6") -> Path:
    model = Path(os.getenv("SCOS_RIFE_MODEL", str(DEFAULT_RIFE_ROOT / name))).resolve()
    if not model.is_dir():
        raise FileNotFoundError(f"RIFE model not found: {model}")
    return model


def _run(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)


def _fps_arg(value: float) -> str:
    fraction = Fraction(value).limit_denominator(100000)
    return f"{fraction.numerator}/{fraction.denominator}"


def interpolate_segment_to_video(
    source: str | Path,
    start: float,
    duration: float,
    output: str | Path,
    *,
    model: str = "rife-v4.6",
    gpu: int = 0,
    threads: str = "2:4:4",
    input_fps: float | None = None,
    target_fps: float = 60.0,
    temp_root: str | Path | None = None,
    keep_temp: bool = False,
) -> dict[str, Any]:
    src = Path(source).resolve(); out = Path(output).resolve()
    if not src.is_file(): raise FileNotFoundError(src)
    if duration <= 0: raise ValueError("duration must be > 0")
    probe = probe_source(src)
    if not probe.cfr: raise ValueError("RIFE requires a CFR source")
    probed_fps = float(probe.fps)
    if probed_fps <= 0: raise ValueError("probed source FPS must be > 0")
    if input_fps is not None and abs(float(input_fps) - probed_fps) > 0.001:
        raise ValueError(
            f"input_fps={float(input_fps):.6f} does not match probed source FPS={probed_fps:.6f}"
        )
    source_fps = probed_fps
    if target_fps <= 0: raise ValueError("target FPS must be > 0")
    ffmpeg = resolve_ffmpeg(); rife = resolve_rife_exe(); model_path = resolve_model(model)
    root = Path(temp_root).resolve() if temp_root else Path(tempfile.mkdtemp(prefix="scos-rife-"))
    root.mkdir(parents=True, exist_ok=True)
    inp = root / "in"; frames = root / "out"; inp.mkdir(exist_ok=True); frames.mkdir(exist_ok=True)
    cleanup = not keep_temp
    try:
        extract = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(src),
            "-ss", f"{start:.9f}", "-t", f"{duration:.9f}", "-map", "0:v:0", "-an",
            "-fps_mode", "passthrough", "-c:v", "libwebp", "-q:v", "85", "-y", str(inp / "%08d.webp"),
        ]
        t0 = time.perf_counter(); p = _run(extract, timeout=900)
        if p.returncode: raise RuntimeError(p.stderr[-3000:])
        input_count = len(list(inp.glob("*.webp")))
        if input_count < 2: raise RuntimeError(f"RIFE needs >=2 source frames, got {input_count}")
        target = max(input_count, round(duration * target_fps))
        output_fps = float(target_fps)
        rife_cmd = [str(rife), "-i", str(inp), "-o", str(frames), "-m", str(model_path), "-g", str(gpu), "-j", threads, "-n", str(target), "-f", "%08d.png"]
        p = _run(rife_cmd, timeout=max(900, int(duration * 60)))
        if p.returncode: raise RuntimeError(p.stderr[-4000:])
        output_count = len(list(frames.glob("*.png")))
        if output_count != target: raise RuntimeError(f"RIFE frame count mismatch: expected {target}, got {output_count}")
        encoded = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-framerate", _fps_arg(output_fps),
            "-i", str(frames / "%08d.png"), "-frames:v", str(target),
            "-c:v", "h264_nvenc", "-preset", "p3", "-tune", "hq", "-rc", "vbr", "-cq", "19", "-b:v", "0",
            "-bf", "3", "-b_ref_mode", "middle", "-temporal-aq", "1", "-rc-lookahead", "16",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-y", str(out),
        ]
        p = _run(encoded, timeout=max(600, int(duration * 30)))
        if p.returncode: raise RuntimeError(p.stderr[-3000:])
        return {
            "output": str(out), "input_frames": input_count, "output_frames": output_count,
            "input_fps": source_fps, "output_fps": output_fps, "target_fps": float(target_fps),
            "elapsed_s": time.perf_counter() - t0,
            "model": str(model_path), "gpu": gpu, "threads": threads,
        }
    finally:
        if cleanup: shutil.rmtree(root, ignore_errors=True)
