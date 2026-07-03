"""test_first_prospect_follow_up_decision.py - SCOS Stage 4.13 decision gate suite."""

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

from first_prospect_follow_up_decision import decide_first_prospect_follow_up  # noqa: E402
from follow_up_models import (  # noqa: E402
    FIRST_PROSPECT_FOLLOW_UP_DECISION_SCHEMA_VERSION,
    FirstProspectFollowUpDecisionError,
    FirstProspectFollowUpDecisionResult,
)
from first_prospect_execution_log import record_first_prospect_execution  # noqa: E402
from prospect_models import (  # noqa: E402
    ProspectOutreachAction,
    ProspectProfile,
    ProspectResponseStatus,
)

_PASS, _FAIL = 0, 0
_NOW = "2026-07-03T07:00:00Z"
_COUNTER = [0]


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _record_log(tmp: Path, **response_overrides) -> Path:
    _COUNTER[0] += 1
    out = tmp / f"log{_COUNTER[0]}"
    prospect = ProspectProfile.of(
        prospect_id="prospect-001",
        display_name="Synthetic Clinic Alias",
        business_type="clinic",
        channel="manual_facebook_dm",
        source="manual_local_observation",
        manual_context="Observed unclear booking path.",
    )
    action = ProspectOutreachAction.of(
        action_id="action-001",
        action_type="manual_dm",
        message_summary="Sent a short manual note offering a mini-audit.",
        performed_at=_NOW,
        performed_by="SCOS Operator",
    )
    resp_fields = dict(
        status="interested",
        response_summary="Owner replied with mild interest.",
        next_action="Prepare a manual mini-audit.",
        follow_up_due=None,
        blocker_summary=None,
    )
    resp_fields.update(response_overrides)
    response = ProspectResponseStatus.of(**resp_fields)
    res = record_first_prospect_execution(
        output_dir=out, checked_at=_NOW, prospect=prospect,
        outreach_action=action, response_status=response)
    return Path(res.execution_log_path)


def _inject(tmp: Path, name: str, src: Path, mutate) -> Path:
    data = json.loads(src.read_text(encoding="utf-8"))
    mutate(data)
    p = tmp / name
    p.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return p


def _action_of(res):
    return res.action.action if isinstance(res, FirstProspectFollowUpDecisionResult) else None


def test_status_mappings(tmp: Path):
    print("\n[1-7] response-status -> action mappings")
    r = decide_first_prospect_follow_up(execution_log_path=_record_log(tmp, status="interested"), checked_at=_NOW)
    check("interested -> SEND_MINI_AUDIT", _action_of(r) == "SEND_MINI_AUDIT" and r.accepted is True)

    r = decide_first_prospect_follow_up(
        execution_log_path=_record_log(tmp, status="mini_audit_requested", next_action="Send the audit."),
        checked_at=_NOW)
    check("mini_audit_requested -> SEND_MINI_AUDIT", _action_of(r) == "SEND_MINI_AUDIT")

    r = decide_first_prospect_follow_up(
        execution_log_path=_record_log(tmp, status="follow_up_needed", next_action="Follow up soon."),
        checked_at=_NOW)
    check("follow_up_needed -> FOLLOW_UP", _action_of(r) == "FOLLOW_UP")

    r = decide_first_prospect_follow_up(
        execution_log_path=_record_log(tmp, status="no_response", next_action="Revisit later.",
                                       follow_up_due="2026-07-10"),
        checked_at=_NOW)
    check("no_response w/ follow-up -> FOLLOW_UP", _action_of(r) == "FOLLOW_UP" and r.action.due_at == "2026-07-10")

    r = decide_first_prospect_follow_up(
        execution_log_path=_record_log(tmp, status="no_response", next_action="Note and move on.",
                                       follow_up_due=None),
        checked_at=_NOW)
    check("no_response w/o follow-up -> WAIT", _action_of(r) == "WAIT")

    r = decide_first_prospect_follow_up(
        execution_log_path=_record_log(tmp, status="not_interested", next_action="Close the thread."),
        checked_at=_NOW)
    check("not_interested -> CLOSE_NO_GO", _action_of(r) == "CLOSE_NO_GO")

    r = decide_first_prospect_follow_up(
        execution_log_path=_record_log(tmp, status="blocked", next_action="Resolve blocker.",
                                       blocker_summary="Owner unavailable."),
        checked_at=_NOW)
    check("blocked -> BLOCKED accepted False", _action_of(r) == "BLOCKED" and r.accepted is False)


