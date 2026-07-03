"""test_customer_kit.py - SCOS Stage 4.6 first customer operating kit suite.

Plain-assert script (project convention, not pytest). Seeds a real Stage 3.9
knowledge index/service, produces a real Stage 4.4 commercial run, certifies it
through the Stage 4.5 acceptance gate to a genuine accepted acceptance report,
then generates a first customer operating kit from that accepted report and
verifies deterministic outputs, evidence behavior, error kinds, source
immutability, and local-only restrictions.

Run: python scos/commercial/tests/test_customer_kit.py
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
from acceptance_models import CommercialAcceptanceReport  # noqa: E402
from customer_kit import generate_first_customer_kit  # noqa: E402
from customer_kit_models import (  # noqa: E402
    CUSTOMER_KIT_SCHEMA_VERSION,
    CustomerKitError,
    CustomerKitResult,
)

_PASS, _FAIL = 0, 0
_RUN_NOW = "2026-07-03T00:00:00Z"
_GATE_NOW = "2026-07-03T01:00:00Z"
_KIT_NOW = "2026-07-03T02:00:00Z"

_REQUIRED_MARKDOWN = (
    "customer_intake_checklist.md",
    "operator_sop.md",
    "delivery_handoff.md",
    "acceptance_certificate.md",
    "pricing_offer_checklist.md",
    "customer_followup_checklist.md",
    "files_to_send.md",
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
# Real fixture: knowledge -> run -> accepted acceptance report
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


def _accepted_report(tmp: Path, name: str) -> Path:
    """Produce a genuine accepted Stage 4.5 acceptance report; return its path."""

    svc = _svc(tmp / f"kb_{name}")
    run = run_commercial_delivery(
        knowledge_service=svc,
        run_id="run_a1",
        output_dir=tmp / f"run_{name}",
        created_at=_RUN_NOW,
    )
    assert isinstance(run, CommercialRunResult), f"fixture run failed for {name}"
    report = run_commercial_acceptance_gate(
        commercial_run_result=run,
        output_dir=tmp / f"cert_{name}",
        created_at=_GATE_NOW,
    )
    assert isinstance(report, CommercialAcceptanceReport), f"fixture gate failed for {name}"
    assert report.overall_status == "PASS", f"fixture gate not PASS for {name}"
    return Path(tmp / f"cert_{name}" / report.certification_id.replace(":", "_")
                / "commercial_acceptance_report.json")


def _gen(report_path: Path, out: Path, **kwargs):
    return generate_first_customer_kit(
        acceptance_report_path=report_path,
        output_dir=out,
        customer_id=kwargs.pop("customer_id", "cust_1"),
        created_at=kwargs.pop("created_at", _KIT_NOW),
        **kwargs,
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_success(tmp: Path):
    print("\n[1-4] successful kit generation from accepted report")
    rp = _accepted_report(tmp, "ok1")
    out = tmp / "kit_ok1"
    res = _gen(rp, out)
    check("returns CustomerKitResult", isinstance(res, CustomerKitResult))
    check("ok is True", res.ok is True)
    check("schema_version == 1", res.schema_version == CUSTOMER_KIT_SCHEMA_VERSION == 1)
    check("kit_id derived", res.kit_id == "first-customer-kit-cust_1")
    check("acceptance_id from certification_id", res.acceptance_id == "commercial-acceptance-run_a1")
    check("run_id mapped", res.run_id == "run_a1")
    kit_dir = Path(res.output_dir)
    check("manifest created", (kit_dir / "customer_kit_manifest.json").is_file())
    for name in _REQUIRED_MARKDOWN:
        check(f"markdown created: {name}", (kit_dir / name).is_file())
    manifest = json.loads((kit_dir / "customer_kit_manifest.json").read_text(encoding="utf-8"))
    check("manifest acceptance_id", manifest["acceptance_id"] == "commercial-acceptance-run_a1")
    check("manifest has source paths", manifest["source_report_path"].endswith("report.json")
          and "delivery_package" in manifest["source_package_path"]
          and manifest["source_package_manifest_path"].endswith("manifest.json"))
    check("manifest generated_files sorted", manifest["generated_files"] == sorted(manifest["generated_files"]))


def test_evidence_copied(tmp: Path):
    print("\n[5] evidence copied when copy_evidence=True")
    rp = _accepted_report(tmp, "ev1")
    res = _gen(rp, tmp / "kit_ev1", copy_evidence=True)
    ev = Path(res.output_dir) / "evidence"
    check("evidence dir exists", ev.is_dir())
    check("acceptance_report copied", (ev / "acceptance_report.json").is_file())
    check("run manifest copied", (ev / "commercial_run_manifest.json").is_file())
    check("package manifest copied", (ev / "package_manifest.json").is_file())


def test_evidence_not_copied(tmp: Path):
    print("\n[6] evidence not copied when copy_evidence=False")
    rp = _accepted_report(tmp, "ev2")
    res = _gen(rp, tmp / "kit_ev2", copy_evidence=False)
    check("no evidence dir", not (Path(res.output_dir) / "evidence").exists())
    manifest = json.loads((Path(res.output_dir) / "customer_kit_manifest.json").read_text(encoding="utf-8"))
    check("manifest still references source paths",
          manifest["source_acceptance_report_path"].endswith("commercial_acceptance_report.json"))


def test_not_accepted(tmp: Path):
    print("\n[7] non-accepted report returns ACCEPTANCE_NOT_PASSED")
    rp = _accepted_report(tmp, "na1")
    data = json.loads(rp.read_text(encoding="utf-8"))
    data["overall_status"] = "FAIL"
    data["ok"] = False
    bad = tmp / "na1_fail.json"
    bad.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")
    res = _gen(bad, tmp / "kit_na1")
    check("returns error", isinstance(res, CustomerKitError))
    check("ACCEPTANCE_NOT_PASSED", res.error_kind == "ACCEPTANCE_NOT_PASSED")


def test_missing_report(tmp: Path):
    print("\n[8] missing acceptance report returns INPUT_NOT_FOUND")
    res = _gen(tmp / "ghost.json", tmp / "kit_ghost")
    check("INPUT_NOT_FOUND", isinstance(res, CustomerKitError) and res.error_kind == "INPUT_NOT_FOUND")


def test_invalid_json(tmp: Path):
    print("\n[9] invalid acceptance JSON returns INVALID_ACCEPTANCE_REPORT")
    bad = tmp / "garbage.json"
    bad.write_text("{not json", encoding="utf-8")
    res = _gen(bad, tmp / "kit_garbage")
    check("INVALID_ACCEPTANCE_REPORT", isinstance(res, CustomerKitError)
          and res.error_kind == "INVALID_ACCEPTANCE_REPORT")


def test_missing_keys(tmp: Path):
    print("\n[10] missing required acceptance keys returns INVALID_ACCEPTANCE_REPORT")
    bad = tmp / "partial.json"
    bad.write_text(json.dumps({"ok": True, "overall_status": "PASS"}), encoding="utf-8")
    res = _gen(bad, tmp / "kit_partial")
    check("INVALID_ACCEPTANCE_REPORT", isinstance(res, CustomerKitError)
          and res.error_kind == "INVALID_ACCEPTANCE_REPORT")


def test_missing_run_manifest(tmp: Path):
    print("\n[11] missing referenced run manifest returns MISSING_SOURCE_ARTIFACT")
    rp = _accepted_report(tmp, "mm1")
    # Remove the run manifest so evidence-path discovery finds a non-existent file.
    manifest = [p for p in json.loads(rp.read_text(encoding="utf-8"))["evidence_paths"]
                if Path(p).name == "commercial_run_manifest.json"][0]
    Path(manifest).unlink()
    res = _gen(rp, tmp / "kit_mm1")
    check("MISSING_SOURCE_ARTIFACT", isinstance(res, CustomerKitError)
          and res.error_kind == "MISSING_SOURCE_ARTIFACT")


def test_missing_source_files(tmp: Path):
    print("\n[12-14] missing referenced report/package/package-manifest -> MISSING_SOURCE_ARTIFACT")
    # report.json
    rp = _accepted_report(tmp, "sf1")
    run_manifest = [p for p in json.loads(rp.read_text(encoding="utf-8"))["evidence_paths"]
                    if Path(p).name == "commercial_run_manifest.json"][0]
    run_data = json.loads(Path(run_manifest).read_text(encoding="utf-8"))
    Path(run_data["report_path"]).unlink()
    r1 = _gen(rp, tmp / "kit_sf1")
    check("missing report -> MISSING_SOURCE_ARTIFACT", isinstance(r1, CustomerKitError)
          and r1.error_kind == "MISSING_SOURCE_ARTIFACT")
    # package dir
    rp2 = _accepted_report(tmp, "sf2")
    rd2 = json.loads(Path([p for p in json.loads(rp2.read_text(encoding="utf-8"))["evidence_paths"]
                           if Path(p).name == "commercial_run_manifest.json"][0]).read_text(encoding="utf-8"))
    shutil.rmtree(rd2["package_path"])
    r2 = _gen(rp2, tmp / "kit_sf2")
    check("missing package -> MISSING_SOURCE_ARTIFACT", isinstance(r2, CustomerKitError)
          and r2.error_kind == "MISSING_SOURCE_ARTIFACT")
    # package manifest only
    rp3 = _accepted_report(tmp, "sf3")
    rd3 = json.loads(Path([p for p in json.loads(rp3.read_text(encoding="utf-8"))["evidence_paths"]
                           if Path(p).name == "commercial_run_manifest.json"][0]).read_text(encoding="utf-8"))
    Path(rd3["package_manifest_path"]).unlink()
    r3 = _gen(rp3, tmp / "kit_sf3")
    check("missing package manifest -> MISSING_SOURCE_ARTIFACT", isinstance(r3, CustomerKitError)
          and r3.error_kind == "MISSING_SOURCE_ARTIFACT")


def test_url_rejected(tmp: Path):
    print("\n[15] URL input/output rejected")
    rp = _accepted_report(tmp, "url1")
    u_out = generate_first_customer_kit(
        acceptance_report_path=rp, output_dir="https://evil.example/kits",
        customer_id="cust_1", created_at=_KIT_NOW)
    check("URL output rejected", isinstance(u_out, CustomerKitError)
          and u_out.error_kind == "INVALID_ARGUMENTS")
    u_in = generate_first_customer_kit(
        acceptance_report_path="http://evil.example/report.json", output_dir=tmp / "kit_url",
        customer_id="cust_1", created_at=_KIT_NOW)
    check("URL input rejected", isinstance(u_in, CustomerKitError)
          and u_in.error_kind == "INVALID_ARGUMENTS")


def test_output_exists_and_overwrite(tmp: Path):
    print("\n[16-17] OUTPUT_ALREADY_EXISTS then overwrite=True succeeds deterministically")
    rp = _accepted_report(tmp, "ow1")
    out = tmp / "kit_ow1"
    first = _gen(rp, out)
    check("first generation ok", isinstance(first, CustomerKitResult))
    second = _gen(rp, out)
    check("OUTPUT_ALREADY_EXISTS", isinstance(second, CustomerKitError)
          and second.error_kind == "OUTPUT_ALREADY_EXISTS")
    over = _gen(rp, out, overwrite=True)
    check("overwrite succeeds", isinstance(over, CustomerKitResult) and over.ok)
    a = json.loads((Path(first.output_dir) / "customer_kit_manifest.json").read_text(encoding="utf-8"))
    b = json.loads((Path(over.output_dir) / "customer_kit_manifest.json").read_text(encoding="utf-8"))
    check("overwrite manifest identical", json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True))


def test_deterministic(tmp: Path):
    print("\n[18-20] deterministic manifest + result/error to_dict")
    rp = _accepted_report(tmp, "det1")
    a = _gen(rp, tmp / "kit_det_a")
    b = _gen(rp, tmp / "kit_det_b")
    ma = json.loads((Path(a.output_dir) / "customer_kit_manifest.json").read_text(encoding="utf-8"))
    mb = json.loads((Path(b.output_dir) / "customer_kit_manifest.json").read_text(encoding="utf-8"))
    # output_dir differs per run; compare the schema-bearing fields only.
    for k in ("acceptance_id", "run_id", "delivery_id", "generated_files", "schema_version"):
        check(f"manifest field deterministic: {k}", ma[k] == mb[k])
    check("result to_dict repeatable",
          json.dumps(a.to_dict(), sort_keys=True) == json.dumps(a.to_dict(), sort_keys=True))
    err = _gen(tmp / "ghost2.json", tmp / "kit_det_err_a")
    err2 = _gen(tmp / "ghost2.json", tmp / "kit_det_err_b")
    check("error to_dict deterministic",
          json.dumps(err.to_dict(), sort_keys=True) == json.dumps(err2.to_dict(), sort_keys=True))


def test_no_source_mutation(tmp: Path):
    print("\n[21] source artifacts are not mutated")
    rp = _accepted_report(tmp, "mut1")
    run_manifest = Path([p for p in json.loads(rp.read_text(encoding="utf-8"))["evidence_paths"]
                         if Path(p).name == "commercial_run_manifest.json"][0])
    run_root = run_manifest.parent
    before = _snapshot(run_root)
    before_report = rp.read_bytes()
    res = _gen(rp, tmp / "kit_mut1")
    check("generation ok", isinstance(res, CustomerKitResult))
    after = _snapshot(run_root)
    check("run artifacts byte-identical", before == after)
    check("acceptance report byte-identical", before_report == rp.read_bytes())


def test_outputs_under_output_dir(tmp: Path):
    print("\n[22] output paths stay under output_dir")
    rp = _accepted_report(tmp, "under1")
    out = (tmp / "kit_under1").resolve()
    res = _gen(rp, out)
    check("output_dir under base", Path(res.output_dir).resolve().parent == out)
    for f in res.files:
        check(f"file under kit dir: {f.file_name}",
              str(Path(f.file_path).resolve()).startswith(str(Path(res.output_dir).resolve())))


def test_markdown_no_clock_random(tmp: Path):
    print("\n[23] generated markdown contains no real clock/random values")
    rp = _accepted_report(tmp, "md1")
    res = _gen(rp, tmp / "kit_md1")
    kit_dir = Path(res.output_dir)
    for name in _REQUIRED_MARKDOWN:
        text = (kit_dir / name).read_text(encoding="utf-8")
        # only the injected fixed timestamps may appear as time-like values
        for token in ("2024-", "2025-", "T12:", "random", "uuid"):
            check(f"{name} free of '{token}'", token not in text)


def test_static_token_scan():
    print("\n[24-26] static forbidden-token scan of customer_kit.py")
    source = (_COMMERCIAL / "customer_kit.py").read_text(encoding="utf-8")
    for token in ("requests", "httpx", "urllib.request", "boto3", "socket",
                  "http.client", "openai", "anthropic"):
        check(f"no network token '{token}'", token not in source)
    for token in ("KnowledgeService", "KnowledgeIndex", "KnowledgeQueryEngine",
                  "KnowledgeExplainEngine", "KnowledgeInsightEngine", "query_engine",
                  "explain_engine", "insight_engine"):
        check(f"no knowledge token '{token}'", token not in source)
    for token in ("build_commercial_report", "create_delivery_package",
                  "run_commercial_delivery", "certify_commercial_run",
                  "import report_builder", "from report_builder",
                  "import delivery_package", "from delivery_package",
                  "import run_orchestrator", "from run_orchestrator",
                  "import acceptance_gate", "from acceptance_gate"):
        check(f"no builder/orchestrator token '{token}'", token not in source)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_success(tmp)
        test_evidence_copied(tmp)
        test_evidence_not_copied(tmp)
        test_not_accepted(tmp)
        test_missing_report(tmp)
        test_invalid_json(tmp)
        test_missing_keys(tmp)
        test_missing_run_manifest(tmp)
        test_missing_source_files(tmp)
        test_url_rejected(tmp)
        test_output_exists_and_overwrite(tmp)
        test_deterministic(tmp)
        test_no_source_mutation(tmp)
        test_outputs_under_output_dir(tmp)
        test_markdown_no_clock_random(tmp)
    test_static_token_scan()

    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
