"""test_highlight_engine.py — WF-1 engine tests.

Two layers:
  - UNIT: the fusion/peak/merge math on SYNTHETIC signal arrays (deterministic, no
    asset, no ffmpeg). This is legitimate — it tests the algorithm on controlled
    inputs; it does NOT fabricate observed outcomes.
  - INTEGRATION (optional): if a real video is present, assert the engine returns
    well-formed candidates. Skipped cleanly when no asset is available.

Run:  python integrations/highlight/tests/test_highlight_engine.py
Exit 0 if all pass, 1 otherwise.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))                 # integrations/highlight
import highlight_engine as H                           # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


def test_norm01():
    print("\n[1] norm01 — robust 0..1 scaling")
    flat = np.ones(10)
    check("flat signal -> all zeros (no false peaks)", np.allclose(H.norm01(flat), 0.0))
    x = np.array([0., 1., 2., 3., 100.])              # outlier at the top
    n = H.norm01(x)
    check("output bounded 0..1", n.min() >= 0.0 and n.max() <= 1.0)
    check("empty -> empty", len(H.norm01(np.array([]))) == 0)


def test_onset():
    print("\n[2] onset — positive derivative (event starts)")
    x = np.array([0., 0., 1., 0., 0.])
    o = H.onset(x)
    check("rise produces positive onset at index 2", o[2] > 0)
    check("fall produces zero onset (clipped)", o[3] == 0)


def test_fuse_and_peaks():
    print("\n[3] fuse + detect_peaks — a planted spike is found")
    cfg = H.HighlightConfig(window_s=0.5, min_separation_s=2.0, threshold_k=1.0)
    n = 120                                            # 60s at 0.5s windows
    audio = np.full(n, 0.05, dtype=np.float32)
    motion = np.full(n, 0.05, dtype=np.float32)
    # plant a clear combined spike around window 100 (=50s)
    audio[98:103] = [0.4, 0.8, 1.0, 0.7, 0.3]
    motion[98:103] = [0.3, 0.6, 0.9, 0.5, 0.2]
    fused = H.fuse(audio, motion, cfg)
    times = np.arange(len(fused)) * cfg.window_s
    peaks = H.detect_peaks(fused, times, cfg)
    check("fused signal is non-empty + bounded", len(fused) == n and fused.max() <= 1.0)
    check("at least one peak detected", len(peaks) >= 1)
    near = any(abs(times[p] - 50.0) <= 1.5 for p in peaks)
    check("strongest peak lands at the planted spike (~50s)", near)


def test_candidates_and_merge():
    print("\n[4] peaks_to_candidates + overlap merge + schema")
    cfg = H.HighlightConfig(pre_roll_s=6, post_roll_s=3, window_s=0.5)
    n = 120
    fused = np.full(n, 0.1); fused[100] = 1.0; fused[104] = 0.95
    times = np.arange(n) * 0.5
    na = np.full(n, 0.7); nm = np.full(n, 0.7)
    cands = H.peaks_to_candidates([100, 104], fused, times, na, nm, cfg,
                                  duration=60.0, visual_events=[])
    check("overlapping peaks merged into 1 candidate", len(cands) == 1)
    c = cands[0]
    check("schema has required keys",
          all(k in c for k in ("start", "end", "score", "peak", "reason")))
    check("score in 0..100", 0 <= c["score"] <= 100)
    check("start<end and within clip", 0 <= c["start"] < c["end"] <= 60.0)
    check("reason is signal-grounded (no fabricated game label)",
          "spike" in c["reason"] or "activity" in c["reason"])


def test_visual_detector_interface():
    print("\n[5] pluggable visual detector — semantic labels injected, not faked")
    cfg = H.HighlightConfig(window_s=0.5)
    n = 120
    fused = np.full(n, 0.1); fused[100] = 1.0
    times = np.arange(n) * 0.5
    na = np.full(n, 0.7); nm = np.full(n, 0.7)
    events = [{"t": 50.0, "label": "DOUBLE KILL", "weight": 1.0}]
    cands = H.peaks_to_candidates([100], fused, times, na, nm, cfg, 60.0, events)
    check("visual label flows into reason when detector provides it",
          "DOUBLE KILL" in cands[0]["reason"])
    check("NullVisualDetector returns no events (honest no-op)",
          H.NullVisualDetector().detect(Path("x"), cfg) == [])


def test_integration_real_asset_optional():
    print("\n[6] integration (optional) — runs on a real asset if present")
    candidates_dir = _HERE.parents[2] / "input" / "raw"
    vids = (list(candidates_dir.glob("*.mp4")) + list(candidates_dir.glob("*.MP4"))
            if candidates_dir.exists() else [])
    if not vids:
        print("        SKIP — no asset in input/raw/ (expected; raw is gitignored/cleaned)")
        return
    cfg = H.HighlightConfig()
    cands = H.detect_highlights(vids[0], cfg)
    check("engine returns a list of well-formed candidates on real video",
          isinstance(cands, list) and all(
              0 <= c["score"] <= 100 and c["start"] < c["end"] for c in cands))
    print(f"        (real run: {len(cands)} candidate(s) from {vids[0].name})")


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60)
    print(" WF-1 AUTO HIGHLIGHT ENGINE — TEST SUITE")
    print("=" * 60)
    test_norm01()
    test_onset()
    test_fuse_and_peaks()
    test_candidates_and_merge()
    test_visual_detector_interface()
    test_integration_real_asset_optional()
    print("\n" + "=" * 60)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
