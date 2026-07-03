"""test_first_paid_customer_dry_run.py - SCOS Stage 4.8 dry-run suite."""

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
import first_paid_customer_dry_run as dry_run_module  # noqa: E402
from acceptance_models import CommercialAcceptanceReport  # noqa: E402
from dry_run_models import (  # noqa: E402
    FIRST_PAID_CUSTOMER_DRY_RUN_SCHEMA_VERSION,
    FirstPaidCustomerDryRunError,
    FirstPaidCustomerDryRunResult,
    SyntheticCustomerCase,
)
from first_paid_customer_dry_run import run_first_paid_customer_dry_run  # noqa: E402

_PASS, _FAIL = 0, 0
_NOW = "2026-07-03T04:00:00Z"
_RUN_ID = "first-paid-customer-dry-run"


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
         "feedback_summary": {"run_id": _RUN_ID, "retention_score": 0.8,
                              "engagement_score": 0.7, "quality_score": 0.9},
         "timestamp": 100},
    ])
    _write_json(p["feedback_log_path"], [
        {"run_id": _RUN_ID, "retention_score": 0.8, "engagement_score": 0.7,
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
             "quality_score": 0.9, "run_id": _RUN_ID, "asset_hash": "deadbeef",
             "timestamp": 100, "error": None, "session_id": "sess_1"},
        ],
    })
    return p


def _svc(base: Path):
    _seed(base)
    return KnowledgeService(LearningKnowledgeIndex(**_paths(base)).build(now_fn=lambda: 1000))