def test_blockers_and_escalation(tmp: Path):
    print("\n[8-10] blockers + escalation gating")
    r = decide_first_prospect_follow_up(
        execution_log_path=_record_log(tmp, status="contacted", next_action="Wait for reply.",
                                       blocker_summary="High severity issue found."),
        checked_at=_NOW)
    check("blocker forces BLOCKED accepted False", _action_of(r) == "BLOCKED" and r.accepted is False)
    check("high blocker -> urgent priority", r.action.priority == "urgent")

    log = _record_log(tmp, status="interested")
    r = decide_first_prospect_follow_up(execution_log_path=log, checked_at=_NOW, allow_escalation=False)
    check("allow_escalation False -> SEND_MINI_AUDIT (no ESCALATE)", _action_of(r) == "SEND_MINI_AUDIT")

    r = decide_first_prospect_follow_up(execution_log_path=log, checked_at=_NOW, allow_escalation=True)
    check("allow_escalation True -> ESCALATE", _action_of(r) == "ESCALATE_TO_FIRST_CUSTOMER_FLOW")
    check("escalation requires human review", r.action.requires_human_review is True)


def test_error_cases(tmp: Path):
    print("\n[11-15] hard error cases")
    r = decide_first_prospect_follow_up(execution_log_path=tmp / "ghost.json", checked_at=_NOW)
    check("missing path -> INPUT_NOT_FOUND",
          isinstance(r, FirstProspectFollowUpDecisionError) and r.error_kind == "INPUT_NOT_FOUND")

    bad = tmp / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    r = decide_first_prospect_follow_up(execution_log_path=bad, checked_at=_NOW)
    check("invalid JSON -> INVALID_EXECUTION_LOG",
          isinstance(r, FirstProspectFollowUpDecisionError) and r.error_kind == "INVALID_EXECUTION_LOG")

    short = tmp / "short.json"
    short.write_text(json.dumps({"schema_version": 1}) + "\n", encoding="utf-8")
    r = decide_first_prospect_follow_up(execution_log_path=short, checked_at=_NOW)
    check("missing keys -> INVALID_EXECUTION_LOG",
          isinstance(r, FirstProspectFollowUpDecisionError) and r.error_kind == "INVALID_EXECUTION_LOG")

    r = decide_first_prospect_follow_up(execution_log_path="https://example.test/log.json", checked_at=_NOW)
    check("URL execution_log_path rejected",
          isinstance(r, FirstProspectFollowUpDecisionError) and r.error_kind == "INVALID_ARGUMENTS")

    r = decide_first_prospect_follow_up(execution_log_path=_record_log(tmp), checked_at=_NOW,
                                        output_path="https://example.test/out.json")
    check("URL output_path rejected",
          isinstance(r, FirstProspectFollowUpDecisionError) and r.error_kind == "INVALID_ARGUMENTS")


def test_output_and_determinism(tmp: Path):
    print("\n[16-20] output + determinism + no source mutation")
    log = _record_log(tmp, status="interested")

    r = decide_first_prospect_follow_up(execution_log_path=log, checked_at=_NOW, output_path=None)
    check("output_path None writes nothing", r.output_path is None)

    out1 = tmp / "dec1.json"
    r1 = decide_first_prospect_follow_up(execution_log_path=log, checked_at=_NOW, output_path=out1)
    check("output_path provided writes file", out1.is_file() and r1.output_path == str(out1))

    out_dir = tmp / "decdir"
    rd = decide_first_prospect_follow_up(execution_log_path=log, checked_at=_NOW, output_path=out_dir)
    check("dir output writes named decision file",
          (out_dir / "first_prospect_follow_up_decision.json").is_file())

    ra = decide_first_prospect_follow_up(execution_log_path=log, checked_at=_NOW)
    rb = decide_first_prospect_follow_up(execution_log_path=log, checked_at=_NOW)
    check("deterministic decision_id", ra.decision_id == rb.decision_id)

    out2 = tmp / "dec2.json"
    decide_first_prospect_follow_up(execution_log_path=log, checked_at=_NOW, output_path=out2)
    first_bytes = out2.read_text(encoding="utf-8")
    decide_first_prospect_follow_up(execution_log_path=log, checked_at=_NOW, output_path=out2)
    check("byte-identical output for fixed inputs",
          first_bytes == out2.read_text(encoding="utf-8"))

    before = log.read_bytes()
    decide_first_prospect_follow_up(execution_log_path=log, checked_at=_NOW)
    check("source execution log not mutated", before == log.read_bytes())


