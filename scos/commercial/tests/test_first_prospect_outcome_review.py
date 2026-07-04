"""test_first_prospect_outcome_review.py - SCOS Stage 4.16 outcome-review suite."""

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

from first_prospect_outcome_review import review_first_prospect_outcome  # noqa: E402
from outcome_review_models import (  # noqa: E402
    FIRST_PROSPECT_OUTCOME_REVIEW_SCHEMA_VERSION,
    FirstProspectOutcomeReviewError,
    FirstProspectOutcomeReviewResult,
)
from first_prospect_mini_audit_delivery_log import (  # noqa: E402
    record_first_prospect_mini_audit_delivery,
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
_DUE = "2026-07-10T07:00:00Z"
_COUNTER = [0]
_DELIVERY_NAME = "first_prospect_mini_audit_delivery_log.json"
_OUTPUT_NAME = "first_prospect_outcome_review.json"

_CORE_CHECKS = {
    "validate_inputs",
    "load_delivery_log",
    "validate_delivery_log_contract",
    "validate_manual_only",
    "validate_sensitive_metadata",
    "validate_handoff_reference",
    "evaluate_blockers",
    "evaluate_review_status",
    "evaluate_send_status",
    "evaluate_response_status",
    "evaluate_conversion_readiness",
}


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


def _delivery_log(tmp, *, review="approved_for_manual_send", send="sent_manually",
                  response="interested", follow_up_due=None, patch=None):
    """Produce a real Stage 4.15 delivery log JSON file, optionally patched."""
    m = _make_handoff(tmp)
    kwargs = dict(handoff_manifest_path=m, checked_at=_NOW,
                  operator_review_status=review, manual_send_status=send,
                  prospect_response_status=response)
    if send == "sent_manually":
        kwargs["sent_at"] = _NOW
    if response not in ("no_response_yet",):
        kwargs["response_received_at"] = _NOW
    if follow_up_due:
        kwargs["follow_up_due_at"] = follow_up_due
    out_dir = tmp / f"dl{_COUNTER[0]}"
    record_first_prospect_mini_audit_delivery(output_path=out_dir, **kwargs)
    path = out_dir / _DELIVERY_NAME
    if patch is not None:
        data = json.loads(path.read_text(encoding="utf-8"))
        patch(data)
        path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path, m


def test_response_decision_table(tmp: Path):
    print("\n[1-8] response decision table")

    p, _ = _delivery_log(tmp, response="interested")
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW)
    check("interested -> REQUEST_SCOPE_CONFIRMATION",
          isinstance(r, FirstProspectOutcomeReviewResult)
          and r.action.action == "REQUEST_SCOPE_CONFIRMATION" and r.conversion_ready is True)

    def to_ready(data):
        data["evidence"]["prospect_response_status"] = "ready_to_buy"
    p, _ = _delivery_log(tmp, response="interested", patch=to_ready)
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW, allow_conversion_escalation=False)
    check("ready_to_buy + no escalation -> REQUEST_SCOPE_CONFIRMATION",
          r.action.action == "REQUEST_SCOPE_CONFIRMATION" and r.conversion_ready is True)

    p, _ = _delivery_log(tmp, response="interested", patch=to_ready)
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW, allow_conversion_escalation=True)
    check("ready_to_buy + escalation -> ESCALATE_TO_FIRST_CUSTOMER_CONVERSION",
          r.action.action == "ESCALATE_TO_FIRST_CUSTOMER_CONVERSION" and r.conversion_ready is True)

    p, _ = _delivery_log(tmp, response="no_response_yet", follow_up_due=_DUE)
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW)
    check("no_response + follow-up evidence -> FOLLOW_UP_AFTER_MINI_AUDIT",
          r.action.action == "FOLLOW_UP_AFTER_MINI_AUDIT")

    p, _ = _delivery_log(tmp, response="no_response_yet")
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW)
    check("no_response + no follow-up -> WAIT_FOR_RESPONSE",
          r.action.action == "WAIT_FOR_RESPONSE")

    def to_changes(data):
        data["evidence"]["prospect_response_status"] = "requested_changes"
    p, _ = _delivery_log(tmp, response="interested", patch=to_changes)
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW)
    check("requested_changes -> SEND_REVISED_MINI_AUDIT",
          r.action.action == "SEND_REVISED_MINI_AUDIT")

    p, _ = _delivery_log(tmp, response="not_interested")
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW)
    check("not_interested -> CLOSE_NO_GO", r.action.action == "CLOSE_NO_GO")

    p, _ = _delivery_log(tmp, response="blocked", send="sent_manually")
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW)
    check("blocked response -> BLOCKED", r.action.action == "BLOCKED" and r.accepted is False)


