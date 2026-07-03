"""test_first_prospect_mini_audit_delivery_log.py - SCOS Stage 4.15 delivery-log suite."""

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

from first_prospect_mini_audit_delivery_log import (  # noqa: E402
    record_first_prospect_mini_audit_delivery,
)
from mini_audit_delivery_models import (  # noqa: E402
    FIRST_PROSPECT_MINI_AUDIT_DELIVERY_LOG_SCHEMA_VERSION,
    FirstProspectMiniAuditDeliveryLogError,
    FirstProspectMiniAuditDeliveryLogResult,
)
from first_prospect_mini_audit_handoff import create_first_prospect_mini_audit_handoff  # noqa: E402
from first_prospect_follow_up_decision import decide_first_prospect_follow_up  # noqa: E402
from first_prospect_execution_log import record_first_prospect_execution  # noqa: E402
from prospect_models import (  # noqa: E402
    ProspectOutreachAction,
    ProspectProfile,
    ProspectResponseStatus,
)

_PASS, _FAIL = 0, 0
_NOW = "2026-07-04T07:00:00Z"
_COUNTER = [0]
_OUTPUT_NAME = "first_prospect_mini_audit_delivery_log.json"
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


def _make_handoff(tmp: Path) -> Path:
    """Chain real 4.12 -> 4.13 -> 4.14 and return the handoff manifest path."""
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
        status="interested", response_summary="Owner replied with mild interest.",
        next_action="Prepare a manual mini-audit.")
    rec = record_first_prospect_execution(
        output_dir=log_dir, checked_at=_NOW, prospect=prospect,
        outreach_action=action, response_status=response)
    dec_path = tmp / f"decision{n}.json"
    decide_first_prospect_follow_up(
        execution_log_path=rec.execution_log_path, checked_at=_NOW, output_path=dec_path)
    out = tmp / f"handoff{n}"
    r = create_first_prospect_mini_audit_handoff(decision_path=dec_path, checked_at=_NOW, output_dir=out)
    return Path(r.manifest_path)


def test_decision_table(tmp: Path):
    print("\n[1-12] delivery-status decision table")
    m = _make_handoff(tmp)

    r = record_first_prospect_mini_audit_delivery(handoff_manifest_path=m, checked_at=_NOW)
    check("not_reviewed -> REVIEW_HANDOFF",
          isinstance(r, FirstProspectMiniAuditDeliveryLogResult) and r.next_action.action == "REVIEW_HANDOFF")

    r = record_first_prospect_mini_audit_delivery(
        handoff_manifest_path=m, checked_at=_NOW,
        operator_review_status="approved_for_manual_send", manual_send_status="not_sent")
    check("approved + not_sent -> SEND_MANUALLY", r.next_action.action == "SEND_MANUALLY")

    r = record_first_prospect_mini_audit_delivery(
        handoff_manifest_path=m, checked_at=_NOW,
        operator_review_status="approved_for_manual_send", manual_send_status="sent_manually",
        sent_at=_NOW, prospect_response_status="no_response_yet")
    check("sent + no_response + no due -> WAIT", r.next_action.action == "WAIT")

    r = record_first_prospect_mini_audit_delivery(
        handoff_manifest_path=m, checked_at=_NOW,
        operator_review_status="approved_for_manual_send", manual_send_status="sent_manually",
        sent_at=_NOW, prospect_response_status="no_response_yet", follow_up_due_at="2026-07-10T07:00:00Z")
    check("sent + no_response + due -> FOLLOW_UP", r.next_action.action == "FOLLOW_UP")

    common = dict(handoff_manifest_path=m, checked_at=_NOW,
                  operator_review_status="approved_for_manual_send", manual_send_status="sent_manually",
                  sent_at=_NOW, response_received_at=_NOW)
    r = record_first_prospect_mini_audit_delivery(prospect_response_status="interested",
                                                  allow_escalation=False, **common)
    check("interested + no escalation -> FOLLOW_UP", r.next_action.action == "FOLLOW_UP")

    r = record_first_prospect_mini_audit_delivery(prospect_response_status="interested",
                                                  allow_escalation=True, **common)
    check("interested + escalation -> ESCALATE",
          r.next_action.action == "ESCALATE_TO_FIRST_CUSTOMER_FLOW")

    r = record_first_prospect_mini_audit_delivery(prospect_response_status="requested_more_info", **common)
    check("requested_more_info -> FOLLOW_UP", r.next_action.action == "FOLLOW_UP")

    r = record_first_prospect_mini_audit_delivery(prospect_response_status="requested_call", **common)
    check("requested_call -> SCHEDULE_CALL", r.next_action.action == "SCHEDULE_CALL")

    r = record_first_prospect_mini_audit_delivery(prospect_response_status="deferred",
                                                  follow_up_due_at="2026-07-10T07:00:00Z", **common)
    check("deferred + due -> FOLLOW_UP", r.next_action.action == "FOLLOW_UP")

    r = record_first_prospect_mini_audit_delivery(prospect_response_status="not_interested", **common)
    check("not_interested -> CLOSE_NO_GO", r.next_action.action == "CLOSE_NO_GO")

    r = record_first_prospect_mini_audit_delivery(
        handoff_manifest_path=m, checked_at=_NOW, manual_send_status="blocked")
    check("blocked send -> BLOCKED + accepted False",
          r.next_action.action == "BLOCKED" and r.accepted is False)

    r = record_first_prospect_mini_audit_delivery(
        handoff_manifest_path=m, checked_at=_NOW,
        operator_review_status="approved_for_manual_send", manual_send_status="sent_manually",
        sent_at=_NOW, prospect_response_status="blocked", response_received_at=_NOW)
    check("blocked response -> BLOCKED", r.next_action.action == "BLOCKED")


