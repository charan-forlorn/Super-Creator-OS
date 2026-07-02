"""test_knowledge_service.py — SCOS Stage 3.9 Knowledge Access Layer suite.

Plain-assert script (project convention, not pytest). Builds real KnowledgeIndex
objects via the certified Stage 3.5 LearningKnowledgeIndex.build(), then exercises
every public KnowledgeService method, the composite view contract, determinism,
and every error-result model.

Run: python scos/knowledge/tests/test_knowledge_service.py
"""

from __future__ import annotations

import inspect
import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from knowledge_index import LearningKnowledgeIndex  # noqa: E402
from knowledge_service import KnowledgeService  # noqa: E402
import knowledge_view_models as vm  # noqa: E402

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


def _svc(base):
    return KnowledgeService(LearningKnowledgeIndex(**_paths(base)).build(now_fn=lambda: 1000))


def _svc_seeded(tmp, name):
    base = tmp / name
    _seed(base)
    return _svc(base)


# --------------------------------------------------------------------------- #


def test_empty_index(tmp):
    print("\n[1] empty index — not-found / empty-scope, never raises")
    svc = KnowledgeService(LearningKnowledgeIndex(**_paths(tmp / "empty")).build(now_fn=lambda: 1))
    check("knowledge_view -> StyleNotFound", isinstance(svc.knowledge_view("s"), vm.StyleNotFound))
    check("run_view -> RunNotFound", isinstance(svc.run_view("r"), vm.RunNotFound))
    check("portfolio_view([]) -> EmptyScope", isinstance(svc.portfolio_view([]), vm.EmptyScope))
    check("overview(None) -> EmptyScope", isinstance(svc.overview(None), vm.EmptyScope))


def test_knowledge_view(tmp):
    print("\n[2] knowledge_view — composite of style+learning+rollback")
    svc = _svc_seeded(tmp, "kv")
    v = svc.knowledge_view("style_a")
    check("returns KnowledgeView", isinstance(v, vm.KnowledgeView))
    check("schema_version == 1", v.schema_version == vm.KNOWLEDGE_VIEW_SCHEMA_VERSION == 1)
    check("subject_type == style", v.subject_type == vm.SUBJECT_STYLE)
    check("view_id == style:style_a", v.view_id == "style:style_a")
    kinds = {s.kind: s.status for s in v.sections}
    check("has style+learning+rollback sections", set(kinds) == {"style", "learning", "rollback"})
    check("style section ok", kinds["style"] == "ok")
    check("rollback section ok (style_a has a rollback)", kinds["rollback"] == "ok")
    check("sections are access-owned ViewSection objects",
          all(isinstance(s, vm.ViewSection) for s in v.sections))
    check("confidence is ViewConfidence", isinstance(v.confidence, vm.ViewConfidence))
    check("generated_from cites insight engine APIs",
          "KnowledgeInsightEngine.style_insight" in v.generated_from)
    check("unknown style -> StyleNotFound", isinstance(svc.knowledge_view("ghost"), vm.StyleNotFound))


def test_run_view(tmp):
    print("\n[3] run_view — run insight composed with provenance/trace")
    svc = _svc_seeded(tmp, "rv")
    v = svc.run_view("run_a1")
    check("returns RunView", isinstance(v, vm.RunView))
    check("view_id == run:run_a1", v.view_id == "run:run_a1")
    check("run_insight section present", v.run_insight is not None)
    check("provenance present (trace)", v.provenance is not None)
    check("run_insight is access-owned ViewInsight", isinstance(v.run_insight, vm.ViewInsight))
    check("provenance is access-owned RunProvenance", isinstance(v.provenance, vm.RunProvenance))
    check("provenance style_id is style_a", v.provenance.style_id == "style_a")
    check("unknown run -> RunNotFound", isinstance(svc.run_view("ghost"), vm.RunNotFound))


