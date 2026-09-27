from __future__ import annotations

import math
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from scos.media_binaries import resolve_ffmpeg
from .source_probe import probe_source

ANALYSIS_WIDTH = 320
DEFAULT_WINDOW_S = 1.0
DEFAULT_MIN_WINDOW_S = 0.5
DEFAULT_MAX_WINDOW_S = 2.0
DEFAULT_DUPLICATE_DIFF = 0.0003
DEFAULT_MOTION_FLOOR = 0.0025
DEFAULT_MOTION_CEILING = 0.045
DEFAULT_INCONSISTENCY_REVIEW = 3.5
DEFAULT_CUT_MARGIN_S = 0.5


@dataclass(frozen=True)
class TemporalWindowEvidence:
    start: float
    end: float
    scene_segment: int
    frame_count: int
    duplicate_ratio: float
    motion_energy: float
    temporal_inconsistency: float
    scene_cut_proximity_s: float
    interpolation_risk: float
    score: float
    decision: str
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdaptiveSmoothPlan:
    source_fps: float
    target_fps: float
    window_s: float
    windows: tuple[TemporalWindowEvidence, ...]
    smooth_spans: tuple[tuple[float, float], ...]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_fps": self.source_fps,
            "target_fps": self.target_fps,
            "window_s": self.window_s,
            "windows": [w.to_dict() for w in self.windows],
            "smooth_spans": [list(x) for x in self.smooth_spans],
            "summary": self.summary,
        }


def _even_height(width: int, source_width: int, source_height: int) -> int:
    value = max(2, round(ANALYSIS_WIDTH * source_height / max(1, source_width) / 2) * 2)
    return value


def _extract_gray_frames(source: Path, start: float, end: float, width: int, height: int) -> np.ndarray:
    ffmpeg = resolve_ffmpeg()
    duration = max(0.001, end - start)
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(source),
        "-ss", f"{start:.9f}", "-t", f"{duration:.9f}",
        "-an", "-vf", f"scale={width}:{height},format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ]
    p = subprocess.run(cmd, capture_output=True, timeout=max(60, int(duration * 10) + 60), check=False)
    if p.returncode:
        raise RuntimeError((p.stderr or b"").decode("utf-8", "replace")[-2000:])
    frame_bytes = width * height
    if len(p.stdout) < frame_bytes:
        raise RuntimeError("temporal analysis produced no usable frames")
    count = len(p.stdout) // frame_bytes
    return np.frombuffer(p.stdout[:count * frame_bytes], dtype=np.uint8).reshape((count, height, width))


def split_scene_safe_ranges(
    keep_ranges: list[tuple[float, float]], scene_cuts: list[float]
) -> list[tuple[int, float, float]]:
    out: list[tuple[int, float, float]] = []
    segment_id = 0
    for start, end in keep_ranges:
        points = [start, *sorted(c for c in scene_cuts if start < c < end), end]
        for a, b in zip(points, points[1:]):
            if b - a >= 0.001:
                out.append((segment_id, a, b))
                segment_id += 1
    return out


def build_micro_windows(
    segment_start: float,
    segment_end: float,
    *,
    window_s: float = DEFAULT_WINDOW_S,
    min_window_s: float = DEFAULT_MIN_WINDOW_S,
    max_window_s: float = DEFAULT_MAX_WINDOW_S,
) -> list[tuple[float, float]]:
    if not (0 < min_window_s <= window_s <= max_window_s):
        raise ValueError("window sizing must satisfy 0 < min <= window <= max")
    if segment_end <= segment_start:
        return []
    spans: list[tuple[float, float]] = []
    start = segment_start
    while segment_end - start > max_window_s + 1e-9:
        end = start + window_s
        spans.append((start, end))
        start = end
    remainder = segment_end - start
    if remainder < min_window_s - 1e-9 and spans:
        prev_start, _ = spans[-1]
        spans[-1] = (prev_start, segment_end)
    else:
        spans.append((start, segment_end))
    return [(round(a, 9), round(b, 9)) for a, b in spans]