def test_manifest_errors(tmp: Path):
    print("\n[13-15] manifest load/contract errors")
    r = record_first_prospect_mini_audit_delivery(
        handoff_manifest_path=tmp / "ghost.json", checked_at=_NOW)
    check("missing manifest -> INPUT_NOT_FOUND",
          isinstance(r, FirstProspectMiniAuditDeliveryLogError) and r.error_kind == "INPUT_NOT_FOUND")

    bad = tmp / "bad_manifest.json"
    bad.write_text("{not json", encoding="utf-8")
    r = record_first_prospect_mini_audit_delivery(handoff_manifest_path=bad, checked_at=_NOW)
    check("invalid JSON -> INVALID_HANDOFF_MANIFEST",
          isinstance(r, FirstProspectMiniAuditDeliveryLogError) and r.error_kind == "INVALID_HANDOFF_MANIFEST")

    short = tmp / "short_manifest.json"
    short.write_text(json.dumps({"schema_version": 1}) + "\n", encoding="utf-8")
    r = record_first_prospect_mini_audit_delivery(handoff_manifest_path=short, checked_at=_NOW)
    check("missing keys -> INVALID_HANDOFF_MANIFEST",
          isinstance(r, FirstProspectMiniAuditDeliveryLogError) and r.error_kind == "INVALID_HANDOFF_MANIFEST")


def test_missing_artifacts(tmp: Path):
    print("\n[16-20] missing handoff artifact detection")
    for name in ("mini_audit_summary.md", "operator_review_checklist.md", "prospect_context.json",
                 "handoff_message_draft.md", "evidence_index.json"):
        m = _make_handoff(tmp)
        (m.parent / name).unlink()
        r = record_first_prospect_mini_audit_delivery(handoff_manifest_path=m, checked_at=_NOW)
        check(f"missing {name} -> INVALID_HANDOFF_PACKAGE",
              isinstance(r, FirstProspectMiniAuditDeliveryLogError) and r.error_kind == "INVALID_HANDOFF_PACKAGE")


def test_path_and_output(tmp: Path):
    print("\n[21-24] URL rejection + output writing")
    m = _make_handoff(tmp)
    r = record_first_prospect_mini_audit_delivery(
        handoff_manifest_path="https://x.test/manifest.json", checked_at=_NOW)
    check("URL manifest path rejected",
          isinstance(r, FirstProspectMiniAuditDeliveryLogError) and r.error_kind == "INVALID_ARGUMENTS")

    r = record_first_prospect_mini_audit_delivery(
        handoff_manifest_path=m, checked_at=_NOW, output_path="https://x.test/out")
    check("URL output path rejected",
          isinstance(r, FirstProspectMiniAuditDeliveryLogError) and r.error_kind == "INVALID_ARGUMENTS")

    r = record_first_prospect_mini_audit_delivery(handoff_manifest_path=m, checked_at=_NOW)
    check("output_path None writes nothing", r.output_path is None)

    out_dir = tmp / "delivery_out"
    r = record_first_prospect_mini_audit_delivery(
        handoff_manifest_path=m, checked_at=_NOW, output_path=out_dir)
    check("output_path provided writes delivery log",
          r.output_path is not None and (out_dir / _OUTPUT_NAME).is_file())


def test_determinism(tmp: Path):
    print("\n[25-26] determinism")
    m = _make_handoff(tmp)
    r1 = record_first_prospect_mini_audit_delivery(handoff_manifest_path=m, checked_at=_NOW)
    r2 = record_first_prospect_mini_audit_delivery(handoff_manifest_path=m, checked_at=_NOW)
    check("fixed checked_at deterministic delivery_log_id", r1.delivery_log_id == r2.delivery_log_id)

    out_dir = tmp / "det_out"
    record_first_prospect_mini_audit_delivery(handoff_manifest_path=m, checked_at=_NOW, output_path=out_dir)
    first = (out_dir / _OUTPUT_NAME).read_text(encoding="utf-8")
    record_first_prospect_mini_audit_delivery(handoff_manifest_path=m, checked_at=_NOW, output_path=out_dir)
    second = (out_dir / _OUTPUT_NAME).read_text(encoding="utf-8")
    check("repeated run byte-identical output", first == second)


