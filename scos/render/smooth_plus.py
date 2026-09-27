from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from scos.media_binaries import resolve_ffmpeg
from scos.media_analysis.adaptive_smooth_plus_v2 import analyze_adaptive_smooth_plus, split_scene_safe_ranges
from scos.media_analysis.adaptive_smooth_plus_v3 import gate_smooth_spans_with_canaries
from scos.media_analysis.source_probe import probe_source
from .rife_interpolator import interpolate_segment_to_video, resolve_model, resolve_rife_exe

TARGET_FPS = 60.0


@dataclass(frozen=True)
class TimelinePart:
    start: float
    end: float
    mode: str
    file: str | None = None
    def to_dict(self) -> dict[str, Any]: return asdict(self)


def _segments(keep_ranges: list[tuple[float, float]], scene_cuts: list[float]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for _, start, end in split_scene_safe_ranges(keep_ranges, scene_cuts):
        if end - start > 0.05: out.append((start, end))
    return out


def _assert_scene_safe(spans: list[tuple[float, float]], scene_cuts: list[float]) -> None:
    for start, end in spans:
        for cut in scene_cuts:
            if start < cut < end:
                raise ValueError(f"SMOOTH+ span crosses hard scene boundary: {start:.6f}-{end:.6f} / {cut:.6f}")


def _timeline_parts(keep_ranges: list[tuple[float, float]], smooth_spans: list[tuple[float, float]]) -> list[TimelinePart]:
    spans = sorted(smooth_spans)
    parts: list[TimelinePart] = []
    for keep_start, keep_end in keep_ranges:
        cursor = keep_start
        for smooth_start, smooth_end in spans:
            if smooth_end <= keep_start or smooth_start >= keep_end: continue
            smooth_start = max(smooth_start, keep_start); smooth_end = min(smooth_end, keep_end)
            if smooth_start > cursor + 1e-7:
                parts.append(TimelinePart(cursor, smooth_start, "PRESERVE"))
            if smooth_end > smooth_start + 1e-7:
                parts.append(TimelinePart(smooth_start, smooth_end, "SMOOTH+"))
                cursor = smooth_end
        if cursor < keep_end - 1e-7:
            parts.append(TimelinePart(cursor, keep_end, "PRESERVE"))
    return parts


def _compose_timeline(source: Path, parts: list[TimelinePart], output: Path, *, target_fps: float = TARGET_FPS) -> dict[str, Any]:
    if not parts: raise ValueError("no timeline parts")
    ffmpeg = resolve_ffmpeg()
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(source)]
    input_files: list[Path] = []
    normalized: list[TimelinePart] = []
    for part in parts:
        if part.mode == "SMOOTH+":
            if not part.file: raise ValueError("SMOOTH+ part missing rendered file")
            path = Path(part.file).resolve()
            cmd += ["-i", str(path)]
            input_files.append(path)
            normalized.append(part)
        else:
            normalized.append(part)
    filters: list[str] = []
    video_labels: list[str] = []
    audio_labels: list[str] = []
    smooth_input_index = 1
    for idx, part in enumerate(normalized):
        if part.mode == "SMOOTH+":
            filters.append(f"[{smooth_input_index}:v:0]fps={target_fps:.6f}:round=near,setpts=PTS-STARTPTS,format=yuv420p[v{idx}]")
            smooth_input_index += 1
        else:
            filters.append(f"[0:v:0]trim=start={part.start:.9f}:end={part.end:.9f},setpts=PTS-STARTPTS,fps={target_fps:.6f}:round=near,format=yuv420p[v{idx}]")
        video_labels.append(f"[v{idx}]")
        audio_labels.append(f"[a{idx}]")
        filters.append(f"[0:a:0]atrim=start={part.start:.9f}:end={part.end:.9f},asetpts=PTS-STARTPTS[a{idx}]")
    filters.append("".join(video_labels) + f"concat=n={len(normalized)}:v=1:a=0[vcat]")
    filters.append("".join(audio_labels) + f"concat=n={len(normalized)}:v=0:a=1[acat]")
    cmd += [
        "-filter_complex", ";".join(filters), "-map", "[vcat]", "-map", "[acat]",
        "-c:v", "h264_nvenc", "-preset", "p3", "-tune", "hq", "-rc", "vbr", "-cq", "19", "-b:v", "0",
        "-bf", "3", "-b_ref_mode", "middle", "-temporal-aq", "1", "-rc-lookahead", "16",
        "-pix_fmt", "yuv420p", "-r", str(target_fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", "-y", str(output),
    ]
    t0 = time.perf_counter(); p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if p.returncode: raise RuntimeError((p.stderr or "")[-5000:])
    return {
        "output": str(output), "elapsed_s": time.perf_counter() - t0,
        "target_fps": target_fps, "timeline_parts": [part.to_dict() for part in normalized],
        "audio_timeline_mode": "source_segment_trim_concat",
    }


def _render_strategy(
    source: str | Path,
    keep_ranges: list[tuple[float, float]],
    scene_cuts: list[float],
    output: str | Path,
    smooth_spans: list[tuple[float, float]],
    *,
    model: str = "rife-v4.6",
    gpu: int = 0,
    threads: str = "2:4:4",
    input_fps: float | None = None,
    mode: str = "adaptive",
) -> dict[str, Any]:
    src = Path(source).resolve(); out = Path(output).resolve(); probe = probe_source(src)
    if not probe.cfr: raise ValueError("SMOOTH+ requires a CFR source")
    source_fps = float(probe.fps)
    if source_fps <= 0: raise ValueError("probed source FPS must be > 0")
    if input_fps is not None and abs(float(input_fps) - source_fps) > 0.001:
        raise ValueError(
            f"input_fps={float(input_fps):.6f} does not match probed source FPS={source_fps:.6f}"
        )
    _assert_scene_safe(smooth_spans, scene_cuts)
    temp = Path(tempfile.mkdtemp(prefix="scos-smoothplus-v2-"))
    try:
        parts = _timeline_parts(keep_ranges, smooth_spans)
        reports: list[dict[str, Any]] = []; rendered_parts: list[TimelinePart] = []
        smooth_index = 0
        for part in parts:
            if part.mode != "SMOOTH+":
                rendered_parts.append(part); continue
            seg = temp / f"rife_{smooth_index:03d}.mp4"
            smooth_index += 1
            try:
                report = interpolate_segment_to_video(
                    src, part.start, part.end - part.start, seg,
                    model=model, gpu=gpu, threads=threads, input_fps=source_fps,
                    target_fps=TARGET_FPS,
                    temp_root=temp / f"rife_frames_{smooth_index:03d}", keep_temp=False,
                )
                reports.append(report); rendered_parts.append(TimelinePart(part.start, part.end, "SMOOTH+", str(seg)))
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                reports.append({"status":"FALLBACK_PRESERVE","start":part.start,"end":part.end,"error":str(exc)})
                rendered_parts.append(TimelinePart(part.start, part.end, "PRESERVE"))
        effective_smooth_seconds = sum(p.end - p.start for p in rendered_parts if p.mode == "SMOOTH+")
        keep_seconds = sum(b - a for a, b in keep_ranges)
        composition_fps = TARGET_FPS if effective_smooth_seconds > 1e-7 else source_fps
        composition = _compose_timeline(src, rendered_parts, out, target_fps=composition_fps)
        fallback_count = sum(1 for r in reports if r.get("status") == "FALLBACK_PRESERVE")
        return {
            "status": "CANDIDATE", "mode": mode, "output": str(out), "source_fps": source_fps,
            "target_fps": composition_fps, "requested_smooth_spans": [list(x) for x in smooth_spans],
            "effective_smooth_seconds": effective_smooth_seconds, "keep_seconds": keep_seconds,
            "interpolation_fraction": effective_smooth_seconds / keep_seconds if keep_seconds else 0.0,
            "fallback_count": fallback_count, "rife_reports": reports, "composition": composition,
            "automatic_promotion": False,
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def render_smooth_plus(
    source: str | Path,
    keep_ranges: list[tuple[float, float]],
    scene_cuts: list[float],
    output: str | Path,
    *,
    duplicate_ratio: float,
    threshold: float = 0.35,
    model: str = "rife-v4.6",
    gpu: int = 0,
) -> dict[str, Any]:
    if duplicate_ratio < threshold:
        raise ValueError(f"SMOOTH+ gate not met: duplicate_ratio={duplicate_ratio:.4f} < {threshold:.4f}")
    spans = _segments(keep_ranges, scene_cuts)
    return _render_strategy(source, keep_ranges, scene_cuts, output, spans, model=model, gpu=gpu, mode="full")



def render_adaptive_smooth_plus_v3(
    source: str | Path,
    keep_ranges: list[tuple[float, float]],
    scene_cuts: list[float],
    output: str | Path,
    *,
    duplicate_ratio: float,
    threshold: float = 0.35,
    model: str = "rife-v4.6",
    gpu: int = 0,
    threads: str = "2:4:4",
    canary_duration_s: float = 0.40,
) -> dict[str, Any]:
    """Adaptive SMOOTH+ V3: V2 route -> temporal quality canary -> full-window RIFE."""
    src = Path(source).resolve()
    plan = analyze_adaptive_smooth_plus(src, keep_ranges, scene_cuts)
    if duplicate_ratio < threshold:
        plan = plan.__class__(
            plan.source_fps, plan.target_fps, plan.window_s, tuple(), tuple(),
            {**plan.summary, "global_gate": "PRESERVE", "global_duplicate_ratio": duplicate_ratio, "threshold": threshold},
        )
    try:
        resolve_rife_exe(); resolve_model(model)
        rife_available = True
    except FileNotFoundError:
        rife_available = False

    requested = list(plan.smooth_spans) if rife_available else []
    accepted: list[tuple[float, float]] = []
    canary_evidence: list[Any] = []
    canary_root = Path(tempfile.mkdtemp(prefix="scos-smoothplus-v3-canary-"))
    try:
        if requested:
            accepted, canary_evidence = gate_smooth_spans_with_canaries(
                src, requested, temp_root=canary_root, model=model, gpu=gpu,
                threads=threads, canary_duration_s=canary_duration_s,
            )
        result = _render_strategy(
            src, keep_ranges, scene_cuts, output, accepted,
            model=model, gpu=gpu, threads=threads, input_fps=probe_source(src).fps, mode="adaptive_v3",
        )
    finally:
        shutil.rmtree(canary_root, ignore_errors=True)

    result["adaptive_plan"] = plan.to_dict()
    result["rife_available"] = rife_available
    result["rife_unavailable_fallback"] = not rife_available
    result["quality_gate"] = "QUALITY_CALIBRATED_CANARY_V3"
    result["requested_smooth_spans"] = [list(x) for x in requested]
    result["accepted_smooth_spans"] = [list(x) for x in accepted]
    result["quality_canaries"] = [item.to_dict() for item in canary_evidence]
    rejected = [item for item in canary_evidence if item.decision != "SMOOTH+"]
    result["quality_rejected_count"] = len(rejected)
    result["promotion_gate"] = (
        "REVIEW"
        if (not rife_available) or rejected or result.get("fallback_count") or (requested and not accepted)
        else "CANDIDATE"
    )
    result["automatic_promotion"] = False
    return result

def render_adaptive_smooth_plus(
    source: str | Path,
    keep_ranges: list[tuple[float, float]],
    scene_cuts: list[float],
    output: str | Path,
    *,
    duplicate_ratio: float,
    threshold: float = 0.35,
    model: str = "rife-v4.6",
    gpu: int = 0,
    threads: str = "2:4:4",
) -> dict[str, Any]:
    src = Path(source).resolve(); probe = probe_source(src)
    plan = analyze_adaptive_smooth_plus(src, keep_ranges, scene_cuts)
    if duplicate_ratio < threshold:
        plan = plan.__class__(plan.source_fps, plan.target_fps, plan.window_s, tuple(), tuple(), {**plan.summary, "global_gate":"PRESERVE", "global_duplicate_ratio":duplicate_ratio, "threshold":threshold})
    try:
        resolve_rife_exe(); resolve_model(model)
        rife_available = True
    except FileNotFoundError:
        rife_available = False
    requested = list(plan.smooth_spans) if rife_available else []
    result = _render_strategy(
        src, keep_ranges, scene_cuts, output, requested,
        model=model, gpu=gpu, threads=threads, input_fps=probe.fps, mode="adaptive"
    )
    result["adaptive_plan"] = plan.to_dict()
    result["rife_available"] = rife_available
    result["rife_unavailable_fallback"] = not rife_available
    result["promotion_gate"] = "REVIEW" if (not rife_available) or plan.summary.get("decision_counts", {}).get("REVIEW", 0) or result.get("fallback_count") else "CANDIDATE"
    return result