def _distance_to_cut(start: float, end: float, cuts: list[float]) -> float:
    if not cuts:
        return float("inf")
    return min(abs(start - c) for c in cuts) if start in cuts else min(abs(start - c) for c in cuts)


def _cut_proximity(start: float, end: float, cuts: list[float]) -> float:
    if not cuts:
        return float("inf")
    return min((min(abs(start - c), abs(end - c)) for c in cuts), default=float("inf"))


def _window_metrics(
    diffs: np.ndarray,
    start_index: int,
    end_index: int,
    frame_count: int,
    cut_proximity: float,
    scene_segment: int,
) -> TemporalWindowEvidence:
    local = diffs[max(0, start_index):max(start_index, end_index)]
    if local.size == 0:
        local = np.asarray([1.0], dtype=np.float32)
    duplicate_ratio = float(np.mean(local <= DEFAULT_DUPLICATE_DIFF))
    motion = float(np.mean(local))
    std = float(np.std(local))
    inconsistency = min(10.0, std / max(motion, 0.001))
    cut_risk = 0.0 if math.isinf(cut_proximity) else math.exp(-cut_proximity / DEFAULT_CUT_MARGIN_S)
    motion_norm = max(0.0, min(1.0, (motion - DEFAULT_MOTION_FLOOR) / (DEFAULT_MOTION_CEILING - DEFAULT_MOTION_FLOOR)))
    inconsistency_norm = max(0.0, min(1.0, inconsistency / DEFAULT_INCONSISTENCY_REVIEW))
    interpolation_risk = max(0.0, min(1.0, 0.45 * motion_norm + 0.35 * inconsistency_norm + 0.20 * cut_risk))
    score = max(0.0, min(1.0, 0.45 * duplicate_ratio + 0.35 * motion_norm + 0.20 * (1.0 - interpolation_risk)))
    reasons: list[str] = []
    decision = "PRESERVE"
    if frame_count < 3:
        decision = "REVIEW"
        reasons.append("insufficient_window_frames")
    elif cut_proximity < DEFAULT_CUT_MARGIN_S:
        reasons.append("near_scene_boundary")
    elif duplicate_ratio < 0.45:
        reasons.append("duplicate_signal_below_floor")
    elif motion < DEFAULT_MOTION_FLOOR:
        reasons.append("motion_energy_below_floor")
    elif motion > DEFAULT_MOTION_CEILING or inconsistency > DEFAULT_INCONSISTENCY_REVIEW:
        decision = "REVIEW"
        reasons.append("interpolation_risk_high")
    elif score >= 0.42:
        decision = "SMOOTH+"
        reasons.append("deterministic_smoothness_evidence")
    else:
        decision = "REVIEW"
        reasons.append("evidence_ambiguous")
    if cut_proximity < DEFAULT_CUT_MARGIN_S and decision == "SMOOTH+":
        decision = "PRESERVE"
    return TemporalWindowEvidence(
        start=round(start_index, 6),
        end=round(end_index, 6),
        scene_segment=scene_segment,
        frame_count=frame_count,
        duplicate_ratio=duplicate_ratio,
        motion_energy=motion,
        temporal_inconsistency=inconsistency,
        scene_cut_proximity_s=cut_proximity,
        interpolation_risk=interpolation_risk,
        score=score,
        decision=decision,
        reasons=tuple(reasons),
    )

def merge_smooth_spans(windows: list[TemporalWindowEvidence]) -> list[tuple[float, float]]:
    spans: list[tuple[float, float]] = []
    current: tuple[int, float, float] | None = None
    for window in windows:
        if window.decision != "SMOOTH+":
            continue
        if current is None:
            current = (window.scene_segment, window.start, window.end)
            continue
        seg, a, b = current
        if seg == window.scene_segment and abs(b - window.start) <= 1e-6:
            current = (seg, a, window.end)
        else:
            spans.append((a, b))
            current = (window.scene_segment, window.start, window.end)
    if current is not None:
        spans.append((current[1], current[2]))
    return [(round(a, 9), round(b, 9)) for a, b in spans]


