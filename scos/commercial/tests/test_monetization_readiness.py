"""test_monetization_readiness.py - SCOS Stage 4.7 monetization readiness suite.

Plain-assert script (project convention, not pytest). Seeds a real Stage 3.9
knowledge index/service, produces a real Stage 4.4 commercial run, certifies it
through the Stage 4.5 acceptance gate to a genuine accepted acceptance report,
generates a Stage 4.6 first customer operating kit, then reviews monetization
readiness against those real artifacts. Verifies deterministic outputs, scoring
(max 70), GO / CONDITIONAL_GO / NO_GO rules, gap blocking, error kinds, source
immutability, and local-only / boundary restrictions.

A default Stage 4.6 kit has no risk checklist, so the happy-path GO case adds an
explicit ``risk_checklist.md`` to the kit; a kit left without one legitimately
produces NO_GO via a blocking risk gap (expected behavior, not a test failure).

Run: python scos/commercial/tests/test_monetization_readiness.py
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
from run_models import CommercialRunResult  # noqa: E402
from acceptance_gate import run_commercial_acceptance_gate  # noqa: E402
from acceptance_models import CommercialAcceptanceReport  # noqa: E402
from customer_kit import generate_first_customer_kit  # noqa: E402
from customer_kit_models import CustomerKitResult  # noqa: E402
from monetization_readiness import review_monetization_readiness  # noqa: E402
from monetization_models import (  # noqa: E402
    MONETIZATION_READINESS_SCHEMA_VERSION,
    MonetizationReadinessError,
    MonetizationReadinessResult,
)

_PASS, _FAIL = 0, 0
_RUN_NOW = "2026-07-03T00:00:00Z"
_GATE_NOW = "2026-07-03T01:00:00Z"
_KIT_NOW = "2026-07-03T02:00:00Z"
_REVIEW_NOW = "2026-07-03T03:00:00Z"


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


# --------------------------------------------------------------------------- #
# Real fixture: knowledge -> run -> accepted acceptance report -> kit
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


def _kit(tmp: Path, name: str, add_risk: bool = True):
    """Build real accepted-report + operating-kit artifacts; return (report_path, kit_dir)."""

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
    report_path = Path(tmp / f"cert_{name}" / report.certification_id.replace(":", "_")
                       / "commercial_acceptance_report.json")
    kit = generate_first_customer_kit(
        acceptance_report_path=report_path,
        output_dir=tmp / f"kit_{name}",
        customer_id="cust_1",
        created_at=_KIT_NOW,
    )
    assert isinstance(kit, CustomerKitResult), f"fixture kit failed for {name}"
    kit_dir = Path(kit.output_dir)
    if add_risk:
        (kit_dir / "risk_checklist.md").write_text(
            "# Risk Checklist\n- [ ] Delivery risk reviewed\n", encoding="utf-8", newline="\n"
        )
    return report_path, kit_dir


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _blocking_categories(res: MonetizationReadinessResult):
    return {g.category for g in res.gaps if g.blocking}


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_success_go(tmp: Path):
    print("\n[1] successful readiness review returns ready=True / GO")
    rp, kit_dir = _kit(tmp, "go1", add_risk=True)
    res = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW
    )
    check("returns Result", isinstance(res, MonetizationReadinessResult))
    check("ok True", res.ok is True)
    check("ready True", res.ready is True)
    check("go_no_go GO", res.go_no_go == "GO")
    check("readiness_level ready", res.readiness_level == "ready")
    check("schema_version 1", res.schema_version == MONETIZATION_READINESS_SCHEMA_VERSION == 1)
    check("score 70", res.score == 70)
    check("max_score 70", res.max_score == 70)
    check("no blocking gaps", not any(g.blocking for g in res.gaps))
    check("readiness_id derived", res.readiness_id.startswith("monetization-readiness-"))


def test_output_written(tmp: Path):
    print("\n[2] output report written only when output_path provided")
    rp, kit_dir = _kit(tmp, "out1")
    out = tmp / "out" / "monetization_readiness_report.json"
    res = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir,
        checked_at=_REVIEW_NOW, output_path=out,
    )
    check("returns Result", isinstance(res, MonetizationReadinessResult))
    check("output file written", out.is_file())
    written = json.loads(out.read_text(encoding="utf-8"))
    check("written matches result", written == res.to_dict())


def test_no_output(tmp: Path):
    print("\n[3] no output written when output_path is None")
    rp, kit_dir = _kit(tmp, "noout1")
    before = _snapshot(kit_dir)
    res = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW
    )
    check("returns Result", isinstance(res, MonetizationReadinessResult))
    after = _snapshot(kit_dir)
    check("no report file created in kit", "monetization_readiness_report.json"
          not in {Path(p).name for p in after})
    check("kit unchanged", before == after)


def test_missing_acceptance(tmp: Path):
    print("\n[4] missing acceptance report returns INPUT_NOT_FOUND")
    _, kit_dir = _kit(tmp, "ma1")
    res = review_monetization_readiness(
        acceptance_report_path=tmp / "ghost.json", operating_kit_path=kit_dir,
        checked_at=_REVIEW_NOW,
    )
    check("INPUT_NOT_FOUND", isinstance(res, MonetizationReadinessError)
          and res.error_kind == "INPUT_NOT_FOUND")


def test_invalid_acceptance(tmp: Path):
    print("\n[5] invalid acceptance JSON returns INVALID_ACCEPTANCE_REPORT")
    _, kit_dir = _kit(tmp, "ia1")
    bad = tmp / "garbage.json"
    bad.write_text("{not json", encoding="utf-8")
    res = review_monetization_readiness(
        acceptance_report_path=bad, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW
    )
    check("INVALID_ACCEPTANCE_REPORT", isinstance(res, MonetizationReadinessError)
          and res.error_kind == "INVALID_ACCEPTANCE_REPORT")


def test_not_accepted_no_go(tmp: Path):
    print("\n[6] accepted=False produces NO_GO / not_ready")
    rp, kit_dir = _kit(tmp, "na1")
    data = json.loads(rp.read_text(encoding="utf-8"))
    data["ok"] = False
    data["overall_status"] = "FAIL"
    bad = tmp / "na1_fail.json"
    bad.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")
    res = review_monetization_readiness(
        acceptance_report_path=bad, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW
    )
    check("returns Result", isinstance(res, MonetizationReadinessResult))
    check("NO_GO", res.go_no_go == "NO_GO")
    check("not_ready", res.readiness_level == "not_ready")
    check("ready False", res.ready is False)
    check("acceptance blocking gap", "acceptance_readiness" in _blocking_categories(res))


def test_spec_shape_acceptance(tmp: Path):
    print("\n[6b] spec-shape acceptance report is accepted")
    rp, kit_dir = _kit(tmp, "spec1")
    data = json.loads(rp.read_text(encoding="utf-8"))
    spec = {
        "accepted": True,
        "acceptance_id": "acceptance-spec-1",
        "checked_at": "2026-07-03T01:30:00Z",
        "checks": data["checks"],
    }
    spec_path = tmp / "spec_acceptance.json"
    spec_path.write_text(json.dumps(spec, sort_keys=True, indent=2), encoding="utf-8")
    res = review_monetization_readiness(
        acceptance_report_path=spec_path,
        operating_kit_path=kit_dir,
        checked_at=_REVIEW_NOW,
    )
    check("returns Result", isinstance(res, MonetizationReadinessResult))
    check("GO", res.go_no_go == "GO")
    check("spec acceptance id used", res.readiness_id == "monetization-readiness-acceptance-spec-1")
    check("acceptance checked_at adapted",
          res.metadata.to_dict().get("acceptance_checked_at") == "2026-07-03T01:30:00Z")


def test_missing_kit(tmp: Path):
    print("\n[7] missing operating kit returns INPUT_NOT_FOUND")
    rp, _ = _kit(tmp, "mk1")
    res = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=tmp / "ghost_kit",
        checked_at=_REVIEW_NOW,
    )
    check("INPUT_NOT_FOUND", isinstance(res, MonetizationReadinessError)
          and res.error_kind == "INPUT_NOT_FOUND")


def test_missing_offer(tmp: Path):
    print("\n[8-9] missing offer: blocks when required, not when not required")
    rp, kit_dir = _kit(tmp, "off1")
    (kit_dir / "pricing_offer_checklist.md").unlink()
    blocked = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW,
        require_offer=True, require_pricing=False,
    )
    check("offer blocking when required", "offer_readiness" in _blocking_categories(blocked))
    not_blocked = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW,
        require_offer=False, require_pricing=False,
    )
    check("offer not blocking when not required",
          "offer_readiness" not in _blocking_categories(not_blocked))


def test_missing_pricing(tmp: Path):
    print("\n[10] missing pricing creates blocking gap when require_pricing=True")
    rp, kit_dir = _kit(tmp, "pr1")
    (kit_dir / "pricing_offer_checklist.md").unlink()
    res = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW,
        require_offer=False, require_pricing=True,
    )
    check("pricing blocking", "pricing_readiness" in _blocking_categories(res))


def test_missing_workflow(tmp: Path):
    print("\n[11] missing workflow creates blocking gap")
    rp, kit_dir = _kit(tmp, "wf1")
    (kit_dir / "operator_sop.md").unlink()
    res = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW
    )
    check("workflow blocking", "workflow_readiness" in _blocking_categories(res))
    check("NO_GO", res.go_no_go == "NO_GO")


def test_missing_delivery(tmp: Path):
    print("\n[12] missing delivery artifact creates blocking gap")
    rp, kit_dir = _kit(tmp, "dl1")
    # Break the referenced commercial report so delivery is incomplete.
    manifest = json.loads((kit_dir / "customer_kit_manifest.json").read_text(encoding="utf-8"))
    Path(manifest["source_report_path"]).unlink()
    res = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW,
        require_delivery_artifacts=True,
    )
    check("delivery blocking", "delivery_readiness" in _blocking_categories(res))


def test_missing_risk(tmp: Path):
    print("\n[13] missing risk checklist blocks when required -> NO_GO")
    rp, kit_dir = _kit(tmp, "rk1", add_risk=False)
    res = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW,
        require_risk_checklist=True,
    )
    check("risk blocking", "risk_readiness" in _blocking_categories(res))
    check("default kit NO_GO", res.go_no_go == "NO_GO")
    not_req = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW,
        require_risk_checklist=False,
    )
    check("risk not blocking when not required",
          "risk_readiness" not in _blocking_categories(not_req))


def test_manifest_referenced_risk(tmp: Path):
    print("\n[13b] manifest-referenced risk file satisfies risk readiness")
    rp, kit_dir = _kit(tmp, "rkm1", add_risk=False)
    nested = kit_dir / "controls" / "risk_checklist.md"
    nested.parent.mkdir(parents=True, exist_ok=True)
    nested.write_text("# Risk Checklist\n- [ ] Reviewed\n", encoding="utf-8", newline="\n")
    manifest_path = kit_dir / "customer_kit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["generated_files"] = sorted(manifest["generated_files"] + ["controls/risk_checklist.md"])
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
    res = review_monetization_readiness(
        acceptance_report_path=rp,
        operating_kit_path=kit_dir,
        checked_at=_REVIEW_NOW,
        require_risk_checklist=True,
    )
    check("risk not blocking", "risk_readiness" not in _blocking_categories(res))
    check("GO", res.go_no_go == "GO")


def test_missing_handoff(tmp: Path):
    print("\n[14] missing handoff script blocks when required")
    rp, kit_dir = _kit(tmp, "hf1")
    (kit_dir / "delivery_handoff.md").unlink()
    res = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW,
        require_handoff_script=True,
    )
    check("handoff blocking", "handoff_readiness" in _blocking_categories(res))


def test_deterministic(tmp: Path):
    print("\n[15-17] deterministic result / to_dict / error to_dict")
    rp, kit_dir = _kit(tmp, "det1")
    a = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW
    )
    b = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW
    )
    check("result to_dict identical across runs",
          json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True))
    check("result to_dict repeatable",
          json.dumps(a.to_dict(), sort_keys=True) == json.dumps(a.to_dict(), sort_keys=True))
    e1 = review_monetization_readiness(
        acceptance_report_path=tmp / "ghostx.json", operating_kit_path=kit_dir, checked_at=_REVIEW_NOW
    )
    e2 = review_monetization_readiness(
        acceptance_report_path=tmp / "ghostx.json", operating_kit_path=kit_dir, checked_at=_REVIEW_NOW
    )
    check("error to_dict deterministic",
          json.dumps(e1.to_dict(), sort_keys=True) == json.dumps(e2.to_dict(), sort_keys=True))


def test_score_max(tmp: Path):
    print("\n[18] score max_score is 70")
    rp, kit_dir = _kit(tmp, "sc1")
    res = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW
    )
    check("max_score 70", res.max_score == 70)
    check("category max_scores sum to 70",
          sum(c.max_score for c in res.checks) == 70)


def test_go_requires_score_and_no_blocking(tmp: Path):
    print("\n[19] GO requires score>=60 and no blocking gaps")
    rp, kit_dir = _kit(tmp, "go2", add_risk=True)
    res = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW
    )
    check("GO with 70 and no blocking", res.go_no_go == "GO" and res.score >= 60
          and not any(g.blocking for g in res.gaps))


def test_conditional_go(tmp: Path):
    print("\n[20] CONDITIONAL_GO for non-blocking shortfall (score 50-59)")
    rp, kit_dir = _kit(tmp, "cg1", add_risk=True)
    # Drop offer+pricing (same file, 20 pts) but mark them not required -> no
    # blocking gaps, score 50, accepted -> CONDITIONAL_GO.
    (kit_dir / "pricing_offer_checklist.md").unlink()
    res = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW,
        require_offer=False, require_pricing=False,
    )
    check("score 50", res.score == 50)
    check("no blocking gaps", not any(g.blocking for g in res.gaps))
    check("CONDITIONAL_GO", res.go_no_go == "CONDITIONAL_GO")
    check("conditional level", res.readiness_level == "conditional")


def test_no_go_blocking(tmp: Path):
    print("\n[21] NO_GO for a blocking gap even with otherwise high score")
    rp, kit_dir = _kit(tmp, "ng1", add_risk=False)  # missing required risk
    res = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW
    )
    check("has blocking gap", any(g.blocking for g in res.gaps))
    check("NO_GO", res.go_no_go == "NO_GO")


def test_url_rejected(tmp: Path):
    print("\n[22-23] URL input and output paths rejected")
    rp, kit_dir = _kit(tmp, "url1")
    u_in = review_monetization_readiness(
        acceptance_report_path="https://evil.example/r.json", operating_kit_path=kit_dir,
        checked_at=_REVIEW_NOW,
    )
    check("URL acceptance rejected", isinstance(u_in, MonetizationReadinessError)
          and u_in.error_kind == "PATH_CONTAINMENT_FAILED")
    u_kit = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path="http://evil.example/kit",
        checked_at=_REVIEW_NOW,
    )
    check("URL kit rejected", isinstance(u_kit, MonetizationReadinessError)
          and u_kit.error_kind == "PATH_CONTAINMENT_FAILED")
    u_out = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW,
        output_path="https://evil.example/out.json",
    )
    check("URL output rejected", isinstance(u_out, MonetizationReadinessError)
          and u_out.error_kind == "PATH_CONTAINMENT_FAILED")


def test_no_source_mutation(tmp: Path):
    print("\n[24] inspected source artifacts are not mutated")
    rp, kit_dir = _kit(tmp, "mut1")
    before_kit = _snapshot(kit_dir)
    before_report = rp.read_bytes()
    res = review_monetization_readiness(
        acceptance_report_path=rp, operating_kit_path=kit_dir, checked_at=_REVIEW_NOW
    )
    check("review completed", isinstance(res, MonetizationReadinessResult))
    check("kit artifacts byte-identical", before_kit == _snapshot(kit_dir))
    check("acceptance report byte-identical", before_report == rp.read_bytes())


def test_static_token_scan():
    print("\n[25-27] static forbidden-token scan of monetization_readiness.py")
    source = (_COMMERCIAL / "monetization_readiness.py").read_text(encoding="utf-8")
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
                  "import acceptance_gate", "from acceptance_gate",
                  "import customer_kit", "from customer_kit"):
        check(f"no builder/orchestrator token '{token}'", token not in source)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_success_go(tmp)
        test_output_written(tmp)
        test_no_output(tmp)
        test_missing_acceptance(tmp)
        test_invalid_acceptance(tmp)
        test_not_accepted_no_go(tmp)
        test_spec_shape_acceptance(tmp)
        test_missing_kit(tmp)
        test_missing_offer(tmp)
        test_missing_pricing(tmp)
        test_missing_workflow(tmp)
        test_missing_delivery(tmp)
        test_missing_risk(tmp)
        test_manifest_referenced_risk(tmp)
        test_missing_handoff(tmp)
        test_deterministic(tmp)
        test_score_max(tmp)
        test_go_requires_score_and_no_blocking(tmp)
        test_conditional_go(tmp)
        test_no_go_blocking(tmp)
        test_url_rejected(tmp)
        test_no_source_mutation(tmp)
        test_static_token_scan()
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