def test_blockers_and_status_gates(tmp: Path):
    print("\n[9-11] blocker + review/send gates")

    def inject_blocker(data):
        data["blockers"] = ["synthetic operator blocker"]
    p, _ = _delivery_log(tmp, response="interested", patch=inject_blocker)
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW)
    check("blocker list forces BLOCKED + accepted False",
          r.action.action == "BLOCKED" and r.accepted is False and r.conversion_ready is False)

    p, _ = _delivery_log(tmp, review="not_reviewed", send="not_sent", response="no_response_yet")
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW)
    check("not_reviewed blocks conversion readiness",
          r.action.action == "BLOCKED" and r.conversion_ready is False)

    def to_send_failed(data):
        data["evidence"]["manual_send_status"] = "send_failed"
    p, _ = _delivery_log(tmp, response="interested", patch=to_send_failed)
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW)
    check("send_failed blocks conversion readiness",
          r.action.action == "BLOCKED" and r.conversion_ready is False)


def test_input_errors(tmp: Path):
    print("\n[12-16] input / contract errors")
    r = review_first_prospect_outcome(delivery_log_path=tmp / "ghost.json", checked_at=_NOW)
    check("missing delivery log -> INPUT_NOT_FOUND",
          isinstance(r, FirstProspectOutcomeReviewError) and r.error_kind == "INPUT_NOT_FOUND")

    bad = tmp / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    r = review_first_prospect_outcome(delivery_log_path=bad, checked_at=_NOW)
    check("invalid JSON -> INVALID_DELIVERY_LOG",
          isinstance(r, FirstProspectOutcomeReviewError) and r.error_kind == "INVALID_DELIVERY_LOG")

    short = tmp / "short.json"
    short.write_text(json.dumps({"schema_version": 1}) + "\n", encoding="utf-8")
    r = review_first_prospect_outcome(delivery_log_path=short, checked_at=_NOW)
    check("missing keys -> INVALID_DELIVERY_LOG",
          isinstance(r, FirstProspectOutcomeReviewError) and r.error_kind == "INVALID_DELIVERY_LOG")

    r = review_first_prospect_outcome(delivery_log_path="https://x.test/log.json", checked_at=_NOW)
    check("URL delivery_log_path rejected",
          isinstance(r, FirstProspectOutcomeReviewError) and r.error_kind == "INVALID_ARGUMENTS")

    p, _ = _delivery_log(tmp, response="interested")
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW, output_path="https://x.test/out")
    check("URL output_path rejected",
          isinstance(r, FirstProspectOutcomeReviewError) and r.error_kind == "INVALID_ARGUMENTS")


def test_output_writing(tmp: Path):
    print("\n[17-18, 28] output writing + containment")
    p, _ = _delivery_log(tmp, response="interested")
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW)
    check("output_path None writes nothing", r.output_path is None)

    out_dir = tmp / "review_out"
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW, output_path=out_dir)
    written = out_dir / _OUTPUT_NAME
    check("output_path provided writes outcome review",
          r.output_path is not None and written.is_file())
    check("output path stays local and contained",
          Path(r.output_path).resolve().parent == out_dir.resolve())


def test_no_mutation(tmp: Path):
    print("\n[19-20] source artifacts not mutated")
    p, m = _delivery_log(tmp, response="interested")
    log_before = p.read_bytes()
    manifest_before = m.read_bytes()
    review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW, output_path=tmp / "nm_out")
    check("source delivery log not mutated", log_before == p.read_bytes())
    check("source handoff manifest not mutated", manifest_before == m.read_bytes())


