"""test_feedback_engine.py — SCOS Stage 2.2 Feedback & Scoring Engine suite.

Builds REAL fixtures with AssetBuilder v2 (read-only use) against a temp
StyleMemoryEngine store, plus a placeholder MP4 (no ffmpeg). Validates scoring,
determinism, persistence, style-update generation, and integration safety.

Run: python scos/analytics/tests/test_feedback_engine.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))          # for scos.* fixture builders
sys.path.insert(0, str(_HERE.parent))        # for `import feedback_engine`

import feedback_engine as FE                  # noqa: E402  (standalone module)
from scos.assets.asset_builder_v2 import AssetBuilderV2   # noqa: E402  (read-only)
from scos.memory.style_memory import StyleMemoryEngine    # noqa: E402  (read-only)

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


SCENE_PLAN = {
    "scenes": [
        {"scene_id": "scene_00", "topic": "gaming", "start": 0.0, "end": 2.0},
        {"scene_id": "scene_01", "topic": "gaming", "start": 2.0, "end": 3.5},
        {"scene_id": "scene_02", "topic": "gaming", "start": 3.5, "end": 5.0},
    ],
    "total_duration": 5.0,
}


def _style(style_id, ct, palette, freq, pacing):
    return {"style_id": style_id, "content_type": ct, "avg_color_palette": palette,
            "audio_frequency_bias": freq, "scene_pacing_profile": pacing,
            "retention_score": 0.9, "created_at": 1000}


def _make_bundle(tmp):
    store = Path(tmp) / f"sm_{os.urandom(4).hex()}.json"
    eng = StyleMemoryEngine(store)
    eng.record_video_metrics(_style("warm", "gaming", [200, 60, 40], 320.0, 1.0))
    res = AssetBuilderV2(eng).run(SCENE_PLAN)
    mp4 = Path(tmp) / "output.mp4"
    mp4.write_bytes(b"\x00FAKE-MP4" * 64)        # placeholder real file (engine never parses it)
    bundle = {
        "run_id": res["run_id"],
        "mp4_path": str(mp4),
        "manifest_path": res["manifest_path"],
        "assets": res["assets"],
        "content_type": "gaming",
    }
    return bundle, store


def test_score_correctness(tmp):
    print("\n[1] score correctness")
    bundle, _ = _make_bundle(tmp)
    s = FE.FeedbackEngine().evaluate(bundle)
    keys = ["retention_score", "engagement_score", "style_match_score", "quality_score"]
    check("all four scores present", all(k in s for k in keys))
    check("all scores in [0,1]", all(0.0 <= s[k] <= 1.0 for k in keys))
    expected_q = round(0.4 * s["retention_score"] + 0.3 * s["engagement_score"]
                       + 0.3 * s["style_match_score"], 6)
    check("quality = 0.4R+0.3E+0.3S", abs(s["quality_score"] - expected_q) < 1e-6)
    check("run_id echoed", s["run_id"] == bundle["run_id"])


def test_determinism(tmp):
    print("\n[2] determinism — same input -> identical output")
    bundle, _ = _make_bundle(tmp)
    e = FE.FeedbackEngine()
    a = e.evaluate(bundle)
    b = e.evaluate(bundle)
    check("identical score dict across calls", a == b)


def test_persistence(tmp):
    print("\n[3] persistence — append-only, no duplicates, sorted")
    bundle, _ = _make_bundle(tmp)
    store = Path(tmp) / "feedback_log.json"
    e = FE.FeedbackEngine(store_path=store)
    res = e.evaluate(bundle)
    e.persist_feedback(res)
    e.persist_feedback(res)                       # same run_id again
    log = json.loads(store.read_text(encoding="utf-8"))
    check("no duplicate run_id", len(log) == 1)
    # add a second, lexicographically smaller run_id -> must sort first
    res2 = dict(res); res2["run_id"] = "000000000000"
    e.persist_feedback(res2)
    log = json.loads(store.read_text(encoding="utf-8"))
    ids = [r["run_id"] for r in log]
    check("sorted by run_id", ids == sorted(ids) and ids[0] == "000000000000")
    check("valid JSON list of 2", isinstance(log, list) and len(log) == 2)


def test_style_update(tmp):
    print("\n[4] style update generation — bounded + sign rules")
    bundle, _ = _make_bundle(tmp)
    s = FE.FeedbackEngine().evaluate(bundle)
    u = s["derived_style_updates"]
    check("content_type passed through", u["content_type"] == "gaming")
    check("freq delta bounded [-50,50]", -50.0 <= u["audio_frequency_bias_delta"] <= 50.0)
    check("pacing delta bounded [-0.5,0.5]", -0.5 <= u["scene_pacing_delta"] <= 0.5)
    ph = u["palette_shift_hint"]
    check("palette hint = 3 ints in [-32,32]",
          len(ph) == 3 and all(isinstance(v, int) and -32 <= v <= 32 for v in ph))
    # engagement low -> larger freq delta (>=0 always; rule monotonic)
    check("freq delta >= 0 (more variance when engagement<1)", u["audio_frequency_bias_delta"] >= 0.0)
    # retention high (>0.5) -> positive pacing reinforcement
    sign_ok = (u["scene_pacing_delta"] >= 0) == (s["retention_score"] >= 0.5)
    check("pacing delta sign tracks retention vs 0.5", sign_ok)


def test_integration_safety(tmp):
    print("\n[5] integration safety — never modifies StyleMemoryEngine")
    bundle, store = _make_bundle(tmp)
    before = hashlib.sha256(store.read_bytes()).hexdigest()
    e = FE.FeedbackEngine()
    e.evaluate(bundle)
    after = hashlib.sha256(store.read_bytes()).hexdigest()
    check("style store file unchanged by evaluate", before == after)
    check("engine holds no StyleMemoryEngine reference",
          not any("style" in a.lower() and "engine" in a.lower() for a in vars(e)))


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60); print(" STAGE 2.2 — FEEDBACK & SCORING ENGINE — TEST SUITE"); print("=" * 60)
    with tempfile.TemporaryDirectory() as tmp:
        test_score_correctness(tmp)
        test_determinism(tmp)
        test_persistence(tmp)
        test_style_update(tmp)
        test_integration_safety(tmp)
    print("\n" + "=" * 60); print(f" RESULT: {_PASS} passed, {_FAIL} failed"); print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
