"""test_commercial_run_orchestrator.py - SCOS Stage 4.4 orchestrator suite.

Plain-assert script (project convention, not pytest). Seeds a real Stage 3.9
KnowledgeService, runs the Stage 4.4 local commercial run orchestrator over it,
and verifies deterministic outputs, boundary rules, and local-only restrictions.

Run: python scos/commercial/tests/test_commercial_run_orchestrator.py
"""

from __future__ import annotations

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
from run_orchestrator import run_commercial_delivery  # noqa: E402
from run_models import (  # noqa: E402
    COMMERCIAL_RUN_SCHEMA_VERSION,
    CommercialRunError,
    CommercialRunResult,
    CommercialRunStep,
)

_PASS, _FAIL = 0, 0
_FIXED_NOW = "2026-07-03T00:00:00Z"
_STEP_NAMES = (
    "validate_inputs",
    "build_report",
    "write_report",
    "build_package",
    "write_manifest",
)


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


# --------------------------------------------------------------------------- #
# KnowledgeService seed (mirrors test_report_builder.py)
# --------------------------------------------------------------------------- #
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
    return p


def _svc(base: Path):
    _seed(base)
    return KnowledgeService(LearningKnowledgeIndex(**_paths(base)).build(now_fn=lambda: 1000))


def _run(tmp: Path, name: str, svc, **kwargs):
    return run_commercial_delivery(
        knowledge_service=svc,
        run_id=kwargs.pop("run_id", "run_a1"),
        output_dir=tmp / name,
        created_at=kwargs.pop("created_at", _FIXED_NOW),
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_success(tmp: Path):
    print("\n[1] successful run creates report + package + run manifest")
    svc = _svc(tmp / "kb1")
    result = _run(tmp, "out1", svc)
    check("returns CommercialRunResult", isinstance(result, CommercialRunResult))
    check("ok is True", result.ok is True)
    check("schema_version == 1", result.schema_version == COMMERCIAL_RUN_SCHEMA_VERSION == 1)
    out = Path(result.output_dir)
    check("report.json exists", (out / "report.json").is_file())
    check("commercial_run_manifest.json exists", (out / "commercial_run_manifest.json").is_file())
    check("delivery package dir exists", Path(result.package_path).is_dir())
    check("package manifest.json exists", (Path(result.package_path) / "manifest.json").is_file())
    check("report_id from report", result.report_id == "commercial:run_summary:run_a1")


def test_deterministic_manifest(tmp: Path):
    print("\n[2] fixed created_at -> deterministic manifest (same dir, overwrite)")
    svc = _svc(tmp / "kb2")
    a = _run(tmp, "det", svc)
    b = _run(tmp, "det", svc, overwrite=True)
    ma = (Path(a.output_dir) / "commercial_run_manifest.json").read_text(encoding="utf-8")
    mb = (Path(b.output_dir) / "commercial_run_manifest.json").read_text(encoding="utf-8")
    check("manifest bytes identical", ma == mb)


def test_report_build_failure(tmp: Path):
    print("\n[3] report build failure -> CommercialRunError")
    svc = _svc(tmp / "kb3")
    result = _run(tmp, "rbf", svc, run_id="run_missing")
    check("returns CommercialRunError", isinstance(result, CommercialRunError))
    check("error_kind REPORT_BUILD_FAILED", result.error_kind == "REPORT_BUILD_FAILED")
    check("failed_step build_report", result.failed_step == "build_report")
    check("ok is False", result.ok is False)


def test_package_build_failure(tmp: Path):
    print("\n[4] package build failure -> CommercialRunError")
    svc = _svc(tmp / "kb4")
    _run(tmp, "pbf", svc)  # first run creates the package
    again = _run(tmp, "pbf", svc, overwrite=False)  # second run: package exists
    check("returns CommercialRunError", isinstance(again, CommercialRunError))
    check("error_kind PACKAGE_BUILD_FAILED", again.error_kind == "PACKAGE_BUILD_FAILED")
    check("failed_step build_package", again.failed_step == "build_package")


def test_missing_video(tmp: Path):
    print("\n[5] provided-but-missing video_path -> deterministic error")
    svc = _svc(tmp / "kb5")
    result = _run(tmp, "mv", svc, video_path=tmp / "ghost.mp4")
    check("returns CommercialRunError", isinstance(result, CommercialRunError))
    check("error_kind INPUT_NOT_FOUND", result.error_kind == "INPUT_NOT_FOUND")
    check("failed_step validate_inputs", result.failed_step == "validate_inputs")


def test_overwrite_false_repeat(tmp: Path):
    print("\n[6] overwrite=False repeated run fails deterministically")
    svc = _svc(tmp / "kb6")
    first = _run(tmp, "owf", svc)
    check("first succeeds", isinstance(first, CommercialRunResult))
    second = _run(tmp, "owf", svc, overwrite=False)
    third = _run(tmp, "owf", svc, overwrite=False)
    check("repeat fails", isinstance(second, CommercialRunError))
    check("repeat is deterministic",
          json.dumps(second.to_dict(), sort_keys=True) == json.dumps(third.to_dict(), sort_keys=True))


def test_overwrite_true_repeat(tmp: Path):
    print("\n[7] overwrite=True repeated run succeeds deterministically")
    svc = _svc(tmp / "kb7")
    first = _run(tmp, "owt", svc)
    second = _run(tmp, "owt", svc, overwrite=True)
    check("first succeeds", isinstance(first, CommercialRunResult))
    check("repeat succeeds", isinstance(second, CommercialRunResult))
    check("repeat manifest identical",
          json.dumps(first.to_dict(), sort_keys=True) == json.dumps(second.to_dict(), sort_keys=True))


def test_no_source_mutation(tmp: Path):
    print("\n[8] no source artifact mutation")
    base = tmp / "kb8"
    svc = _svc(base)
    video = tmp / "src_video.mp4"
    video.write_bytes(b"\x00realvideo")
    manifest = tmp / "src_manifest.json"
    manifest.write_text('{"source": "job_8"}', encoding="utf-8")
    seed_before = _paths(base)["feedback_log_path"].read_text(encoding="utf-8")
    result = _run(tmp, "nsm", svc, video_path=video, source_manifest_path=manifest)
    check("run succeeds", isinstance(result, CommercialRunResult))
    check("source video unchanged", video.read_bytes() == b"\x00realvideo")
    check("source manifest unchanged", manifest.read_text(encoding="utf-8") == '{"source": "job_8"}')
    check("seed feedback log unchanged",
          _paths(base)["feedback_log_path"].read_text(encoding="utf-8") == seed_before)


def test_no_knowledge_import_leak():
    print("\n[9] no knowledge implementation import leak in run_orchestrator.py")
    source = (_COMMERCIAL / "run_orchestrator.py").read_text(encoding="utf-8")
    for token in ("import knowledge", "from knowledge", "knowledge_index",
                  "KnowledgeQueryEngine", "KnowledgeExplainEngine", "KnowledgeInsightEngine",
                  "query_engine", "explain_engine", "insight_engine"):
        check(f"no '{token}'", token not in source)


def test_no_network_imports():
    print("\n[10] no network/cloud imports in run_orchestrator.py")
    source = (_COMMERCIAL / "run_orchestrator.py").read_text(encoding="utf-8")
    for token in ("requests", "httpx", "urllib.request", "boto3", "socket",
                  "http.client", "openai", "anthropic"):
        check(f"no '{token}'", token not in source)


def test_url_rejected(tmp: Path):
    print("\n[11] URL paths are rejected")
    svc = _svc(tmp / "kb11")
    result = run_commercial_delivery(
        knowledge_service=svc, run_id="run_a1",
        output_dir="https://evil.example/out", created_at=_FIXED_NOW)
    check("returns CommercialRunError", isinstance(result, CommercialRunError))
    check("error_kind INVALID_ARGUMENTS", result.error_kind == "INVALID_ARGUMENTS")
    vid = _run(tmp, "url_vid", svc, video_path="http://evil.example/v.mp4")
    check("URL video rejected", isinstance(vid, CommercialRunError)
          and vid.error_kind == "INVALID_ARGUMENTS")


def test_manifest_references_exist(tmp: Path):
    print("\n[12] manifest references existing generated files")
    svc = _svc(tmp / "kb12")
    result = _run(tmp, "mref", svc)
    data = json.loads((Path(result.output_dir) / "commercial_run_manifest.json").read_text(encoding="utf-8"))
    check("report_path exists", Path(data["report_path"]).is_file())
    check("package_path exists", Path(data["package_path"]).is_dir())
    check("package_manifest_path exists", Path(data["package_manifest_path"]).is_file())
    check("manifest run_id matches", data["run_id"] == "run_a1")


def test_result_to_dict_deterministic(tmp: Path):
    print("\n[13] result.to_dict() is deterministic")
    svc = _svc(tmp / "kb13")
    a = _run(tmp, "rd", svc)
    b = _run(tmp, "rd", svc, overwrite=True)
    check("result serializes identically",
          json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True))


