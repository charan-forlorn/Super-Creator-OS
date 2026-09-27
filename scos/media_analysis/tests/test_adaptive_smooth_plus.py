from scos.media_analysis.adaptive_smooth_plus_v2 import (
    analyze_adaptive_smooth_plus,
    build_micro_windows,
    merge_smooth_spans,
    split_scene_safe_ranges,
)
from types import SimpleNamespace
import numpy as np

from scos.media_analysis.adaptive_smooth_plus_v2 import TemporalWindowEvidence


def test_micro_windows_respect_bounds_and_merge_short_tail():
    spans = build_micro_windows(0.0, 3.2, window_s=1.0, min_window_s=0.5, max_window_s=2.0)
    assert spans == [(0.0, 1.0), (1.0, 2.0), (2.0, 3.2)]


def test_scene_safe_ranges_never_cross_cut():
    assert split_scene_safe_ranges([(10.0, 30.0)], [20.0]) == [(0, 10.0, 20.0), (1, 20.0, 30.0)]


def test_smooth_spans_merge_only_adjacent_same_scene():
    rows = [
        TemporalWindowEvidence(1,2,0,30,.6,.01,1,2,.2,.5,"SMOOTH+"),
        TemporalWindowEvidence(2,3,0,30,.6,.01,1,2,.2,.5,"SMOOTH+"),
        TemporalWindowEvidence(3,4,1,30,.6,.01,1,2,.2,.5,"SMOOTH+"),
    ]
    assert merge_smooth_spans(rows) == [(1,3),(3,4)]


def test_current_source_routes_some_windows_without_crossing_cut():
    source = r"C:\Users\chara\OneDrive\Videos\การบันทึกหน้าจอ\การบันทึกหน้าจอ 2026-09-27 091454.mp4"
    plan = analyze_adaptive_smooth_plus(source, [(18.263437,50.245583)], [31.166667])
    assert plan.source_fps == 30.0
    assert plan.summary["decision_counts"]["SMOOTH+"] > 0
    assert plan.summary["decision_counts"]["REVIEW"] > 0
    assert all(not (a < 31.166667 < b) for a,b in plan.smooth_spans)


def test_analysis_uses_probed_non30fps(monkeypatch, tmp_path):
    import scos.media_analysis.adaptive_smooth_plus_v2 as mod

    source = tmp_path / "synthetic_25fps.mp4"
    source.write_bytes(b"x")
    monkeypatch.setattr(
        mod,
        "probe_source",
        lambda _: SimpleNamespace(fps=25.0, cfr=True, width=640, height=360),
    )
    monkeypatch.setattr(
        mod,
        "_extract_gray_frames",
        lambda *args, **kwargs: np.zeros((25, 360, 640), dtype=np.uint8),
    )
    plan = mod.analyze_adaptive_smooth_plus(source, [(0.0, 0.96)], [])
    assert plan.source_fps == 25.0
    assert plan.target_fps == 60.0
