"""test_query_engine.py — SCOS Stage 3.6 Knowledge Query Engine suite.

Plain-assert script (project convention, not pytest). Builds real
KnowledgeIndex objects from hand-crafted source artifacts via the certified
Stage 3.5 LearningKnowledgeIndex.build(), then exercises every public
KnowledgeQueryEngine method and every error-result model over them.

Run: python scos/knowledge/tests/test_query_engine.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))  # knowledge_index, query_engine, query_models, models

from knowledge_index import LearningKnowledgeIndex  # noqa: E402
from query_engine import KnowledgeQueryEngine  # noqa: E402
from query_models import (  # noqa: E402
    ExplainStyleResult, CompareVersionsResult, RunTraceResult, StyleChangeExplanation,
    RollbackHistory, RelatedEvents, LearningChain, StyleSummary,
    StyleNotFound, RunNotFound, VersionNotFound, BrokenReference, InvalidComparison,
)

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


_PROFILE_A0 = {"style_id": "style_a", "content_type": "youtube", "avg_color_palette": [10, 10, 10],
               "audio_frequency_bias": 440.0, "scene_pacing_profile": 1.0}
_PROFILE_A1 = {"style_id": "style_a", "content_type": "youtube", "avg_color_palette": [12, 12, 12],
               "audio_frequency_bias": 445.0, "scene_pacing_profile": 1.1, "new_field": "x"}
_PROFILE_B = {"style_id": "style_b", "content_type": "youtube", "avg_color_palette": [20, 20, 20],
              "audio_frequency_bias": 400.0, "scene_pacing_profile": 1.2}


def _seed(base: Path):
    """2 styles; style_a: APPLY (v1) then ROLLBACK; style_b: APPLY (v1).
    Replay-linked runs + a replay FAIL. Profiles differ between a-v0 and a-v1
    (added + modified fields) for a meaningful compare_versions."""
    p = _paths(base)
    _write_json(p["learning_audit_path"], [
        {"audit_id": "aid_a1", "decision": "APPLY", "reason": "policy applied",
         "style_before": _PROFILE_A0, "style_after": _PROFILE_A1,
         "feedback_summary": {"run_id": "run_a1", "retention_score": 0.8, "engagement_score": 0.7,
                              "style_match_score": 0.6, "quality_score": 0.9}, "timestamp": 100},
        {"audit_id": "aid_rb", "decision": "ROLLBACK", "reason": "restored v0",
         "style_before": _PROFILE_A1, "style_after": _PROFILE_A0,
         "feedback_summary": {"run_id": "run_rb"}, "timestamp": 300},
        {"audit_id": "aid_b1", "decision": "APPLY", "reason": "policy applied",
         "style_before": _PROFILE_B, "style_after": _PROFILE_B,
         "feedback_summary": {"run_id": "run_b1", "retention_score": 0.9, "engagement_score": 0.9,
                              "style_match_score": 0.9, "quality_score": 0.95}, "timestamp": 150},
    ])
    _write_json(p["feedback_log_path"], [
        {"run_id": "run_a1", "retention_score": 0.8, "engagement_score": 0.7,
         "style_match_score": 0.6, "quality_score": 0.9, "derived_style_updates": {}},
        {"run_id": "run_b1", "retention_score": 0.9, "engagement_score": 0.9,
         "style_match_score": 0.9, "quality_score": 0.95, "derived_style_updates": {}},
    ])
    _write_json(p["style_history_path"], {
        "style_a": [
            {"version": 0, "profile": _PROFILE_A0, "audit_id": "seed", "timestamp": 90},
            {"version": 1, "profile": _PROFILE_A1, "audit_id": "aid_a1", "timestamp": 100},
        ],
        "style_b": [
            {"version": 0, "profile": _PROFILE_B, "audit_id": "seed", "timestamp": 140},
            {"version": 1, "profile": _PROFILE_B, "audit_id": "aid_b1", "timestamp": 150},
        ],
    })
    _write_json(p["replay_report_path"], {
        "status": "PASS", "session_id": "sess_1",
        "results": [
            {"record_id": "vid1", "decision": "APPLY", "style_id": "style_a", "quality_score": 0.9,
             "run_id": "run_a1", "asset_hash": "deadbeef", "timestamp": 100, "error": None,
             "session_id": "sess_1"},
            {"record_id": "vidFAIL", "decision": "FAIL", "style_id": None, "quality_score": None,
             "run_id": "run_fail", "asset_hash": None, "timestamp": 110, "error": "boom",
             "session_id": "sess_1"},
        ],
    })
    return p


def _engine(base):
    return KnowledgeQueryEngine(LearningKnowledgeIndex(**_paths(base)).build(now_fn=lambda: 1000))


def _engine_seeded(tmp, name):
    base = tmp / name
    _seed(base)
    return _engine(base)


# --------------------------------------------------------------------------- #


def test_empty_index(tmp):
    print("\n[1] empty index — every method degrades to not-found, never crashes")
    eng = KnowledgeQueryEngine(LearningKnowledgeIndex(**_paths(tmp / "empty")).build(now_fn=lambda: 1))
    check("explain_style -> StyleNotFound", isinstance(eng.explain_style("x"), StyleNotFound))
    check("summarize -> StyleNotFound", isinstance(eng.summarize_style_history("x"), StyleNotFound))
    check("trace_run -> RunNotFound", isinstance(eng.trace_run("r"), RunNotFound))
    check("find_learning_chain -> RunNotFound", isinstance(eng.find_learning_chain("r"), RunNotFound))
    check("find_related_events -> RunNotFound", isinstance(eng.find_related_events("r"), RunNotFound))
    rb = eng.list_rollbacks()
    check("list_rollbacks -> empty RollbackHistory (not error)",
          isinstance(rb, RollbackHistory) and rb.rollbacks == ())


def test_single_and_multiple_styles(tmp):
    print("\n[2] single + multiple styles, explain + summary")
    eng = _engine_seeded(tmp, "multi")
    ex = eng.explain_style("style_a")
    check("explain_style returns ExplainStyleResult", isinstance(ex, ExplainStyleResult))
    check("style_a has 2 versions", ex.version_count == 2)
    check("style_a current_version == 1", ex.current_version == 1)
    check("first_seen is earliest ts (90)", ex.first_seen == 90)
    check("decisions include APPLY and ROLLBACK",
          "APPLY" in ex.decisions and "ROLLBACK" in ex.decisions)
    check("summary is StyleSummary", isinstance(ex.summary, StyleSummary))
    check("style_b also resolvable", isinstance(eng.explain_style("style_b"), ExplainStyleResult))
    check("unknown style -> StyleNotFound", isinstance(eng.explain_style("nope"), StyleNotFound))


def test_compare_versions(tmp):
    print("\n[3] compare_versions — structural diff, added/modified, error paths")
    eng = _engine_seeded(tmp, "cmp")
    res = eng.compare_versions("style_a", 0, 1)
    check("returns CompareVersionsResult", isinstance(res, CompareVersionsResult))
    by_type = {}
    for c in res.changes:
        by_type.setdefault(c.change_type, []).append(c.field)
    check("'new_field' detected as added", "new_field" in by_type.get("added", []))
    check("'audio_frequency_bias' detected as modified",
          "audio_frequency_bias" in by_type.get("modified", []))
    check("no spurious 'removed' changes", "removed" not in by_type)
    check("audit_id on to-version is aid_a1", res.audit_id == "aid_a1")
    check("decision on to-version is APPLY", res.decision == "APPLY")
    check("changes sorted by field name",
          list(c.field for c in res.changes) == sorted(c.field for c in res.changes))
    check("identical versions -> InvalidComparison",
          isinstance(eng.compare_versions("style_a", 1, 1), InvalidComparison))
    check("missing version -> VersionNotFound",
          isinstance(eng.compare_versions("style_a", 0, 9), VersionNotFound))
    check("missing style -> StyleNotFound",
          isinstance(eng.compare_versions("nope", 0, 1), StyleNotFound))


def test_trace_run(tmp):
    print("\n[4] trace_run — full provenance + missing/invalid runs")
    eng = _engine_seeded(tmp, "trace")
    tr = eng.trace_run("run_a1")
    check("returns RunTraceResult", isinstance(tr, RunTraceResult))
    check("asset_hash resolved (deadbeef)", tr.asset_hash == "deadbeef")
    check("session_id resolved (sess_1)", tr.session_id == "sess_1")
    check("style_id resolved (style_a)", tr.style_id == "style_a")
    check("decision is APPLY", tr.decision == "APPLY")
    check("replay link present", tr.replay is not None)
    check("feedback link present", tr.feedback is not None)
    check("audit link present", tr.audit is not None)
    check("style_version link present", tr.style_version is not None)
    # replay-only FAIL run: exists, partial chain, no error
    trf = eng.trace_run("run_fail")
    check("replay-only run still traces", isinstance(trf, RunTraceResult))
    check("replay-only run has no audit link", trf.audit is None)
    check("unknown run -> RunNotFound", isinstance(eng.trace_run("ghost"), RunNotFound))


def test_why_was_style_changed(tmp):
    print("\n[5] why_was_style_changed — recorded facts only, never invented")
    eng = _engine_seeded(tmp, "why")
    w = eng.why_was_style_changed("style_a", 1)
    check("returns StyleChangeExplanation", isinstance(w, StyleChangeExplanation))
    check("audit_reason is the recorded reason", w.audit_reason == "policy applied")
    check("previous_version == 0", w.previous_version == 0)
    check("feedback_summary carries quality_score", w.feedback_summary.get("quality_score") == 0.9)
    # seed version has no audit -> reason stays None (not invented)
    w0 = eng.why_was_style_changed("style_a", 0)
    check("seed version audit_reason is None", w0.audit_reason is None)
    check("missing version -> VersionNotFound",
          isinstance(eng.why_was_style_changed("style_a", 9), VersionNotFound))
    check("missing style -> StyleNotFound",
          isinstance(eng.why_was_style_changed("nope", 1), StyleNotFound))


def test_rollbacks(tmp):
    print("\n[6] list_rollbacks — global + per-style, ordered")
    eng = _engine_seeded(tmp, "rb")
    allrb = eng.list_rollbacks()
    check("global rollbacks returns RollbackHistory", isinstance(allrb, RollbackHistory))
    check("exactly one rollback globally", len(allrb.rollbacks) == 1)
    check("rollback run_id is run_rb", allrb.rollbacks[0]["run_id"] == "run_rb")
    perstyle = eng.list_rollbacks("style_a")
    check("style_a has its rollback", len(perstyle.rollbacks) == 1)
    check("style_b has no rollbacks", len(eng.list_rollbacks("style_b").rollbacks) == 0)


def test_related_and_chain(tmp):
    print("\n[7] find_related_events + find_learning_chain")
    eng = _engine_seeded(tmp, "rel")
    rel = eng.find_related_events("run_a1")
    check("returns RelatedEvents", isinstance(rel, RelatedEvents))
    check("related events are non-empty", len(rel.events) > 0)
    keys = [(e.timestamp, e.source, e.event_type, e.run_id) for e in rel.events]
    check("no duplicate events", len(keys) == len(set(keys)))
    check("related events sorted by timestamp",
          [e.timestamp for e in rel.events] == sorted(e.timestamp for e in rel.events))
    check("unknown run related -> RunNotFound",
          isinstance(eng.find_related_events("ghost"), RunNotFound))

    chain = eng.find_learning_chain("run_a1")
    check("returns LearningChain", isinstance(chain, LearningChain))
    check("chain replay link present", chain.replay is not None)
    check("chain feedback link present", chain.feedback is not None)
    check("chain audit link present", chain.audit is not None)
    check("chain version link present", chain.version is not None)
    check("chain current_style present", chain.current_style is not None)
    # missing-link chain: replay-only run -> audit/version None, never inferred
    cf = eng.find_learning_chain("run_fail")
    check("replay-only chain has replay", cf.replay is not None)
    check("replay-only chain audit is None (not inferred)", cf.audit is None)
    check("replay-only chain version is None (not inferred)", cf.version is None)
    check("unknown run chain -> RunNotFound",
          isinstance(eng.find_learning_chain("ghost"), RunNotFound))


def test_summary_trends(tmp):
    print("\n[8] summarize_style_history — computed counts + trends")
    eng = _engine_seeded(tmp, "sum")
    s = eng.summarize_style_history("style_a")
    check("returns StyleSummary", isinstance(s, StyleSummary))
    check("version_count == 2", s.version_count == 2)
    check("rollback_count == 1", s.rollback_count == 1)
    check("decision_distribution has APPLY + ROLLBACK",
          "APPLY" in s.decision_distribution and "ROLLBACK" in s.decision_distribution)
    check("quality_trend ordered by timestamp",
          [t for t, _ in s.quality_trend] == sorted(t for t, _ in s.quality_trend))
    check("missing style -> StyleNotFound",
          isinstance(eng.summarize_style_history("nope"), StyleNotFound))


def test_broken_reference(tmp):
    print("\n[9] broken/missing references — deterministic error models")
    base = tmp / "broken"
    p = _paths(base)
    # style v1 references an audit_id that doesn't exist -> index flags it unresolved
    _write_json(p["style_history_path"], {
        "style_a": [
            {"version": 0, "profile": _PROFILE_A0, "audit_id": "seed", "timestamp": 1},
            {"version": 1, "profile": _PROFILE_A1, "audit_id": "missing_audit", "timestamp": 2},
        ],
    })
    eng = _engine(base)
    check("nonexistent run -> RunNotFound", isinstance(eng.trace_run("run_x"), RunNotFound))
    # v1's audit_id ("missing_audit") doesn't resolve -> why_was_style_changed
    # must surface that as a BrokenReference, NOT a fabricated explanation.
    w = eng.why_was_style_changed("style_a", 1)
    check("unresolved version audit -> BrokenReference", isinstance(w, BrokenReference))
    check("BrokenReference names the unresolved audit_id", w.reference == "missing_audit")
    # the seed v0 is legitimately audit-less -> normal explanation, not an error
    w0 = eng.why_was_style_changed("style_a", 0)
    check("seed version -> StyleChangeExplanation (not BrokenReference)",
          isinstance(w0, StyleChangeExplanation))


def test_determinism(tmp):
    print("\n[10] determinism — identical index -> byte-identical results, repeatable")
    base1, base2 = tmp / "det1", tmp / "det2"
    _seed(base1); _seed(base2)
    e1, e2 = _engine(base1), _engine(base2)

    def snapshot(eng):
        return {
            "explain_a": eng.explain_style("style_a").to_dict(),
            "explain_b": eng.explain_style("style_b").to_dict(),
            "compare": eng.compare_versions("style_a", 0, 1).to_dict(),
            "trace": eng.trace_run("run_a1").to_dict(),
            "why": eng.why_was_style_changed("style_a", 1).to_dict(),
            "rollbacks": eng.list_rollbacks().to_dict(),
            "related": eng.find_related_events("run_a1").to_dict(),
            "chain": eng.find_learning_chain("run_a1").to_dict(),
            "summary": eng.summarize_style_history("style_a").to_dict(),
        }

    s1a = json.dumps(snapshot(e1), sort_keys=True)
    s1b = json.dumps(snapshot(e1), sort_keys=True)
    s2 = json.dumps(snapshot(e2), sort_keys=True)
    check("repeated queries on one index are identical", s1a == s1b)
    check("two indexes from identical input are identical", s1a == s2)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_empty_index(tmp)
        test_single_and_multiple_styles(tmp)
        test_compare_versions(tmp)
        test_trace_run(tmp)
        test_why_was_style_changed(tmp)
        test_rollbacks(tmp)
        test_related_and_chain(tmp)
        test_summary_trends(tmp)
        test_broken_reference(tmp)
        test_determinism(tmp)

    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