def test_error_to_dict_deterministic(tmp: Path):
    print("\n[14] error.to_dict() is deterministic")
    svc = _svc(tmp / "kb14")
    a = _run(tmp, "ed_a", svc, video_path=tmp / "ghost.mp4")
    b = _run(tmp, "ed_b", svc, video_path=tmp / "ghost.mp4")
    # Normalize the differing 'path' metadata (embeds output-dir-independent ghost path).
    check("errors serialize identically",
          json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True))
    check("no traceback leakage", "Traceback" not in json.dumps(a.to_dict(), sort_keys=True))


def test_steps_present(tmp: Path):
    print("\n[15] steps include all five stage names on success")
    svc = _svc(tmp / "kb15")
    result = _run(tmp, "steps", svc)
    names = tuple(s.step_name for s in result.steps)
    check("all five step names present", all(n in names for n in _STEP_NAMES))
    check("all steps succeeded", all(s.status == "success" for s in result.steps))
    check("steps are CommercialRunStep", all(isinstance(s, CommercialRunStep) for s in result.steps))


def test_created_at_consistency(tmp: Path):
    print("\n[16] created_at in report/result/manifest equals injected string")
    svc = _svc(tmp / "kb16")
    result = _run(tmp, "cat", svc)
    report = json.loads((Path(result.output_dir) / "report.json").read_text(encoding="utf-8"))
    manifest = json.loads((Path(result.output_dir) / "commercial_run_manifest.json").read_text(encoding="utf-8"))
    check("result.created_at", result.created_at == _FIXED_NOW)
    check("report.json created_at", report["created_at"] == _FIXED_NOW)
    check("manifest created_at", manifest["created_at"] == _FIXED_NOW)


