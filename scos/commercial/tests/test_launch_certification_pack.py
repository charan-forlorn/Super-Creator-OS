"""test_launch_certification_pack.py - SCOS Stage 4.9 certification pack suite."""

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
from first_paid_customer_dry_run import run_first_paid_customer_dry_run  # noqa: E402
from dry_run_models import FirstPaidCustomerDryRunResult  # noqa: E402
from launch_certification_models import (  # noqa: E402
    COMMERCIAL_LAUNCH_CERTIFICATION_SCHEMA_VERSION,
    LaunchCertificationError,
    LaunchCertificationResult,
)
from launch_certification_pack import create_commercial_launch_certification_pack  # noqa: E402

_PASS, _FAIL = 0, 0
_DRY_NOW = "2026-07-03T04:00:00Z"
_CERT_NOW = "2026-07-03T05:00:00Z"


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
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")


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
         "feedback_summary": {"run_id": "first-paid-customer-dry-run", "retention_score": 0.8,
                              "engagement_score": 0.7, "quality_score": 0.9},
         "timestamp": 100},
    ])
    _write_json(p["feedback_log_path"], [
        {"run_id": "first-paid-customer-dry-run", "retention_score": 0.8, "engagement_score": 0.7,
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
             "quality_score": 0.9, "run_id": "first-paid-customer-dry-run",
             "asset_hash": "deadbeef", "timestamp": 100, "error": None, "session_id": "sess_1"},
        ],
    })
    return p


def _svc(base: Path):
    _seed(base)
    return KnowledgeService(LearningKnowledgeIndex(**_paths(base)).build(now_fn=lambda: 1000))


def _dry_run(tmp: Path, name: str, **kwargs) -> Path:
    res = run_first_paid_customer_dry_run(
        knowledge_service=_svc(tmp / f"kb_{name}"),
        output_dir=tmp / f"dry_{name}",
        checked_at=_DRY_NOW,
        **kwargs,
    )
    assert isinstance(res, FirstPaidCustomerDryRunResult), f"fixture dry run failed for {name}"
    return Path(res.dry_run_report_path)


def _cert(path: Path, out: Path, **kwargs):
    return create_commercial_launch_certification_pack(
        dry_run_report_path=path,
        output_dir=out,
        checked_at=_CERT_NOW,
        **kwargs,
    )


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot(paths: list[Path]) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    out[str(child)] = child.read_bytes()
        elif path.is_file():
            out[str(path)] = path.read_bytes()
    return out


def _mutated_report(tmp: Path, name: str, mutate):
    source = _dry_run(tmp, name)
    data = _read(source)
    mutate(data)
    target = tmp / f"{name}_mutated_dry_run.json"
    _write_json(target, data)
    return target


def test_success_and_outputs(tmp: Path):
    print("\n[1-5] successful launch certification writes deterministic pack")
    dry = _dry_run(tmp, "ok1")
    res = _cert(dry, tmp / "cert_ok1")
    check("returns Result", isinstance(res, LaunchCertificationResult))
    check("schema version", res.schema_version == COMMERCIAL_LAUNCH_CERTIFICATION_SCHEMA_VERSION == 1)
    check("PASS", res.certification_status == "PASS")
    check("derived id", res.launch_certification_id.startswith("commercial-launch-certification-"))
    files = [
        res.launch_certification_report_path,
        res.launch_certification_summary_path,
        res.launch_readiness_checklist_path,
        res.launch_blockers_path,
        res.operator_next_steps_path,
    ]
    for path in files:
        check(f"pack file exists: {Path(path).name}", Path(path).is_file())
        check(f"pack file under output_dir: {Path(path).name}",
              str(Path(path).resolve()).startswith(str((tmp / "cert_ok1").resolve())))
    report = _read(Path(res.launch_certification_report_path))
    check("written report matches result", report == res.to_dict())
    before_json = Path(res.launch_certification_report_path).read_text(encoding="utf-8")
    before_md = {Path(p).name: Path(p).read_text(encoding="utf-8") for p in files[1:]}
    over = _cert(dry, tmp / "cert_ok1", overwrite=True)
    check("overwrite True succeeds", isinstance(over, LaunchCertificationResult))
    check("fixed checked_at deterministic JSON",
          before_json == Path(over.launch_certification_report_path).read_text(encoding="utf-8"))
    after_md = {Path(p).name: Path(p).read_text(encoding="utf-8")
                for p in [over.launch_certification_summary_path, over.launch_readiness_checklist_path,
                          over.launch_blockers_path, over.operator_next_steps_path]}
    check("fixed checked_at deterministic Markdown", before_md == after_md)


