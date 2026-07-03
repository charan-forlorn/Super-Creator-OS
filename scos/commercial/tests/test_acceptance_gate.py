"""test_acceptance_gate.py - SCOS Stage 4.5 commercial acceptance gate suite.

Plain-assert script (project convention, not pytest). Seeds a real Stage 3.9
KnowledgeService, produces a real Stage 4.4 commercial run, then certifies it
through the Stage 4.5 acceptance gate and verifies deterministic PASS / FAIL /
BLOCKED behavior, evidence rules, and local-only restrictions.

Tests 21-24 of the Stage 4.5 spec (Stage 4.1-4.4 regressions) are covered by
running the existing test scripts in the verification step:
test_report_builder.py, test_delivery_package.py, test_cli.py,
test_commercial_run_orchestrator.py.

Run: python scos/commercial/tests/test_acceptance_gate.py
"""

from __future__ import annotations

import json
import shutil
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
from run_models import CommercialRunResult  # noqa: E402
from acceptance_gate import run_commercial_acceptance_gate  # noqa: E402
from acceptance_models import (  # noqa: E402
    COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION,
    CommercialAcceptanceError,
    CommercialAcceptanceReport,
)

_PASS, _FAIL = 0, 0
_FIXED_NOW = "2026-07-03T00:00:00Z"
_GATE_NOW = "2026-07-03T01:00:00Z"


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


# --------------------------------------------------------------------------- #
# KnowledgeService seed + Stage 4.4 run fixture (mirrors orchestrator suite)
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


def _make_run(tmp: Path, name: str, **kwargs) -> CommercialRunResult:
    """Produce one real, complete Stage 4.4 commercial run for certification."""

    svc = _svc(tmp / f"kb_{name}")
    result = run_commercial_delivery(
        knowledge_service=svc,
        run_id="run_a1",
        output_dir=tmp / name,
        created_at=_FIXED_NOW,
        **kwargs,
    )
    assert isinstance(result, CommercialRunResult), f"fixture run failed for {name}"
    return result


def _gate(run, out: Path, **kwargs):
    return run_commercial_acceptance_gate(
        commercial_run_result=run,
        output_dir=out,
        created_at=kwargs.pop("created_at", _GATE_NOW),
        **kwargs,
    )


def _report_file(out: Path, report: CommercialAcceptanceReport) -> Path:
    return out / report.certification_id.replace(":", "_") / "commercial_acceptance_report.json"


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_pass_and_report_written(tmp: Path):
    print("\n[1-2] successful acceptance gate returns PASS and writes report file")
    run = _make_run(tmp, "ok1")
    out = tmp / "cert1"
    report = _gate(run, out)
    check("returns CommercialAcceptanceReport", isinstance(report, CommercialAcceptanceReport))
    check("overall_status PASS", report.overall_status == "PASS")
    check("ok is True", report.ok is True)
    check("schema_version == 1", report.schema_version == COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION == 1)
    check("readiness_score == 100", report.readiness_score == 100)
    check("certification_id derived", report.certification_id == "commercial-acceptance-run_a1")
    check("commercial_acceptance_report.json created", _report_file(out, report).is_file())
    data = json.loads(_report_file(out, report).read_text(encoding="utf-8"))
    check("written file matches to_dict",
          json.dumps(data, sort_keys=True) == json.dumps(report.to_dict(), sort_keys=True))
    check("no blocking reasons", report.blocking_reasons == ())
    # gate also accepts dict and manifest-path input forms for the same run
    from_dict = _gate(run.to_dict(), tmp / "cert1_dict")
    from_path = _gate(run.manifest_path, tmp / "cert1_path")
    check("dict input PASS", isinstance(from_dict, CommercialAcceptanceReport) and from_dict.ok)
    check("manifest path input PASS", isinstance(from_path, CommercialAcceptanceReport) and from_path.ok)


def test_deterministic_output(tmp: Path):
    print("\n[3] fixed created_at produces deterministic output")
    run = _make_run(tmp, "det1")
    a = _gate(run, tmp / "cert_det_a")
    b = _gate(run, tmp / "cert_det_b")
    fa = _report_file(tmp / "cert_det_a", a).read_text(encoding="utf-8")
    fb = _report_file(tmp / "cert_det_b", b).read_text(encoding="utf-8")
    check("report bytes identical", fa == fb)
    check("no traceback leakage", "Traceback" not in fa)