def analyze_adaptive_smooth_plus(
    source: str | Path,
    keep_ranges: list[tuple[float, float]],
    scene_cuts: list[float],
    *,
    window_s: float = DEFAULT_WINDOW_S,
    min_window_s: float = DEFAULT_MIN_WINDOW_S,
    max_window_s: float = DEFAULT_MAX_WINDOW_S,
) -> AdaptiveSmoothPlan:
    src = Path(source).resolve()
    probe = probe_source(src)
    if probe.fps <= 0:
        raise ValueError("adaptive SMOOTH+ requires a valid source FPS")
    if not getattr(probe, "cfr", True):
        raise ValueError("adaptive SMOOTH+ fails closed for non-CFR/VFR source")
    if probe.fps >= 59.5:
        return AdaptiveSmoothPlan(
            source_fps=probe.fps,
            target_fps=60.0,
            window_s=window_s,
            windows=tuple(),
            smooth_spans=tuple(),
            summary={"decision":"PRESERVE","reason":"source_already_near_60fps"},
        )
    all_windows: list[TemporalWindowEvidence] = []
    for scene_segment, seg_start, seg_end in split_scene_safe_ranges(keep_ranges, scene_cuts):
        windows = build_micro_windows(
            seg_start, seg_end, window_s=window_s, min_window_s=min_window_s, max_window_s=max_window_s
        )
        frames = _extract_gray_frames(src, seg_start, seg_end, ANALYSIS_WIDTH, _even_height(ANALYSIS_WIDTH, probe.width, probe.height))
        diffs = np.abs(frames[1:].astype(np.int16) - frames[:-1].astype(np.int16)).mean(axis=(1, 2)) / 255.0 if len(frames) > 1 else np.asarray([])
        for w_start, w_end in windows:
            start_index = max(0, round((w_start - seg_start) * probe.fps))
            end_index = min(len(frames), round((w_end - seg_start) * probe.fps))
            frame_count = max(0, end_index - start_index)
            cut_proximity = _cut_proximity(w_start, w_end, scene_cuts)
            evidence = _window_metrics(diffs, start_index, max(start_index, end_index - 1), frame_count, cut_proximity, scene_segment)
            evidence = TemporalWindowEvidence(
                start=round(w_start, 9), end=round(w_end, 9), scene_segment=evidence.scene_segment,
                frame_count=evidence.frame_count, duplicate_ratio=evidence.duplicate_ratio,
                motion_energy=evidence.motion_energy, temporal_inconsistency=evidence.temporal_inconsistency,
                scene_cut_proximity_s=evidence.scene_cut_proximity_s, interpolation_risk=evidence.interpolation_risk,
                score=evidence.score, decision=evidence.decision, reasons=evidence.reasons,
            )
            all_windows.append(evidence)
    smooth_spans = merge_smooth_spans(all_windows)
    counts = {key: sum(1 for w in all_windows if w.decision == key) for key in ("PRESERVE", "SMOOTH+", "REVIEW")}
    smooth_seconds = sum(b - a for a, b in smooth_spans)
    kept_seconds = sum(b - a for a, b in keep_ranges)
    summary = {
        "window_count": len(all_windows),
        "decision_counts": counts,
        "keep_duration_s": kept_seconds,
        "smooth_duration_s": smooth_seconds,
        "smooth_fraction": (smooth_seconds / kept_seconds) if kept_seconds else 0.0,
        "scene_cuts": sorted(scene_cuts),
        "rife_interpolation_reduction": 1.0 - ((smooth_seconds / kept_seconds) if kept_seconds else 0.0),
    }
    return AdaptiveSmoothPlan(
        source_fps=probe.fps, target_fps=60.0, window_s=window_s,
        windows=tuple(all_windows), smooth_spans=tuple(smooth_spans), summary=summary,
    )
