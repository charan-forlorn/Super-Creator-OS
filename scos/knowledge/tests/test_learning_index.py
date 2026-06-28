"""test_learning_index.py — SCOS Stage 3.5 Learning Knowledge Index suite.

Plain-assert script (this project's convention, not pytest). Hand-crafts minimal,
exact-schema fixtures for the 4 source artifacts (feedback_log.json,
learning_audit.json, style_history.json, replay_report.json) — the indexer is
fully decoupled from the engines that normally produce them, so testing it
against hand-built JSON is the correct, isolated way to exercise its parsing,
correlation, validation, and determinism logic.

Run: python scos/knowledge/tests/test_learning_index.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_HERE.parent))  # knowledge_index, query, index_store, timeline, models

from knowledge_index import LearningKnowledgeIndex  # noqa: E402
from index_store import IndexStore  # noqa: E402
from knowledge_models import DECISION_ROLLBACK  # noqa: E402
import query as q  # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False), encoding="utf-8")


def _paths(base: Path):
    return dict(
        feedback_log_path=base / "analytics" / "feedback_log.json",
        learning_audit_path=base / "learning" / "learning_audit.json",
        style_history_path=base / "learning" / "style_history.json",
        replay_report_path=base / "replay" / "replay_report.json",
    )


_PROFILE_A = {"style_id": "style_a", "content_type": "youtube", "avg_color_palette": [10, 10, 10],
              "audio_frequency_bias": 440.0, "scene_pacing_profile": 1.0}
_PROFILE_B = {"style_id": "style_b", "content_type": "youtube", "avg_color_palette": [20, 20, 20],
              "audio_frequency_bias": 400.0, "scene_pacing_profile": 1.2}


def _seed_rich_repo(base: Path) -> dict:
    """A coherent fixture set: 2 styles, an APPLY, a REJECT, a ROLLBACK, a
    replay-linked run, a replay FAIL, and matching feedback_log/style_history
    cross-references — used by most of the "happy path" tests below."""
    p = _paths(base)

    audit = [
        {
            "audit_id": "aid_apply_1", "decision": "APPLY", "reason": "policy applied",
            "style_before": _PROFILE_A, "style_after": _PROFILE_A,
            "feedback_summary": {"run_id": "run_apply_1", "retention_score": 0.8,
                                 "engagement_score": 0.7, "style_match_score": 0.6,
                                 "quality_score": 0.9},
            "timestamp": 100,
        },
        {
            "audit_id": "aid_reject_1", "decision": "REJECT", "reason": "quality below threshold",
            "style_before": _PROFILE_A, "style_after": _PROFILE_A,
            "feedback_summary": {"run_id": "run_reject_1", "retention_score": 0.2,
                                 "engagement_score": 0.1, "style_match_score": 0.2,
                                 "quality_score": 0.3},
            "timestamp": 200,
        },
        {
            "audit_id": "aid_rollback_1", "decision": "ROLLBACK",
            "reason": "restored version 0",
            "style_before": _PROFILE_A, "style_after": _PROFILE_A,
            "feedback_summary": {}, "timestamp": 300,
        },
        {
            "audit_id": "aid_apply_b1", "decision": "APPLY", "reason": "policy applied",
            "style_before": _PROFILE_B, "style_after": _PROFILE_B,
            "feedback_summary": {"run_id": "run_apply_b1", "retention_score": 0.9,
                                 "engagement_score": 0.9, "style_match_score": 0.9,
                                 "quality_score": 0.95},
            "timestamp": 150,
        },
    ]
    _write_json(p["learning_audit_path"], audit)

    feedback_log = [
        {"run_id": "run_apply_1", "retention_score": 0.8, "engagement_score": 0.7,
         "style_match_score": 0.6, "quality_score": 0.9,
         "derived_style_updates": {"content_type": "youtube", "audio_frequency_bias_delta": 5.0,
                                   "scene_pacing_delta": 0.1, "palette_shift_hint": [1, 1, 1]}},
        {"run_id": "run_reject_1", "retention_score": 0.2, "engagement_score": 0.1,
         "style_match_score": 0.2, "quality_score": 0.3,
         "derived_style_updates": {"content_type": "youtube", "audio_frequency_bias_delta": 30.0,
                                   "scene_pacing_delta": -0.4, "palette_shift_hint": [5, 5, 5]}},
        {"run_id": "run_apply_b1", "retention_score": 0.9, "engagement_score": 0.9,
         "style_match_score": 0.9, "quality_score": 0.95,
         "derived_style_updates": {"content_type": "youtube", "audio_frequency_bias_delta": 1.0,
                                   "scene_pacing_delta": 0.05, "palette_shift_hint": [0, 0, 0]}},
    ]
    _write_json(p["feedback_log_path"], feedback_log)

    style_history = {
        "style_a": [
            {"version": 0, "profile": _PROFILE_A, "audit_id": "seed", "timestamp": 90},
            {"version": 1, "profile": _PROFILE_A, "audit_id": "aid_apply_1", "timestamp": 100},
        ],
        "style_b": [
            {"version": 0, "profile": _PROFILE_B, "audit_id": "seed", "timestamp": 140},
            {"version": 1, "profile": _PROFILE_B, "audit_id": "aid_apply_b1", "timestamp": 150},
        ],
    }
    _write_json(p["style_history_path"], style_history)

    replay_report = {
        "status": "PASS", "records_processed": 2, "records_applied": 1, "records_rejected": 0,
        "styles_updated": 1, "replay_version": 1, "session_id": "replay_abc123",
        "results": [
            {"record_id": "vid1", "decision": "APPLY", "style_id": "style_a",
             "quality_score": 0.9, "run_id": "run_apply_1", "asset_hash": "deadbeef",
             "timestamp": 100, "error": None, "session_id": "replay_abc123"},
            {"record_id": "vidFAIL", "decision": "FAIL", "style_id": None,
             "quality_score": None, "run_id": "run_replay_fail", "asset_hash": None,
             "timestamp": 110, "error": "translation error", "session_id": "replay_abc123"},
        ],
    }
    _write_json(p["replay_report_path"], replay_report)
    return p


def test_empty_repository(tmp):
    print("\n[1] empty repository — no source files at all")
    base = tmp / "empty"
    idx = LearningKnowledgeIndex(**_paths(base))
    index = idx.build(now_fn=lambda: 1000)
    check("no events", len(index.events) == 0)
    check("no timelines", len(index.timeline) == 0)
    check("all 4 sources missing", set(index.statistics["counts"]["sources_missing"])
          == {"feedback_log", "learning_audit", "style_history", "replay_report"})
    check("no validation issues", len(index.validation_issues) == 0)
    check("consistency defaults to 1.0", index.statistics["consistency"] == 1.0)
    check("build_id present", index.metadata["build_id"].startswith("kidx_"))


def test_single_learning_event(tmp):
    print("\n[2] single learning event")
    base = tmp / "single"
    p = _paths(base)
    _write_json(p["learning_audit_path"], [{
        "audit_id": "aid_x", "decision": "APPLY", "reason": "policy applied",
        "style_before": _PROFILE_A, "style_after": _PROFILE_A,
        "feedback_summary": {"run_id": "run_x", "retention_score": 0.5,
                             "engagement_score": 0.5, "style_match_score": 0.5,
                             "quality_score": 0.5},
        "timestamp": 50,
    }])
    idx = LearningKnowledgeIndex(**p)
    index = idx.build(now_fn=lambda: 1000)
    check("one event indexed", len(index.events) == 1)
    check("event is the audit decision", index.events[0].decision == "APPLY")
    check("sources_missing has the other 3", len(index.statistics["counts"]["sources_missing"]) == 3)


def test_multiple_style_versions_and_replay_mapping(tmp):
    print("\n[3+4] multiple style versions + replay mapping")
    base = tmp / "rich"
    _seed_rich_repo(base)
    idx = LearningKnowledgeIndex(**_paths(base))
    index = idx.build(now_fn=lambda: 1000)

    tl_a = index.timeline.get("style_a")
    check("style_a has 2 versions", tl_a is not None and len(tl_a.versions) == 2)
    check("style_a current_version == 1", tl_a.current_version == 1)

    apply_event = next(e for e in index.events if e.run_id == "run_apply_1")
    check("replay-linked event gets session_id backfilled",
          apply_event.session_id == "replay_abc123")
    check("replay-linked event gets replay_id backfilled",
          apply_event.replay_id == "replay_abc123")
    check("asset_map carries the asset_hash", index.asset_map.get("run_apply_1") == "deadbeef")


def test_rollback_history_and_timeline(tmp):
    print("\n[5+12] rollback history + timeline correctness")
    base = tmp / "rich2"
    _seed_rich_repo(base)
    idx = LearningKnowledgeIndex(**_paths(base))
    index = idx.build(now_fn=lambda: 1000)

    rollbacks = q.find_rollbacks(index)
    check("exactly one rollback found", len(rollbacks) == 1)
    check("rollback decision constant matches", rollbacks[0].decision == DECISION_ROLLBACK)

    tl_a = q.timeline(index, "style_a")
    check("rollback event attached to style_a's timeline",
          any(e.decision == "ROLLBACK" for e in tl_a.events))
    check("rollback did not create a 3rd version", len(tl_a.versions) == 2)


def test_duplicate_detection(tmp):
    print("\n[6] duplicate detection (artifact-aware)")
    base = tmp / "dup"
    p = _paths(base)
    _write_json(p["learning_audit_path"], [
        {"audit_id": "aid_dup", "decision": "APPLY", "reason": "x",
         "style_before": _PROFILE_A, "style_after": _PROFILE_A,
         "feedback_summary": {"run_id": "r1"}, "timestamp": 10},
        {"audit_id": "aid_dup", "decision": "APPLY", "reason": "y",
         "style_before": _PROFILE_A, "style_after": _PROFILE_A,
         "feedback_summary": {"run_id": "r2"}, "timestamp": 20},
    ])
    _write_json(p["feedback_log_path"], [
        {"run_id": "r3", "retention_score": 0.5, "engagement_score": 0.5,
         "style_match_score": 0.5, "quality_score": 0.5, "derived_style_updates": {}},
        {"run_id": "r3", "retention_score": 0.6, "engagement_score": 0.6,
         "style_match_score": 0.6, "quality_score": 0.6, "derived_style_updates": {}},
    ])
    idx = LearningKnowledgeIndex(**p)
    index = idx.build(now_fn=lambda: 1000)
    check("duplicate audit_id -> only 1 audit event indexed", len(
        [e for e in index.events if e.source == "learning_audit"]) == 1)
    check("duplicate run_id -> only 1 feedback event indexed", len(
        [e for e in index.events if e.source == "feedback_log"]) == 1)
    check("2 validation issues recorded", index.statistics["errors"]["validation_issue_count"] == 2)
    # Replay results may legitimately repeat run_id (Stage 3.4 no-dedup behavior) —
    # confirm that is NOT flagged as corruption.
    replay_report = {
        "status": "PASS", "records_processed": 2, "records_applied": 0, "records_rejected": 0,
        "styles_updated": 0, "replay_version": 1, "session_id": "s1",
        "results": [
            {"record_id": "same", "decision": "REJECT", "style_id": None, "quality_score": None,
             "run_id": "dup_run", "asset_hash": None, "timestamp": 1, "error": None, "session_id": "s1"},
            {"record_id": "same", "decision": "REJECT", "style_id": None, "quality_score": None,
             "run_id": "dup_run", "asset_hash": None, "timestamp": 2, "error": None, "session_id": "s1"},
        ],
    }
    _write_json(p["replay_report_path"], replay_report)
    index2 = LearningKnowledgeIndex(**p).build(now_fn=lambda: 1000)
    check("duplicate replay run_id is NOT a validation error", len(
        [i for i in index2.validation_issues if i.source == "replay_report"]) == 0)
    check("both replay results still indexed (no dedup)", len(
        [e for e in index2.events if e.source == "replay_report"]) == 2)


def test_missing_files_tolerated(tmp):
    print("\n[7] missing files tolerated, individually and combined")
    base = tmp / "missing"
    p = _paths(base)
    _write_json(p["learning_audit_path"], [{
        "audit_id": "aid_only", "decision": "APPLY", "reason": "x",
        "style_before": _PROFILE_A, "style_after": _PROFILE_A,
        "feedback_summary": {"run_id": "r1"}, "timestamp": 5,
    }])
    # feedback_log, style_history, replay_report all absent.
    index = LearningKnowledgeIndex(**p).build(now_fn=lambda: 1000)
    check("indexing succeeds with only 1 of 4 sources present", len(index.events) == 1)
    check("3 sources reported missing", len(index.statistics["counts"]["sources_missing"]) == 3)
    check("no validation issues from missing (not malformed) files",
          len(index.validation_issues) == 0)


def test_corrupted_records_isolated(tmp):
    print("\n[8] corrupted records isolated, not fatal")
    base = tmp / "corrupt"
    p = _paths(base)
    _write_json(p["learning_audit_path"], [
        "not_a_dict",
        {"audit_id": "aid_bad", "style_before": _PROFILE_A},  # missing decision/timestamp
        {"audit_id": "aid_good", "decision": "APPLY", "reason": "x",
         "style_before": _PROFILE_A, "style_after": _PROFILE_A,
         "feedback_summary": {"run_id": "r_good"}, "timestamp": 7},
    ])
    index = LearningKnowledgeIndex(**p).build(now_fn=lambda: 1000)
    check("only the 1 good record indexed", len(index.events) == 1)
    check("good record is the right one", index.events[0].run_id == "r_good")
    check("2 corrupted records reported as issues",
          index.statistics["errors"]["validation_issue_count"] == 2)


def test_broken_reference_not_counted_as_coverage(tmp):
    """Regression test for the Stage 3.5 certification finding: a style_history
    snapshot whose audit_id does NOT resolve to a real audit entry must be
    flagged as a broken reference AND must NOT also be counted as "linked" for
    coverage purposes — the two statistics must not contradict each other."""
    print("\n[15] broken reference is not double-counted as coverage")
    base = tmp / "broken_ref"
    p = _paths(base)
    _write_json(p["style_history_path"], {
        "style_a": [
            {"version": 0, "profile": _PROFILE_A, "audit_id": "seed", "timestamp": 1},
            {"version": 1, "profile": _PROFILE_A, "audit_id": "audit_id_that_does_not_exist",
             "timestamp": 2},
        ],
    })
    # No learning_audit.json at all -> the v1 snapshot's audit_id can never resolve.
    index = LearningKnowledgeIndex(**p).build(now_fn=lambda: 1000)

    broken_event = next(e for e in index.events
                        if e.source == "style_history" and e.style_version == 1)
    check("broken-reference event marked unresolved", broken_event.metadata["resolved"] is False)
    check("broken reference reported as a validation issue",
          any("does not resolve" in i.message for i in index.validation_issues))
    check("coverage excludes the unresolved event (only the seed v0 counts)",
          index.statistics["coverage"] == round(1 / 2, 6))


def test_deterministic_ordering_and_serialization(tmp):
    print("\n[9+10] deterministic ordering + byte-identical serialization")
    base = tmp / "det"
    _seed_rich_repo(base)
    p = _paths(base)
    store_path = base / "knowledge" / "index.json"

    idx1 = LearningKnowledgeIndex(**p)
    index1 = idx1.build(now_fn=lambda: 1000)
    store1 = IndexStore(store_path)
    store1.save(index1)
    text1 = store_path.read_text(encoding="utf-8")

    idx2 = LearningKnowledgeIndex(**p)
    index2 = idx2.build(now_fn=lambda: 1000)
    store2 = IndexStore(store_path)
    store2.save(index2)
    text2 = store_path.read_text(encoding="utf-8")

    check("repeated build produces identical event order",
          [e.to_dict() for e in index1.events] == [e.to_dict() for e in index2.events])
    check("repeated build + save is byte-identical", text1 == text2)
    check("build_id stable across rebuilds",
          index1.metadata["build_id"] == index2.metadata["build_id"])

    loaded = store2.load()
    check("load() round-trips to an equivalent index", loaded.to_dict() == index2.to_dict())


def test_statistics_generation(tmp):
    print("\n[11] statistics generation")
    base = tmp / "stats"
    _seed_rich_repo(base)
    index = LearningKnowledgeIndex(**_paths(base)).build(now_fn=lambda: 1000)
    stats = q.statistics(index)
    check("counts.events_total > 0", stats["counts"]["events_total"] > 0)
    check("by_decision has APPLY/REJECT/ROLLBACK", set(stats["counts"]["by_decision"])
          >= {"APPLY", "REJECT", "ROLLBACK"})
    check("coverage in [0,1]", 0.0 <= stats["coverage"] <= 1.0)
    check("consistency in [0,1]", 0.0 <= stats["consistency"] <= 1.0)
    check("rollback_frequency.count == 1", stats["rollback_frequency"]["count"] == 1)
    check("style_evolution_count == 2 (both styles reached v1)",
          stats["style_evolution_count"] == 2)
    check("timeline_depth.max == 2", stats["timeline_depth"]["max"] == 2)


def test_best_style_and_failed_learning(tmp):
    print("\n[13+14] best style lookup + failed learning lookup")
    base = tmp / "lookup"
    _seed_rich_repo(base)
    index = LearningKnowledgeIndex(**_paths(base)).build(now_fn=lambda: 1000)

    best = q.find_best_style(index)
    check("best style found", best is not None)
    check("best style is style_b (quality 0.95 > 0.9)",
          best is not None and best.metadata["style_id"] == "style_b")

    failed = q.find_failed_learning(index)
    failed_run_ids = {e.run_id for e in failed}
    check("REJECT event present in failed learning", "run_reject_1" in failed_run_ids)
    check("replay FAIL event present in failed learning", "run_replay_fail" in failed_run_ids)


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("=" * 64)
    print(" STAGE 3.5 — LEARNING KNOWLEDGE INDEX — TEST SUITE")
    print("=" * 64)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        test_empty_repository(tmp)
        test_single_learning_event(tmp)
        test_multiple_style_versions_and_replay_mapping(tmp)
        test_rollback_history_and_timeline(tmp)
        test_duplicate_detection(tmp)
        test_missing_files_tolerated(tmp)
        test_corrupted_records_isolated(tmp)
        test_broken_reference_not_counted_as_coverage(tmp)
        test_deterministic_ordering_and_serialization(tmp)
        test_statistics_generation(tmp)
        test_best_style_and_failed_learning(tmp)
    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
