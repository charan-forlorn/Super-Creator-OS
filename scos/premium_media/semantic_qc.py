
"""Pluggable semantic-continuity QC with a deterministic visual-identity fallback."""
from __future__ import annotations
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class VisualIdentityReport:
    passed: bool
    score: float | None
    threshold: float
    method: str
    reason: str
    model_backed: bool = False


class SemanticEmbeddingEvaluator(Protocol):
    model_id: str
    def compare(self, previous: Path, current: Path) -> float: ...


def _frame_signature(path: Path, *, last: bool) -> tuple[float, ...]:
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if last:
        args += ["-sseof", "-0.20"]
    args += ["-i", str(path), "-frames:v", "1", "-vf", "scale=32:32,format=rgb24", "-f", "rawvideo", "pipe:1"]
    proc = subprocess.run(args, capture_output=True, timeout=60)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[-1200:])
    data = proc.stdout
    channels = [[data[i] / 255.0 for i in range(c, len(data), 3)] for c in range(3)]
    means = [sum(ch) / max(1, len(ch)) for ch in channels]
    stds = [math.sqrt(sum((v - m) ** 2 for v in ch) / max(1, len(ch))) for ch, m in zip(channels, means)]
    gray = [(r + g + b) / 3.0 for r, g, b in zip(channels[0], channels[1], channels[2])]
    edges = []
    width = 32
    for y in range(width - 1):
        for x in range(width - 1):
            a = (gray[y * width + x] + gray[y * width + x + 1] + gray[(y + 1) * width + x]) / 3.0
            b = (gray[y * width + x + 1] + gray[(y + 1) * width + x + 1]) / 2.0
            edges.append(abs(a - b))
    edge_density = sum(edges) / max(1, len(edges))
    return tuple(means + stds + [edge_density])


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def visual_identity_check(
    previous: Path,
    current: Path,
    *,
    threshold: float = 0.90,
    embedding_evaluator: SemanticEmbeddingEvaluator | None = None,
) -> VisualIdentityReport:
    if embedding_evaluator is not None:
        try:
            score = float(embedding_evaluator.compare(previous, current))
            return VisualIdentityReport(score >= threshold, score, threshold, f"embedding:{embedding_evaluator.model_id}", "model-backed semantic embedding comparison", True)
        except Exception as exc:
            return VisualIdentityReport(False, None, threshold, f"embedding:{embedding_evaluator.model_id}", f"semantic evaluator failed closed: {exc}", True)
    try:
        score = _cosine(_frame_signature(previous, last=True), _frame_signature(current, last=False))
    except Exception as exc:
        return VisualIdentityReport(False, None, threshold, "deterministic_visual_identity_proxy", f"proxy evaluator failed closed: {exc}", False)
    return VisualIdentityReport(score >= threshold, score, threshold, "deterministic_visual_identity_proxy", "color/statistical/edge boundary similarity; not a semantic-model claim", False)