def test_missing_report_json(tmp: Path):
    print("\n[4] missing report.json fails deterministically")
    run = _make_run(tmp, "mr1")
    Path(run.report_path).unlink()
    a = _gate(run, tmp / "cert_mr_a")
    b = _gate(run, tmp / "cert_mr_b")
    check("overall_status FAIL", a.overall_status == "FAIL")
    check("ok is False", a.ok is False)
    failing = {c.check_name for c in a.checks if c.status == "FAIL"}
    check("report_json_exists failed", "report_json_exists" in failing)
    check("deterministic failure",
          json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True))


def test_missing_delivery_package(tmp: Path):
    print("\n[5] missing delivery package fails deterministically")
    run = _make_run(tmp, "mp1")
    shutil.rmtree(run.package_path)
    a = _gate(run, tmp / "cert_mp_a")
    b = _gate(run, tmp / "cert_mp_b")
    check("overall_status FAIL", a.overall_status == "FAIL")
    failing = {c.check_name for c in a.checks if c.status == "FAIL"}
    check("delivery_package_exists failed", "delivery_package_exists" in failing)
    check("required_delivery_files_exist failed", "required_delivery_files_exist" in failing)
    check("deterministic failure",
          json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True))


def test_missing_required_delivery_file(tmp: Path):
    print("\n[6] missing required delivery file fails deterministically")
    run = _make_run(tmp, "mf1")
    (Path(run.package_path) / "qa_summary.md").unlink()
    a = _gate(run, tmp / "cert_mf_a")
    b = _gate(run, tmp / "cert_mf_b")
    check("overall_status FAIL", a.overall_status == "FAIL")
    chk = {c.check_name: c for c in a.checks}["required_delivery_files_exist"]
    check("check failed", chk.status == "FAIL")
    check("names missing file", "qa_summary.md" in (chk.error_detail or ""))
    check("deterministic failure",
          json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True))


def test_failed_run_blocked(tmp: Path):
    print("\n[7, 12] failed/blocked commercial run forces BLOCKED deterministically")
    failed_run = {
        "ok": False, "schema_version": 1, "run_id": "run_a1",
        "delivery_id": "local-commercial-run-run_a1", "created_at": _FIXED_NOW,
        "report_path": str(tmp / "nowhere" / "report.json"),
        "package_path": str(tmp / "nowhere" / "delivery_package"),
        "steps": [], "metadata": {},
    }
    a = _gate(dict(failed_run), tmp / "cert_blk_a")
    b = _gate(dict(failed_run), tmp / "cert_blk_b")
    check("returns report", isinstance(a, CommercialAcceptanceReport))
    check("overall_status BLOCKED", a.overall_status == "BLOCKED")
    check("ok is False", a.ok is False)
    check("run check BLOCKED",
          {c.check_name: c.status for c in a.checks}["run_result_is_successful"] == "BLOCKED")
    check("evidence checks skipped",
          {c.check_name: c.status for c in a.checks}["report_json_exists"] == "SKIPPED")
    check("blocking reasons recorded", len(a.blocking_reasons) >= 1)
    check("deterministic blocked output",
          json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True))


def test_invalid_run_result(tmp: Path):
    print("\n[8] invalid run result returns CommercialAcceptanceError")
    bad_type = _gate(12345, tmp / "cert_bad1")
    check("int input -> error", isinstance(bad_type, CommercialAcceptanceError))
    check("error_kind INVALID_RUN_RESULT", bad_type.error_kind == "INVALID_RUN_RESULT")
    missing_keys = _gate({"ok": True}, tmp / "cert_bad2")
    check("missing fields -> error", isinstance(missing_keys, CommercialAcceptanceError)
          and missing_keys.error_kind == "INVALID_RUN_RESULT")
    ghost = _gate(tmp / "ghost_manifest.json", tmp / "cert_bad3")
    check("missing manifest -> INPUT_NOT_FOUND", isinstance(ghost, CommercialAcceptanceError)
          and ghost.error_kind == "INPUT_NOT_FOUND")
    garbage = tmp / "garbage.json"
    garbage.write_text("{not json", encoding="utf-8")
    parsed = _gate(garbage, tmp / "cert_bad4")
    check("bad JSON -> INVALID_RUN_RESULT", isinstance(parsed, CommercialAcceptanceError)
          and parsed.error_kind == "INVALID_RUN_RESULT")
    no_args = run_commercial_acceptance_gate(
        commercial_run_result={"run_id": "x"}, output_dir=tmp / "cert_bad5", created_at="")
    check("empty created_at -> INVALID_ARGUMENTS", isinstance(no_args, CommercialAcceptanceError)
          and no_args.error_kind == "INVALID_ARGUMENTS")


