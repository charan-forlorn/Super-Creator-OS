"""test_analytics_translator.py — SCOS Stage 3.2 Analytics Translator suite.

Deterministic, stdlib only. Unit + bounds + validation + determinism, plus an
integration proving the certified FeedbackEngine + LearningCoordinator consume the
translator payload WITHOUT modification.

Run: python scos/analytics/translator/tests/test_analytics_translator.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[3]
sys.path.insert(0, str(_REPO_ROOT))                                   # scos.*
sys.path.insert(0, str(_HERE.parent))                                 # translator modules
sys.path.insert(0, str(_REPO_ROOT / "scos" / "analytics" / "adapters"))   # analytics_models
sys.path.insert(0, str(_REPO_ROOT / "scos" / "analytics"))           # feedback_engine
sys.path.insert(0, str(_REPO_ROOT / "scos" / "learning"))            # learning_coordinator

from analytics_models import NormalizedAnalytics                     # noqa: E402
from analytics_translator import AnalyticsTranslator, TranslationError  # noqa: E402
from translation_rules import TranslationRules                        # noqa: E402
import feedback_engine as FE                                          # noqa: E402
import learning_coordinator as LC                                     # noqa: E402
from scos.memory.style_memory import StyleMemoryEngine                # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


def _rec(vid="v1", views=1000, ctr=0.05, ret=0.45, likes=50, comments=30, shares=20,
         subs=5, wt=5000.0, avd=30.0, dur=70.0, platform="youtube", meta=None):
    return NormalizedAnalytics(
        video_id=vid, platform=platform, publish_time="2026-06-01", views=views,
        watch_time_seconds=wt, average_view_duration=avd, retention_rate=ret, ctr=ctr,
        likes=likes, comments=comments, shares=shares, subscribers_gained=subs,
        duration_seconds=dur, metadata=meta or {})


_KEYS = {"content_type", "quality_score", "engagement_score", "retention_score",
         "style_match_score", "derived_style_updates"}


def test_valid():
    print("\n[1] valid translation + output contract")
    p = AnalyticsTranslator().translate([_rec()], content_type="gaming")
    check("exact output keys", set(p) == _KEYS)
    check("content_type honored", p["content_type"] == "gaming")
    check("scores in [0,1]", all(0.0 <= p[k] <= 1.0 for k in
          ("quality_score", "engagement_score", "retention_score", "style_match_score")))
    u = p["derived_style_updates"]
    check("derived keys", set(u) == {"audio_frequency_bias_delta", "scene_pacing_delta", "palette_shift_hint"})


def test_determinism():
    print("\n[2] determinism — translate() 100x byte-identical")
    recs = [_rec("a"), _rec("b", views=2000, ctr=0.08, ret=0.6)]
    first = json.dumps(AnalyticsTranslator().translate(recs, content_type="g"), sort_keys=True)
    same = all(json.dumps(AnalyticsTranslator().translate(recs, content_type="g"), sort_keys=True) == first
               for _ in range(100))
    check("100 runs identical", same)
    # identical separate inputs -> identical payload
    a = AnalyticsTranslator().translate([_rec("x")], content_type="g")
    b = AnalyticsTranslator().translate([_rec("x")], content_type="g")
    check("identical inputs -> identical payload", a == b)


def test_calculations():
    print("\n[3] engagement / quality / retention / style_match formulas")
    rec = _rec(views=1000, likes=50, comments=30, shares=20, ctr=0.05, ret=0.45)
    pol = TranslationRules()
    agg = pol.aggregate([rec])
    p = AnalyticsTranslator(policy=pol).translate([rec], content_type="g")
    check("engagement (0.1 rate -> 1.0)", p["engagement_score"] == 1.0)
    check("retention maps retention_rate", p["retention_score"] == 0.45)
    exp_q = round(0.4 * pol.retention_score(agg) + 0.3 * pol.ctr_score(agg)
                  + 0.3 * pol.engagement_score(agg), 6)
    check("quality = 0.4R+0.3CTR+0.3E", p["quality_score"] == exp_q)
    check("style_match matches policy", p["style_match_score"] == pol.style_match_score(agg))


def test_bounds():
    print("\n[4] derived_style_updates bounds")
    # extreme: zero engagement, low retention, low style_match
    p = AnalyticsTranslator().translate([_rec(views=1000, likes=0, comments=0, shares=0,
                                              ctr=0.0, ret=0.0)], content_type="g")
    u = p["derived_style_updates"]
    check("freq delta in [-50,50]", -50.0 <= u["audio_frequency_bias_delta"] <= 50.0)
    check("pacing delta in [-0.5,0.5]", -0.5 <= u["scene_pacing_delta"] <= 0.5)
    ph = u["palette_shift_hint"]
    check("palette 3 ints in [-32,32]", len(ph) == 3 and all(isinstance(v, int) and -32 <= v <= 32 for v in ph))
    check("low engagement -> positive freq delta", u["audio_frequency_bias_delta"] >= 0.0)


def test_invalid():
    print("\n[5] invalid inputs rejected (deterministic, never repaired)")
    cases = {
        "empty list": [],
        "negative views": [_rec(views=-1)],
        "ctr > 1": [_rec(ctr=1.5)],
        "retention > 1": [_rec(ret=2.0)],
        "NaN ctr": [_rec(ctr=float("nan"))],
        "Inf retention": [_rec(ret=float("inf"))],
        "negative likes": [_rec(likes=-5)],
    }
    for name, recs in cases.items():
        raised = False
        try:
            AnalyticsTranslator().translate(recs)
        except TranslationError:
            raised = True
        check(f"reject: {name}", raised)
    # missing field
    bad = types.SimpleNamespace(video_id="z", platform="youtube", views=1)  # missing many
    raised = False
    try:
        AnalyticsTranslator().translate([bad])
    except TranslationError:
        raised = True
    check("reject: missing fields", raised)


def test_no_side_effects():
    print("\n[6] no persistence / no learning / no input mutation")
    rec = _rec()
    before = rec.to_dict()
    t = AnalyticsTranslator()
    t.translate([rec], content_type="g")
    check("input not mutated", rec.to_dict() == before)
    check("no persistence method", not hasattr(t, "persist") and not hasattr(t, "save"))
    check("no learning/coordinator/engine reference",
          not any(k in ("engine", "coordinator", "style_engine") for k in vars(t)))


def test_dependency_injection():
    print("\n[7] dependency injection of rules")
    class FakeRules(TranslationRules):
        def retention_score(self, agg):
            return 0.111
    p = AnalyticsTranslator(policy=FakeRules()).translate([_rec()], content_type="g")
    check("injected rule used", p["retention_score"] == 0.111)


def test_integration():
    print("\n[8] integration — certified FeedbackEngine + Coordinator accept payload")
    recs = [_rec(views=1000, ctr=0.05, ret=0.4, likes=10, comments=5, shares=2)]
    payload = AnalyticsTranslator().translate(recs, content_type="gaming")

    # FeedbackEngine.to_style_update consumes the translator's score dict unmodified.
    derived = FE.FeedbackEngine().to_style_update(payload, manifest={}, content_type="gaming")
    check("FeedbackEngine.to_style_update accepts payload",
          {"content_type", "audio_frequency_bias_delta", "scene_pacing_delta", "palette_shift_hint"} <= set(derived))

    # LearningCoordinator consumes the full payload end-to-end (no core change).
    with tempfile.TemporaryDirectory() as tmp:
        eng = StyleMemoryEngine(Path(tmp) / "sm.json")
        style = {"style_id": "s1", "content_type": "gaming", "avg_color_palette": [120, 120, 120],
                 "audio_frequency_bias": 440.0, "scene_pacing_profile": 1.0,
                 "retention_score": 0.7, "created_at": 1000}
        eng.record_video_metrics(style)
        coord = LC.LearningCoordinator(eng, now_fn=lambda: 0, work_dir=Path(tmp) / "wk")
        out = coord.coordinate({"feedback": payload, "style_profile": style})
        check("Coordinator accepts payload", out["decision"] in {"APPLY", "CLAMP", "REJECT"})


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60); print(" STAGE 3.2 — ANALYTICS TRANSLATOR — TEST SUITE"); print("=" * 60)
    test_valid(); test_determinism(); test_calculations(); test_bounds()
    test_invalid(); test_no_side_effects(); test_dependency_injection(); test_integration()
    print("\n" + "=" * 60); print(f" RESULT: {_PASS} passed, {_FAIL} failed"); print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
