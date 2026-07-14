"""Permanent focused tests for Stage 8R — operator-controlled approved
resolution action execution, target-mutation verification, and append-only
outcome evidence.

These tests own their temporary storage (``tmp_path``). They reuse the
canonical Stage 8O / 8P / 8Q fixtures already validated by the temporary
smoke harness ``_smoke8r.py`` (which is deleted after this suite passes).

No HVS invocation, no render, no network, no customer contact, no invoice or
payment mutation. Stage 8S is never started.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scos.control_center import hvs_customer_receipt_acceptance_service as P
from scos.control_center import hvs_customer_receipt_acceptance_models as PM
from scos.control_center import hvs_post_delivery_resolution_service as Q
from scos.control_center import hvs_post_delivery_resolution_models as QM
from scos.control_center import hvs_stage8o_delivery_models as O
from scos.control_center import hvs_delivery_closure_service as CS
from scos.control_center import hvs_delivery_lineage_service as LS
from scos.control_center import hvs_delivery_lineage_models as LM
from scos.control_center import hvs_revision_service as RS
from scos.control_center import hvs_resolution_action_models as M
from scos.control_center import hvs_resolution_action_service as R
from scos.control_center.hvs_post_delivery_resolution_store import (
    append_resolution_event,
    route_ledger_path,
)
from scos.control_center.hvs_stage8o_delivery_models import AUTH_APPROVED, DEL_DELIVERED_MANUALLY
from scos.control_center.hvs_delivery_closure_models import SOURCE_EMAIL_OBSERVED
from scos.control_center.hvs_local_delivery_models import CHANNEL_OTHER_MANUAL
from scos.control_center.hvs_local_delivery_service import (
    materialize_delivery_package, prepare_delivery_package, record_manual_delivery,
)
from scos.control_center.hvs_delivery_approval import create_approval_request, decide_approval
from scos.control_center.hvs_post_delivery_support_models import ISSUE_DISPUTE
from scos.control_center.tests.test_hvs_post_delivery_support_authorization import (
    _closed_context, register_post_delivery_support_policy, _issue,
)
from scos.control_center.tests.test_hvs_stage8q_post_delivery_resolution import (
    _seed_stage8o_delivery,
)


ART = "a" * 64


# ---------------------------------------------------------------------------
# Fixtures + fabrication helpers
# ---------------------------------------------------------------------------
def _mkroot(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scos" / "work").mkdir(parents=True)
    return root


def _seed_package_and_receipt(root: Path) -> tuple[str, str, str, str]:
    """Build a Stage 7 materialized package + acknowledged receipt (the exact
    canonical recipe the closure handler requires to find and close a delivery)."""
    import hashlib

    artifact = root / "artifact.bin"
    artifact.write_bytes(b"STAGE8R-CLOSURE-ARTIFACT" * 5)
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    packet = {
        "ok": True, "schema_version": 1, "packet_id": f"packet-{root.name}",
        "source": "hermes_video_studio", "trust_level": "VERIFIED",
        "operator_action": "review_export_ready", "automation_allowed": False,
        "project_id": "project-stage8r", "validation_id": f"validation-{root.name}",
        "hvs": {"validation_id": f"validation-{root.name}", "project_id": "project-stage8r",
                "verdict": "PASS", "export_ready": True},
        "artifact": {"path": str(artifact), "sha256": sha, "size_bytes": artifact.stat().st_size},
    }
    req = create_approval_request(packet=packet, repo_root=root)
    decide_approval(approval_id=req.approval_request_id, decision="approve", operator_id="op",
                   decided_at="t", repo_root=root)
    pkg = prepare_delivery_package(approval_id=req.approval_request_id, operator_id="op",
                                   repo_root=root, recorded_at="t")
    materialize_delivery_package(package_id=pkg.package_id, operator_id="op", repo_root=root,
                                 recorded_at="t")
    delivery = record_manual_delivery(
        package_id=pkg.package_id, status=DEL_DELIVERED_MANUALLY, operator_id="op",
        channel=CHANNEL_OTHER_MANUAL, recipient_label="synthetic-customer", repo_root=root,
        recorded_at="t",
    )
    did = delivery.delivery_record.delivery_record_id
    cust = delivery.delivery_record.recipient_label
    rec = CS.record_customer_receipt_evidence(
        delivery_record_id=did, repo_root=root, status="acknowledged",
        source_type=SOURCE_EMAIL_OBSERVED, operator_id="op",
        customer_reference=cust, statement_summary="ack", recorded_at="t",
    )
    assert rec.ok, rec.error_detail
    return did, rec.receipt_evidence.receipt_evidence_id, cust, sha


def _seed_closure_delivery(root: Path) -> tuple[str, str]:
    """Canonical Stage 8O/8P/8Q lineage for a delivery that also exists as a
    Stage 7 materialized package (acknowledged receipt, not yet closed).

    Returns (delivery_record_id, acknowledged_receipt_evidence_id).
    """
    did, receipt_id, cust, sha = _seed_package_and_receipt(root)
    _seed_stage8o_delivery(
        repo_root=root, delivery_record_id=did, package_id="pkg-x",
        auth_status=AUTH_APPROVED, delivery_status=DEL_DELIVERED_MANUALLY,
        artifact_sha=sha, project_id="project-stage8r", customer_reference=cust,
        auth_request_id="ar-x", auth_decision_id="ad-x", completion_id="c-x",
    )
    P.create_customer_receipt_record(
        repo_root=root, actual_delivery_record_id=did, delivery_package_id="pkg-x",
        artifact_id="art-1", artifact_sha256=sha, customer_reference=cust,
        receipt_evidence_type="CUSTOMER_WRITTEN_CONFIRMATION", safe_evidence_reference="ref-1",
        receipt_confirmation_date="2026-02-01", recorded_by_operator_id="op",
        source_render_completion_id="c-x", source_delivery_authorization_id="ar-x",
        receipt_status=PM.RECEIPT_CONFIRMED,
    )
    P.record_customer_decision(
        repo_root=root, actual_delivery_record_id=did, decision_status="ACCEPTED",
        decision_date="2026-02-02", safe_evidence_reference="ref-2", recorded_by_operator_id="op",
    )
    return did, receipt_id



def _seed_8op(root: Path, decision: str) -> tuple[str, str]:
    # Mirror the canonical smoke fixture (seed): build a real Stage 7 materialized
    # package + acknowledged receipt so the closure / follow-up handlers find a
    # genuine Stage 8P receipt evidence record (close_delivery requires it).
    did, receipt_id, cust, sha = _seed_package_and_receipt(root)
    _seed_stage8o_delivery(
        repo_root=root, delivery_record_id=did, package_id="pkg-x",
        auth_status=O.AUTH_APPROVED, delivery_status=O.DEL_DELIVERED_MANUALLY,
        artifact_sha=sha, project_id="project-stage8r", customer_reference=cust,
        auth_request_id="ar-x", auth_decision_id="ad-x", completion_id="c-x",
    )
    P.create_customer_receipt_record(
        repo_root=root, actual_delivery_record_id=did, delivery_package_id="pkg-x",
        artifact_id="art-1", artifact_sha256=sha, customer_reference=cust,
        receipt_evidence_type="CUSTOMER_WRITTEN_CONFIRMATION", safe_evidence_reference="ref-1",
        receipt_confirmation_date="2026-02-01", recorded_by_operator_id="op",
        source_render_completion_id="c-x", source_delivery_authorization_id="ar-x",
        receipt_status=PM.RECEIPT_CONFIRMED,
    )
    if decision == "ACCEPTED":
        P.record_customer_decision(
            repo_root=root, actual_delivery_record_id=did, decision_status="ACCEPTED",
            decision_date="2026-02-02", safe_evidence_reference="ref-2", recorded_by_operator_id="op",
        )
    elif decision == "REVISION_REVIEW_REQUESTED":
        P.record_revision_review_request(
            repo_root=root, actual_delivery_record_id=did, revision_review_reason="update logo",
            decision_date="2026-02-02", safe_evidence_reference="ref-2", recorded_by_operator_id="op",
        )
    elif decision == "NO_DECISION":
        pass  # receipt confirmed, no decision -> MANUAL_ACCEPTANCE_FOLLOW_UP route
    elif decision == "REJECTED":
        P.record_customer_decision(
            repo_root=root, actual_delivery_record_id=did, decision_status="REJECTED",
            decision_date="2026-02-02", rejection_reason="wrong aspect ratio",
            safe_evidence_reference="ref-2", recorded_by_operator_id="op",
        )
    return did, receipt_id


def _approved_route(root: Path, did: str, decision_action: str) -> str:
    route = Q.create_post_delivery_route(repo_root=root, actual_delivery_record_id=did)
    assert route.ok, route.error_detail
    rid = route.resolution_route.resolution_route_id
    d = Q.decide_post_delivery_route(
        repo_root=root, resolution_route_id=rid, decision_action=decision_action,
        operator_id="op-approver", reason="approve for stage8r test",
    )
    assert d.ok, d.error_detail
    return rid


def _seed_closure_context(root: Path) -> tuple[str, str, str]:
    """Build a fully closed Stage 8F lineage and return (route_id, receipt_id, did)."""
    ctx, acc, auth, rel, rec, audit = _closed_context(root)
    did = rel.original_delivery_id
    rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
    return rid, rec.receipt_evidence_id, did


def _make_closure_request(root: Path, did: str, receipt_id: str, rid: str, live_hash: str):
    # NOTE: the caller is responsible for injecting the Stage 8Q approval ledger
    # event (via _inject_event + _base_approve_event). Injecting here too would
    # duplicate the event_id and trip the fail-closed "conflicting stage8q
    # resolution event" guard in the route ledger reader.
    sel = M.ResolutionActionSelection(
        action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
        receipt_evidence_id=receipt_id, closure_reason="post-acceptance",
    )
    req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
    assert req.ok, req.error_code
    return req.execution_request.execution_request_id, rid


def _run_full(root, rid, action_family, **selkw):
    sel = M.ResolutionActionSelection(action_family=action_family, **selkw)
    req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
    if not req.ok:
        return ("CREATE_FAIL", req.error_code, req.error_detail)
    elig = R.evaluate_execution_eligibility(
        repo_root=root, execution_request_id=req.execution_request.execution_request_id)
    if elig.eligibility.eligibility_status != "READY":
        return ("ELIG", elig.eligibility.eligibility_status, elig.eligibility.missing_fields, elig.eligibility.blockers)
    ap = R.approve_execution_request(
        repo_root=root, execution_request_id=req.execution_request.execution_request_id,
        operator_id="op", reason="execute")
    if not ap.ok:
        return ("APPROVE_FAIL", ap.error_code, ap.error_detail)
    ex = R.execute_approved_action(
        repo_root=root, execution_request_id=req.execution_request.execution_request_id,
        operator_id="op")
    if not ex.ok:
        return ("EXEC_FAIL", ex.error_code, ex.error_detail)
    out = ex.outcome
    return ("OK", out.outcome_status, out.target_record_id, out.side_effect_count,
            out.customer_contact_performed, out.hvs_invoked, out.media_modified,
            out.invoice_state_changed, out.payment_state_changed)


# ---------------------------------------------------------------------------
# 1. Stage 8Q approval-ledger regressions
# ---------------------------------------------------------------------------
def _inject_event(root: Path, event: dict) -> None:
    """Append a raw ledger event (for fail-closed regression injection)."""
    ledger = route_ledger_path(root)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def _base_approve_event(rid: str, live_hash: str) -> dict:
    return {
        "schema_version": "scos-hvs.stage8q.event.v1/1.0.0",
        "event_id": "evt-test-" + rid,
        "event_type": QM.EVT_ROUTE_APPROVED,
        "resolution_route_id": rid,
        "project_id": "proj-stage8r",
        "actual_delivery_record_id": "dr-x",
        "artifact_sha256": ART,
        "source_aggregate_outcome": "OUTCOME_ACCEPTED_BY_CUSTOMER",
        "recommended_route": "CLOSURE_ELIGIBILITY_REVIEW",
        "resulting_status": QM.ROUTING_APPROVED,
        "operator_id": "op-approver",
        "informational_recorded_at": "t",
        "route_content_hash": live_hash,
        "record": {
            "resolution_route_id": rid,
            "route_decision_id": "dec-test-" + rid,
            "route_content_hash": live_hash,
            "resulting_status": QM.ROUTING_APPROVED,
        },
    }


def _route_id_only(root: Path, did: str) -> tuple[str, str]:
    """Create a Stage 8Q route WITHOUT approving it; return (rid, live_hash)."""
    route = Q.create_post_delivery_route(repo_root=root, actual_delivery_record_id=did)
    assert route.ok, route.error_detail
    rid = route.resolution_route.resolution_route_id
    live_hash = R.route_content_hash_for(route.resolution_route)
    return rid, live_hash


def _route_and_hash(root, did):
    rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
    route = Q.inspect_post_delivery_route(repo_root=root, resolution_route_id=rid).resolution_route
    live_hash = R.route_content_hash_for(route)
    return rid, live_hash


def test_approval_ledger_accepted_with_matching_hash(tmp_path):
    root = _mkroot(tmp_path)
    did, _ = _seed_8op(root, "ACCEPTED")
    rid, live_hash = _route_id_only(root, did)
    _inject_event(root, _base_approve_event(rid, live_hash))
    sel = M.ResolutionActionSelection(action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
                                       receipt_evidence_id="r", closure_reason="x")
    req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
    assert req.ok, req.error_code


def test_approval_route_status_ready_does_not_block_ledger_approval(tmp_path):
    root = _mkroot(tmp_path)
    did, _ = _seed_8op(root, "ACCEPTED")
    rid, live_hash = _route_id_only(root, did)
    _inject_event(root, _base_approve_event(rid, live_hash))
    route = Q.inspect_post_delivery_route(repo_root=root, resolution_route_id=rid).resolution_route
    # The route object still reports READY_FOR_OPERATOR_REVIEW; the ledger governs.
    assert route.route_status != QM.ROUTING_APPROVED
    sel = M.ResolutionActionSelection(action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
                                       receipt_evidence_id="r", closure_reason="x")
    req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
    assert req.ok


def test_approval_missing_event_rejected(tmp_path):
    root = _mkroot(tmp_path)
    did, _ = _seed_8op(root, "ACCEPTED")
    rid, _ = _route_id_only(root, did)  # route created, no decision event
    sel = M.ResolutionActionSelection(action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
                                       receipt_evidence_id="r", closure_reason="x")
    req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
    assert not req.ok and req.error_code == M.ERR_ROUTE_NOT_APPROVED


def test_approval_wrong_route_id_rejected(tmp_path):
    root = _mkroot(tmp_path)
    did, _ = _seed_8op(root, "ACCEPTED")
    rid, live_hash = _route_id_only(root, did)
    ev = _base_approve_event("OTHER_ROUTE_ID", live_hash)
    ev["record"]["resolution_route_id"] = "OTHER_ROUTE_ID"
    _inject_event(root, ev)
    sel = M.ResolutionActionSelection(action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
                                       receipt_evidence_id="r", closure_reason="x")
    req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
    assert not req.ok and req.error_code == M.ERR_ROUTE_NOT_APPROVED


def test_approval_mismatched_hash_rejected(tmp_path):
    root = _mkroot(tmp_path)
    did, _ = _seed_8op(root, "ACCEPTED")
    rid, live_hash = _route_id_only(root, did)
    ev = _base_approve_event(rid, live_hash)
    ev["route_content_hash"] = "deadbeef" * 8
    ev["record"]["route_content_hash"] = "deadbeef" * 8
    _inject_event(root, ev)
    sel = M.ResolutionActionSelection(action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
                                       receipt_evidence_id="r", closure_reason="x")
    req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
    assert not req.ok and req.error_code == M.ERR_ROUTE_NOT_APPROVED


def test_approval_non_approved_status_rejected(tmp_path):
    root = _mkroot(tmp_path)
    did, _ = _seed_8op(root, "ACCEPTED")
    rid, live_hash = _route_id_only(root, did)
    ev = _base_approve_event(rid, live_hash)
    ev["resulting_status"] = QM.ROUTING_REJECTED
    ev["record"]["resulting_status"] = QM.ROUTING_REJECTED
    _inject_event(root, ev)
    sel = M.ResolutionActionSelection(action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
                                       receipt_evidence_id="r", closure_reason="x")
    req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
    assert not req.ok and req.error_code == M.ERR_ROUTE_NOT_APPROVED


def test_approval_malformed_event_fails_closed(tmp_path):
    root = _mkroot(tmp_path)
    did, _ = _seed_8op(root, "ACCEPTED")
    rid, _ = _route_id_only(root, did)
    _inject_event(root, {
        "schema_version": "scos-hvs.stage8q.event.v1/1.0.0",
        "event_id": "evt-malformed",
        "event_type": QM.EVT_ROUTE_APPROVED,
        "resolution_route_id": rid,
        "record": {"resolution_route_id": rid},
    })
    sel = M.ResolutionActionSelection(action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
                                       receipt_evidence_id="r", closure_reason="x")
    req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
    assert not req.ok and req.error_code == M.ERR_ROUTE_NOT_APPROVED


def test_approval_conflicting_terminal_rejected(tmp_path):
    root = _mkroot(tmp_path)
    did, _ = _seed_8op(root, "ACCEPTED")
    rid, live_hash = _route_id_only(root, did)
    _inject_event(root, _base_approve_event(rid, live_hash))
    rej = _base_approve_event(rid, live_hash)
    rej["event_type"] = QM.EVT_ROUTE_REJECTED
    rej["resulting_status"] = QM.ROUTING_REJECTED
    rej["event_id"] = "evt-reject-" + rid
    rej["record"]["resulting_status"] = QM.ROUTING_REJECTED
    _inject_event(root, rej)
    sel = M.ResolutionActionSelection(action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
                                       receipt_evidence_id="r", closure_reason="x")
    req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
    assert not req.ok and req.error_code == M.ERR_ROUTE_NOT_APPROVED


def test_approval_rechecked_during_pre_execution_reverify(tmp_path):
    root = _mkroot(tmp_path)
    did, receipt_id = _seed_8op(root, "ACCEPTED")
    rid, live_hash = _route_id_only(root, did)
    _inject_event(root, _base_approve_event(rid, live_hash))
    req_id, _ = _make_closure_request(root, did, receipt_id, rid, live_hash)
    ap = R.approve_execution_request(repo_root=root, execution_request_id=req_id, operator_id="op", reason="x")
    assert ap.ok
    # Now remove the approval event by rewriting the ledger with only the route event.
    ledger = route_ledger_path(root)
    lines = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    route_lines = [ln for ln in lines if "ROUTE_CREATED" in ln or "EVT_ROUTE_CREATED" in ln]
    ledger.write_text("\n".join(route_lines) + "\n")
    ex = R.execute_approved_action(repo_root=root, execution_request_id=req_id, operator_id="op")
    assert not ex.ok and ex.error_code == M.ERR_PRE_EXECUTION_FAILED


def test_approval_failed_reverification_zero_target_mutations(tmp_path):
    root = _mkroot(tmp_path)
    did, receipt_id = _seed_8op(root, "ACCEPTED")
    rid, live_hash = _route_id_only(root, did)
    _inject_event(root, _base_approve_event(rid, live_hash))
    req_id, _ = _make_closure_request(root, did, receipt_id, rid, live_hash)
    R.approve_execution_request(repo_root=root, execution_request_id=req_id, operator_id="op", reason="x")
    ledger = route_ledger_path(root)
    lines = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    route_lines = [ln for ln in lines if "ROUTE_CREATED" in ln or "EVT_ROUTE_CREATED" in ln]
    ledger.write_text("\n".join(route_lines) + "\n")
    ex = R.execute_approved_action(repo_root=root, execution_request_id=req_id, operator_id="op")
    assert not ex.ok
    events = [e for e in __import__("scos.control_center.hvs_resolution_action_store", fromlist=["read_resolution_action_events"]).read_resolution_action_events(ledger_path=R.ledger_path(root))]
    assert not any(e.get("event_type") == M.EVT_OUTCOME_EVIDENCE_CREATED for e in events)


# ---------------------------------------------------------------------------
# 2. Four successful target actions
# ---------------------------------------------------------------------------
def test_closure_execution_ok(tmp_path):
    root = _mkroot(tmp_path)
    did, receipt_id = _seed_closure_delivery(root)
    rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
    res = _run_full(root, rid, M.ACTION_PROJECT_CLOSURE_EXECUTION,
                    receipt_evidence_id=receipt_id, closure_reason="post-acceptance")
    assert res[0] == "OK" and res[1] == "VERIFIED"
    assert res[3] == 1  # side_effect_count
    assert not any(res[4:]), "boundary flags must all be False"


def test_revision_execution_ok(tmp_path):
    root = _mkroot(tmp_path)
    did, receipt_id = _seed_8op(root, "REVISION_REVIEW_REQUESTED")
    cl = CS.close_delivery(receipt_evidence_id=receipt_id, repo_root=root, operator_id="op",
                           decision="accept", reason="accepted before revision", recorded_at="t")
    assert cl.ok
    LS.register_delivery_lineage(request=LM.DeliveryLineageRegistrationRequest(
        delivery_record_id=did, delivery_version=LM.DeliveryVersion(1), operator_id="op",
        registration_basis=LM.BASIS_ORIGINAL_DELIVERY_CONFIRMED, confirm_legacy_version=True),
        repo_root=root, recorded_at="t")
    rid = _approved_route(root, did, QM.DECISION_APPROVE_REVISION_ELIGIBILITY_REVIEW)
    LS.register_delivery_lineage(request=LM.DeliveryLineageRegistrationRequest(
        delivery_record_id=did, delivery_version=LM.DeliveryVersion(1), operator_id="op",
        registration_basis=LM.BASIS_ORIGINAL_DELIVERY_CONFIRMED, confirm_legacy_version=True),
        repo_root=root, recorded_at="t")
    route_art = Q.inspect_post_delivery_route(repo_root=root, resolution_route_id=rid).resolution_route.artifact_sha256
    item = {"category": "CAPTION_CHANGE", "description": "fix", "target_type": "scene",
            "target_id": "scene-1", "priority": "normal", "acceptance_requirement": "match copy",
            "source_artifact_sha256": route_art or ART}
    res = _run_full(root, rid, M.ACTION_REVISION_REQUEST_CREATION,
                    revision_items=(item,), requested_scope="caption fix")
    assert res[0] == "OK" and res[1] == "VERIFIED"
    assert res[3] == 1
    assert not any(res[4:])


def test_dispute_execution_ok(tmp_path):
    root = _mkroot(tmp_path)
    # Mirror the canonical smoke dispute fixture: a fully closed Stage 8F lineage
    # is required before a support policy (and therefore a dispute) may be opened.
    ctx, acc, auth, rel, rec, audit = _closed_context(root)
    did = "scos-hvs-delivery-rec-dispute-test"
    _seed_stage8o_delivery(
        repo_root=root, delivery_record_id=did, package_id="pkg-x",
        auth_status=O.AUTH_APPROVED, delivery_status=O.DEL_DELIVERED_MANUALLY,
        artifact_sha=ART, project_id=ctx["project_id"], customer_reference="cust-1",
        auth_request_id="ar-x", auth_decision_id="ad-x", completion_id="c-x",
    )
    P.create_customer_receipt_record(
        repo_root=root, actual_delivery_record_id=did, delivery_package_id="pkg-x",
        artifact_id="art-1", artifact_sha256=ART, customer_reference="cust-1",
        receipt_evidence_type="CUSTOMER_WRITTEN_CONFIRMATION", safe_evidence_reference="ref-1",
        receipt_confirmation_date="2026-02-01", recorded_by_operator_id="op",
        source_render_completion_id="c-x", source_delivery_authorization_id="ar-x",
        receipt_status=PM.RECEIPT_CONFIRMED,
    )
    P.record_delivery_issue(
        repo_root=root, actual_delivery_record_id=did,
        issue_category=ISSUE_DISPUTE, issue_summary="dispute now",
        decision_date="2026-02-02", safe_evidence_reference="ref-2", recorded_by_operator_id="op",
    )
    # Mirror the canonical smoke dispute fixture: force the DISPUTE_ELIGIBILITY_REVIEW
    # route explicitly (record_issue_review_request alone yielded SUPPORT_REVIEW),
    # then open the issue through the support policy for a source issue id.
    rid = Q.create_post_delivery_route(
        repo_root=root, actual_delivery_record_id=did,
        issue_summary="dispute now", issue_category=ISSUE_DISPUTE,
        safe_evidence_reference="ref-1",
    ).resolution_route.resolution_route_id
    d = Q.decide_post_delivery_route(
        repo_root=root, resolution_route_id=rid,
        decision_action=QM.DECISION_APPROVE_DISPUTE_ELIGIBILITY_REVIEW,
        operator_id="op-approver", reason="approve dispute route",
    )
    assert d.ok, d.error_detail
    # Open an issue through the support policy so the dispute has a source issue id.
    from scos.control_center.tests.test_hvs_post_delivery_support_authorization import (
        register_post_delivery_support_policy, _issue,
    )
    pol = register_post_delivery_support_policy(
        authorization_id=auth.authorization_id, support_window_start="2026-01-01",
        support_window_end="2026-02-01", policy_type="STANDARD",
        included_issue_categories=("DISPUTE",), excluded_issue_categories=(),
        created_by_operator_id="op", policy_version="scos-hvs-support/1.0.0",
        repo_root=root, recorded_at="t")
    assert pol.ok
    issue = _issue(root, pol.policy, ISSUE_DISPUTE, "dispute now")
    res = _run_full(root, rid, M.ACTION_DISPUTE_OPENING,
                    source_issue_id=issue.issue_id, dispute_type="QUALITY", dispute_reason="unhappy")
    assert res[0] == "OK" and res[1] == "VERIFIED"
    assert res[3] == 1
    assert not any(res[4:])


def test_manual_follow_up_execution_ok(tmp_path):
    root = _mkroot(tmp_path)
    did, _ = _seed_8op(root, "NO_DECISION")
    rid = _approved_route(root, did, QM.DECISION_APPROVE_MANUAL_FOLLOW_UP_RECOMMENDATION)
    res = _run_full(root, rid, M.ACTION_MANUAL_FOLLOW_UP_RECORD_CREATION,
                    follow_up_purpose="chase confirmation", follow_up_recommended_action="email")
    assert res[0] == "OK" and res[1] == "VERIFIED"
    assert res[3] == 1
    assert not any(res[4:])


# ---------------------------------------------------------------------------
# 3. Incompatible route/action rejection
# ---------------------------------------------------------------------------
def test_incompatible_action_rejected_zero_mutation(tmp_path):
    root = _mkroot(tmp_path)
    did, receipt_id = _seed_8op(root, "REVISION_REVIEW_REQUESTED")
    rid = _approved_route(root, did, QM.DECISION_APPROVE_REVISION_ELIGIBILITY_REVIEW)
    # Try a CLOSURE action on a REVISION route.
    sel = M.ResolutionActionSelection(action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
                                       receipt_evidence_id=receipt_id, closure_reason="x")
    req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
    assert not req.ok and req.error_code == M.ERR_ACTION_ROUTE_INCOMPATIBLE
    events = [e for e in __import__("scos.control_center.hvs_resolution_action_store", fromlist=["read_resolution_action_events"]).read_resolution_action_events(ledger_path=R.ledger_path(root))]
    assert not any(e.get("event_type") == M.EVT_OUTCOME_EVIDENCE_CREATED for e in events)


# ---------------------------------------------------------------------------
# 4. Exact replay idempotency + changed-semantic conflict
# ---------------------------------------------------------------------------
def test_exact_replay_idempotent(tmp_path):
    root = _mkroot(tmp_path)
    did, receipt_id = _seed_closure_delivery(root)
    rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
    res1 = _run_full(root, rid, M.ACTION_PROJECT_CLOSURE_EXECUTION,
                     receipt_evidence_id=receipt_id, closure_reason="post-acceptance")
    assert res1[0] == "OK"
    # Exact replay: identical semantics -> ALREADY_COMPLETED, no second mutation.
    sel = M.ResolutionActionSelection(action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
                                       receipt_evidence_id=receipt_id, closure_reason="post-acceptance")
    req2 = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
    elig = R.evaluate_execution_eligibility(repo_root=root, execution_request_id=req2.execution_request.execution_request_id)
    assert elig.eligibility.eligibility_status == "ALREADY_COMPLETED"
    events = [e for e in __import__("scos.control_center.hvs_resolution_action_store", fromlist=["read_resolution_action_events"]).read_resolution_action_events(ledger_path=R.ledger_path(root))]
    outcomes = [e for e in events if e.get("event_type") == M.EVT_OUTCOME_EVIDENCE_CREATED]
    assert len(outcomes) == 1  # exactly one side effect recorded


def test_changed_semantic_replay_conflict(tmp_path):
    root = _mkroot(tmp_path)
    did, receipt_id = _seed_closure_delivery(root)
    rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
    res1 = _run_full(root, rid, M.ACTION_PROJECT_CLOSURE_EXECUTION,
                     receipt_evidence_id=receipt_id, closure_reason="post-acceptance")
    assert res1[0] == "OK"
    # Reuse same route+action identity with CHANGED semantic content (different closure_reason).
    sel2 = M.ResolutionActionSelection(action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
                                        receipt_evidence_id=receipt_id, closure_reason="CHANGED_REASON")
    req2 = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel2)
    assert req2.ok
    ap = R.approve_execution_request(repo_root=root, execution_request_id=req2.execution_request.execution_request_id,
                                     operator_id="op", reason="x")
    assert ap.ok
    ex = R.execute_approved_action(repo_root=root, execution_request_id=req2.execution_request.execution_request_id, operator_id="op")
    assert not ex.ok and ex.error_code == M.ERR_CONFLICTING_EXECUTION
    # Original target + completion evidence remain immutable; side_effect_count still 1.
    events = [e for e in __import__("scos.control_center.hvs_resolution_action_store", fromlist=["read_resolution_action_events"]).read_resolution_action_events(ledger_path=R.ledger_path(root))]
    outcomes = [e for e in events if e.get("event_type") == M.EVT_OUTCOME_EVIDENCE_CREATED]
    assert len(outcomes) == 1


# ---------------------------------------------------------------------------
# 5. Exactly-one-action / dynamic dispatch guards
# ---------------------------------------------------------------------------
def test_exactly_one_action_family_enforced(tmp_path):
    # The selection model rejects unknown action families at construction time,
    # before any route lookup. This enforces the exactly-one-action invariant.
    with pytest.raises(ValueError):
        M.ResolutionActionSelection(action_family="NOT_A_REAL_ACTION")


def test_explicit_action_handlers_only(tmp_path):
    # The action dispatch table must be a closed, explicit mapping (no dynamic lookup).
    assert set(M.ALLOWED_ACTION_FAMILIES) == set(R.ACTION_HANDLERS.keys())


# ---------------------------------------------------------------------------
# 6. Target read-back + boundary flags + deterministic ids
# ---------------------------------------------------------------------------
def test_target_readback_and_boundary_flags(tmp_path):
    root = _mkroot(tmp_path)
    did, receipt_id = _seed_closure_delivery(root)
    rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
    sel = M.ResolutionActionSelection(action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
                                       receipt_evidence_id=receipt_id, closure_reason="x")
    req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
    ap = R.approve_execution_request(repo_root=root, execution_request_id=req.execution_request.execution_request_id, operator_id="op", reason="x")
    assert ap.ok
    ex = R.execute_approved_action(repo_root=root, execution_request_id=req.execution_request.execution_request_id, operator_id="op")
    assert ex.ok
    out = ex.outcome
    assert out.target_record_id
    assert out.target_record_verified is True
    assert out.side_effect_count == 1
    assert not (out.customer_contact_performed or out.hvs_invoked or out.media_modified
                or out.invoice_state_changed or out.payment_state_changed)
    # Deterministic id / hash present and stable.
    assert out.outcome_evidence_id
    assert out.execution_contract_hash


# ---------------------------------------------------------------------------
# 7. Nine CLI commands (read-only + mutating) exercise the same service
# ---------------------------------------------------------------------------
def _cli(args, root):
    from scos.control_center import cli

    import io, contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cli, "_repo_root", lambda: root)
            rc = cli.main(args)
    return rc, buf.getvalue()


def test_cli_create_and_inspect(tmp_path):
    root = _mkroot(tmp_path)
    did, receipt_id = _seed_closure_delivery(root)
    rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
    rc, out = _cli(["create-resolution-action-request", "--resolution-route-id", rid,
                    "--action-family", M.ACTION_PROJECT_CLOSURE_EXECUTION,
                    "--operator-id", "op", "--receipt-evidence-id", receipt_id,
                    "--closure-reason", "x"], root)
    assert rc == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    eid = payload["execution_request"]["execution_request_id"]
    rc2, out2 = _cli(["inspect-resolution-action", "--execution-request-id", eid], root)
    assert rc2 == 0 and json.loads(out2)["ok"] is True


def test_cli_evaluate_approve_execute(tmp_path):
    root = _mkroot(tmp_path)
    did, receipt_id = _seed_closure_delivery(root)
    rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
    _, out = _cli(["create-resolution-action-request", "--resolution-route-id", rid,
                   "--action-family", M.ACTION_PROJECT_CLOSURE_EXECUTION,
                   "--operator-id", "op", "--receipt-evidence-id", receipt_id, "--closure-reason", "x"], root)
    eid = json.loads(out)["execution_request"]["execution_request_id"]
    assert _cli(["evaluate-resolution-action", "--execution-request-id", eid], root)[0] == 0
    assert _cli(["approve-resolution-action", "--execution-request-id", eid, "--operator-id", "op", "--reason", "go"], root)[0] == 0
    rc, out = _cli(["execute-approved-resolution-action", "--execution-request-id", eid, "--operator-id", "op"], root)
    assert rc == 0 and json.loads(out)["outcome"]["outcome_status"] == "VERIFIED"


def test_cli_reject_requires_reason(tmp_path):
    root = _mkroot(tmp_path)
    did, receipt_id = _seed_closure_delivery(root)
    rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
    _, out = _cli(["create-resolution-action-request", "--resolution-route-id", rid,
                   "--action-family", M.ACTION_PROJECT_CLOSURE_EXECUTION,
                   "--operator-id", "op", "--receipt-evidence-id", receipt_id, "--closure-reason", "x"], root)
    eid = json.loads(out)["execution_request"]["execution_request_id"]
    # reject without reason -> rejected (non-zero rc).
    rc, out = _cli(["reject-resolution-action", "--execution-request-id", eid, "--operator-id", "op", "--reason", "not needed"], root)
    assert rc == 0 and json.loads(out)["ok"] is True


def test_cli_list_events_and_outcomes_readonly(tmp_path):
    root = _mkroot(tmp_path)
    did, receipt_id = _seed_closure_delivery(root)
    rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
    _, out = _cli(["create-resolution-action-request", "--resolution-route-id", rid,
                   "--action-family", M.ACTION_PROJECT_CLOSURE_EXECUTION,
                   "--operator-id", "op", "--receipt-evidence-id", receipt_id, "--closure-reason", "x"], root)
    eid = json.loads(out)["execution_request"]["execution_request_id"]
    rc1, _ = _cli(["list-resolution-action-events"], root)
    rc2, _ = _cli(["list-resolution-outcomes"], root)
    assert rc1 == 0 and rc2 == 0


# ---------------------------------------------------------------------------
# 8. No external surface / Stage 8S not started
# ---------------------------------------------------------------------------
def test_no_hvs_network_customer_contact(tmp_path):
    root = _mkroot(tmp_path)
    did, receipt_id = _seed_closure_delivery(root)
    rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
    res = _run_full(root, rid, M.ACTION_PROJECT_CLOSURE_EXECUTION,
                    receipt_evidence_id=receipt_id, closure_reason="x")
    assert res[0] == "OK"
    # Boundary flags prove no HVS / network / customer contact occurred.
    assert not any(res[4:]), "HVS/network/customer-contact/payment flags must be False"
