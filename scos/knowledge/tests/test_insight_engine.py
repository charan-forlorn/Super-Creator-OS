"""test_insight_engine.py — SCOS Stage 3.8 Knowledge Insight Engine suite.

Plain-assert script (project convention, not pytest). Builds real KnowledgeIndex
objects via the certified Stage 3.5 LearningKnowledgeIndex.build(), then exercises
every public KnowledgeInsightEngine method, the Insight/InsightStatistics
contract, deterministic ordering, and every error-result model.

Run: python scos/knowledge/tests/test_insight_engine.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from knowledge_index import LearningKnowledgeIndex  # noqa: E402
from insight_engine import KnowledgeInsightEngine  # noqa: E402
import insight_models as im  # noqa: E402
import explain_facade as ef  # noqa: E402

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


_PA0 = {"style_id": "style_a", "content_type": "youtube", "scene_pacing_profile": 1.0}
_PA1 = {"style_id": "style_a", "content_type": "youtube", "scene_pacing_profile": 1.1, "new_field": "x"}
_PB = {"style_id": "style_b", "content_type": "youtube", "scene_pacing_profile": 1.2}


def _seed(base: Path):
    p = _paths(base)
    _write_json(p["learning_audit_path"], [
        {"audit_id": "aid_a1", "decision": "APPLY", "reason": "policy applied",
         "style_before": _PA0, "style_after": _PA1,
         "feedback_summary": {"run_id": "run_a1", "retention_score": 0.8, "engagement_score": 0.7,
                              "style_match_score": 0.6, "quality_score": 0.9}, "timestamp": 100},
        {"audit_id": "aid_rb", "decision": "ROLLBACK", "reason": "restored v0",
         "style_before": _PA1, "style_after": _PA0,
         "feedback_summary": {"run_id": "run_rb"}, "timestamp": 300},
        {"audit_id": "aid_b1", "decision": "APPLY", "reason": "policy applied",
         "style_before": _PB, "style_after": _PB,
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
            {"version": 0, "profile": _PA0, "audit_id": "seed", "timestamp": 90},
            {"version": 1, "profile": _PA1, "audit_id": "aid_a1", "timestamp": 100},
        ],
        "style_b": [
            {"version": 0, "profile": _PB, "audit_id": "seed", "timestamp": 140},
            {"version": 1, "profile": _PB, "audit_id": "aid_b1", "timestamp": 150},
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


def _eng(base):
    return KnowledgeInsightEngine(LearningKnowledgeIndex(**_paths(base)).build(now_fn=lambda: 1000))


def _eng_seeded(tmp, name):
    base = tmp / name
    _seed(base)
    return _eng(base)


# --------------------------------------------------------------------------- #


def test_empty_index(tmp):
    print("\n[1] empty index — deterministic not-found / unavailable, never raises")
    eng = KnowledgeInsightEngine(LearningKnowledgeIndex(**_paths(tmp / "empty")).build(now_fn=lambda: 1))
    check("style_insight -> StyleNotFound", isinstance(eng.style_insight("s"), im.StyleNotFound))
    check("run_insight -> RunNotFound", isinstance(eng.run_insight("r"), im.RunNotFound))
    check("learning_insight -> StyleNotFound", isinstance(eng.learning_insight("s"), im.StyleNotFound))
    check("rollback_insight -> StyleNotFound", isinstance(eng.rollback_insight("s"), im.StyleNotFound))
    check("portfolio_summary([]) -> InsightUnavailable",
          isinstance(eng.portfolio_summary([]), im.InsightUnavailable))


def test_style_insight(tmp):
    print("\n[2] style_insight — facts, schema_version, insight_id, generated_from")
    eng = _eng_seeded(tmp, "style")
    ins = eng.style_insight("style_a")
    check("returns Insight", isinstance(ins, im.Insight))
    check("schema_version == 1", ins.schema_version == im.INSIGHT_SCHEMA_VERSION == 1)
    check("insight_type == style", ins.insight_type == im.INSIGHT_STYLE)
    check("insight_id == style:style_a", ins.insight_id == "style:style_a")
    check("generated_from cites facade explain_style",
          "KnowledgeExplainFacade.explain_style" in ins.generated_from)
    check("statistics is InsightStatistics", isinstance(ins.statistics, im.InsightStatistics))
    check("version_count == 2", ins.statistics.version_count == 2)
    check("rollback_count == 1", ins.statistics.rollback_count == 1)
    check("decision_counts has APPLY + ROLLBACK",
          "APPLY" in ins.statistics.decision_counts and "ROLLBACK" in ins.statistics.decision_counts)
    check("summary template populated", "contains 2 version(s)" in ins.summary)


def test_run_and_learning_and_rollback(tmp):
    print("\n[3] run / learning / rollback insights")
    eng = _eng_seeded(tmp, "rlr")
    r = eng.run_insight("run_a1")
    check("run_insight -> Insight", isinstance(r, im.Insight))
    check("run insight_id == run:run_a1", r.insight_id == "run:run_a1")
    check("run insight_type == run", r.insight_type == im.INSIGHT_RUN)
    li = eng.learning_insight("style_a")
    check("learning_insight -> Insight", isinstance(li, im.Insight))
    check("learning insight_type == learning", li.insight_type == im.INSIGHT_LEARNING)
    rb = eng.rollback_insight("style_a")
    check("rollback_insight -> Insight", isinstance(rb, im.Insight))
    check("rollback insight_id == rollback:style_a", rb.insight_id == "rollback:style_a")
    check("rollback_count == 1", rb.statistics.rollback_count == 1)
    check("style_b has no rollback -> MissingEvidence",
          isinstance(eng.rollback_insight("style_b"), im.MissingEvidence))


def test_portfolio(tmp):
    print("\n[4] portfolio_summary — aggregation over explicit style_ids")
    eng = _eng_seeded(tmp, "port")
    p = eng.portfolio_summary(["style_a", "style_b"])
    check("returns Insight", isinstance(p, im.Insight))
    check("insight_type == portfolio", p.insight_type == im.INSIGHT_PORTFOLIO)
    check("style_count == 2", p.statistics.style_count == 2)
    check("aggregate version_count == 4", p.statistics.version_count == 4)
    check("aggregate rollback_count == 1", p.statistics.rollback_count == 1)
    check("insight_id == portfolio:2", p.insight_id == "portfolio:2")
    # unknown styles are skipped, not fatal
    p2 = eng.portfolio_summary(["style_a", "ghost"])
    check("unknown style skipped (resolved 1)", p2.statistics.style_count == 1)
    # scope-object form (forward-compatible canonical scope)
    p3 = eng.portfolio_summary({"type": "explicit", "style_ids": ["style_a", "style_b"]})
    check("explicit scope object matches list form", p3.to_dict() == p.to_dict())
    check("unsupported scope type -> InsightUnavailable",
          isinstance(eng.portfolio_summary({"type": "explain-derived"}), im.InsightUnavailable))
    check("None scope -> InsightUnavailable", isinstance(eng.portfolio_summary(None), im.InsightUnavailable))


def test_confidence(tmp):
    print("\n[5] confidence — evidence completeness only (Stage 3.7 model)")
    eng = _eng_seeded(tmp, "conf")
    ins = eng.style_insight("style_a")
    check("confidence is facade ConfidenceFact (no explain_models leak)",
          isinstance(ins.confidence, ef.ConfidenceFact))
    check("confidence level is complete (all categories present)",
          ins.confidence.level == ef.CONFIDENCE_COMPLETE)
    run = eng.run_insight("run_fail")  # replay-only -> partial evidence
    check("replay-only run confidence partial", run.confidence.level == ef.CONFIDENCE_PARTIAL)


def test_reference_ordering(tmp):
    print("\n[6] Reference Ordering Contract — run < style < version < audit < session")
    eng = _eng_seeded(tmp, "refs")
    ins = eng.style_insight("style_a")
    cats = [r.split(":")[0] for r in ins.references]
    order = {c: i for i, c in enumerate(ef.REF_CATEGORY_ORDER)}
    idxs = [order[c] for c in cats]
    check("references grouped by category order", idxs == sorted(idxs))
    check("references deduped", len(ins.references) == len(set(ins.references)))


def test_broken_reference(tmp):
    print("\n[7] broken reference — surfaced, not repaired")
    base = tmp / "broken"
    p = _paths(base)
    _write_json(p["style_history_path"], {
        "style_a": [
            {"version": 0, "profile": _PA0, "audit_id": "seed", "timestamp": 1},
            {"version": 1, "profile": _PA1, "audit_id": "missing_audit", "timestamp": 2},
        ],
    })
    eng = _eng(base)
    # style_insight still aggregates (explain_style succeeds); learning chain has no runs
    check("style_insight still returns Insight", isinstance(eng.style_insight("style_a"), im.Insight))
    check("learning_insight (no run-bearing versions) -> MissingEvidence",
          isinstance(eng.learning_insight("style_a"), im.MissingEvidence))


def test_large_history(tmp):
    print("\n[8] large history — deterministic termination")
    base = tmp / "large"
    p = _paths(base)
    N = 220
    prof = lambda v: {"style_id": "s", "content_type": "yt", "scene_pacing_profile": 1.0 + v}
    audit = []; fb = []; hist = {"s": [{"version": 0, "profile": prof(0), "audit_id": "seed", "timestamp": 0}]}
    res = []
    for v in range(1, N + 1):
        rid = f"run_{v}"; aid = f"aid_{v}"
        audit.append({"audit_id": aid, "decision": "APPLY", "reason": f"r{v}",
                      "style_before": prof(v - 1), "style_after": prof(v),
                      "feedback_summary": {"run_id": rid, "quality_score": 0.5, "retention_score": 0.4},
                      "timestamp": v})
        fb.append({"run_id": rid, "quality_score": 0.5, "retention_score": 0.4, "derived_style_updates": {}})
        hist["s"].append({"version": v, "profile": prof(v), "audit_id": aid, "timestamp": v})
        res.append({"record_id": f"rec_{v}", "decision": "APPLY", "style_id": "s", "quality_score": 0.5,
                    "run_id": rid, "asset_hash": f"h{v}", "timestamp": v, "error": None, "session_id": "sess"})
    _write_json(p["learning_audit_path"], audit)
    _write_json(p["feedback_log_path"], fb)
    _write_json(p["style_history_path"], hist)
    _write_json(p["replay_report_path"], {"status": "PASS", "session_id": "sess", "results": res})
    eng = _eng(base)
    ins = eng.style_insight("s")
    check("large style_insight -> Insight", isinstance(ins, im.Insight))
    check("large version_count == 221", ins.statistics.version_count == 221)
    check("large learning chain insight ok", isinstance(eng.learning_insight("s"), im.Insight))

    # single (seed-only) version
    base2 = tmp / "single"
    _write_json(_paths(base2)["style_history_path"],
                {"s": [{"version": 0, "profile": prof(0), "audit_id": "seed", "timestamp": 0}]})
    eng2 = _eng(base2)
    check("single-version style_insight version_count == 1", eng2.style_insight("s").statistics.version_count == 1)


def test_determinism(tmp):
    print("\n[9] determinism — identical index -> byte-identical JSON, repeatable")
    base1, base2 = tmp / "det1", tmp / "det2"
    _seed(base1); _seed(base2)
    e1, e2 = _eng(base1), _eng(base2)

    def snapshot(eng):
        return {
            "style": eng.style_insight("style_a").to_dict(),
            "run": eng.run_insight("run_a1").to_dict(),
            "learning": eng.learning_insight("style_a").to_dict(),
            "rollback": eng.rollback_insight("style_a").to_dict(),
            "portfolio": eng.portfolio_summary(["style_a", "style_b"]).to_dict(),
        }

    s1a = json.dumps(snapshot(e1), sort_keys=True)
    s1b = json.dumps(snapshot(e1), sort_keys=True)
    s2 = json.dumps(snapshot(e2), sort_keys=True)
    check("repeated queries on one index identical", s1a == s1b)
    check("two identical indexes identical", s1a == s2)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_empty_index(tmp)
        test_style_insight(tmp)
        test_run_and_learning_and_rollback(tmp)
        test_portfolio(tmp)
        test_confidence(tmp)
        test_reference_ordering(tmp)
        test_broken_reference(tmp)
        test_large_history(tmp)
        test_determinism(tmp)

    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
