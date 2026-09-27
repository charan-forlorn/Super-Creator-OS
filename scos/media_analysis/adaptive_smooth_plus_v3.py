from __future__ import annotations

import json
import math
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from scos.media_binaries import resolve_ffmpeg
from scos.render.rife_interpolator import interpolate_segment_to_video
from .adaptive_smooth_plus_v2 import TemporalWindowEvidence
from .source_probe import probe_source

ANALYSIS_WIDTH = 320
MIN_CANARY_S = 0.30
DEFAULT_CANARY_S = 0.40
MAX_CANARY_S = 0.50
MIN_VALID_TRIPLE_RATIO = 0.40
ROBUST_Z_LIMIT = 4.0
EPS = 1e-5


@dataclass(frozen=True)
class CanaryEvidence:
    window_start: float
    window_end: float
    canary_start: float
    canary_end: float
    sample_count: int
    valid_triple_ratio: float
    source_baseline: dict[str, float]
    candidate_metrics: dict[str, float]
    robust_z: dict[str, float]
    calibration_z: dict[str, float]
    quality_score: float
    decision: str
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _height(width: int, source_width: int, source_height: int) -> int:
    return max(2, round(ANALYSIS_WIDTH * source_height / max(1, source_width) / 2) * 2)


def _extract_gray(path: str | Path, start: float, duration: float, fps: float, width: int, height: int) -> np.ndarray:
    ff = resolve_ffmpeg()
    cmd = [
        ff, "-hide_banner", "-loglevel", "error", "-ss", f"{start:.9f}", "-t", f"{duration:.9f}",
        "-i", str(path), "-an", "-vf", f"scale={width}:{height},format=gray,fps={fps:.9f}",
        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ]
    p = subprocess.run(cmd, capture_output=True, timeout=max(120, int(duration * 30) + 120), check=False)
    if p.returncode:
        raise RuntimeError((p.stderr or b"").decode("utf-8", "replace")[-3000:])
    frame_bytes = width * height
    if len(p.stdout) < frame_bytes:
        raise RuntimeError("quality canary produced no usable frames")
    count = len(p.stdout) // frame_bytes
    return np.frombuffer(p.stdout[:count * frame_bytes], dtype=np.uint8).reshape((count, height, width)).astype(np.float32) / 255.0


def choose_canary_span(start: float, end: float, source_fps: float, *, duration_s: float = DEFAULT_CANARY_S) -> tuple[float, float]:
    if end <= start:
        raise ValueError("invalid window span")
    span = end - start
    duration = min(MAX_CANARY_S, max(MIN_CANARY_S, min(duration_s, span)))
    frame_margin = 1.0 / max(source_fps, 1.0)
    if span > duration + 2.0 * frame_margin:
        duration = min(duration, span - 2.0 * frame_margin)
    duration = max(MIN_CANARY_S if span >= MIN_CANARY_S else span, duration)
    center = (start + end) / 2.0
    canary_start = max(start + frame_margin, center - duration / 2.0)
    canary_end = min(end - frame_margin, canary_start + duration)
    canary_start = max(start, canary_end - duration)
    if canary_end <= canary_start:
        canary_start, canary_end = start, end
    return round(canary_start, 9), round(canary_end, 9)


def _mean_abs(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.mean(np.abs(a - b), axis=(1, 2))


def _natural_triplets(frames: np.ndarray) -> dict[str, np.ndarray]:
    if len(frames) < 3:
        return {k: np.asarray([], dtype=np.float32) for k in ("path_excess", "asymmetry", "blend_deviation", "jerk")}
    a, b, c = frames[:-2], frames[1:-1], frames[2:]
    d_ab = _mean_abs(a, b)
    d_bc = _mean_abs(b, c)
    d_ac = _mean_abs(a, c)
    denom = np.maximum(d_ac, EPS)
    blend = 0.5 * (a + c)
    blend_dev = np.mean(np.abs(b - blend), axis=(1, 2)) / denom
    path_excess = np.maximum(0.0, (d_ab + d_bc - d_ac) / denom)
    asymmetry = np.abs(d_ab - d_bc) / denom
    jerk = np.abs(d_bc - d_ab)
    valid = d_ac > 0.001
    return {
        "path_excess": path_excess[valid],
        "asymmetry": asymmetry[valid],
        "blend_deviation": blend_dev[valid],
        "jerk": jerk[valid],
    }


def _candidate_triplets(frames: np.ndarray) -> dict[str, np.ndarray]:
    if len(frames) < 3:
        return {k: np.asarray([], dtype=np.float32) for k in ("path_excess", "asymmetry", "blend_deviation", "jerk")}
    usable = ((len(frames) - 1) // 2) * 2 + 1
    f = frames[:usable]
    a, m, c = f[:-2:2], f[1:-1:2], f[2::2]
    d_am = _mean_abs(a, m)
    d_mc = _mean_abs(m, c)
    d_ac = _mean_abs(a, c)
    denom = np.maximum(d_ac, EPS)
    blend = 0.5 * (a + c)
    blend_dev = np.mean(np.abs(m - blend), axis=(1, 2)) / denom
    path_excess = np.maximum(0.0, (d_am + d_mc - d_ac) / denom)
    asymmetry = np.abs(d_am - d_mc) / denom
    jerk = np.abs(d_mc - d_am)
    valid = d_ac > 0.001
    return {
        "path_excess": path_excess[valid],
        "asymmetry": asymmetry[valid],
        "blend_deviation": blend_dev[valid],
        "jerk": jerk[valid],
    }


def _robust_stats(values: np.ndarray) -> tuple[float, float]:
    if values.size == 0:
        return 0.0, 1.0
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median))) * 1.4826
    scale = max(mad, abs(median) * 0.25, 1e-4)
    return median, scale