def test_portfolio_and_overview(tmp):
    print("\n[4] portfolio_view + overview over explicit scope")
    svc = _svc_seeded(tmp, "pv")
    p = svc.portfolio_view(["style_a", "style_b"])
    check("returns PortfolioView", isinstance(p, vm.PortfolioView))
    check("portfolio view_id includes scope key", p.view_id == "portfolio:7:style_a|7:style_b")
    check("style_count == 2", p.style_count == 2)
    check("aggregate version_count == 4", p.aggregate_statistics.version_count == 4)
    check("two per-style sections", len(p.sections) == 2)
    # scope object form equivalence
    p2 = svc.portfolio_view({"type": "explicit", "style_ids": ["style_a", "style_b"]})
    check("scope-object form equals list form", p2.to_dict() == p.to_dict())
    pa = svc.portfolio_view(["style_a"])
    pb = svc.portfolio_view(["style_b"])
    check("different same-size portfolios have different view_id", pa.view_id != pb.view_id)
    check("unsupported scope -> ViewUnavailable",
          isinstance(svc.portfolio_view({"type": "explain-derived"}), vm.ViewUnavailable))

    o = svc.overview(["style_a", "style_b"])
    check("returns SystemOverview", isinstance(o, vm.SystemOverview))
    check("scope_size == 2", o.scope_size == 2)
    check("totals rollback_count == 1", o.totals.rollback_count == 1)
    check("overview empty scope -> EmptyScope", isinstance(svc.overview([]), vm.EmptyScope))
    check("string scope -> ViewUnavailable", isinstance(svc.portfolio_view("style_a"), vm.ViewUnavailable))
    check("scalar scope -> ViewUnavailable", isinstance(svc.overview(123), vm.ViewUnavailable))
    check("malformed explicit scope -> ViewUnavailable",
          isinstance(svc.portfolio_view({"type": "explicit", "style_ids": "style_a"}), vm.ViewUnavailable))


def test_no_lower_layer_type_leak(tmp):
    print("\n[5] no Insight/Query type leaks through the service boundary")
    svc = _svc_seeded(tmp, "leak")
    v = svc.knowledge_view("style_a")
    # confidence and error/view objects are all Access-layer (vm.*) types
    check("confidence is vm.ViewConfidence", type(v.confidence).__module__.endswith("knowledge_view_models"))
    check("section insight is vm.ViewInsight", isinstance(v.sections[0].insight, vm.ViewInsight))
    r = svc.run_view("run_a1")
    check("run confidence is vm.ViewConfidence", isinstance(r.confidence, vm.ViewConfidence))
    check("run insight is vm.ViewInsight", isinstance(r.run_insight, vm.ViewInsight))
    check("provenance is vm.RunProvenance", isinstance(r.provenance, vm.RunProvenance))
    check("provenance nested payloads are frozen", isinstance(r.provenance.replay, vm.FrozenPayload))
    # to_dict fully serializable (no custom objects)
    json.dumps(v.to_dict()); json.dumps(r.to_dict())
    check("views fully JSON-serializable", True)
    check("view internals are not raw dict payloads", not isinstance(r.run_insight, dict))


def test_broken_reference(tmp):
    print("\n[6] broken reference — translated, not repaired")
    base = tmp / "broken"
    p = _paths(base)
    _write_json(p["style_history_path"], {
        "style_a": [
            {"version": 0, "profile": _PA0, "audit_id": "seed", "timestamp": 1},
            {"version": 1, "profile": _PA1, "audit_id": "missing_audit", "timestamp": 2},
        ],
    })
    svc = _svc(base)
    # style still composes; learning chain has no runs -> learning section missing_evidence
    v = svc.knowledge_view("style_a")
    check("knowledge_view still returns KnowledgeView", isinstance(v, vm.KnowledgeView))
    kinds = {s.kind: s.status for s in v.sections}
    check("learning section missing_evidence", kinds["learning"] == "missing_evidence")
    check("confidence partial (not all sections present)",
          v.confidence.level in (vm.CONFIDENCE_PARTIAL, vm.CONFIDENCE_NONE))