def test_paths_under_output_dir(tmp: Path):
    print("\n[17] output paths stay under requested output_dir")
    svc = _svc(tmp / "kb17")
    requested = (tmp / "under").resolve()
    result = run_commercial_delivery(
        knowledge_service=svc, run_id="run_a1",
        output_dir=str(tmp / "under"), created_at=_FIXED_NOW)
    for label in ("output_dir", "report_path", "package_path", "manifest_path"):
        value = Path(getattr(result, label)).resolve()
        check(f"{label} under output_dir", str(value).startswith(str(requested)))


def test_stage_contracts_intact():
    print("\n[18-20] Stage 4.1/4.2/4.3 contracts still importable & intact")
    from report_builder import build_commercial_report  # noqa: F401
    from delivery_package import create_delivery_package  # noqa: F401
    import cli  # noqa: E402
    check("4.1 build_commercial_report importable", callable(build_commercial_report))
    check("4.2 create_delivery_package importable", callable(create_delivery_package))
    check("4.3 cli.main importable", callable(getattr(cli, "main", None)))
    check("4.3 CLI schema version unchanged", cli.COMMERCIAL_CLI_SCHEMA_VERSION == 1)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_success(tmp)
        test_deterministic_manifest(tmp)
        test_report_build_failure(tmp)
        test_package_build_failure(tmp)
        test_missing_video(tmp)
        test_overwrite_false_repeat(tmp)
        test_overwrite_true_repeat(tmp)
        test_no_source_mutation(tmp)
        test_no_knowledge_import_leak()
        test_no_network_imports()
        test_url_rejected(tmp)
        test_manifest_references_exist(tmp)
        test_result_to_dict_deterministic(tmp)
        test_error_to_dict_deterministic(tmp)
        test_steps_present(tmp)
        test_created_at_consistency(tmp)
        test_paths_under_output_dir(tmp)
        test_stage_contracts_intact()

    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