def test_overwrite_false(tmp: Path):
    print("\n[6] overwrite=False fails if pack already exists")
    dry = _dry_run(tmp, "ow1")
    first = _cert(dry, tmp / "cert_ow1")
    second = _cert(dry, tmp / "cert_ow1")
    check("first succeeds", isinstance(first, LaunchCertificationResult))
    check("second OUTPUT_ALREADY_EXISTS", isinstance(second, LaunchCertificationError)
          and second.error_kind == "OUTPUT_ALREADY_EXISTS")


def test_input_errors(tmp: Path):
    print("\n[7-10] input and dry-run JSON errors")
    missing = _cert(tmp / "ghost.json", tmp / "cert_missing")
    check("missing dry_run_report_path INPUT_NOT_FOUND", isinstance(missing, LaunchCertificationError)
          and missing.error_kind == "INPUT_NOT_FOUND")
    bad = tmp / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    invalid = _cert(bad, tmp / "cert_bad")
    check("invalid JSON INVALID_DRY_RUN_REPORT", isinstance(invalid, LaunchCertificationError)
          and invalid.error_kind == "INVALID_DRY_RUN_REPORT")
    partial = tmp / "partial.json"
    _write_json(partial, {"ok": True})
    missing_keys = _cert(partial, tmp / "cert_partial")
    check("missing keys INVALID_DRY_RUN_REPORT", isinstance(missing_keys, LaunchCertificationError)
          and missing_keys.error_kind == "INVALID_DRY_RUN_REPORT")
    url_in = create_commercial_launch_certification_pack(
        dry_run_report_path="https://example.test/dry.json",
        output_dir=tmp / "cert_url",
        checked_at=_CERT_NOW,
    )
    check("URL dry_run_report_path rejected", isinstance(url_in, LaunchCertificationError)
          and url_in.error_kind == "INVALID_ARGUMENTS")
    url_out = create_commercial_launch_certification_pack(
        dry_run_report_path=partial,
        output_dir="http://example.test/out",
        checked_at=_CERT_NOW,
    )
    check("URL output_dir rejected", isinstance(url_out, LaunchCertificationError)
          and url_out.error_kind == "INVALID_ARGUMENTS")