def test_sensitive_and_alias(tmp: Path):
    print("\n[21-22] PII rejection + alias allowance")
    pii_keys = ("phone", "email", "address", "personal_name", "personal_id",
                "national_id", "tax_id", "line_id", "contact_handle")
    for key in pii_keys:
        def inject(data, k=key):
            data["metadata"][k] = "synthetic forbidden value"
        p, _ = _delivery_log(tmp, response="interested", patch=inject)
        r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW)
        check(f"metadata {key} rejected",
              isinstance(r, FirstProspectOutcomeReviewError) and r.error_kind == "SENSITIVE_METADATA")

    def inject_alias(data):
        data["metadata"]["display_alias"] = "Clinic A"
        data["metadata"]["business_type"] = "clinic"
    p, _ = _delivery_log(tmp, response="interested", patch=inject_alias)
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW)
    check("business/display aliases allowed", isinstance(r, FirstProspectOutcomeReviewResult))


def test_determinism(tmp: Path):
    print("\n[23-26] determinism")
    p, _ = _delivery_log(tmp, response="interested")
    r1 = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW)
    r2 = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW)
    check("review_id deterministic", r1.review_id == r2.review_id)

    out_dir = tmp / "det_out"
    review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW, output_path=out_dir)
    first = (out_dir / _OUTPUT_NAME).read_text(encoding="utf-8")
    review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW, output_path=out_dir)
    second = (out_dir / _OUTPUT_NAME).read_text(encoding="utf-8")
    check("fixed checked_at byte-identical output", first == second)
    check("result.to_dict deterministic",
          json.dumps(r1.to_dict(), sort_keys=True) == json.dumps(r2.to_dict(), sort_keys=True))

    e1 = review_first_prospect_outcome(delivery_log_path=tmp / "ghost.json", checked_at=_NOW)
    e2 = review_first_prospect_outcome(delivery_log_path=tmp / "ghost.json", checked_at=_NOW)
    check("error.to_dict deterministic",
          json.dumps(e1.to_dict(), sort_keys=True) == json.dumps(e2.to_dict(), sort_keys=True))


def test_required_checks(tmp: Path):
    print("\n[27] all required checks present")
    p, _ = _delivery_log(tmp, response="interested")
    r = review_first_prospect_outcome(delivery_log_path=p, checked_at=_NOW, output_path=tmp / "rc_out")
    names = {c.check_name for c in r.checks}
    check("core checks present", _CORE_CHECKS.issubset(names))
    check("output checks present",
          {"validate_output_path", "write_outcome_review"}.issubset(names))
    check("schema version 1",
          r.schema_version == FIRST_PROSPECT_OUTCOME_REVIEW_SCHEMA_VERSION == 1)


def test_static_boundaries():
    print("\n[29-31] static boundary scans (executable source only)")
    source = (_COMMERCIAL / "first_prospect_outcome_review.py").read_text(encoding="utf-8")
    source += (_COMMERCIAL / "outcome_review_models.py").read_text(encoding="utf-8")
    for token in ("requests", "httpx", "urllib.request", "boto3", "socket",
                  "http.client", "openai", "anthropic", "stripe", "paypal",
                  "selenium", "playwright", "smtp", "imaplib", "smtplib"):
        check(f"no network/service token '{token}'", token not in source)
    for token in ("KnowledgeService", "KnowledgeIndex", "KnowledgeQueryEngine",
                  "KnowledgeExplainEngine", "KnowledgeInsightEngine",
                  "query_engine", "explain_engine", "insight_engine"):
        check(f"no lower knowledge token '{token}'", token not in source)
    for token in ("send_email", "send_message", "auto_dm", "scrape", "scraper",
                  "CRM", "invoice", "checkout"):
        check(f"no auto-message/scrape/CRM token '{token}'", token not in source)
    for token in ("pay" + "ment", "auth"):
        check(f"no billing/permission-word token '{token}'", token not in source)


def test_existing_suites():
    print("\n[32-47] existing lower-stage + knowledge suites still pass")
    suites = [
        _HERE / "test_first_prospect_mini_audit_delivery_log.py",
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
        test_response_decision_table(tmp)
        test_blockers_and_status_gates(tmp)
        test_input_errors(tmp)
        test_output_writing(tmp)
        test_no_mutation(tmp)
        test_sensitive_and_alias(tmp)
        test_determinism(tmp)
        test_required_checks(tmp)
    test_static_boundaries()
    test_existing_suites()
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
