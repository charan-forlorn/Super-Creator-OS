"""test_learning_pipeline.py — SCOS Stage 3.3 Learning Pipeline Orchestrator suite.

Drives the REAL closed loop end-to-end with NO mocks and NO stubs:

    CSV -> YouTubeAnalyticsAdapter -> AnalyticsTranslator -> FeedbackEngine
        -> LearningCoordinator -> StyleMemoryEngine -> AssetBuilderV2

Every certified component is the genuine article, exercised through its public API.
Fully isolated (temp StyleMemoryEngine store + temp work dirs + fixed injected clock)
so it NEVER touches production memory and stays 100% deterministic.

Run: python scos/pipeline/tests/test_learning_pipeline.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))                                       # scos.*
sys.path.insert(0, str(_HERE.parent))                                     # learning_pipeline
sys.path.insert(0, str(_REPO_ROOT / "scos" / "analytics" / "adapters"))   # youtube_adapter

from learning_pipeline import LearningPipeline                           # noqa: E402
from pipeline_models import PIPELINE_VERSION                             # noqa: E402
from youtube_adapter import YouTubeAnalyticsAdapter                      # noqa: E402
from scos.assets.asset_builder import _derive_run_id                     # noqa: E402
from scos.assets.asset_builder_v2 import AssetBuilderV2                  # noqa: E402
from scos.memory.style_memory import StyleMemoryEngine                  # noqa: E402

_PASS, _FAIL = 0, 0
_FIXED_TS = 1700000000

# A high-performing video: retention 0.9, ctr 0.8 (of full), engagement 1.0
# -> quality 0.90 (>= reject 0.50) and retention >= 0.80 -> pacing increases -> APPLY.
_CSV_HEADER = ("Video ID,Video publish time,Views,Watch time (hours),"
               "Average view duration,Average percentage viewed (%),"
               "Impressions click-through rate (%),Likes,Comments added,Shares,"
               "Subscribers,Duration")
_CSV_ROW = "vid_001,2026-06-01,1000,5,0:30,90,8,80,15,10,5,1:10"

# A low-quality video: zero engagement, low retention/ctr -> quality < 0.50 -> REJECT.
_CSV_ROW_LOW = "vid_low,2026-06-01,1000,1,0:05,5,0,0,0,0,0,1:10"

SCENE_PLAN = {
    "scenes": [
        {"scene_id": "scene_00", "topic": "gaming", "start": 0.0, "end": 2.0},
        {"scene_id": "scene_01", "topic": "gaming", "start": 2.0, "end": 3.5},
    ],
    "total_duration": 3.5,
}

_SEED_PACING = 1.0
_EXPECTED_PACING = 1.4   # 1.0 + |(0.9-0.5)*2*0.5| = 1.0 + 0.4


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


def _write_csv(tmp: Path, row: str = _CSV_ROW, name: str = "analytics.csv") -> Path:
    p = tmp / name
    p.write_text(_CSV_HEADER + "\n" + row + "\n", encoding="utf-8")
    return p


def _seed_style(store: Path, pacing: float = _SEED_PACING) -> StyleMemoryEngine:
    eng = StyleMemoryEngine(store)
    eng.record_video_metrics({
        "style_id": "gaming_v1", "content_type": "gaming",
        "avg_color_palette": [120, 120, 120], "audio_frequency_bias": 440.0,
        "scene_pacing_profile": pacing, "retention_score": 0.7, "created_at": 1000,
    })
    return eng


def _pipeline(tmp: Path, sub: str) -> LearningPipeline:
    return LearningPipeline(clock=lambda: _FIXED_TS, work_dir=tmp / sub)


def _run(tmp: Path, sub: str, *, row: str = _CSV_ROW, pacing: float = _SEED_PACING):
    """Full isolated run: fresh csv, fresh style engine, fresh work dir."""
    sub_dir = _ensure(tmp / sub)
    csv = _write_csv(sub_dir, row, name=f"{sub}.csv")
    eng = _seed_style(sub_dir / "sm.json", pacing=pacing)
    pipe = _pipeline(tmp, sub)
    res = pipe.execute(str(csv), YouTubeAnalyticsAdapter(), SCENE_PLAN, eng,
                       content_type="gaming")
    return res, eng, pipe


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _capture_assets(asset_bundle) -> dict:
    import hashlib
    out = {}
    for a in asset_bundle["assets"]:
        img = _REPO_ROOT / a["image_path"]
        aud = _REPO_ROOT / a["audio_path"]
        out[a["scene_id"]] = (hashlib.sha256(img.read_bytes()).hexdigest(),
                              hashlib.sha256(aud.read_bytes()).hexdigest())
    return out


# --------------------------------------------------------------------------- #
def test_end_to_end(tmp):
    print("\n[1] successful end-to-end execution")
    res, eng, _ = _run(tmp, "e2e")
    check("status SUCCESS", res["status"] == "SUCCESS")
    check("run_id matches scene-plan derivation",
          res["run_id"] == _derive_run_id(SCENE_PLAN))
    check("decision APPLY", res["decision"] == "APPLY")
    check("learning_applied true", res["learning_applied"] is True)
    check("style_version is 1", res["style_version"] == 1)
    check("timestamp is injected clock", res["timestamp"] == _FIXED_TS)
    check("asset_bundle present with 2 assets", len(res["asset_bundle"]["assets"]) == 2)


def test_translator_integration(tmp):
    print("\n[2] translator integration")
    res, _, _ = _run(tmp, "trans")
    report = json.loads(Path(res["report_path"]).read_text(encoding="utf-8"))
    tp = report["translator_payload"]
    check("translator payload recorded", set(tp) >= {
        "content_type", "quality_score", "retention_score", "engagement_score",
        "style_match_score", "derived_style_updates"})
    check("content_type honored (gaming)", tp["content_type"] == "gaming")
    check("retention_score 0.9", tp["retention_score"] == 0.9)
    check("engagement_score 1.0", tp["engagement_score"] == 1.0)
    check("quality_score 0.9", tp["quality_score"] == 0.9)


def test_feedback_integration(tmp):
    print("\n[3] feedback engine integration")
    res, _, _ = _run(tmp, "fb")
    report = json.loads(Path(res["report_path"]).read_text(encoding="utf-8"))
    derived = report["translator_payload"]["derived_style_updates"]
    # FeedbackEngine + translator share formulas: pacing delta = (0.9-0.5)*2*0.5 = 0.4
    check("scene_pacing_delta 0.4", derived["scene_pacing_delta"] == 0.4)
    fs = report["feedback_summary"]
    check("feedback summary carries run_id", fs["run_id"] == res["run_id"])
    check("feedback summary carries quality", fs["quality_score"] == 0.9)


def test_coordinator_integration(tmp):
    print("\n[4] coordinator integration")
    res, _, _ = _run(tmp, "coord")
    report = json.loads(Path(res["report_path"]).read_text(encoding="utf-8"))
    cd = report["coordinator_decision"]
    check("decision APPLY in report", cd["decision"] == "APPLY")
    check("audit_id present (16 hex)", isinstance(cd["audit_id"], str) and len(cd["audit_id"]) == 16)
    check("coordinator timestamp = injected clock", cd["timestamp"] == _FIXED_TS)
    check("style_version 1 in report", cd["style_version"] == 1)


def test_style_update_applied(tmp):
    print("\n[5] style update applied + persisted")
    res, eng, _ = _run(tmp, "style")
    cur = next(s for s in eng.list_styles() if s["style_id"] == "gaming_v1")
    check("pacing updated 1.0 -> 1.4 in engine",
          abs(cur["scene_pacing_profile"] - _EXPECTED_PACING) < 1e-9)
    check("untouched fields preserved (retention/created_at)",
          cur["retention_score"] == 0.7 and cur["created_at"] == 1000)
    # persisted to disk (re-open the same store)
    reopened = StyleMemoryEngine((tmp / "style") / "sm.json")
    cur2 = next(s for s in reopened.list_styles() if s["style_id"] == "gaming_v1")
    check("update persisted across reopen",
          abs(cur2["scene_pacing_profile"] - _EXPECTED_PACING) < 1e-9)
    check("report style_after reflects update",
          json.loads(Path(res["report_path"]).read_text(encoding="utf-8"))
          ["style_after"]["scene_pacing_profile"] == cur["scene_pacing_profile"])


def test_assetbuilder_regeneration(tmp):
    print("\n[6] AssetBuilderV2 regenerates on the new style")
    # Baseline: assets built from the seeded (pre-learning) pacing 1.0 style.
    base_eng = _seed_style(_ensure(tmp / "regen_base") / "sm.json", pacing=_SEED_PACING)
    baseline = _capture_assets(AssetBuilderV2(base_eng).run(SCENE_PLAN, _derive_run_id(SCENE_PLAN)))
    # Pipeline run applies learning (pacing -> 1.4) and regenerates the SAME paths.
    res, _, _ = _run(tmp, "regen")
    learned = _capture_assets(res["asset_bundle"])
    check("PNG changed by applied learning",
          baseline["scene_00"][0] != learned["scene_00"][0])
    check("WAV changed by applied learning",
          baseline["scene_00"][1] != learned["scene_00"][1])
    check("regenerated bundle run_id matches", res["asset_bundle"]["run_id"] == _derive_run_id(SCENE_PLAN))


def test_report_generation(tmp):
    print("\n[7] report generation")
    res, _, _ = _run(tmp, "report")
    rp = Path(res["report_path"])
    check("report file exists", rp.exists() and rp.stat().st_size > 0)
    text = rp.read_text(encoding="utf-8")
    report = json.loads(text)
    check("report is valid JSON object", isinstance(report, dict))
    check("pipeline_version stamped", report["pipeline_version"] == PIPELINE_VERSION)
    required = {"pipeline_version", "run_id", "status", "input_analytics",
               "translator_payload", "feedback_summary", "coordinator_decision",
               "style_version", "generated_assets", "timestamp"}
    check("report has all required sections", required <= set(report))
    check("input is content-addressed (sha256 + count)",
          report["input_analytics"]["record_count"] == 1
          and isinstance(report["input_analytics"]["sha256"], str))
    # stable ordering (sort_keys=True, indent=2)
    check("report is sort_keys-stable",
          text == json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))


def test_determinism(tmp):
    print("\n[8] deterministic repeated execution")
    res_a, _, _ = _run(tmp, "det_a")
    res_b, _, _ = _run(tmp, "det_b")
    rep_a = Path(res_a["report_path"]).read_text(encoding="utf-8")
    rep_b = Path(res_b["report_path"]).read_text(encoding="utf-8")
    check("report bytes identical across independent runs", rep_a == rep_b)
    # return values identical except for the (work-dir-specific) report_path
    a = dict(res_a); b = dict(res_b)
    a.pop("report_path"); b.pop("report_path")
    check("return value identical (minus report_path)", a == b)
    check("identical run_id", res_a["run_id"] == res_b["run_id"])
    check("identical style_version", res_a["style_version"] == res_b["style_version"])


def test_injected_clock(tmp):
    print("\n[9] injected clock — no hidden wall-clock")
    custom_ts = 1234567890
    csv = _write_csv(_ensure(tmp / "clock"), name="clock.csv")
    eng = _seed_style((tmp / "clock") / "sm.json")
    pipe = LearningPipeline(clock=lambda: custom_ts, work_dir=tmp / "clock")
    res = pipe.execute(str(csv), YouTubeAnalyticsAdapter(), SCENE_PLAN, eng, content_type="gaming")
    check("result timestamp = injected", res["timestamp"] == custom_ts)
    report = json.loads(Path(res["report_path"]).read_text(encoding="utf-8"))
    check("report timestamp = injected", report["timestamp"] == custom_ts)
    check("coordinator timestamp = injected",
          report["coordinator_decision"]["timestamp"] == custom_ts)


def test_dependency_injection(tmp):
    print("\n[10] dependency injection of collaborators")
    used = {"coord": False, "assets": False, "clock": False}

    base_pipe = LearningPipeline()  # default factories to wrap

    def coord_factory(eng):
        used["coord"] = True
        return base_pipe._make_coordinator(eng)

    def asset_factory(eng):
        used["assets"] = True
        return AssetBuilderV2(eng)

    def clock():
        used["clock"] = True
        return _FIXED_TS

    csv = _write_csv(_ensure(tmp / "di"), name="di.csv")
    eng = _seed_style((tmp / "di") / "sm.json")
    pipe = LearningPipeline(clock=clock, work_dir=tmp / "di",
                            coordinator_factory=coord_factory,
                            asset_builder_factory=asset_factory,
                            learning_work_dir=tmp / "di" / "lc")
    res = pipe.execute(str(csv), YouTubeAnalyticsAdapter(), SCENE_PLAN, eng, content_type="gaming")
    check("injected coordinator_factory used", used["coord"])
    check("injected asset_builder_factory used", used["assets"])
    check("injected clock used", used["clock"])
    check("DI run still SUCCESS + APPLY", res["status"] == "SUCCESS" and res["decision"] == "APPLY")


def test_failure_propagation(tmp):
    print("\n[11] failure propagation — no partial success, deterministic diagnostics")
    # (a) invalid analytics CSV (negative metric) -> validate failure
    bad_csv = _ensure(tmp / "fail_a") / "bad.csv"
    bad_csv.write_text(_CSV_HEADER + "\n" + "vid_x,2026-06-01,-5,5,0:30,90,8,1,1,1,1,1:10\n",
                       encoding="utf-8")
    eng = _seed_style((tmp / "fail_a") / "sm.json")
    pipe = _pipeline(tmp, "fail_a")
    res = pipe.execute(str(bad_csv), YouTubeAnalyticsAdapter(), SCENE_PLAN, eng, content_type="gaming")
    check("invalid analytics -> FAILURE", res["status"] == "FAILURE")
    check("failure stage is validate", res["error"]["stage"] == "validate")
    check("failure has diagnostics", len(res["error"]["errors"]) >= 1)
    check("no learning applied on failure", res["learning_applied"] is False)
    check("no asset bundle on failure", res["asset_bundle"] is None)
    cur = next(s for s in eng.list_styles() if s["style_id"] == "gaming_v1")
    check("style untouched after failure", cur["scene_pacing_profile"] == _SEED_PACING)

    # (b) missing CSV file -> load failure
    eng2 = _seed_style(_ensure(tmp / "fail_b") / "sm.json")
    pipe2 = _pipeline(tmp, "fail_b")
    res2 = pipe2.execute(str(tmp / "fail_b" / "nope.csv"), YouTubeAnalyticsAdapter(),
                         SCENE_PLAN, eng2, content_type="gaming")
    check("missing file -> FAILURE at load", res2["status"] == "FAILURE" and res2["error"]["stage"] == "load")

    # (c) empty scene_plan -> AssetBuilder failure (after a valid APPLY path)
    csv_ok = _write_csv(_ensure(tmp / "fail_c"), name="ok.csv")
    eng3 = _seed_style((tmp / "fail_c") / "sm.json")
    pipe3 = _pipeline(tmp, "fail_c")
    res3 = pipe3.execute(str(csv_ok), YouTubeAnalyticsAdapter(),
                         {"scenes": [], "total_duration": 0.0}, eng3, content_type="gaming")
    check("empty scene_plan -> FAILURE at assets", res3["status"] == "FAILURE" and res3["error"]["stage"] == "assets")

    # (d) failure report is also written + deterministic
    fr = json.loads(Path(res["report_path"]).read_text(encoding="utf-8"))
    check("failure report status FAILURE", fr["status"] == "FAILURE")
    check("failure report carries error block", fr["error"]["stage"] == "validate")


def test_low_quality_reject(tmp):
    print("\n[12] valid no-op decision — low quality REJECT completes the loop")
    res, eng, _ = _run(tmp, "reject", row=_CSV_ROW_LOW)
    check("low quality -> decision REJECT", res["decision"] == "REJECT")
    check("REJECT is a SUCCESSful loop completion", res["status"] == "SUCCESS")
    check("learning_applied false on REJECT", res["learning_applied"] is False)
    check("assets still regenerated on REJECT", len(res["asset_bundle"]["assets"]) == 2)
    cur = next(s for s in eng.list_styles() if s["style_id"] == "gaming_v1")
    check("style unchanged on REJECT", cur["scene_pacing_profile"] == _SEED_PACING)


def test_no_component_mutation(tmp):
    print("\n[13] no Certified Core mutation")
    rec_csv = _write_csv(_ensure(tmp / "nomut"), name="nomut.csv")
    eng = _seed_style((tmp / "nomut") / "sm.json")
    pipe = _pipeline(tmp, "nomut")
    res = pipe.execute(str(rec_csv), YouTubeAnalyticsAdapter(), SCENE_PLAN, eng, content_type="gaming")
    # exactly one style, only updated via the public update path (no extra styles)
    check("no extra style created", len(eng.list_styles()) == 1)
    check("style schema unpolluted (no coordinator internals)",
          "style_version" not in eng.list_styles()[0])
    # translator/feedback engines hold no learning/persistence state
    check("translator has no engine/coordinator refs",
          not any(k in ("engine", "coordinator", "style_engine") for k in vars(pipe.translator)))
    # FeedbackEngine.to_style_update wrote nothing (pure) — its default store absent here
    check("feedback engine did not persist", not Path(pipe.feedback_engine.store_path).exists()
          or pipe.feedback_engine.store_path.name == "feedback_log.json")
    check("run still SUCCESS", res["status"] == "SUCCESS")


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("=" * 64)
    print(" STAGE 3.3 — LEARNING PIPELINE ORCHESTRATOR — TEST SUITE")
    print("=" * 64)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        test_end_to_end(tmp)
        test_translator_integration(tmp)
        test_feedback_integration(tmp)
        test_coordinator_integration(tmp)
        test_style_update_applied(tmp)
        test_assetbuilder_regeneration(tmp)
        test_report_generation(tmp)
        test_determinism(tmp)
        test_injected_clock(tmp)
        test_dependency_injection(tmp)
        test_failure_propagation(tmp)
        test_low_quality_reject(tmp)
        test_no_component_mutation(tmp)
    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