def test_status_rules(tmp: Path):
    print("\n[11-16] status and blocker rules")
    not_passed = _mutated_report(tmp, "np1", lambda d: d.update({"passed": False}))
    r1 = _cert(not_passed, tmp / "cert_np1")
    check("dry_run passed=False produces FAIL", isinstance(r1, LaunchCertificationResult)
          and r1.certification_status == "FAIL")
    no_go = _mutated_report(tmp, "ng1", lambda d: d.update({"go_no_go": "NO_GO"}))
    r2 = _cert(no_go, tmp / "cert_ng1")
    check("go_no_go != GO require_go True FAIL", isinstance(r2, LaunchCertificationResult)
          and r2.certification_status == "FAIL")
    r3 = _cert(no_go, tmp / "cert_ng2", require_go=False)
    check("go_no_go != GO require_go False CONDITIONAL_PASS", isinstance(r3, LaunchCertificationResult)
          and r3.certification_status == "CONDITIONAL_PASS")
    accepted_false = _mutated_report(
        tmp, "af1",
        lambda d: _write_json(Path(d["acceptance_report_path"]),
                              dict(_read(Path(d["acceptance_report_path"])), ok=False, overall_status="FAIL")),
    )
    r4 = _cert(accepted_false, tmp / "cert_af1")
    check("acceptance accepted=False creates blocker", isinstance(r4, LaunchCertificationResult)
          and any(b.blocker_id == "BLOCKER_ACCEPTANCE_NOT_ACCEPTED" for b in r4.blockers))
    ready_no_go = _mutated_report(
        tmp, "rno1",
        lambda d: _write_json(Path(d["monetization_readiness_report_path"]),
                              dict(_read(Path(d["monetization_readiness_report_path"])), go_no_go="NO_GO")),
    )
    r5 = _cert(ready_no_go, tmp / "cert_rno1")
    check("readiness NO_GO creates blocker", isinstance(r5, LaunchCertificationResult)
          and any(b.blocker_id == "BLOCKER_READINESS_NOT_GO" for b in r5.blockers))
    critical = _mutated_report(
        tmp, "crit1",
        lambda d: d["blockers"].append({
            "blocker_id": "BLOCKER_SYNTHETIC_CRITICAL",
            "category": "synthetic",
            "severity": "critical",
            "title": "Synthetic critical blocker",
            "detail": "Synthetic critical blocker.",
            "recommended_action": "Fix it.",
            "source_step": "test",
            "metadata": {},
        }),
    )
    r6 = _cert(critical, tmp / "cert_crit1")
    check("critical blocker produces FAIL", isinstance(r6, LaunchCertificationResult)
          and r6.certification_status == "FAIL")
    warning = _mutated_report(
        tmp, "warn1",
        lambda d: d["blockers"].append({
            "blocker_id": "BLOCKER_SYNTHETIC_WARNING",
            "category": "synthetic",
            "severity": "warning",
            "title": "Synthetic warning blocker",
            "detail": "Synthetic warning blocker.",
            "recommended_action": "Review it.",
            "source_step": "test",
            "metadata": {},
        }),
    )
    r7 = _cert(warning, tmp / "cert_warn1")
    check("warning blocker can produce CONDITIONAL_PASS", isinstance(r7, LaunchCertificationResult)
          and r7.certification_status == "CONDITIONAL_PASS")


def test_missing_evidence(tmp: Path):
    print("\n[17-20] missing evidence paths produce MISSING_EVIDENCE")
    for key in ("commercial_run_manifest_path", "acceptance_report_path",
                "operating_kit_path", "monetization_readiness_report_path"):
        bad = _mutated_report(tmp, f"miss_{key}", lambda d, k=key: d.update({k: str(tmp / f"missing_{k}")}))
        res = _cert(bad, tmp / f"cert_miss_{key}")
        check(f"{key} MISSING_EVIDENCE", isinstance(res, LaunchCertificationError)
              and res.error_kind == "MISSING_EVIDENCE")


def test_pii_and_path_containment(tmp: Path):
    print("\n[21-24] PII and containment protection")
    phone = _mutated_report(tmp, "pii_phone", lambda d: d["customer_case"].update({"phone": "555"}))
    r1 = _cert(phone, tmp / "cert_pii_phone")
    check("customer_case phone key rejected", isinstance(r1, LaunchCertificationError)
          and r1.error_kind == "PII_DETECTED")
    email = _mutated_report(tmp, "pii_email", lambda d: d["metadata"].update({"email": "x@example.test"}))
    r2 = _cert(email, tmp / "cert_pii_email")
    check("metadata email key rejected", isinstance(r2, LaunchCertificationError)
          and r2.error_kind == "PII_DETECTED")
    dry = _dry_run(tmp, "contain1")
    escaped = _cert(dry, tmp / "cert_contain1", certification_id="..\\escape")
    check("path containment escape rejected", isinstance(escaped, LaunchCertificationError)
          and escaped.error_kind == "PATH_CONTAINMENT_FAILED")
    ok = _cert(dry, tmp / "cert_contain2")
    check("output files remain under output_dir", isinstance(ok, LaunchCertificationResult)
          and all(str(Path(p).resolve()).startswith(str((tmp / "cert_contain2").resolve()))
                  for p in (ok.launch_certification_report_path, ok.launch_certification_summary_path,
                            ok.launch_readiness_checklist_path, ok.launch_blockers_path,
                            ok.operator_next_steps_path)))


