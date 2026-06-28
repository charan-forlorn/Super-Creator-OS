"""test_learning_coordinator.py — SCOS Stage 2.3 Learning Coordinator suite.

Covers policy decisions, clamp, reject, audit, confidence, version history, rollback,
determinism, and integration safety. Stdlib only; temp StyleMemoryEngine store + temp
work_dir + fixed clock for full determinism.

Run: python scos/learning/tests/test_learning_coordinator.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))       # for scos.*
sys.path.insert(0, str(_HERE.parent))     # for learning_coordinator + learning_policy

from learning_coordinator import LearningCoordinator   # noqa: E402
from learning_policy import LearningPolicy              # noqa: E402
from scos.memory.style_memory import StyleMemoryEngine  # noqa: E402

_PASS, _FAIL = 0, 0
_FIXED_TS = 1700000000


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


def _profile(tmp_engine, *, pacing=1.0, freq=440.0, palette=None):
    palette = palette if palette is not None else [120, 120, 120]
    prof = {"style_id": "s1", "content_type": "gaming", "avg_color_palette": palette,
            "audio_frequency_bias": freq, "scene_pacing_profile": pacing,
            "retention_score": 0.7, "created_at": 1000}
    tmp_engine.record_video_metrics(prof)
    return prof


def _feedback(q, r, e, s, *, pace_d=0.0, freq_d=0.0, palette_hint=None, run_id="run1"):
    return {
        "run_id": run_id, "retention_score": r, "engagement_score": e,
        "style_match_score": s, "quality_score": q,
        "derived_style_updates": {
            "content_type": "gaming", "audio_frequency_bias_delta": freq_d,
            "scene_pacing_delta": pace_d, "palette_shift_hint": palette_hint or [0, 0, 0],
        },
    }


def _setup(tmp, **style_kw):
    eng = StyleMemoryEngine(Path(tmp) / f"sm_{os.urandom(4).hex()}.json")
    prof = _profile(eng, **style_kw)
    work = Path(tmp) / f"wk_{os.urandom(4).hex()}"
    coord = LearningCoordinator(eng, now_fn=lambda: _FIXED_TS, work_dir=work)
    return eng, coord, prof, work


def test_policy(tmp):
    print("\n[1] policy decisions")
    eng, coord, prof, _ = _setup(tmp)
    # high retention + good quality, engagement/style high -> only pacing increases -> APPLY
    out = coord.coordinate({"feedback": _feedback(0.9, 0.9, 0.8, 0.9, pace_d=0.2), "style_profile": prof})
    check("high retention -> APPLY", out["decision"] == "APPLY")
    check("pacing increased 1.0->1.2", abs(out["updated_style"]["scene_pacing_profile"] - 1.2) < 1e-9)
    # low quality -> REJECT
    out2 = coord.coordinate({"feedback": _feedback(0.3, 0.9, 0.2, 0.2, pace_d=0.2), "style_profile": prof})
    check("low quality -> REJECT", out2["decision"] == "REJECT" and "quality" in out2["reason"])
    # mid retention, high engagement, high style -> nothing to do -> REJECT (no penalty)
    out3 = coord.coordinate({"feedback": _feedback(0.9, 0.6, 0.9, 0.9, pace_d=0.2), "style_profile": prof})
    check("no actionable -> REJECT", out3["decision"] == "REJECT" and "no actionable" in out3["reason"])


def test_clamp(tmp):
    print("\n[2] clamp behavior")
    eng, coord, prof, _ = _setup(tmp, pacing=1.9)
    out = coord.coordinate({"feedback": _feedback(0.9, 0.9, 0.8, 0.9, pace_d=0.5), "style_profile": prof})
    check("over-bound pacing -> CLAMP", out["decision"] == "CLAMP")
    check("pacing clamped to 2.0", out["updated_style"]["scene_pacing_profile"] == 2.0)
    # palette clamp
    eng2, coord2, prof2, _ = _setup(tmp, palette=[250, 250, 250])
    out2 = coord2.coordinate({"feedback": _feedback(0.9, 0.6, 0.2, 0.2, palette_hint=[32, 32, 32]),
                              "style_profile": prof2})
    check("palette over 255 -> CLAMP", out2["decision"] == "CLAMP")
    check("palette clamped to <=255", all(c <= 255 for c in out2["updated_style"]["avg_color_palette"]))


def test_reject(tmp):
    print("\n[3] reject + safety (NaN)")
    eng, coord, prof, _ = _setup(tmp)
    nan = float("nan")
    out = coord.coordinate({"feedback": _feedback(0.9, 0.5, 0.2, 0.9, freq_d=nan), "style_profile": prof})
    check("NaN proposal -> REJECT", out["decision"] == "REJECT" and "unsafe" in out["reason"])
    # style unchanged in engine after reject
    cur = next(s for s in eng.list_styles() if s["style_id"] == "s1")
    check("style unchanged after reject", cur["audio_frequency_bias"] == 440.0)


def test_audit(tmp):
    print("\n[4] audit logging")
    eng, coord, prof, work = _setup(tmp)
    coord.coordinate({"feedback": _feedback(0.9, 0.9, 0.8, 0.9, pace_d=0.2), "style_profile": prof})
    log = json.loads((work / "learning_audit.json").read_text(encoding="utf-8"))
    check("audit entry written", len(log) == 1)
    e = log[0]
    check("audit schema complete",
          {"audit_id", "decision", "reason", "style_before", "style_after",
           "feedback_summary", "timestamp"} <= set(e))
    # re-running identical op does not duplicate audit_id
    coord.coordinate({"feedback": _feedback(0.9, 0.9, 0.8, 0.9, pace_d=0.2),
                      "style_profile": eng.list_styles()[0]})
    log2 = json.loads((work / "learning_audit.json").read_text(encoding="utf-8"))
    ids = [x["audit_id"] for x in log2]
    check("no duplicate audit_id", len(ids) == len(set(ids)))


def test_confidence(tmp):
    print("\n[5] confidence model")
    eng, coord, prof, work = _setup(tmp)
    coord.coordinate({"feedback": _feedback(0.9, 0.9, 0.8, 0.9, pace_d=0.2), "style_profile": prof})
    st = json.loads((work / "learning_state.json").read_text(encoding="utf-8"))
    check("confidence up after APPLY", st["confidence"] > 0.5)
    coord.coordinate({"feedback": _feedback(0.2, 0.9, 0.8, 0.9), "style_profile": eng.list_styles()[0]})
    st2 = json.loads((work / "learning_state.json").read_text(encoding="utf-8"))
    check("confidence down after REJECT", st2["confidence"] < st["confidence"])
    check("confidence bounded [0,1]", 0.0 <= st2["confidence"] <= 1.0)


def test_versioning_and_rollback(tmp):
    print("\n[6/7] version history + rollback")
    eng, coord, prof, work = _setup(tmp)
    coord.coordinate({"feedback": _feedback(0.9, 0.9, 0.8, 0.9, pace_d=0.2), "style_profile": prof})  # v1
    hist = json.loads((work / "style_history.json").read_text(encoding="utf-8"))
    versions = [s["version"] for s in hist["s1"]]
    check("history seeded v0 + v1", versions == [0, 1])
    check("v0 snapshot preserves original pacing", hist["s1"][0]["profile"]["scene_pacing_profile"] == 1.0)
    # rollback to v0
    rb = coord.rollback("s1", 0)
    check("rollback decision", rb["decision"] == "ROLLBACK")
    cur = next(s for s in eng.list_styles() if s["style_id"] == "s1")
    check("engine restored to v0 pacing 1.0", cur["scene_pacing_profile"] == 1.0)
    # unknown version raises
    raised = False
    try:
        coord.rollback("s1", 99)
    except ValueError:
        raised = True
    check("rollback unknown version -> ValueError", raised)


def test_determinism(tmp):
    print("\n[8] determinism")
    fb = _feedback(0.9, 0.9, 0.8, 0.9, pace_d=0.2)
    eng_a, coord_a, prof_a, work_a = _setup(tmp)
    eng_b, coord_b, prof_b, work_b = _setup(tmp)
    out_a = coord_a.coordinate({"feedback": fb, "style_profile": prof_a})
    out_b = coord_b.coordinate({"feedback": fb, "style_profile": prof_b})
    check("identical decision output", out_a == out_b)
    aud_a = (work_a / "learning_audit.json").read_text(encoding="utf-8")
    aud_b = (work_b / "learning_audit.json").read_text(encoding="utf-8")
    check("identical persisted audit json", aud_a == aud_b)


def test_integration_safety(tmp):
    print("\n[9] integration safety — only via update_style")
    eng, coord, prof, _ = _setup(tmp)
    coord.coordinate({"feedback": _feedback(0.9, 0.9, 0.8, 0.9, pace_d=0.2), "style_profile": prof})
    styles = eng.list_styles()
    check("no extra style created", len(styles) == 1)
    cur = styles[0]
    check("preserved untouched fields (retention/created_at/content_type)",
          cur["retention_score"] == 0.7 and cur["created_at"] == 1000 and cur["content_type"] == "gaming")
    check("style schema unpolluted by coordinator internals", "style_version" not in cur)


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60); print(" STAGE 2.3 — LEARNING COORDINATOR — TEST SUITE"); print("=" * 60)
    with tempfile.TemporaryDirectory() as tmp:
        test_policy(tmp)
        test_clamp(tmp)
        test_reject(tmp)
        test_audit(tmp)
        test_confidence(tmp)
        test_versioning_and_rollback(tmp)
        test_determinism(tmp)
        test_integration_safety(tmp)
    print("\n" + "=" * 60); print(f" RESULT: {_PASS} passed, {_FAIL} failed"); print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