def test_url_rejected(tmp: Path):
    print("\n[9] URL paths are rejected")
    run = _make_run(tmp, "url1")
    url_out = _gate(run, "https://evil.example/certs")
    check("URL output_dir rejected", isinstance(url_out, CommercialAcceptanceError)
          and url_out.error_kind == "INVALID_ARGUMENTS")
    url_in = _gate("http://evil.example/manifest.json", tmp / "cert_url")
    check("URL input path rejected", isinstance(url_in, CommercialAcceptanceError)
          and url_in.error_kind == "INVALID_ARGUMENTS")
    url_evidence = dict(run.to_dict())
    url_evidence["report_path"] = "https://evil.example/report.json"
    report = _gate(url_evidence, tmp / "cert_url2")
    check("URL evidence -> report FAIL", isinstance(report, CommercialAcceptanceReport)
          and report.overall_status == "FAIL")
    chk = {c.check_name: c for c in report.checks}["local_only_paths"]
    check("local_only_paths failed", chk.status == "FAIL")


def test_readiness_score_deterministic(tmp: Path):
    print("\n[10] readiness score is deterministic")
    run = _make_run(tmp, "score1")
    (Path(run.package_path) / "assets").mkdir(exist_ok=True)
    a = _gate(run, tmp / "cert_sc_a", require_video=True)
    b = _gate(run, tmp / "cert_sc_b", require_video=True)
    # one HIGH failure (video missing) -> 100 - 25 = 75
    check("score is 75 after one HIGH failure", a.readiness_score == 75)
    check("score repeats identically", a.readiness_score == b.readiness_score)
    check("threshold check failed at min 100",
          {c.check_name: c.status for c in a.checks}["readiness_score_threshold"] == "FAIL")
    relaxed = _gate(run, tmp / "cert_sc_c", require_video=True, min_readiness_score=70)
    check("relaxed threshold passes threshold check",
          {c.check_name: c.status for c in relaxed.checks}["readiness_score_threshold"] == "PASS")
    check("HIGH failure still blocks PASS", relaxed.overall_status == "FAIL")


def test_critical_failure_forces_fail(tmp: Path):
    print("\n[11] critical failure forces FAIL")
    run = _make_run(tmp, "crit1")
    Path(run.report_path).unlink()
    report = _gate(run, tmp / "cert_crit", min_readiness_score=0)
    check("overall_status FAIL despite min score 0", report.overall_status == "FAIL")
    check("readiness_score clamped at 0", report.readiness_score == 0)
    check("critical fail in blocking_reasons",
          any("report_json_exists" in r for r in report.blocking_reasons))


def test_require_video(tmp: Path):
    print("\n[13] require_video=True fails when video evidence is missing")
    run = _make_run(tmp, "vid1")
    without = _gate(run, tmp / "cert_vid_a", require_video=True)
    check("FAIL without video", without.overall_status == "FAIL")
    check("video_asset_exists failed",
          {c.check_name: c.status for c in without.checks}["video_asset_exists"] == "FAIL")
    video = tmp / "clip.mp4"
    video.write_bytes(b"\x00videobytes")
    run_with = _make_run(tmp, "vid2", video_path=video)
    with_video = _gate(run_with, tmp / "cert_vid_b", require_video=True)
    check("PASS with video asset", with_video.overall_status == "PASS")
    default = _gate(run, tmp / "cert_vid_c")
    check("default require_video=False -> SKIPPED",
          {c.check_name: c.status for c in default.checks}["video_asset_exists"] == "SKIPPED")


def test_require_assets(tmp: Path):
    print("\n[14] require_assets=True fails when assets are missing")
    run = _make_run(tmp, "ast1")
    without = _gate(run, tmp / "cert_ast_a", require_assets=True)
    check("FAIL without assets folder", without.overall_status == "FAIL")
    check("asset_folder_exists failed",
          {c.check_name: c.status for c in without.checks}["asset_folder_exists"] == "FAIL")
    manifest = tmp / "src_manifest.json"
    manifest.write_text('{"source": "job_45"}', encoding="utf-8")
    run_with = _make_run(tmp, "ast2", source_manifest_path=manifest)
    with_assets = _gate(run_with, tmp / "cert_ast_b", require_assets=True)
    check("PASS with assets folder", with_assets.overall_status == "PASS")
    default = _gate(run, tmp / "cert_ast_c")
    check("default require_assets=False -> SKIPPED",
          {c.check_name: c.status for c in default.checks}["asset_folder_exists"] == "SKIPPED")