def test_determinism_and_source_immutability(tmp: Path):
    print("\n[25-28] deterministic serialization and source immutability")
    dry = _dry_run(tmp, "immut1")
    data = _read(dry)
    source_paths = [
        dry,
        Path(data["commercial_run_manifest_path"]),
        Path(data["acceptance_report_path"]),
        Path(data["operating_kit_path"]),
        Path(data["monetization_readiness_report_path"]),
    ]
    before = _snapshot(source_paths)
    res = _cert(dry, tmp / "cert_immut1")
    after = _snapshot(source_paths)
    check("inspected source artifacts are not mutated", before == after)
    check("result.to_dict deterministic", isinstance(res, LaunchCertificationResult)
          and json.dumps(res.to_dict(), sort_keys=True) == json.dumps(res.to_dict(), sort_keys=True))
    err1 = _cert(tmp / "ghost_a.json", tmp / "cert_err_a")
    err2 = _cert(tmp / "ghost_a.json", tmp / "cert_err_b")
    check("error.to_dict deterministic", isinstance(err1, LaunchCertificationError)
          and isinstance(err2, LaunchCertificationError)
          and json.dumps(err1.to_dict(), sort_keys=True) == json.dumps(err2.to_dict(), sort_keys=True))


def test_static_boundary_scans(tmp: Path):
    print("\n[29-32] static and markdown boundary scans")
    source = (_COMMERCIAL / "launch_certification_pack.py").read_text(encoding="utf-8")
    for token in ("requests", "httpx", "urllib.request", "boto3", "socket",
                  "http.client", "openai", "anthropic", "stripe", "paypal"):
        check(f"no network/service token '{token}'", token not in source)
    for token in ("KnowledgeService", "KnowledgeIndex", "KnowledgeQueryEngine",
                  "KnowledgeExplainEngine", "KnowledgeInsightEngine", "query_engine",
                  "explain_engine", "insight_engine"):
        check(f"no knowledge implementation token '{token}'", token not in source)
    for token in ("build_commercial_report", "create_delivery_package",
                  "run_commercial_delivery", "certify_commercial_run",
                  "generate_first_customer_kit", "review_monetization_readiness",
                  "run_first_paid_customer_dry_run"):
        check(f"no Stage 4.1-4.8 execution token '{token}'", token not in source)
    dry = _dry_run(tmp, "md_scan")
    res = _cert(dry, tmp / "cert_md_scan")
    text = "\n".join(Path(p).read_text(encoding="utf-8") for p in (
        res.launch_certification_summary_path,
        res.launch_readiness_checklist_path,
        res.launch_blockers_path,
        res.operator_next_steps_path,
    ))
    lowered = text.lower()
    check("markdown contains no real outreach automation claim", "automated outreach" not in lowered)
    for token in ("saas", "payment", "auth", "crm"):
        check(f"markdown contains no {token} instructions", token not in lowered)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_success_and_outputs(tmp)
        test_overwrite_false(tmp)
        test_input_errors(tmp)
        test_status_rules(tmp)
        test_missing_evidence(tmp)
        test_pii_and_path_containment(tmp)
        test_determinism_and_source_immutability(tmp)
        test_static_boundary_scans(tmp)
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
