"""test_analytics_replay.py — SCOS Stage 3.4 Analytics Replay Engine suite.

Drives the REAL replay chain end-to-end with NO mocks and NO stubs:

    CSV(s) / in-memory records -> YouTubeAnalyticsAdapter -> AnalyticsTranslator
        -> FeedbackEngine -> LearningCoordinator -> StyleMemoryEngine
        -> (optionally) AssetBuilderV2

Every certified component is the genuine article, exercised through its public API.
Fully isolated (temp StyleMemoryEngine store + temp work dirs + fixed injected clock)
so it NEVER touches production memory and stays 100% deterministic.

Run: python scos/replay/tests/test_analytics_replay.py
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
sys.path.insert(0, str(_HERE.parent))                                     # analytics_replay
sys.path.insert(0, str(_REPO_ROOT / "scos" / "analytics" / "adapters"))   # youtube_adapter
sys.path.insert(0, str(_REPO_ROOT / "scos" / "analytics" / "translator"))  # analytics_translator
sys.path.insert(0, str(_REPO_ROOT / "scos" / "learning"))                 # learning_policy

from analytics_replay import AnalyticsReplayEngine                       # noqa: E402
from replay_models import ReplayFatalError, REPORT_FILENAME              # noqa: E402
from analytics_models import NormalizedAnalytics                         # noqa: E402
from analytics_translator import AnalyticsTranslator                     # noqa: E402
from youtube_adapter import YouTubeAnalyticsAdapter                      # noqa: E402
from learning_policy import LearningPolicy                               # noqa: E402
from scos.analytics.feedback_engine import FeedbackEngine                # noqa: E402
from scos.learning.learning_coordinator import LearningCoordinator       # noqa: E402
from scos.memory.style_memory import StyleMemoryEngine                  # noqa: E402
from scos.assets.asset_builder import _derive_run_id                     # noqa: E402
from scos.assets.asset_builder_v2 import AssetBuilderV2                  # noqa: E402

_PASS, _FAIL = 0, 0
_FIXED_TS = 1700000000

# High-quality video: retention 0.9, ctr 0.8 (of full), engagement 1.0 -> quality 0.90 -> APPLY.
_CSV_HEADER = ("Video ID,Video publish time,Views,Watch time (hours),"
               "Average view duration,Average percentage viewed (%),"
               "Impressions click-through rate (%),Likes,Comments added,Shares,"
               "Subscribers,Duration")
_CSV_ROW = "vid_001,2026-06-01,1000,5,0:30,90,8,80,15,10,5,1:10"
_CSV_ROW_2 = "vid_002,2026-06-01,1000,5,0:30,90,8,80,15,10,5,1:10"
# Low-quality video: zero engagement, low retention/ctr -> quality < 0.50 -> REJECT.
_CSV_ROW_LOW = "vid_low,2026-06-01,1000,1,0:05,5,0,0,0,0,0,1:10"
# High retention + low engagement against a deliberately-invalid seeded style ->
# the coordinator's "unsafe value" rejection path (downgraded to a per-record FAIL).
_CSV_ROW_UNSAFE = "vid_unsafe,2026-06-01,1000,5,0:30,90,8,1,0,0,0,1:10"

SCENE_PLAN = {
    "scenes": [
        {"scene_id": "scene_00", "topic": "gaming", "start": 0.0, "end": 2.0},
        {"scene_id": "scene_01", "topic": "gaming", "start": 2.0, "end": 3.5},
    ],
    "total_duration": 3.5,
}

_SEED_PACING = 1.0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_csv(tmp: Path, row: str = _CSV_ROW, name: str = "analytics.csv") -> Path:
    p = tmp / name
    p.write_text(_CSV_HEADER + "\n" + row + "\n", encoding="utf-8")
    return p


def _record(**overrides) -> NormalizedAnalytics:
    fields = dict(
        video_id="vid_001", platform="youtube", publish_time="2026-06-01T00:00:00",
        views=1000, watch_time_seconds=18000.0, average_view_duration=30.0,
        retention_rate=0.9, ctr=0.08, likes=80, comments=15, shares=10,
        subscribers_gained=5, duration_seconds=70.0, metadata={},
    )
    fields.update(overrides)
    return NormalizedAnalytics(**fields)


def _seed_style(store: Path, style_id="youtube_v1", content_type="youtube",
                pacing=_SEED_PACING, freq=440.0, palette=None) -> StyleMemoryEngine:
    eng = StyleMemoryEngine(store)
    eng.record_video_metrics({
        "style_id": style_id, "content_type": content_type,
        "avg_color_palette": palette or [120, 120, 120], "audio_frequency_bias": freq,
        "scene_pacing_profile": pacing, "retention_score": 0.7, "created_at": 1000,
    })
    return eng


def _collaborators(tmp: Path, sub: str, *, pacing=_SEED_PACING, freq=440.0,
                   style_id="youtube_v1", content_type="youtube"):
    """Fresh, fully isolated set of certified collaborators bound to one work dir."""
    sub_dir = _ensure(tmp / sub)
    style_eng = _seed_style(sub_dir / "sm.json", style_id=style_id,
                            content_type=content_type, pacing=pacing, freq=freq)
    coordinator = LearningCoordinator(style_eng, LearningPolicy(),
                                      now_fn=lambda: _FIXED_TS, work_dir=sub_dir / "learning")
    adapter = YouTubeAnalyticsAdapter()
    translator = AnalyticsTranslator()
    feedback_engine = FeedbackEngine()
    return adapter, translator, feedback_engine, coordinator, style_eng, sub_dir


def _engine(tmp: Path, sub: str, *, with_assets=False, session_id=None, **kw):
    adapter, translator, feedback_engine, coordinator, style_eng, sub_dir = _collaborators(
        tmp, sub, **kw)
    factory = (lambda: AssetBuilderV2(style_eng)) if with_assets else None
    eng = AnalyticsReplayEngine(
        adapter, translator, feedback_engine, coordinator,
        asset_builder_factory=factory, scene_plan=SCENE_PLAN if with_assets else None,
        now_fn=lambda: _FIXED_TS, work_dir=sub_dir / "replay", session_id=session_id,
    )
    return eng, style_eng, sub_dir


# --------------------------------------------------------------------------- #
def test_single_csv_replay(tmp):
    print("\n[1] single CSV replay")
    eng, style_eng, sub_dir = _engine(tmp, "single")
    csv = _write_csv(sub_dir, _CSV_ROW, "a.csv")
    report = eng.replay(str(csv))
    check("status PASS", report["status"] == "PASS")
    check("one record processed", report["records_processed"] == 1)
    check("one record applied", report["records_applied"] == 1)
    check("decision APPLY", report["results"][0]["decision"] == "APPLY")
    check("record_id is video id", report["results"][0]["record_id"] == "vid_001")


def test_multi_file_replay_history(tmp):
    print("\n[2] multi-file replay_history — one combined report")
    eng, style_eng, sub_dir = _engine(tmp, "multi")
    csv_a = _write_csv(sub_dir, _CSV_ROW, "a.csv")
    csv_b = _write_csv(sub_dir, _CSV_ROW_2, "b.csv")
    report = eng.replay_history([str(csv_a), str(csv_b)])
    check("status PASS", report["status"] == "PASS")
    check("two records processed (combined)", report["records_processed"] == 2)
    check("two records applied", report["records_applied"] == 2)
    check("single session_id shared across both files",
          report["results"][0]["session_id"] == report["results"][1]["session_id"])


def test_replay_records_in_memory(tmp):
    print("\n[3] in-memory replay_records")
    eng, style_eng, sub_dir = _engine(tmp, "mem")
    report = eng.replay_records([_record()])
    check("status PASS", report["status"] == "PASS")
    check("one record processed", report["records_processed"] == 1)
    check("decision APPLY", report["results"][0]["decision"] == "APPLY")


def test_determinism(tmp):
    print("\n[4] deterministic repeated execution")
    eng_a, _, sub_a = _engine(tmp, "det_a")
    eng_b, _, sub_b = _engine(tmp, "det_b")
    csv_a = _write_csv(sub_a, _CSV_ROW, "a.csv")
    csv_b = _write_csv(sub_b, _CSV_ROW, "a.csv")
    rep_a = eng_a.replay(str(csv_a))
    rep_b = eng_b.replay(str(csv_b))
    a = dict(rep_a); b = dict(rep_b)
    check("reports identical (content-addressed session_id, fixed clock)", a == b)


def test_report_schema(tmp):
    print("\n[5] replay report schema")
    eng, _, sub_dir = _engine(tmp, "schema")
    csv = _write_csv(sub_dir, _CSV_ROW, "a.csv")
    report = eng.replay(str(csv))
    required = {"status", "records_processed", "records_applied", "records_rejected",
               "styles_updated", "replay_version", "results", "session_id"}
    check("top-level schema complete", required <= set(report))
    result_keys = {"record_id", "decision", "style_id", "quality_score", "run_id",
                  "asset_hash", "timestamp", "error", "session_id"}
    check("per-result schema complete", all(result_keys <= set(r) for r in report["results"]))


def test_continue_after_invalid_record(tmp):
    print("\n[6] continue after an invalid record (no abort)")
    eng, _, _ = _engine(tmp, "invalid")
    records = [_record(video_id="vid_a"),
              _record(video_id="vid_bad", retention_rate=1.5),
              _record(video_id="vid_c")]
    report = eng.replay_records(records)
    check("all 3 records processed despite one invalid", report["records_processed"] == 3)
    decisions = [r["decision"] for r in report["results"]]
    check("invalid record -> FAIL, others unaffected",
          decisions == ["APPLY", "FAIL", "APPLY"])
    check("FAIL entry carries a diagnostic error", report["results"][1]["error"] is not None)


def test_summary_statistics(tmp):
    print("\n[7] summary statistics correctness")
    eng, _, _ = _engine(tmp, "stats")
    records = [_record(video_id="vid_a"),
              _record(video_id="vid_b", retention_rate=0.05, ctr=0.0,
                      likes=0, comments=0, shares=0),
              _record(video_id="vid_c", retention_rate=2.0)]
    report = eng.replay_records(records)
    check("processed = 3", report["records_processed"] == 3)
    check("applied = 1 (vid_a)", report["records_applied"] == 1)
    check("rejected = 1 (vid_b, low quality)", report["records_rejected"] == 1)
    check("styles_updated = 1 distinct style touched", report["styles_updated"] == 1)


def test_asset_regeneration_integration(tmp):
    print("\n[8] asset regeneration integration")
    eng_with, style_eng, sub_dir = _engine(tmp, "assets_on", with_assets=True)
    csv = _write_csv(sub_dir, _CSV_ROW, "a.csv")
    rep1 = eng_with.replay(str(csv))
    check("asset_hash present when factory configured", rep1["results"][0]["asset_hash"] is not None)

    eng_no, _, sub_dir2 = _engine(tmp, "assets_off", with_assets=False)
    csv2 = _write_csv(sub_dir2, _CSV_ROW, "a.csv")
    rep2 = eng_no.replay(str(csv2))
    check("asset_hash None without factory", rep2["results"][0]["asset_hash"] is None)

    eng_with2, _, sub_dir3 = _engine(tmp, "assets_repeat", with_assets=True)
    csv3 = _write_csv(sub_dir3, _CSV_ROW, "a.csv")
    rep3 = eng_with2.replay(str(csv3))
    check("asset_hash deterministic given identical inputs",
          rep1["results"][0]["asset_hash"] == rep3["results"][0]["asset_hash"])


def test_no_dedup_duplicate_record_ids(tmp):
    print("\n[9] no dedup of repeated record_ids")
    eng, _, _ = _engine(tmp, "dup")
    records = [_record(video_id="same_id"), _record(video_id="same_id")]
    report = eng.replay_records(records)
    check("both duplicate-id records processed (no merging)", report["records_processed"] == 2)
    check("both decisions present in encounter order",
          len(report["results"]) == 2 and report["results"][0]["record_id"] == "same_id"
          and report["results"][1]["record_id"] == "same_id")


def test_report_persistence(tmp):
    print("\n[10] report persistence (atomic, valid JSON)")
    eng, _, sub_dir = _engine(tmp, "persist")
    csv = _write_csv(sub_dir, _CSV_ROW, "a.csv")
    report = eng.replay(str(csv))
    rp = sub_dir / "replay" / REPORT_FILENAME
    check("report file exists on disk", rp.exists() and rp.stat().st_size > 0)
    text = rp.read_text(encoding="utf-8")
    on_disk = json.loads(text)
    check("on-disk report matches return value", on_disk == report)
    check("sort_keys + indent formatting", text == json.dumps(report, sort_keys=True,
                                                               indent=2, ensure_ascii=False))


def test_confidence_bounded(tmp):
    print("\n[11] confidence remains bounded [0,1]")
    eng, _, sub_dir = _engine(tmp, "conf")
    records = [_record(video_id=f"vid_{i}") for i in range(10)]
    eng.replay_records(records)
    state = json.loads((sub_dir / "learning" / "learning_state.json").read_text(encoding="utf-8"))
    check("confidence within [0,1]", 0.0 <= state["confidence"] <= 1.0)


def test_audit_log_validity(tmp):
    print("\n[12] audit log validity (incl. unsafe -> FAIL case)")
    eng, style_eng, sub_dir = _engine(tmp, "audit", style_id="unsafe_v1",
                                      content_type="youtube", freq=-500.0)
    csv = _write_csv(sub_dir, _CSV_ROW_UNSAFE, "a.csv")
    report = eng.replay(str(csv))
    check("unsafe coordinator rejection downgraded to FAIL, not aborted",
          report["status"] == "PASS" and report["results"][0]["decision"] == "FAIL")
    audit = json.loads((sub_dir / "learning" / "learning_audit.json").read_text(encoding="utf-8"))
    check("audit log is a non-empty list", isinstance(audit, list) and len(audit) >= 1)
    check("audit entry recorded for the unsafe rejection (coordinate() did run)",
          any("unsafe value" in (e.get("reason") or "") for e in audit))
    check("every audit entry has the required fields",
          all({"audit_id", "decision", "reason", "timestamp"} <= set(e) for e in audit))


def test_style_history_validity(tmp):
    print("\n[13] style history validity")
    eng, _, sub_dir = _engine(tmp, "history")
    csv = _write_csv(sub_dir, _CSV_ROW, "a.csv")
    eng.replay(str(csv))
    history = json.loads((sub_dir / "learning" / "style_history.json").read_text(encoding="utf-8"))
    check("history keyed by style_id", "youtube_v1" in history)
    check("history has seed (v0) + applied (v1) snapshots",
          {s["version"] for s in history["youtube_v1"]} == {0, 1})


def test_multiple_runs_byte_identical(tmp):
    print("\n[14] multiple full runs byte-identical across all artifacts")
    eng_a, _, sub_a = _engine(tmp, "rep_a")
    eng_b, _, sub_b = _engine(tmp, "rep_b")
    csv_a = _write_csv(sub_a, _CSV_ROW, "a.csv")
    csv_b = _write_csv(sub_b, _CSV_ROW, "a.csv")
    eng_a.replay(str(csv_a))
    eng_b.replay(str(csv_b))
    for fname, sub in (("replay/" + REPORT_FILENAME, None),
                       ("learning/learning_audit.json", None),
                       ("learning/learning_state.json", None),
                       ("learning/style_history.json", None)):
        text_a = (sub_a / fname).read_text(encoding="utf-8")
        text_b = (sub_b / fname).read_text(encoding="utf-8")
        check(f"{fname} byte-identical across independent runs", text_a == text_b)


def test_fatal_missing_file(tmp):
    print("\n[15] fatal error on unreadable dataset (aborts, no report-of-record)")
    eng, _, sub_dir = _engine(tmp, "fatal")
    raised = False
    try:
        eng.replay(str(sub_dir / "does_not_exist.csv"))
    except ReplayFatalError as exc:
        raised = True
        check("fatal error stage is load", exc.stage == "load")
    check("ReplayFatalError raised for missing file", raised)
    check("no report written on fatal abort", not (sub_dir / "replay" / REPORT_FILENAME).exists())


def test_progress_callback_side_channel(tmp):
    print("\n[16] progress callback is a pure side channel")
    eng, _, sub_dir = _engine(tmp, "progress")
    csv = _write_csv(sub_dir, _CSV_ROW, "a.csv")
    calls = []
    report_with_cb = eng.replay(str(csv), on_progress=lambda p, t, rid: calls.append((p, t, rid)))

    eng2, _, sub_dir2 = _engine(tmp, "progress_nocb")
    csv2 = _write_csv(sub_dir2, _CSV_ROW, "a.csv")
    report_without_cb = eng2.replay(str(csv2))

    check("progress callback invoked", len(calls) == 1 and calls[0][0] == 1 and calls[0][1] == 1)
    check("callback presence/absence does not change the report",
          report_with_cb == report_without_cb)


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("=" * 64)
    print(" STAGE 3.4 — ANALYTICS REPLAY ENGINE — TEST SUITE")
    print("=" * 64)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        test_single_csv_replay(tmp)
        test_multi_file_replay_history(tmp)
        test_replay_records_in_memory(tmp)
        test_determinism(tmp)
        test_report_schema(tmp)
        test_continue_after_invalid_record(tmp)
        test_summary_statistics(tmp)
        test_asset_regeneration_integration(tmp)
        test_no_dedup_duplicate_record_ids(tmp)
        test_report_persistence(tmp)
        test_confidence_bounded(tmp)
        test_audit_log_validity(tmp)
        test_style_history_validity(tmp)
        test_multiple_runs_byte_identical(tmp)
        test_fatal_missing_file(tmp)
        test_progress_callback_side_channel(tmp)
    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
