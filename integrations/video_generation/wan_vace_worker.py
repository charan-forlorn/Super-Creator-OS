"""Worker process for local Wan VACE generation.

The worker is intentionally isolated from SCOS runtime dependencies. It loads one
pipeline per process, executes a single JSON job, verifies the MP4, then exits.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from diffusers import DiffusionPipeline

from resource_policy import decide_resources
from diffusers.utils import export_to_video, load_image


def _probe_video(path: Path) -> dict[str, object]:
    import subprocess

    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,width,height,r_frame_rate,codec_name",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[-500:])
    data = json.loads(proc.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    return {
        "duration_s": float(data.get("format", {}).get("duration") or 0.0),
        "size_bytes": int(data.get("format", {}).get("size") or path.stat().st_size),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": video.get("r_frame_rate"),
        "codec": video.get("codec_name"),
    }


def _motion_score(frames: list[np.ndarray]) -> float:
    if len(frames) < 2:
        return 0.0
    a = np.asarray(frames[0], dtype=np.float32)
    diffs = []
    for frame in frames[1:]:
        b = np.asarray(frame, dtype=np.float32)
        diffs.append(float(np.mean(np.abs(b - a)) / 255.0))
        a = b
    return round(float(np.mean(diffs)), 6)


def generate(job: dict[str, object]) -> dict[str, object]:
    model_dir = Path(str(job["model_dir"])).resolve()
    reference_path = Path(str(job["reference_image"])).resolve()
    output_path = Path(str(job["output_path"])).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    requested_mode = str(job.get("load_mode", "auto")).lower()
    total_vram_gb = (
        torch.cuda.get_device_properties(0).total_memory / (1024**3)
        if torch.cuda.is_available() else 0.0
    )
    decision = decide_resources(
        total_vram_gb=total_vram_gb,
        width=int(job["width"]),
        height=int(job["height"]),
        requested_load_mode=requested_mode,
        adaptive_resolution=bool(job.get("adaptive_resolution", True)),
    )
    use_cpu_offload = decision.load_mode == "cpu_offload"
    if use_cpu_offload:
        pipe = DiffusionPipeline.from_pretrained(
            str(model_dir),
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
        )
        pipe.enable_model_cpu_offload()
        load_mode = "cpu_offload"
    else:
        pipe = DiffusionPipeline.from_pretrained(
            str(model_dir),
            torch_dtype=torch.float16,
            device_map="cuda",
            low_cpu_mem_usage=True,
        )
        load_mode = "cuda"

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    image = load_image(str(reference_path)).convert("RGB")
    seed = int(job["seed"])
    generator = torch.Generator(device="cuda").manual_seed(seed)

    result = pipe(
        prompt=str(job["prompt"]),
        reference_images=[image],
        height=decision.effective_height,
        width=decision.effective_width,
        num_frames=int(job["num_frames"]),
        num_inference_steps=int(job["num_inference_steps"]),
        guidance_scale=float(job["guidance_scale"]),
        generator=generator,
        output_type="np",
    )
    frames = result.frames[0]
    peak_vram_mib = (
        round(torch.cuda.max_memory_allocated() / (1024**2), 1)
        if torch.cuda.is_available() else 0.0
    )
    fps = int(job["fps"])
    export_to_video(frames, str(output_path), fps=fps)

    probe = _probe_video(output_path)
    motion_score = _motion_score(list(frames))
    return {
        "status": "PASS",
        "scene_id": job["scene_id"],
        "output_path": str(output_path),
        "probe": probe,
        "motion_score": motion_score,
        "seed": seed,
        "frames": len(frames),
        "fps": fps,
        "load_mode": load_mode,
        "total_vram_gb": round(total_vram_gb, 2),
        "requested_width": decision.requested_width,
        "requested_height": decision.requested_height,
        "effective_width": decision.effective_width,
        "effective_height": decision.effective_height,
        "adaptive_resolution": decision.adaptive_resolution,
        "resource_policy_reason": decision.reason,
        "peak_vram_mib": peak_vram_mib,
        "generation_seconds": round(time.perf_counter() - started, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-json")
    parser.add_argument("--job-file")
    args = parser.parse_args()
    try:
        if bool(args.job_json) == bool(args.job_file):
            raise ValueError("exactly one of --job-json or --job-file is required")
        if args.job_file:
            job = json.loads(Path(args.job_file).read_text(encoding="utf-8"))
        else:
            job = json.loads(args.job_json)
        result = generate(job)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
