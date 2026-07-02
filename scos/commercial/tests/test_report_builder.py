"""test_report_builder.py - SCOS Stage 4.1 Commercial Report Contract suite.

Plain-assert script (project convention, not pytest). Builds real Stage 3.9
KnowledgeService views and verifies the commercial report boundary over them.

Run: python scos/commercial/tests/test_report_builder.py
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COMMERCIAL = _HERE.parent
_SCOS = _COMMERCIAL.parent
_KNOWLEDGE = _SCOS / "knowledge"

sys.path.insert(0, str(_COMMERCIAL))
sys.path.insert(0, str(_KNOWLEDGE))

from knowledge_index import LearningKnowledgeIndex  # noqa: E402
from knowledge_service import KnowledgeService  # noqa: E402
from report_builder import build_commercial_report  # noqa: E402
from report_models import (  # noqa: E402
    COMMERCIAL_REPORT_SCHEMA_VERSION,
    CommercialReport,
    CommercialReportError,
    FrozenMap,
    ReportEvidence,
)

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")


def _paths(base: Path):
    return dict(
        feedback_log_path=base / "analytics" / "feedback_log.json",
        learning_audit_path=base / "learning" / "learning_audit.json",
        style_history_path=base / "learning" / "style_history.json",
        replay_report_path=base / "replay" / "replay_report.json",
    )


def _seed(base: Path):
    p = _paths(base)
    profile_0 = {"style_id": "style_a", "content_type": "youtube", "scene_pacing_profile": 1.0}
    profile_1 = {"style_id": "style_a", "content_type": "youtube", "scene_pacing_profile": 1.1}
    _write_json(p["learning_audit_path"], [
        {"audit_id": "aid_a1", "decision": "APPLY", "reason": "policy applied",
         "style_before": profile_0, "style_after": profile_1,
         "feedback_summary": {"run_id": "run_a1", "retention_score": 0.8,
                              "engagement_score": 0.7, "quality_score": 0.9},
         "timestamp": 100},
    ])
    _write_json(p["feedback_log_path"], [
        {"run_id": "run_a1", "retention_score": 0.8, "engagement_score": 0.7,
         "style_match_score": 0.6, "quality_score": 0.9, "derived_style_updates": {}},
    ])
    _write_json(p["style_history_path"], {
        "style_a": [
            {"version": 0, "profile": profile_0, "audit_id": "seed", "timestamp": 90},
            {"version": 1, "profile": profile_1, "audit_id": "aid_a1", "timestamp": 100},
        ],
    })
    _write_json(p["replay_report_path"], {
        "status": "PASS", "session_id": "sess_1",
        "results": [
            {"record_id": "vid1", "decision": "APPLY", "style_id": "style_a",
             "quality_score": 0.9, "run_id": "run_a1", "asset_hash": "deadbeef",
             "timestamp": 100, "error": None, "session_id": "sess_1"},
        ],
    })


def _svc(base: Path):
    return KnowledgeService(LearningKnowledgeIndex(**_paths(base)).build(now_fn=lambda: 1000))


def _report(tmp: Path):
    base = tmp / "contract"
    _seed(base)
    return build_commercial_report(
        _svc(base),
        "run_a1",
        now_fn=lambda: "2026-07-02T00:00:00Z",
        qa_status="PASS",
    )


def test_report_creation(tmp: Path):
    print("\n[1] report creation")
    report = _report(tmp)
    check("returns CommercialReport", isinstance(report, CommercialReport))
    check("schema_version == 1", report.schema_version == COMMERCIAL_REPORT_SCHEMA_VERSION == 1)
    check("report_id stable", report.report_id == "commercial:run_summary:run_a1")
    check("source_run_id stable", report.source_run_id == "run_a1")
    check("style_id from public run view", report.style_id == "style_a")
    check("qa_status from explicit input", report.qa_status == "PASS")
    check("recommendations empty without explicit evidence", report.recommendations == ())
    check("evidence is tuple", isinstance(report.evidence, tuple))
    check("metadata is FrozenMap", isinstance(report.metadata, FrozenMap))


def test_deterministic_serialization(tmp: Path):
    print("\n[2] deterministic serialization")
    a = _report(tmp / "a").to_dict()
    b = _report(tmp / "b").to_dict()
    check("reports serialize identically", json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True))
    check("created_at from injected now_fn", a["created_at"] == "2026-07-02T00:00:00Z")
    check("top-level key order stable", tuple(a.keys()) == (
        "report_id", "schema_version", "report_type", "created_at", "source_run_id",
        "style_id", "qa_status", "summary", "evidence", "recommendations",
        "risks", "metadata",
    ))


def test_immutability_and_no_mutable_leakage(tmp: Path):
    print("\n[3] immutability + no mutable leakage")
    report = _report(tmp)
    try:
        report.summary = "changed"
        frozen = False
    except FrozenInstanceError:
        frozen = True
    check("CommercialReport is frozen", frozen)

    source = {"b": [1, {"z": 2}], "a": "x"}
    evidence = ReportEvidence("mutable", "probe", "test", source)
    source["b"][1]["z"] = 99
    check("ReportEvidence freezes nested mappings", evidence.to_dict()["value"]["b"][1]["z"] == 2)
    check("report evidence values are commercial-owned", all(
        type(item).__module__.endswith("report_models") for item in report.evidence
    ))


def test_missing_run_id_safe_failure(tmp: Path):
    print("\n[4] missing run_id safe failure")
    base = tmp / "missing"
    _seed(base)
    svc = _svc(base)
    empty = build_commercial_report(svc, "", now_fn=lambda: "fixed")
    ghost = build_commercial_report(svc, "ghost", now_fn=lambda: "fixed")
    check("empty run_id -> CommercialReportError", isinstance(empty, CommercialReportError))
    check("unknown run -> CommercialReportError", isinstance(ghost, CommercialReportError))
    check("errors serialize deterministically", json.dumps(empty.to_dict(), sort_keys=True) ==
          json.dumps(build_commercial_report(svc, "", now_fn=lambda: "later").to_dict(), sort_keys=True))
    check("raw exception text not leaked", "Traceback" not in json.dumps(ghost.to_dict(), sort_keys=True))


def test_no_direct_lower_layer_dependency():
    print("\n[5] no direct lower-layer dependency")
    source = (_COMMERCIAL / "report_builder.py").read_text(encoding="utf-8")
    forbidden = (
        "KnowledgeIndex",
        "KnowledgeQueryEngine",
        "KnowledgeExplainEngine",
        "KnowledgeInsightEngine",
        "query_engine",
        "explain_engine",
        "insight_engine",
        "query_models",
        "explain_models",
        "insight_models",
    )
    check("imports KnowledgeService boundary", "from knowledge_service import KnowledgeService" in source)
    check("no forbidden lower-layer imports or names", all(token not in source for token in forbidden))
    check("commercial code does not mutate sys.path", "sys.path" not in source)


def test_stable_schema_version():
    print("\n[6] stable schema_version")
    check("schema constant is 1", COMMERCIAL_REPORT_SCHEMA_VERSION == 1)


def test_no_raw_lower_layer_payload_leakage(tmp: Path):
    print("\n[7] no raw lower-layer payload leakage")
    data = _report(tmp).to_dict()
    dumped = json.dumps(data, sort_keys=True)
    forbidden_payload_keys = ("replay", "feedback", "audit", "style_version", "timeline_ref")
    check("serialized report is JSON-safe", isinstance(dumped, str) and dumped.startswith("{"))
    check("no raw provenance payload keys", all(key not in dumped for key in forbidden_payload_keys))
    check("evidence IDs are stable ordered", [item["evidence_id"] for item in data["evidence"]] ==
          sorted(item["evidence_id"] for item in data["evidence"]))


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_report_creation(tmp)
        test_deterministic_serialization(tmp)
        test_immutability_and_no_mutable_leakage(tmp)
        test_missing_run_id_safe_failure(tmp)
        test_no_direct_lower_layer_dependency()
        test_stable_schema_version()
        test_no_raw_lower_layer_payload_leakage(tmp)

    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