def _metrics_summary(values: dict[str, np.ndarray]) -> dict[str, float]:
    result: dict[str, float] = {}
    for key, arr in values.items():
        result[f"{key}_median"] = float(np.median(arr)) if arr.size else 0.0
        result[f"{key}_p95"] = float(np.percentile(arr, 95)) if arr.size else 0.0
    return result


def evaluate_canary_pair(source_frames: np.ndarray, candidate_frames: np.ndarray) -> dict[str, Any]:
    natural = _natural_triplets(source_frames)
    candidate = _candidate_triplets(candidate_frames)
    natural_valid = min((len(x) for x in natural.values()), default=0)
    candidate_valid = min((len(x) for x in candidate.values()), default=0)
    source_count = max(0, len(source_frames) - 2)
    candidate_count = max(0, (len(candidate_frames) - 1) // 2)
    valid_ratio = min(1.0, (candidate_valid / max(1, candidate_count))) if candidate_count else 0.0
    baseline: dict[str, float] = {}
    metrics: dict[str, float] = {}
    z: dict[str, float] = {}
    if natural_valid == 0 or candidate_valid == 0:
        return {
            "sample_count": candidate_valid,
            "valid_triple_ratio": valid_ratio,
            "source_baseline": baseline,
            "candidate_metrics": metrics,
            "robust_z": z,
            "calibration_z": {},
            "quality_score": 0.0,
            "decision": "REVIEW",
            "reasons": ("insufficient_temporal_samples",),
        }
    for key in ("path_excess", "asymmetry", "blend_deviation", "jerk"):
        n = natural[key]
        c = candidate[key]
        baseline[f"{key}_median"] = float(np.median(n))
        baseline[f"{key}_p95"] = float(np.percentile(n, 95))
        metrics[f"{key}_median"] = float(np.median(c))
        metrics[f"{key}_p95"] = float(np.percentile(c, 95))
        center, scale = _robust_stats(n)
        z[key] = max(0.0, (float(np.median(c)) - center) / scale)
    positive = [value for value in z.values() if math.isfinite(value)]
    worst_z = max(positive, default=float("inf"))
    avg_z = float(np.mean(positive)) if positive else float("inf")
    score = max(0.0, min(1.0, 1.0 / (1.0 + avg_z)))
    reasons: list[str] = []
    decision = "SMOOTH+"
    if valid_ratio < MIN_VALID_TRIPLE_RATIO:
        decision = "REVIEW"
        reasons.append("insufficient_valid_temporal_triplets")
    if worst_z > ROBUST_Z_LIMIT:
        decision = "REVIEW"
        reasons.append("temporal_quality_outlier")
    if decision == "SMOOTH+":
        reasons.append("canary_temporally_coherent")
    return {
        "sample_count": candidate_valid,
        "source_sample_count": natural_valid,
        "valid_triple_ratio": valid_ratio,
        "source_baseline": baseline,
        "candidate_metrics": metrics,
        "robust_z": z,
        "calibration_z": {},
        "quality_score": score,
        "decision": decision,
        "reasons": tuple(reasons),
    }


def run_quality_canary(
    source: str | Path,
    window: TemporalWindowEvidence | tuple[float, float],
    *,
    temp_root: str | Path,
    model: str = "rife-v4.6",
    gpu: int = 0,
    threads: str = "2:4:4",
    canary_duration_s: float = DEFAULT_CANARY_S,
) -> CanaryEvidence:
    source_path = Path(source).resolve()
    probe = probe_source(source_path)
    start, end = (window.start, window.end) if isinstance(window, TemporalWindowEvidence) else window
    canary_start, canary_end = choose_canary_span(float(start), float(end), probe.fps, duration_s=canary_duration_s)
    canary_duration = canary_end - canary_start
    width = ANALYSIS_WIDTH
    height = _height(width, probe.width, probe.height)
    source_frames = _extract_gray(source_path, canary_start, canary_duration, probe.fps, width, height)
    canary_path = Path(temp_root) / "canary.mp4"
    render = interpolate_segment_to_video(
        source_path, canary_start, canary_duration, canary_path,
        model=model, gpu=gpu, threads=threads, input_fps=probe.fps, target_fps=60.0,
        temp_root=Path(temp_root) / "rife", keep_temp=False,
    )
    candidate_probe = probe_source(canary_path)
    candidate_frames = _extract_gray(canary_path, 0.0, candidate_probe.duration_s, 60.0, width, height)
    evaluated = evaluate_canary_pair(source_frames, candidate_frames)
    return CanaryEvidence(
        window_start=round(float(start), 9), window_end=round(float(end), 9),
        canary_start=round(canary_start, 9), canary_end=round(canary_end, 9),
        sample_count=int(evaluated["sample_count"]), valid_triple_ratio=float(evaluated["valid_triple_ratio"]),
        source_baseline=evaluated["source_baseline"], candidate_metrics=evaluated["candidate_metrics"],
        robust_z=evaluated["robust_z"], calibration_z=evaluated.get("calibration_z", {}), quality_score=float(evaluated["quality_score"]),
        decision=str(evaluated["decision"]), reasons=tuple(evaluated["reasons"]),
    )


def _cross_window_calibration(evidence: list[CanaryEvidence]) -> tuple[dict[str, float], dict[int, dict[str, float]]]:
    metric_keys = ("path_excess_median", "blend_deviation_median", "asymmetry_median", "jerk_median")
    centers: dict[str, float] = {}
    scales: dict[str, float] = {}
    z_by_index: dict[int, dict[str, float]] = {i: {} for i in range(len(evidence))}
    for key in metric_keys:
        values = np.asarray([item.candidate_metrics.get(key, 0.0) for item in evidence], dtype=np.float32)
        center, scale = _robust_stats(values)
        centers[key] = center
        scales[key] = scale
        for index, value in enumerate(values):
            z_by_index[index][key] = max(0.0, (float(value) - center) / scale)
    return centers, z_by_index


def gate_smooth_spans_with_canaries(
    source: str | Path,
    smooth_spans: list[tuple[float, float]],
    *,
    temp_root: str | Path,
    model: str = "rife-v4.6",
    gpu: int = 0,
    threads: str = "2:4:4",
    canary_duration_s: float = DEFAULT_CANARY_S,
) -> tuple[list[tuple[float, float]], list[CanaryEvidence]]:
    """Run one RIFE canary per candidate window, then calibrate decisions across those observed canaries."""
    accepted: list[tuple[float, float]] = []
    evidence: list[CanaryEvidence] = []
    root = Path(temp_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for index, span in enumerate(smooth_spans):
        result = run_quality_canary(
            source, span, temp_root=root / f"span-{index:03d}", model=model, gpu=gpu,
            threads=threads, canary_duration_s=canary_duration_s,
        )
        evidence.append(result)

    if len(evidence) < 2:
        finalized: list[CanaryEvidence] = []
        for item in evidence:
            finalized.append(CanaryEvidence(
                **{**item.to_dict(),
                   "calibration_z": {"insufficient_cross_window_samples": 1.0},
                   "quality_score": 0.0,
                   "decision": "REVIEW",
                   "reasons": tuple(item.reasons) + ("insufficient_cross_window_calibration",)}
            ))
        return [], finalized

    _, z_by_index = _cross_window_calibration(evidence)
    for index, item in enumerate(evidence):
        calibration_z = z_by_index[index]
        worst = max(calibration_z.values(), default=float("inf"))
        mean_z = float(np.mean(list(calibration_z.values()))) if calibration_z else float("inf")
        score = max(0.0, min(1.0, 1.0 / (1.0 + mean_z)))
        reasons = list(item.reasons)
        decision = "SMOOTH+"
        if item.valid_triple_ratio < MIN_VALID_TRIPLE_RATIO:
            decision = "REVIEW"
            reasons.append("insufficient_valid_temporal_triplets")
        if worst > ROBUST_Z_LIMIT:
            decision = "REVIEW"
            reasons.append("cross_window_temporal_outlier")
        elif decision == "SMOOTH+":
            reasons.append("within_observed_canary_distribution")
        updated = CanaryEvidence(
            window_start=item.window_start, window_end=item.window_end,
            canary_start=item.canary_start, canary_end=item.canary_end,
            sample_count=item.sample_count, valid_triple_ratio=item.valid_triple_ratio,
            source_baseline=item.source_baseline, candidate_metrics=item.candidate_metrics,
            robust_z=item.robust_z, calibration_z=calibration_z,
            quality_score=score, decision=decision, reasons=tuple(dict.fromkeys(reasons)),
        )
        evidence[index] = updated
        if decision == "SMOOTH+":
            accepted.append((item.window_start, item.window_end))
    return accepted, evidence


def write_canary_evidence(path: str | Path, evidence: list[CanaryEvidence]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps([item.to_dict() for item in evidence], ensure_ascii=False, indent=2), encoding="utf-8")
