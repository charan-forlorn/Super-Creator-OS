"""test_explain_engine.py — SCOS Stage 3.7 Knowledge Explain Engine suite.

Plain-assert script (project convention, not pytest). Builds real KnowledgeIndex
objects from hand-crafted source artifacts via the certified Stage 3.5
LearningKnowledgeIndex.build(), then exercises every public KnowledgeExplainEngine
method, the Explanation/Confidence contract, and every error-result model.

Run: python scos/knowledge/tests/test_explain_engine.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from knowledge_index import LearningKnowledgeIndex  # noqa: E402
from explain_engine import KnowledgeExplainEngine  # noqa: E402
import explain_models as em  # noqa: E402

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
    """style_a: APPLY (v1) + ROLLBACK; style_b: APPLY (v1). Replay-linked runs."""
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
    return KnowledgeExplainEngine(LearningKnowledgeIndex(**_paths(base)).build(now_fn=lambda: 1000))


def _eng_seeded(tmp, name):
    base = tmp / name
    _seed(base)
    return _eng(base)


# --------------------------------------------------------------------------- #


def test_empty_index(tmp):
    print("\n[1] empty index — deterministic not-found / missing, never raises")
    eng = KnowledgeExplainEngine(LearningKnowledgeIndex(**_paths(tmp / "empty")).build(now_fn=lambda: 1))
    check("explain_run -> RunNotFound", isinstance(eng.explain_run("r"), em.RunNotFound))
    check("explain_style -> StyleNotFound", isinstance(eng.explain_style("s"), em.StyleNotFound))
    check("explain_learning_chain -> StyleNotFound", isinstance(eng.explain_learning_chain("s"), em.StyleNotFound))
    check("summarize_learning -> StyleNotFound", isinstance(eng.summarize_learning("s"), em.StyleNotFound))


def test_valid_explanations_and_types(tmp):
    print("\n[2] valid explanations + explanation_type + schema_version")
    eng = _eng_seeded(tmp, "valid")
    r = eng.explain_run("run_a1")
    check("explain_run -> Explanation", isinstance(r, em.Explanation))
    check("explain_run type == run", r.explanation_type == em.EXPLANATION_RUN)
    check("schema_version == 1", r.schema_version == 1)
    check("explain_run confidence complete (all 4 links)", r.confidence.level == em.CONFIDENCE_COMPLETE)
    s = eng.explain_style("style_a")
    check("explain_style type == style", s.explanation_type == em.EXPLANATION_STYLE)
    v = eng.explain_version("style_a:1")
    check("explain_version type == version", v.explanation_type == em.EXPLANATION_VERSION)
    check("explain_version reason recorded", "policy applied" in v.summary)
    c = eng.explain_learning_chain("style_a")
    check("explain_learning_chain type == learning_chain", c.explanation_type == em.EXPLANATION_LEARNING_CHAIN)
    rb = eng.explain_rollback("style_a:1")
    check("explain_rollback type == rollback", rb.explanation_type == em.EXPLANATION_ROLLBACK)
    check("explain_rollback reason surfaced", "restored v0" in rb.summary)
    sm = eng.summarize_learning("style_a")
    check("summarize_learning type == summary", sm.explanation_type == em.EXPLANATION_SUMMARY)


def test_reference_ordering(tmp):
    print("\n[3] Reference Ordering Contract — run < style < version < audit < session")
    eng = _eng_seeded(tmp, "refs")
    r = eng.explain_run("run_a1")
    cats = [ref.split(":")[0] for ref in r.references]
    order = {c: i for i, c in enumerate(em.REF_CATEGORY_ORDER)}
    idxs = [order[c] for c in cats]
    check("references grouped by category order (non-decreasing)", idxs == sorted(idxs))
    check("references not alphabetical", cats != sorted(cats) or len(set(cats)) <= 1)
    check("references deduped", len(r.references) == len(set(r.references)))


def test_confidence_levels(tmp):
    print("\n[4] confidence levels — complete / partial / none")
    eng = _eng_seeded(tmp, "conf")
    full = eng.explain_run("run_a1")
    check("full-evidence run -> complete", full.confidence.level == em.CONFIDENCE_COMPLETE)
    partial = eng.explain_run("run_fail")  # replay only, no feedback/audit/version
    check("replay-only run -> partial", partial.confidence.level == em.CONFIDENCE_PARTIAL)
    check("partial lists missing evidence", "feedback" in partial.confidence.missing)


def test_missing_and_errors(tmp):
    print("\n[5] missing evidence + error models (returned, never raised)")
    eng = _eng_seeded(tmp, "err")
    check("unknown run -> RunNotFound", isinstance(eng.explain_run("ghost"), em.RunNotFound))
    check("unknown style -> StyleNotFound", isinstance(eng.explain_style("ghost"), em.StyleNotFound))
    check("malformed version_id -> ExplanationUnavailable",
          isinstance(eng.explain_version("noColonHere"), em.ExplanationUnavailable))
    check("non-int version -> ExplanationUnavailable",
          isinstance(eng.explain_version("style_a:x"), em.ExplanationUnavailable))
    check("missing version -> ExplanationUnavailable",
          isinstance(eng.explain_version("style_a:9"), em.ExplanationUnavailable))
    check("style_b has no rollback -> MissingEvidence",
          isinstance(eng.explain_rollback("style_b:1"), em.MissingEvidence))


def test_broken_reference(tmp):
    print("\n[6] broken reference — unresolved audit_id surfaced, not repaired")
    base = tmp / "broken"
    p = _paths(base)
    _write_json(p["style_history_path"], {
        "style_a": [
            {"version": 0, "profile": _PA0, "audit_id": "seed", "timestamp": 1},
            {"version": 1, "profile": _PA1, "audit_id": "missing_audit", "timestamp": 2},
        ],
    })
    eng = _eng(base)
    res = eng.explain_version("style_a:1")
    check("unresolved audit -> BrokenReference", isinstance(res, em.BrokenReference))
    check("BrokenReference names the audit_id", res.reference == "missing_audit")
    # seed version is legitimately audit-less -> normal Explanation, not error
    res0 = eng.explain_version("style_a:0")
    check("seed version -> Explanation", isinstance(res0, em.Explanation))


def test_rollback_and_multiple(tmp):
    print("\n[7] rollback explanation + multiple rollbacks")
    base = tmp / "rbs"
    p = _seed(base)
    # add a second rollback for style_a
    audit = json.loads(p["learning_audit_path"].read_text(encoding="utf-8"))
    audit.append({"audit_id": "aid_rb2", "decision": "ROLLBACK", "reason": "second rollback",
                  "style_before": _PA1, "style_after": _PA0,
                  "feedback_summary": {"run_id": "run_rb2"}, "timestamp": 400})
    _write_json(p["learning_audit_path"], audit)
    eng = _eng(base)
    rb = eng.explain_rollback("style_a:1")
    check("rollback Explanation returned", isinstance(rb, em.Explanation))
    check("counts 2 rollbacks", "2 recorded rollback" in rb.summary)
    check("rollback supporting_events present", len(rb.supporting_events) == 2)


def test_deep_chain_and_large(tmp):
    print("\n[8] deep learning chain + large timeline + single version")
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
    chain = eng.explain_learning_chain("s")
    check("large chain -> Explanation", isinstance(chain, em.Explanation))
    check("large chain spans 220 transitions", "220 version transition" in chain.summary)
    check("large chain has supporting events", len(chain.supporting_events) > 0)

    # single version (seed only) -> no run-bearing version events -> MissingEvidence
    base2 = tmp / "single"
    p2 = _paths(base2)
    _write_json(p2["style_history_path"], {"s": [{"version": 0, "profile": prof(0), "audit_id": "seed", "timestamp": 0}]})
    eng2 = _eng(base2)
    check("single seed-only version chain -> MissingEvidence",
          isinstance(eng2.explain_learning_chain("s"), em.MissingEvidence))


def test_determinism(tmp):
    print("\n[9] determinism — identical index -> byte-identical JSON, repeatable")
    base1, base2 = tmp / "det1", tmp / "det2"
    _seed(base1); _seed(base2)
    e1, e2 = _eng(base1), _eng(base2)

    def snapshot(eng):
        return {
            "run": eng.explain_run("run_a1").to_dict(),
            "style": eng.explain_style("style_a").to_dict(),
            "version": eng.explain_version("style_a:1").to_dict(),
            "chain": eng.explain_learning_chain("style_a").to_dict(),
            "rollback": eng.explain_rollback("style_a:1").to_dict(),
            "summary": eng.summarize_learning("style_a").to_dict(),
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
        test_valid_explanations_and_types(tmp)
        test_reference_ordering(tmp)
        test_confidence_levels(tmp)
        test_missing_and_errors(tmp)
        test_broken_reference(tmp)
        test_rollback_and_multiple(tmp)
        test_deep_chain_and_large(tmp)
        test_determinism(tmp)

    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
