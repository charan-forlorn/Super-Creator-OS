"""test_first_prospect_mini_audit_handoff.py - SCOS Stage 4.14 handoff suite."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COMMERCIAL = _HERE.parent
_ROOT = _HERE.parents[2]

sys.path.insert(0, str(_COMMERCIAL))

from first_prospect_mini_audit_handoff import create_first_prospect_mini_audit_handoff  # noqa: E402
from mini_audit_handoff_models import (  # noqa: E402
    FIRST_PROSPECT_MINI_AUDIT_HANDOFF_SCHEMA_VERSION,
    FirstProspectMiniAuditHandoffError,
    FirstProspectMiniAuditHandoffResult,
)
from first_prospect_follow_up_decision import decide_first_prospect_follow_up  # noqa: E402
from first_prospect_execution_log import record_first_prospect_execution  # noqa: E402
from prospect_models import (  # noqa: E402
    ProspectOutreachAction,
    ProspectProfile,
    ProspectResponseStatus,
)

_PASS, _FAIL = 0, 0
_NOW = "2026-07-03T07:00:00Z"
_COUNTER = [0]
_REQUIRED_FILES = (
    "mini_audit_handoff_manifest.json",
    "mini_audit_summary.md",
    "operator_review_checklist.md",
    "prospect_context.json",
    "handoff_message_draft.md",
    "evidence_index.json",
)


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _make_decision(tmp: Path, *, status="interested", next_action="Prepare a manual mini-audit.",
                   follow_up_due=None, blocker_summary=None, allow_escalation=False) -> Path:
    """Chain real 4.12 record -> 4.13 decide, return the written decision JSON path."""
    _COUNTER[0] += 1
    n = _COUNTER[0]
    log_dir = tmp / f"log{n}"
    prospect = ProspectProfile.of(
        prospect_id="prospect-001", display_name="Synthetic Clinic Alias",
        business_type="clinic", channel="manual_facebook_dm",
        source="manual_local_observation", manual_context="Observed unclear booking path.")
    action = ProspectOutreachAction.of(
        action_id="action-001", action_type="manual_dm",
        message_summary="Sent a short manual note offering a mini-audit.",
        performed_at=_NOW, performed_by="SCOS Operator")
    response = ProspectResponseStatus.of(
        status=status, response_summary="Owner replied with mild interest.",
        next_action=next_action, follow_up_due=follow_up_due, blocker_summary=blocker_summary)
    rec = record_first_prospect_execution(
        output_dir=log_dir, checked_at=_NOW, prospect=prospect,
        outreach_action=action, response_status=response)
    dec_path = tmp / f"decision{n}.json"
    decide_first_prospect_follow_up(
        execution_log_path=rec.execution_log_path, checked_at=_NOW,
        output_path=dec_path, allow_escalation=allow_escalation)
    return dec_path


def _inject(tmp: Path, name: str, src: Path, mutate) -> Path:
    data = json.loads(src.read_text(encoding="utf-8"))
    mutate(data)
    p = tmp / name
    p.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return p


def test_success(tmp: Path):
    print("\n[1-6] successful SEND_MINI_AUDIT handoff package")
    dec = _make_decision(tmp)
    out = tmp / "out1"
    r = create_first_prospect_mini_audit_handoff(decision_path=dec, checked_at=_NOW, output_dir=out)
    check("returns Result accepted", isinstance(r, FirstProspectMiniAuditHandoffResult) and r.accepted is True)
    hd = Path(r.output_dir)
    check("writes all six artifacts", all((hd / f).is_file() for f in _REQUIRED_FILES))
    manifest = json.loads((hd / "mini_audit_handoff_manifest.json").read_text(encoding="utf-8"))
    check("manifest references existing files",
          all(Path(a["path"]).is_file() for a in manifest["artifacts"]))
    ctx = json.loads((hd / "prospect_context.json").read_text(encoding="utf-8"))
    check("prospect_context only safe fields",
          set(ctx.keys()) == {"prospect_id", "business_display_name", "market_category",
                              "response_status", "next_action", "blockers", "metadata"})
    draft = (hd / "handoff_message_draft.md").read_text(encoding="utf-8")
    check("draft includes manual review warning", "MANUAL REVIEW REQUIRED" in draft)
    checklist = (hd / "operator_review_checklist.md").read_text(encoding="utf-8")
    check("checklist has no-PII and manual checks",
          "personal data" in checklist and "manually selected" in checklist)


def test_determinism(tmp: Path):
    print("\n[7-10] determinism, overwrite, containment")
    dec = _make_decision(tmp)
    out = tmp / "det"
    r1 = create_first_prospect_mini_audit_handoff(decision_path=dec, checked_at=_NOW, output_dir=out)
    r2 = create_first_prospect_mini_audit_handoff(decision_path=_make_decision(tmp), checked_at=_NOW,
                                                  output_dir=tmp / "det2")
    check("fixed checked_at deterministic handoff_id", r1.handoff_id == r2.handoff_id)

    before = (Path(r1.output_dir) / "mini_audit_handoff_manifest.json").read_text(encoding="utf-8")
    r3 = create_first_prospect_mini_audit_handoff(decision_path=dec, checked_at=_NOW, output_dir=out, overwrite=True)
    after = (Path(r3.output_dir) / "mini_audit_handoff_manifest.json").read_text(encoding="utf-8")
    check("overwrite=True byte-identical", before == after)

    blocked = create_first_prospect_mini_audit_handoff(decision_path=dec, checked_at=_NOW, output_dir=out)
    check("overwrite=False fails OUTPUT_EXISTS",
          isinstance(blocked, FirstProspectMiniAuditHandoffError) and blocked.error_kind == "OUTPUT_EXISTS")

    check("output stays inside output_dir",
          str(Path(r1.output_dir).resolve()).startswith(str(out.resolve())))


def test_argument_errors(tmp: Path):
    print("\n[11-15] argument + decision errors")
    dec = _make_decision(tmp)
    r = create_first_prospect_mini_audit_handoff(decision_path="https://x.test/d.json", checked_at=_NOW,
                                                 output_dir=tmp / "u1")
    check("URL decision_path rejected",
          isinstance(r, FirstProspectMiniAuditHandoffError) and r.error_kind == "INVALID_ARGUMENTS")
    r = create_first_prospect_mini_audit_handoff(decision_path=dec, checked_at=_NOW,
                                                 output_dir="https://x.test/out")
    check("URL output_dir rejected",
          isinstance(r, FirstProspectMiniAuditHandoffError) and r.error_kind == "INVALID_ARGUMENTS")
    r = create_first_prospect_mini_audit_handoff(decision_path=tmp / "ghost.json", checked_at=_NOW,
                                                 output_dir=tmp / "u2")
    check("missing decision INPUT_NOT_FOUND",
          isinstance(r, FirstProspectMiniAuditHandoffError) and r.error_kind == "INPUT_NOT_FOUND")
    bad = tmp / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    r = create_first_prospect_mini_audit_handoff(decision_path=bad, checked_at=_NOW, output_dir=tmp / "u3")
    check("invalid JSON INVALID_DECISION",
          isinstance(r, FirstProspectMiniAuditHandoffError) and r.error_kind == "INVALID_DECISION")
    short = tmp / "short.json"
    short.write_text(json.dumps({"schema_version": 1}) + "\n", encoding="utf-8")
    r = create_first_prospect_mini_audit_handoff(decision_path=short, checked_at=_NOW, output_dir=tmp / "u4")
    check("missing keys INVALID_DECISION",
          isinstance(r, FirstProspectMiniAuditHandoffError) and r.error_kind == "INVALID_DECISION")


def test_handoff_allowed(tmp: Path):
    print("\n[16-21] handoff-allowed gating")
    base = _make_decision(tmp)

    def _reject(data):
        data["accepted"] = False
    p = _inject(tmp, "notacc.json", base, _reject)
    r = create_first_prospect_mini_audit_handoff(decision_path=p, checked_at=_NOW, output_dir=tmp / "g0")
    check("accepted False -> DECISION_NOT_ACCEPTED",
          isinstance(r, FirstProspectMiniAuditHandoffError) and r.error_kind == "DECISION_NOT_ACCEPTED")

    for act in ("FOLLOW_UP", "WAIT", "CLOSE_NO_GO", "BLOCKED"):
        def _set(data, a=act):
            data["action"]["action"] = a
        p = _inject(tmp, f"act_{act}.json", base, _set)
        r = create_first_prospect_mini_audit_handoff(decision_path=p, checked_at=_NOW, output_dir=tmp / f"g_{act}")
        check(f"{act} -> HANDOFF_NOT_ALLOWED",
              isinstance(r, FirstProspectMiniAuditHandoffError) and r.error_kind == "HANDOFF_NOT_ALLOWED")

    esc = _make_decision(tmp, allow_escalation=True)
    r = create_first_prospect_mini_audit_handoff(decision_path=esc, checked_at=_NOW, output_dir=tmp / "g_esc0")
    check("ESCALATE without opt-in -> HANDOFF_NOT_ALLOWED",
          isinstance(r, FirstProspectMiniAuditHandoffError) and r.error_kind == "HANDOFF_NOT_ALLOWED")
    r = create_first_prospect_mini_audit_handoff(decision_path=esc, checked_at=_NOW, output_dir=tmp / "g_esc1",
                                                 allow_escalation_handoff=True)
    check("ESCALATE with opt-in -> Result", isinstance(r, FirstProspectMiniAuditHandoffResult) and r.accepted)


def test_execution_log_reference(tmp: Path):
    print("\n[22-25] execution log reference + no mutation")
    base = _make_decision(tmp)

    def _reroute(data):
        data["source_execution_log_path"] = str(tmp / "missing_log.json")
    p = _inject(tmp, "missing_log_ref.json", base, _reroute)
    r = create_first_prospect_mini_audit_handoff(decision_path=p, checked_at=_NOW, output_dir=tmp / "e1")
    check("missing execution log -> blocker + accepted False",
          isinstance(r, FirstProspectMiniAuditHandoffResult) and r.accepted is False and len(r.blockers) >= 1)

    bad_log = tmp / "bad_log.json"
    bad_log.write_text("{not json", encoding="utf-8")

    def _badlog(data):
        data["source_execution_log_path"] = str(bad_log)
    p = _inject(tmp, "bad_log_ref.json", base, _badlog)
    r = create_first_prospect_mini_audit_handoff(decision_path=p, checked_at=_NOW, output_dir=tmp / "e2")
    check("invalid execution log JSON -> INVALID_EXECUTION_LOG",
          isinstance(r, FirstProspectMiniAuditHandoffError) and r.error_kind == "INVALID_EXECUTION_LOG")

    dec = _make_decision(tmp)
    dec_before = dec.read_bytes()
    exec_log = Path(json.loads(dec.read_text(encoding="utf-8"))["source_execution_log_path"])
    log_before = exec_log.read_bytes()
    create_first_prospect_mini_audit_handoff(decision_path=dec, checked_at=_NOW, output_dir=tmp / "e3")
    check("decision artifact not mutated", dec_before == dec.read_bytes())
    check("execution log not mutated", log_before == exec_log.read_bytes())


def test_sensitive_and_manual_only(tmp: Path):
    print("\n[26-30] sensitive metadata + manual-only")
    base = _make_decision(tmp)
    for key in ("phone", "email", "address"):
        def _pii(data, k=key):
            data.setdefault("metadata", {})[k] = "synthetic forbidden value"
        p = _inject(tmp, f"pii_{key}.json", base, _pii)
        r = create_first_prospect_mini_audit_handoff(decision_path=p, checked_at=_NOW, output_dir=tmp / f"s_{key}")
        check(f"sensitive {key} rejected",
              isinstance(r, FirstProspectMiniAuditHandoffError) and r.error_kind == "SENSITIVE_METADATA")

    def _alias(data):
        data.setdefault("metadata", {})["display_alias"] = "Clinic A"
    p = _inject(tmp, "alias.json", base, _alias)
    r = create_first_prospect_mini_audit_handoff(decision_path=p, checked_at=_NOW, output_dir=tmp / "s_alias")
    check("business display alias allowed", isinstance(r, FirstProspectMiniAuditHandoffResult))

    def _auto(data):
        data.setdefault("metadata", {})["auto_send"] = True
    p = _inject(tmp, "auto.json", base, _auto)
    r = create_first_prospect_mini_audit_handoff(decision_path=p, checked_at=_NOW, output_dir=tmp / "s_auto")
    check("manual-only violation rejected",
          isinstance(r, FirstProspectMiniAuditHandoffError) and r.error_kind == "MANUAL_ONLY_VIOLATION")


def test_serialization(tmp: Path):
    print("\n[31-32] serialization determinism")
    r = create_first_prospect_mini_audit_handoff(decision_path=_make_decision(tmp), checked_at=_NOW,
                                                 output_dir=tmp / "ser")
    check("schema version 1", r.schema_version == FIRST_PROSPECT_MINI_AUDIT_HANDOFF_SCHEMA_VERSION == 1)
    check("result.to_dict deterministic",
          json.dumps(r.to_dict(), sort_keys=True) == json.dumps(r.to_dict(), sort_keys=True))
    e1 = create_first_prospect_mini_audit_handoff(decision_path=tmp / "ghost.json", checked_at=_NOW,
                                                  output_dir=tmp / "ser2")
    e2 = create_first_prospect_mini_audit_handoff(decision_path=tmp / "ghost.json", checked_at=_NOW,
                                                  output_dir=tmp / "ser3")
    check("error.to_dict deterministic",
          json.dumps(e1.to_dict(), sort_keys=True) == json.dumps(e2.to_dict(), sort_keys=True))


def test_static_boundaries():
    print("\n[33-35] static boundary scans (executable source only)")
    source = (_COMMERCIAL / "first_prospect_mini_audit_handoff.py").read_text(encoding="utf-8")
    source += (_COMMERCIAL / "mini_audit_handoff_models.py").read_text(encoding="utf-8")
    for token in ("requests", "httpx", "urllib.request", "boto3", "socket",
                  "http.client", "openai", "anthropic", "stripe", "paypal",
                  "selenium", "playwright", "smtp", "imaplib", "smtplib"):
        check(f"no network/service token '{token}'", token not in source)
    for token in ("KnowledgeIndex", "KnowledgeQueryEngine", "KnowledgeExplainEngine",
                  "KnowledgeInsightEngine", "query_engine", "explain_engine", "insight_engine"):
        check(f"no lower knowledge token '{token}'", token not in source)
    for token in ("send_email", "send_message", "auto_dm", "scrape", "scraper", "CRM"):
        check(f"no auto-message/scrape/CRM token '{token}'", token not in source)
    for token in ("pay" + "ment", "auth"):
        check(f"no billing/permission-word token '{token}'", token not in source)


def test_existing_suites():
    print("\n[36-49] existing lower-stage + knowledge suites still pass")
    suites = [
        _HERE / "test_first_prospect_follow_up_decision.py",
        _HERE / "test_first_prospect_execution_log.py",
        _HERE / "test_first_outreach_launch_kit.py",
        _HERE / "test_operator_practice_lab.py",
        _HERE / "test_launch_certification_pack.py",
        _HERE / "test_first_paid_customer_dry_run.py",
        _HERE / "test_monetization_readiness.py",
        _HERE / "test_customer_kit.py",
        _HERE / "test_acceptance_gate.py",
        _HERE / "test_commercial_run_orchestrator.py",
        _HERE / "test_cli.py",
        _HERE / "test_delivery_package.py",
        _HERE / "test_report_builder.py",
        _ROOT / "scos" / "knowledge" / "tests" / "test_knowledge_service.py",
    ]
    for suite in suites:
        proc = subprocess.run([sys.executable, str(suite)], capture_output=True, text=True)
        check(f"{suite.name} exits 0", proc.returncode == 0)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_success(tmp)
        test_determinism(tmp)
        test_argument_errors(tmp)
        test_handoff_allowed(tmp)
        test_execution_log_reference(tmp)
        test_sensitive_and_manual_only(tmp)
        test_serialization(tmp)
    test_static_boundaries()
    test_existing_suites()
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