def _run(tmp: Path, name: str, **kwargs):
    return run_first_paid_customer_dry_run(
        knowledge_service=_svc(tmp / f"kb_{name}"),
        output_dir=tmp / f"dry_{name}",
        checked_at=_NOW,
        **kwargs,
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_success(tmp: Path):
    print("\n[1-4] successful dry run writes report under output_dir")
    res = _run(tmp, "ok1")
    check("returns Result", isinstance(res, FirstPaidCustomerDryRunResult))
    check("ok True", res.ok is True)
    check("passed True", res.passed is True)
    check("schema_version", res.schema_version == FIRST_PAID_CUSTOMER_DRY_RUN_SCHEMA_VERSION == 1)
    check("GO", res.go_no_go == "GO")
    check("ready level", res.readiness_level == "ready")
    report = Path(res.dry_run_report_path)
    check("dry-run report written", report.is_file())
    check("report under output_dir", str(report.resolve()).startswith(str((tmp / "dry_ok1").resolve())))
    written = json.loads(report.read_text(encoding="utf-8"))
    check("written report schema", written["schema_version"] == 1)
    check("no output outside output_dir",
          all(str(Path(p).resolve()).startswith(str((tmp / "dry_ok1").resolve()))
              for p in (res.commercial_run_manifest_path, res.acceptance_report_path,
                        res.operating_kit_path, res.monetization_readiness_report_path,
                        res.dry_run_report_path)))


def test_deterministic(tmp: Path):
    print("\n[3,18-19] deterministic result and error to_dict")
    a = _run(tmp, "det_a")
    b = _run(tmp, "det_b")
    da = a.to_dict()
    db = b.to_dict()
    for field in ("schema_version", "passed", "go_no_go", "readiness_level",
                  "readiness_score", "readiness_max_score", "customer_case"):
        check(f"deterministic field {field}", da[field] == db[field])
    check("result to_dict repeatable",
          json.dumps(a.to_dict(), sort_keys=True) == json.dumps(a.to_dict(), sort_keys=True))
    e1 = run_first_paid_customer_dry_run(
        knowledge_service=_svc(tmp / "kb_err"),
        output_dir="",
        checked_at=_NOW,
    )
    e2 = run_first_paid_customer_dry_run(
        knowledge_service=_svc(tmp / "kb_err2"),
        output_dir="",
        checked_at=_NOW,
    )
    check("error to_dict deterministic",
          json.dumps(e1.to_dict(), sort_keys=True) == json.dumps(e2.to_dict(), sort_keys=True))


def test_validation_errors(tmp: Path):
    print("\n[5-9] validation errors")
    svc = _svc(tmp / "kb_val")
    missing_out = run_first_paid_customer_dry_run(
        knowledge_service=svc, output_dir="", checked_at=_NOW)
    check("missing output_dir INVALID_ARGUMENTS", isinstance(missing_out, FirstPaidCustomerDryRunError)
          and missing_out.error_kind == "INVALID_ARGUMENTS")
    missing_time = run_first_paid_customer_dry_run(
        knowledge_service=svc, output_dir=tmp / "dry_time", checked_at="")
    check("missing checked_at INVALID_ARGUMENTS", isinstance(missing_time, FirstPaidCustomerDryRunError)
          and missing_time.error_kind == "INVALID_ARGUMENTS")
    url_out = run_first_paid_customer_dry_run(
        knowledge_service=svc, output_dir="https://example.test/out", checked_at=_NOW)
    check("URL output rejected", isinstance(url_out, FirstPaidCustomerDryRunError)
          and url_out.error_kind == "INVALID_ARGUMENTS")
    url_video = run_first_paid_customer_dry_run(
        knowledge_service=svc, output_dir=tmp / "dry_url_video", checked_at=_NOW,
        video_path="http://example.test/video.mp4")
    check("URL video rejected", isinstance(url_video, FirstPaidCustomerDryRunError)
          and url_video.error_kind == "INVALID_ARGUMENTS")
    url_manifest = run_first_paid_customer_dry_run(
        knowledge_service=svc, output_dir=tmp / "dry_url_manifest", checked_at=_NOW,
        source_manifest_path="https://example.test/manifest.json")
    check("URL source manifest rejected", isinstance(url_manifest, FirstPaidCustomerDryRunError)
          and url_manifest.error_kind == "INVALID_ARGUMENTS")
    missing_video = run_first_paid_customer_dry_run(
        knowledge_service=svc, output_dir=tmp / "dry_missing_video", checked_at=_NOW,
        video_path=tmp / "ghost.mp4")
    check("missing video INPUT_NOT_FOUND", isinstance(missing_video, FirstPaidCustomerDryRunError)
          and missing_video.error_kind == "INPUT_NOT_FOUND")


def test_customer_cases(tmp: Path):
    print("\n[10-12] synthetic and custom customer cases")
    res = _run(tmp, "case_default")
    case = res.customer_case.to_dict()
    check("default synthetic id", case["customer_id"] == "synthetic-first-customer-001")
    text = json.dumps(case, sort_keys=True).lower()
    check("default no email key", "email" not in text)
    check("default no phone key", "phone" not in text)
    check("default no address key", "address" not in text)
    custom = SyntheticCustomerCase.of(
        customer_id="synthetic-custom-002",
        business_name="Synthetic Studio",
        business_type="studio",
        target_offer="AI Content Delivery Audit",
        target_price="5900 THB dry-run offer",
        intake_summary="Custom synthetic dry-run case.",
        expected_deliverables=("commercial_report", "monetization_readiness_report"),
        metadata={"case_type": "synthetic"},
    )
    custom_res = _run(tmp, "case_custom", customer_case=custom)
    check("custom customer works", isinstance(custom_res, FirstPaidCustomerDryRunResult)
          and custom_res.customer_case.customer_id == "synthetic-custom-002")
    bad = SyntheticCustomerCase.of(
        customer_id="synthetic-bad-003",
        business_name="Synthetic Bad",
        business_type="clinic",
        target_offer="AI Content Delivery Audit",
        target_price="4900 THB dry-run offer",
        intake_summary="Bad metadata case.",
        expected_deliverables=("commercial_report",),
        metadata={"email": "hidden@example.test"},
    )
    bad_res = _run(tmp, "case_bad", customer_case=bad)
    check("metadata email rejected", isinstance(bad_res, FirstPaidCustomerDryRunError)
          and bad_res.error_kind == "INVALID_CUSTOMER_CASE")


def test_risk_and_require_go(tmp: Path):
    print("\n[13-15,17] risk checklist and require_go behavior")
    go = _run(tmp, "risk_go", add_synthetic_risk_checklist=True)
    check("synthetic risk enables GO", isinstance(go, FirstPaidCustomerDryRunResult)
          and go.go_no_go == "GO" and go.passed is True)
    no_go = _run(tmp, "risk_no_go", add_synthetic_risk_checklist=False)
    check("without risk returns Result", isinstance(no_go, FirstPaidCustomerDryRunResult))
    check("without risk NO_GO", no_go.go_no_go == "NO_GO")
    check("without risk passed False", no_go.passed is False)
    check("risk blocker exposed", any(b.category == "risk_readiness" for b in no_go.blockers))
    relaxed = _run(tmp, "risk_relaxed", add_synthetic_risk_checklist=False, require_go=False)
    check("require_go False completes", isinstance(relaxed, FirstPaidCustomerDryRunResult))
    check("require_go False still documents non-pass", relaxed.passed is False and relaxed.go_no_go == "NO_GO")
    check("monetization NO_GO blocker", any(b.blocker_id == "BLOCKER_MONETIZATION_NOT_GO"
                                           for b in no_go.blockers))


def test_acceptance_failure_blocker(tmp: Path):
    print("\n[16] acceptance failure creates blocker")
    original = dry_run_module.run_commercial_acceptance_gate

    def fake_gate(*, commercial_run_result, output_dir, created_at, **kwargs):
        return CommercialAcceptanceReport(
            ok=False,
            schema_version=1,
            certification_id="commercial-acceptance-fake",
            run_id="fake-run",
            delivery_id="fake-delivery",
            created_at=created_at,
            overall_status="FAIL",
            readiness_score=0,
            checks=(),
            evidence_paths=(),
            blocking_reasons=("synthetic acceptance failure",),
            metadata=dry_run_module.FrozenMap.from_mapping({"fake": True}),
        )

    try:
        dry_run_module.run_commercial_acceptance_gate = fake_gate
        res = _run(tmp, "accept_fail")
    finally:
        dry_run_module.run_commercial_acceptance_gate = original
    check("returns Error after kit cannot continue", isinstance(res, FirstPaidCustomerDryRunError))
    check("acceptance blocker carried", any(b.blocker_id == "BLOCKER_ACCEPTANCE_NOT_READY"
                                           for b in res.blockers))


def test_artifact_references(tmp: Path):
    print("\n[20-23] report references existing artifacts")
    res = _run(tmp, "refs")
    check("run manifest exists", Path(res.commercial_run_manifest_path).is_file())
    check("acceptance report exists", Path(res.acceptance_report_path).is_file())
    check("operating kit exists", Path(res.operating_kit_path).is_dir())
    check("readiness report exists", Path(res.monetization_readiness_report_path).is_file())


def test_no_source_mutation(tmp: Path):
    print("\n[24] inspected source artifacts are not mutated")
    video = tmp / "source.mp4"
    source_manifest = tmp / "source_manifest.json"
    video.write_bytes(b"synthetic video bytes")
    source_manifest.write_text('{"source":"synthetic"}\n', encoding="utf-8")
    before = {str(video): video.read_bytes(), str(source_manifest): source_manifest.read_bytes()}
    res = run_first_paid_customer_dry_run(
        knowledge_service=_svc(tmp / "kb_mut"),
        output_dir=tmp / "dry_mut",
        checked_at=_NOW,
        video_path=video,
        source_manifest_path=source_manifest,
    )
    check("dry run completed", isinstance(res, FirstPaidCustomerDryRunResult))
    after = {str(video): video.read_bytes(), str(source_manifest): source_manifest.read_bytes()}
    check("source bytes unchanged", before == after)
    check("source not inside output", not str(video.resolve()).startswith(str((tmp / "dry_mut").resolve())))


def test_static_token_scan():
    print("\n[25-28] static boundary scans")
    source = (_COMMERCIAL / "first_paid_customer_dry_run.py").read_text(encoding="utf-8")
    for token in ("requests", "httpx", "urllib.request", "boto3", "socket",
                  "http.client", "openai", "anthropic"):
        check(f"no network token '{token}'", token not in source)
    for token in ("stripe", "paypal", "payment", "invoice", "CRM"):
        check(f"no commercial service token '{token}'", token not in source)
    for token in ("KnowledgeIndex", "KnowledgeQueryEngine", "KnowledgeExplainEngine",
                  "KnowledgeInsightEngine", "query_engine", "explain_engine", "insight_engine"):
        check(f"no lower knowledge token '{token}'", token not in source)
    check("uses public run API", "run_commercial_delivery" in source)
    check("uses public acceptance API", "run_commercial_acceptance_gate" in source)
    check("uses public kit API", "generate_first_customer_kit" in source)
    check("uses public readiness API", "review_monetization_readiness" in source)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_success(tmp)
        test_deterministic(tmp)
        test_validation_errors(tmp)
        test_customer_cases(tmp)
        test_risk_and_require_go(tmp)
        test_acceptance_failure_blocker(tmp)
        test_artifact_references(tmp)
        test_no_source_mutation(tmp)
    test_static_token_scan()
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