def test_evidence_paths_local(tmp: Path):
    print("\n[15] evidence_paths reference local files only")
    run = _make_run(tmp, "ev1")
    report = _gate(run, tmp / "cert_ev")
    check("evidence paths present", len(report.evidence_paths) >= 4)
    check("no URL evidence paths",
          all(not p.startswith(("http://", "https://")) for p in report.evidence_paths))
    check("evidence paths sorted", list(report.evidence_paths) == sorted(report.evidence_paths))
    check("all evidence paths exist",
          all(Path(p).exists() for p in report.evidence_paths))


def test_result_to_dict_deterministic(tmp: Path):
    print("\n[16] result.to_dict() is deterministic")
    run = _make_run(tmp, "rd1")
    report = _gate(run, tmp / "cert_rd")
    check("repeat to_dict identical",
          json.dumps(report.to_dict(), sort_keys=True) == json.dumps(report.to_dict(), sort_keys=True))
    again = _gate(run, tmp / "cert_rd2")
    check("independent evaluations serialize identically",
          json.dumps(report.to_dict(), sort_keys=True) == json.dumps(again.to_dict(), sort_keys=True))


def test_error_to_dict_deterministic(tmp: Path):
    print("\n[17] error.to_dict() is deterministic")
    a = _gate(12345, tmp / "cert_ed_a")
    b = _gate(12345, tmp / "cert_ed_b")
    check("errors serialize identically",
          json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True))
    check("no traceback leakage", "Traceback" not in json.dumps(a.to_dict(), sort_keys=True))


def test_no_source_mutation(tmp: Path):
    print("\n[18] no source artifact mutation")
    run = _make_run(tmp, "mut1")
    run_root = Path(run.output_dir)
    before = _snapshot(run_root)
    report = _gate(run, tmp / "cert_mut", require_assets=True, require_video=True)
    check("gate returned a report", isinstance(report, CommercialAcceptanceReport))
    after = _snapshot(run_root)
    check("stage 4 artifacts byte-identical", before == after)
    check("no files added or removed under run dir", sorted(before) == sorted(after))


def test_no_network_imports():
    print("\n[19] no network/cloud imports in acceptance_gate.py")
    source = (_COMMERCIAL / "acceptance_gate.py").read_text(encoding="utf-8")
    for token in ("requests", "httpx", "urllib.request", "boto3", "socket",
                  "http.client", "openai", "anthropic"):
        check(f"no '{token}'", token not in source)


def test_no_lower_layer_imports():
    print("\n[20] no knowledge/builder-layer imports in acceptance_gate.py")
    source = (_COMMERCIAL / "acceptance_gate.py").read_text(encoding="utf-8")
    for token in ("KnowledgeIndex", "KnowledgeQueryEngine", "KnowledgeExplainEngine",
                  "KnowledgeInsightEngine", "query_engine", "explain_engine",
                  "insight_engine", "import knowledge", "from knowledge"):
        check(f"no '{token}'", token not in source)
    # Stage 4.1/4.2/4.4 builder modules must never be imported by the gate.
    # (The literal module names may appear only inside check-name strings such
    # as 'delivery_package_exists', which the Stage 4.5 spec itself mandates.)
    for token in ("import report_builder", "from report_builder",
                  "import delivery_package", "from delivery_package",
                  "import run_orchestrator", "from run_orchestrator",
                  "build_commercial_report", "create_delivery_package",
                  "run_commercial_delivery", "KnowledgeService"):
        check(f"no '{token}'", token not in source)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_pass_and_report_written(tmp)
        test_deterministic_output(tmp)
        test_missing_report_json(tmp)
        test_missing_delivery_package(tmp)
        test_missing_required_delivery_file(tmp)
        test_failed_run_blocked(tmp)
        test_invalid_run_result(tmp)
        test_url_rejected(tmp)
        test_readiness_score_deterministic(tmp)
        test_critical_failure_forces_fail(tmp)
        test_require_video(tmp)
        test_require_assets(tmp)
        test_evidence_paths_local(tmp)
        test_result_to_dict_deterministic(tmp)
        test_error_to_dict_deterministic(tmp)
        test_no_source_mutation(tmp)
        test_no_network_imports()
        test_no_lower_layer_imports()

    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