def test_large_history(tmp):
    print("\n[7] large history — deterministic termination")
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
    svc = _svc(base)
    v = svc.knowledge_view("s")
    check("large knowledge_view -> KnowledgeView", isinstance(v, vm.KnowledgeView))
    style_section = next(s for s in v.sections if s.kind == "style")
    check("large version_count == 221",
          style_section.insight.statistics.version_count == 221)


def test_static_boundary_contract():
    print("\n[8] static boundary contract")
    service_source = (_HERE.parent / "knowledge_service.py").read_text(encoding="utf-8")
    models_source = (_HERE.parent / "knowledge_view_models.py").read_text(encoding="utf-8")
    service_code = service_source.split('"""', 2)[2]
    check("knowledge_service does not import sys", "import sys" not in service_code)
    check("knowledge_service does not import Path", "from pathlib import Path" not in service_code)
    check("knowledge_service does not mutate sys.path", "sys.path" not in service_code)
    check("knowledge_service does not call open()", "open(" not in service_code)
    check("knowledge_service does not import explain_models", "explain_models" not in service_code)
    check("knowledge_service does not import IndexStore", "IndexStore" not in service_code)
    check("view models do not import lower layers",
          "import insight_" not in models_source and
          "import query_" not in models_source and
          "from insight_" not in models_source and
          "from query_" not in models_source)


def test_public_api_contract():
    print("\n[9] public API contract")
    public = tuple(
        name for name, value in KnowledgeService.__dict__.items()
        if not name.startswith("_") and inspect.isfunction(value)
    )
    check("exactly four public methods",
          public == ("knowledge_view", "run_view", "portfolio_view", "overview"))


def test_error_to_dict_contracts():
    print("\n[10] error to_dict contracts")
    check("ViewUnavailable to_dict",
          vm.ViewUnavailable("portfolio", "bad").to_dict() ==
          {"error": "ViewUnavailable", "target": "portfolio", "reason": "bad"})
    check("StyleNotFound to_dict",
          vm.StyleNotFound("missing").to_dict() ==
          {"error": "StyleNotFound", "style_id": "missing"})
    check("RunNotFound to_dict",
          vm.RunNotFound("run_x").to_dict() ==
          {"error": "RunNotFound", "run_id": "run_x"})
    check("EmptyScope to_dict",
          vm.EmptyScope("empty scope").to_dict() ==
          {"error": "EmptyScope", "reason": "empty scope"})


def test_determinism(tmp):
    print("\n[8] determinism — identical index -> byte-identical JSON, repeatable")
    base1, base2 = tmp / "det1", tmp / "det2"
    _seed(base1); _seed(base2)
    s1, s2 = _svc(base1), _svc(base2)

    def snapshot(svc):
        return {
            "kv": svc.knowledge_view("style_a").to_dict(),
            "rv": svc.run_view("run_a1").to_dict(),
            "pv": svc.portfolio_view(["style_a", "style_b"]).to_dict(),
            "ov": svc.overview(["style_a", "style_b"]).to_dict(),
        }

    a = json.dumps(snapshot(s1), sort_keys=True)
    b = json.dumps(snapshot(s1), sort_keys=True)
    c = json.dumps(snapshot(s2), sort_keys=True)
    check("repeated queries on one index identical", a == b)
    check("two identical indexes identical", a == c)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_empty_index(tmp)
        test_knowledge_view(tmp)
        test_run_view(tmp)
        test_portfolio_and_overview(tmp)
        test_no_lower_layer_type_leak(tmp)
        test_broken_reference(tmp)
        test_large_history(tmp)
        test_static_boundary_contract()
        test_public_api_contract()
        test_error_to_dict_contracts()
        test_determinism(tmp)

    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
