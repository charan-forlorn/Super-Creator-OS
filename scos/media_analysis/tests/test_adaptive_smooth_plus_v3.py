import numpy as np
from types import SimpleNamespace

from scos.media_analysis.adaptive_smooth_plus_v3 import (
    choose_canary_span,
    evaluate_canary_pair,
)


def _moving_frames(count: int, h: int = 32, w: int = 48) -> np.ndarray:
    base = np.zeros((count, h, w), dtype=np.float32)
    for i in range(count):
        base[i, :, :] = i / max(1, count - 1)
    return base


def test_choose_canary_is_interior_to_window():
    start, end = choose_canary_span(10.0, 20.0, 30.0, duration_s=0.4)
    assert start > 10.0
    assert end < 20.0
    assert abs((end - start) - 0.4) < 1e-9


def test_canary_accepts_linearly_smooth_sequence():
    source = _moving_frames(15)
    candidate = np.empty((30, 32, 48), dtype=np.float32)
    for i in range(15):
        candidate[2 * i] = source[i]
        if i < 14:
            candidate[2 * i + 1] = 0.5 * (source[i] + source[i + 1])
    candidate[29] = source[-1]
    result = evaluate_canary_pair(source, candidate)
    assert result["decision"] == "SMOOTH+"
    assert result["valid_triple_ratio"] >= 0.4


def test_canary_rejects_temporal_outlier():
    source = _moving_frames(15)
    candidate = np.empty((30, 32, 48), dtype=np.float32)
    for i in range(15):
        candidate[2 * i] = source[i]
        if i < 14:
            candidate[2 * i + 1] = 1.0 - source[i]
    candidate[29] = source[-1]
    result = evaluate_canary_pair(source, candidate)
    assert result["decision"] == "REVIEW"
    assert "temporal_quality_outlier" in result["reasons"]


def test_canary_reviews_insufficient_motion_samples():
    source = np.zeros((6, 32, 48), dtype=np.float32)
    candidate = np.zeros((12, 32, 48), dtype=np.float32)
    result = evaluate_canary_pair(source, candidate)
    assert result["decision"] == "REVIEW"
    assert "insufficient_temporal_samples" in result["reasons"] or result["valid_triple_ratio"] < 0.4