def test_no_mutation(tmp: Path):
    print("\n[27-28] source handoff package is not mutated")
    m = _make_handoff(tmp)
    before = {f: (m.parent / f).read_bytes() for f in _REQUIRED_FILES}
    record_first_prospect_mini_audit_delivery(
        handoff_manifest_path=m, checked_at=_NOW, output_path=tmp / "nm_out")
    check("handoff manifest not mutated",
          before["mini_audit_handoff_manifest.json"] == m.read_bytes())
    check("handoff package files not mutated",
          all(before[f] == (m.parent / f).read_bytes() for f in _REQUIRED_FILES))


def test_sensitive_and_manual_only(tmp: Path):
    print("\n[29-34] sensitive metadata + manual-only")
    m = _make_handoff(tmp)
    for key in ("phone", "email", "address"):
        r = record_first_prospect_mini_audit_delivery(
            handoff_manifest_path=m, checked_at=_NOW, metadata={key: "synthetic forbidden value"})
        check(f"supplied metadata {key} rejected",
              isinstance(r, FirstProspectMiniAuditDeliveryLogError) and r.error_kind == "SENSITIVE_METADATA")

    r = record_first_prospect_mini_audit_delivery(
        handoff_manifest_path=m, checked_at=_NOW, metadata={"display_alias": "Clinic A"})
    check("business display alias allowed", isinstance(r, FirstProspectMiniAuditDeliveryLogResult))

    for key in ("line_id", "contact_handle"):
        r = record_first_prospect_mini_audit_delivery(
            handoff_manifest_path=m, checked_at=_NOW, metadata={key: "synthetic forbidden value"})
        check(f"supplied metadata {key} rejected",
              isinstance(r, FirstProspectMiniAuditDeliveryLogError) and r.error_kind == "SENSITIVE_METADATA")

    r = record_first_prospect_mini_audit_delivery(
        handoff_manifest_path=m, checked_at=_NOW, metadata={"auto_send": True})
    check("manual-only violation rejected",
          isinstance(r, FirstProspectMiniAuditDeliveryLogError) and r.error_kind == "MANUAL_ONLY_VIOLATION")


def test_evidence_argument_rules(tmp: Path):
    print("\n[35-37] enum + evidence consistency rules")
    m = _make_handoff(tmp)
    r = record_first_prospect_mini_audit_delivery(
        handoff_manifest_path=m, checked_at=_NOW, operator_review_status="bogus")
    check("invalid enum -> INVALID_DELIVERY_EVIDENCE",
          isinstance(r, FirstProspectMiniAuditDeliveryLogError) and r.error_kind == "INVALID_DELIVERY_EVIDENCE")

    r = record_first_prospect_mini_audit_delivery(
        handoff_manifest_path=m, checked_at=_NOW, manual_send_status="not_sent", sent_at=_NOW)
    check("sent_at with not_sent -> INVALID_ARGUMENTS",
          isinstance(r, FirstProspectMiniAuditDeliveryLogError) and r.error_kind == "INVALID_ARGUMENTS")

    r = record_first_prospect_mini_audit_delivery(
        handoff_manifest_path=m, checked_at=_NOW,
        prospect_response_status="no_response_yet", response_received_at=_NOW)
    check("response_received_at with no_response_yet -> INVALID_ARGUMENTS",
          isinstance(r, FirstProspectMiniAuditDeliveryLogError) and r.error_kind == "INVALID_ARGUMENTS")


def test_serialization(tmp: Path):
    print("\n[38-39] serialization determinism")
    m = _make_handoff(tmp)
    r = record_first_prospect_mini_audit_delivery(handoff_manifest_path=m, checked_at=_NOW)
    check("schema version 1",
          r.schema_version == FIRST_PROSPECT_MINI_AUDIT_DELIVERY_LOG_SCHEMA_VERSION == 1)
    check("result.to_dict deterministic",
          json.dumps(r.to_dict(), sort_keys=True) == json.dumps(r.to_dict(), sort_keys=True))
    e1 = record_first_prospect_mini_audit_delivery(handoff_manifest_path=tmp / "ghost.json", checked_at=_NOW)
    e2 = record_first_prospect_mini_audit_delivery(handoff_manifest_path=tmp / "ghost.json", checked_at=_NOW)
    check("error.to_dict deterministic",
          json.dumps(e1.to_dict(), sort_keys=True) == json.dumps(e2.to_dict(), sort_keys=True))


def test_static_boundaries():
    print("\n[40-42] static boundary scans (executable source only)")
    source = (_COMMERCIAL / "first_prospect_mini_audit_delivery_log.py").read_text(encoding="utf-8")
    source += (_COMMERCIAL / "mini_audit_delivery_models.py").read_text(encoding="utf-8")
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
    print("\n[43-57] existing lower-stage + knowledge suites still pass")
    suites = [
        _HERE / "test_first_prospect_mini_audit_handoff.py",
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
        test_decision_table(tmp)
        test_manifest_errors(tmp)
        test_missing_artifacts(tmp)
        test_path_and_output(tmp)
        test_determinism(tmp)
        test_no_mutation(tmp)
        test_sensitive_and_manual_only(tmp)
        test_evidence_argument_rules(tmp)
        test_serialization(tmp)
    test_static_boundaries()
    test_existing_suites()
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