def test_sensitive_and_manual_only(tmp: Path):
    print("\n[21-25] sensitive metadata + manual-only")
    base = _record_log(tmp, status="interested")

    for key in ("phone", "email", "address"):
        def _mut(data, k=key):
            data["prospect"]["metadata"][k] = "synthetic forbidden value"
        p = _inject(tmp, f"pii_{key}.json", base, _mut)
        r = decide_first_prospect_follow_up(execution_log_path=p, checked_at=_NOW)
        check(f"sensitive {key} rejected",
              isinstance(r, FirstProspectFollowUpDecisionError) and r.error_kind == "SENSITIVE_METADATA")

    def _alias(data):
        data["prospect"]["metadata"]["display_alias"] = "Clinic A"
    p = _inject(tmp, "alias.json", base, _alias)
    r = decide_first_prospect_follow_up(execution_log_path=p, checked_at=_NOW)
    check("business display alias allowed", isinstance(r, FirstProspectFollowUpDecisionResult) and r.accepted)

    def _auto(data):
        data["outreach_action"]["auto_send"] = True
    p = _inject(tmp, "auto.json", base, _auto)
    r = decide_first_prospect_follow_up(execution_log_path=p, checked_at=_NOW)
    check("manual-only violation -> BLOCKED accepted False",
          isinstance(r, FirstProspectFollowUpDecisionResult)
          and r.action.action == "BLOCKED" and r.accepted is False)


def test_serialization(tmp: Path):
    print("\n[26-27] serialization determinism")
    r = decide_first_prospect_follow_up(execution_log_path=_record_log(tmp), checked_at=_NOW)
    check("schema version 1", r.schema_version == FIRST_PROSPECT_FOLLOW_UP_DECISION_SCHEMA_VERSION == 1)
    check("result.to_dict deterministic",
          json.dumps(r.to_dict(), sort_keys=True) == json.dumps(r.to_dict(), sort_keys=True))
    e1 = decide_first_prospect_follow_up(execution_log_path=tmp / "ghost.json", checked_at=_NOW)
    e2 = decide_first_prospect_follow_up(execution_log_path=tmp / "ghost.json", checked_at=_NOW)
    check("error.to_dict deterministic",
          json.dumps(e1.to_dict(), sort_keys=True) == json.dumps(e2.to_dict(), sort_keys=True))


def test_static_boundaries():
    print("\n[28-30] static boundary scans (executable source only)")
    source = (_COMMERCIAL / "first_prospect_follow_up_decision.py").read_text(encoding="utf-8")
    source += (_COMMERCIAL / "follow_up_models.py").read_text(encoding="utf-8")
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
        check(f"no payment/permission-word token '{token}'", token not in source)


def test_existing_suites():
    print("\n[31-43] existing lower-stage + knowledge suites still pass")
    suites = [
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
        _HERE / "test_report_builder.py",
        _HERE / "test_delivery_package.py",
        _ROOT / "scos" / "knowledge" / "tests" / "test_knowledge_service.py",
    ]
    for suite in suites:
        proc = subprocess.run([sys.executable, str(suite)], capture_output=True, text=True)
        check(f"{suite.name} exits 0", proc.returncode == 0)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_status_mappings(tmp)
        test_blockers_and_escalation(tmp)
        test_error_cases(tmp)
        test_output_and_determinism(tmp)
        test_sensitive_and_manual_only(tmp)
        test_serialization(tmp)
    test_static_boundaries()
    test_existing_suites()
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
