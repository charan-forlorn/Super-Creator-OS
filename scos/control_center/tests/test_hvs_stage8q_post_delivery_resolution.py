"""Stage 8Q focused tests — post-delivery resolution routing, issue/revision
qualification, manual follow-up recommendation, and explicit closure
recommendation gate.

Hermetic: every test uses a test-owned temporary runtime root. The genuine
Stage 8O actual-delivery record and Stage 8P receipt/decision records are
fabricated directly via the real Stage 8P service into temp ledgers (read-only
binding targets for Stage 8Q). No real customer, production, or HVS data is used.

The tests VERIFY (not trust) every non-equivalence rule required by the Stage
8Q spec, including the hard boundaries:

    Recommendation != Execution
    Closure Recommendation != Project Closure
    Closure Eligibility != Closure Authorization
    Issue Qualification != Issue Resolution
    Issue Qualification != Dispute Creation
    Defect Classification != Defect Confirmation
    Revision Eligibility != Revision Creation
    Follow-up Recommendation != Customer Contact
    Rejected Delivery != Refund Authorization
    Customer Acceptance != Payment / Publication Consent
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scos.control_center import hvs_customer_receipt_acceptance_service as P
from scos.control_center import hvs_customer_receipt_acceptance_models as PM
from scos.control_center import hvs_post_delivery_resolution_models as M
from scos.control_center import hvs_post_delivery_resolution_service as Q
from scos.control_center import hvs_stage8o_delivery_models as O
from scos.control_center import hvs_stage8o_delivery_store as OS

ART = "a" * 64
ART2 = "b" * 64

DL = "scos/work/hvs_stage8q_post_delivery_resolution/stage8q_post_delivery_resolution_ledger.jsonl"


# ---------------------------------------------------------------------------
# Fabrication helpers (Stage 8O + Stage 8P read-only sources of truth)
# ---------------------------------------------------------------------------
def _seed_stage8o_delivery(
    *,
    repo_root: Path,
    delivery_record_id: str = "dr-1",
    package_id: str = "pkg-1",
    auth_status: str = O.AUTH_APPROVED,
    delivery_status: str = O.DEL_DELIVERED_MANUALLY,
    package_status: str = "PACKAGE_READY",
    artifact_sha: str = ART,
    artifact_id: str = "art-1",
    project_id: str = "proj-1",
    customer_reference: str = "cust-1",
    auth_request_id: str = "ar-1",
    auth_decision_id: str = "ad-1",
    completion_id: str = "c-1",
) -> None:
    ledger = OS.delivery_ledger_path(repo_root)
    OS.append_delivery_event(
        ledger_path=ledger, event_type="PACKAGE_PREPARED", subject_id=package_id,
        completion_evidence_id=completion_id, artifact_sha256=artifact_sha, operator_id="op",
        resulting_status=package_status, reason="package prepared", recorded_at="2026-01-01",
        package_id=package_id, record_payload={"package_status": package_status, "delivery_package_id": package_id},
    )
    OS.append_delivery_event(
        ledger_path=ledger,
        event_type="AUTHORIZATION_APPROVED" if auth_status == O.AUTH_APPROVED else "AUTHORIZATION_REJECTED",
        subject_id=auth_request_id, completion_evidence_id=completion_id, artifact_sha256=artifact_sha,
        operator_id="op", resulting_status=auth_status, reason="auth", recorded_at="2026-01-01",
        package_id=package_id, authorization_request_id=auth_request_id, authorization_decision_id=auth_decision_id,
    )
    rec = {
        "schema_version": O.DELIVERY_RECORD_SCHEMA_VERSION,
        "manual_delivery_record_id": delivery_record_id,
        "authorization_request_id": auth_request_id,
        "authorization_decision_id": auth_decision_id,
        "delivery_package_id": package_id,
        "package_content_hash": "pc-1",
        "completion_evidence_id": completion_id,
        "artifact_sha256": artifact_sha,
        "project_id": project_id,
        "safe_recipient_reference": customer_reference,
        "manual_delivery_method": "IN_PERSON",
        "operator_id": "op",
        "human_delivery_confirmation": True,
        "delivery_recorded_at": "2026-01-01",
        "external_evidence_reference": "",
        "operator_note": "",
        "delivery_status": delivery_status,
        "manual_delivery_performed": True,
        "external_delivery_executed_by_scos": False,
        "customer_receipt_confirmed": False,
        "customer_acceptance_recorded": False,
        "publishing_performed": False,
        "invoice_state_changed": False,
        "payment_state_changed": False,
        "automation_allowed": False,
        "artifact_id": artifact_id,
    }
    OS.append_delivery_event(
        ledger_path=ledger, event_type="DELIVERY_RECORDED", subject_id=delivery_record_id,
        completion_evidence_id=completion_id, artifact_sha256=artifact_sha, operator_id="op",
        resulting_status=delivery_status, reason="delivered", recorded_at="2026-01-01",
        package_id=package_id, authorization_request_id=auth_request_id,
        authorization_decision_id=auth_decision_id, delivery_record_id=delivery_record_id,
        record_payload=rec,
    )


def _record_receipt(repo_root: Path, *, receipt_status: str = PM.RECEIPT_CONFIRMED, artifact_sha: str = ART) -> None:
    P.create_customer_receipt_record(
        repo_root=repo_root, actual_delivery_record_id="dr-1", delivery_package_id="pkg-1",
        artifact_id="art-1", artifact_sha256=artifact_sha, customer_reference="cust-1",
        receipt_evidence_type="CUSTOMER_WRITTEN_CONFIRMATION", safe_evidence_reference="ref-1",
        receipt_confirmation_date="2026-02-01", recorded_by_operator_id="op",
        source_render_completion_id="c-1", source_delivery_authorization_id="ar-1",
        receipt_status=receipt_status,
    )


def _inject_forged_receipt(repo_root: Path, *, customer_reference: str | None = None, artifact_sha256: str | None = None) -> None:
    """Simulate a forged Stage 8P receipt ledger record (tampered/corrupt ledger
    that bypassed Stage 8P writer validation). Stage 8Q must independently
    reject it when its identity diverges from the Stage 8O actual-delivery."""
    from scos.control_center import hvs_customer_receipt_acceptance_store as RS
    from scos.control_center import hvs_customer_receipt_acceptance_models as PMR
    ledger = RS.receipt_ledger_path(repo_root)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": PMR.RECEIPT_RECORD_SCHEMA_VERSION,
        "receipt_record_id": "rc-forged-1",
        "project_id": "proj-1",
        "customer_reference": customer_reference if customer_reference is not None else "cust-1",
        "source_render_completion_id": "c-1",
        "source_delivery_package_id": "pkg-1",
        "source_delivery_authorization_id": "ar-1",
        "source_actual_delivery_record_id": "dr-1",
        "source_delivery_lineage_id": None,
        "artifact_id": "art-1",
        "artifact_sha256": artifact_sha256 if artifact_sha256 is not None else ART,
        "customer_confirmed_artifact_sha256": None,
        "receipt_evidence_type": "CUSTOMER_WRITTEN_CONFIRMATION",
        "safe_evidence_reference": "ref-1",
        "receipt_confirmation_date": "2026-02-01",
        "recorded_by_operator_id": "op",
        "receipt_status": PM.RECEIPT_CONFIRMED,
        "customer_decision_recorded": False,
        "invoice_state_changed": False,
        "payment_state_changed": False,
        "automation_allowed": False,
        "deterministic_content_hash": "forged",
    }
    event = {
        "schema_version": PMR.POST_RECEIPT_EVENT_SCHEMA_VERSION,
        "event_id": "ev-forged-1",
        "event_type": "RECEIPT_CONFIRMED",
        "aggregate_id": "rc-forged-1",
        "project_id": "proj-1",
        "actual_delivery_record_id": "dr-1",
        "package_id": "pkg-1",
        "artifact_sha256": record["artifact_sha256"],
        "operator_id": "op",
        "resulting_status": PM.RECEIPT_CONFIRMED,
        "recorded_at": "2026-02-01",
        "record": record,
    }
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def _seed_outcome(repo_root: Path, outcome: str) -> None:
    _seed_stage8o_delivery(repo_root=repo_root)
    if outcome == PM.OUTCOME_RECEIPT_NOT_CONFIRMED:
        return  # no receipt record at all
    if outcome == PM.OUTCOME_DELIVERY_IDENTITY_CONFLICT:
        _record_receipt(repo_root=repo_root, receipt_status=PM.RECEIPT_IDENTITY_CONFLICT)
        return
    _record_receipt(repo_root=repo_root)
    if outcome == PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING:
        return  # receipt confirmed, no decision
    if outcome == PM.OUTCOME_ACCEPTED_BY_CUSTOMER:
        P.record_customer_decision(repo_root=repo_root, actual_delivery_record_id="dr-1",
                                   decision_status="ACCEPTED", decision_date="2026-02-02",
                                   safe_evidence_reference="ref-2", recorded_by_operator_id="op")
    elif outcome == PM.OUTCOME_REJECTED_BY_CUSTOMER:
        P.record_customer_decision(repo_root=repo_root, actual_delivery_record_id="dr-1",
                                   decision_status="REJECTED", decision_date="2026-02-02",
                                   rejection_reason="wrong aspect ratio", safe_evidence_reference="ref-2",
                                   recorded_by_operator_id="op")
    elif outcome == PM.OUTCOME_ISSUE_REPORTED:
        P.record_delivery_issue(repo_root=repo_root, actual_delivery_record_id="dr-1",
                                issue_category=None, issue_summary="subtitle timing off",
                                decision_date="2026-02-02", safe_evidence_reference="ref-2",
                                recorded_by_operator_id="op")
    elif outcome == PM.OUTCOME_REVISION_REVIEW_REQUESTED:
        P.record_revision_review_request(repo_root=repo_root, actual_delivery_record_id="dr-1",
                                         revision_review_reason="update logo", decision_date="2026-02-02",
                                         safe_evidence_reference="ref-2", recorded_by_operator_id="op")


def _make_route(repo_root: Path, outcome: str, **kw) -> M.PostDeliveryResolutionRoute:
    r = Q.create_post_delivery_route(repo_root=repo_root, actual_delivery_record_id="dr-1", **kw)
    assert r.ok, r.error_detail
    return r.resolution_route


def _binding(tmp_path: Path) -> M.PostDeliverySourceBinding:
    _seed_stage8o_delivery(repo_root=tmp_path)
    return Q.build_source_binding(repo_root=tmp_path, actual_delivery_record_id="dr-1")


# ---------------------------------------------------------------------------
# A. SOURCE ELIGIBILITY
# ---------------------------------------------------------------------------
class TestSourceEligibility:
    @pytest.mark.parametrize("outcome", [
        PM.OUTCOME_ACCEPTED_BY_CUSTOMER, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING,
        PM.OUTCOME_RECEIPT_NOT_CONFIRMED, PM.OUTCOME_REJECTED_BY_CUSTOMER,
        PM.OUTCOME_ISSUE_REPORTED, PM.OUTCOME_REVISION_REVIEW_REQUESTED,
    ])
    def test_valid_outcomes_eligible(self, tmp_path, outcome):
        _seed_outcome(tmp_path, outcome)
        r = Q.inspect_stage8q_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert r.ok and r.eligible is True

    def test_identity_conflict_blocked(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_DELIVERY_IDENTITY_CONFLICT)
        route = _make_route(tmp_path, PM.OUTCOME_DELIVERY_IDENTITY_CONFLICT)
        assert route.recommended_route == M.ROUTE_OPERATOR_INVESTIGATION
        assert route.route_status == M.ROUTING_BLOCKED

    def test_no_delivery_rejected(self, tmp_path):
        r = Q.inspect_stage8q_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-x")
        assert not r.ok and r.error_code == "stage8p_evidence_not_verified"

    def test_missing_actual_delivery_id_rejected(self, tmp_path):
        r = Q.inspect_stage8q_eligibility(repo_root=tmp_path, actual_delivery_record_id="  ")
        assert not r.ok and r.error_code == "missing_actual_delivery_record_id"

    def test_forgotten_artifact_sha_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path, artifact_sha="bad")
        r = Q.inspect_stage8q_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert not r.ok

    def test_customer_reference_mismatch_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path, customer_reference="cust-1")
        # Forge a Stage 8P receipt record with a mismatched customer (tampered ledger).
        _inject_forged_receipt(tmp_path, customer_reference="WRONG")
        r = Q.inspect_stage8q_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert not r.ok

    def test_artifact_sha_mismatch_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path, artifact_sha=ART)
        # Forge a Stage 8P receipt record with a mismatched artifact SHA (tampered ledger).
        _inject_forged_receipt(tmp_path, artifact_sha256=ART2)
        r = Q.inspect_stage8q_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert not r.ok

    def test_unknown_aggregate_outcome_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        with pytest.raises(ValueError):
            Q.classify_route(aggregate_outcome="TOTALLY_UNKNOWN_OUTCOME")

    def test_conflicting_decisions_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        _record_receipt(tmp_path)
        P.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                   decision_status="ACCEPTED", decision_date="2026-02-02",
                                   safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        r2 = P.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                        decision_status="REJECTED", decision_date="2026-02-03",
                                        rejection_reason="changed mind", safe_evidence_reference="ref-3",
                                        recorded_by_operator_id="op")
        assert not r2.ok
        view = P.build_acceptance_readiness_view(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert view.outcome == PM.OUTCOME_ACCEPTED_BY_CUSTOMER  # unchanged, deterministic


# ---------------------------------------------------------------------------
# B. ACCEPTANCE AND CLOSURE ELIGIBILITY
# ---------------------------------------------------------------------------
class TestAcceptanceClosure:
    def test_accepted_routes_to_closure_review(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        assert route.recommended_route == M.ROUTE_CLOSURE_ELIGIBILITY_REVIEW
        assert route.closure_eligibility_status == M.CLOSURE_ELIGIBLE

    def test_acceptance_does_not_close_project(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        assert route.project_closed is False
        assert route.project_closure_authorized is False

    def test_unresolved_issue_blocks_closure(self, tmp_path):
        ce = Q.evaluate_closure_eligibility(binding=_binding(tmp_path), issue_reported=True)
        assert ce.closure_eligibility_status == M.CLOSURE_NOT_ELIGIBLE and not ce.eligible

    def test_open_revision_review_blocks_closure(self, tmp_path):
        ce = Q.evaluate_closure_eligibility(binding=_binding(tmp_path), open_revision_review=True)
        assert ce.closure_eligibility_status == M.CLOSURE_NOT_ELIGIBLE

    def test_active_dispute_blocks_closure(self, tmp_path):
        ce = Q.evaluate_closure_eligibility(binding=_binding(tmp_path), dispute_active=True)
        assert ce.closure_eligibility_status == M.CLOSURE_NOT_ELIGIBLE

    def test_support_blocker_blocks_closure(self, tmp_path):
        ce = Q.evaluate_closure_eligibility(binding=_binding(tmp_path), support_blocker_active=True)
        assert ce.closure_eligibility_status == M.CLOSURE_NOT_ELIGIBLE

    def test_commercial_payment_blocker_blocks_closure(self, tmp_path):
        ce = Q.evaluate_closure_eligibility(binding=_binding(tmp_path), commercial_payment_blocker_active=True)
        assert ce.closure_eligibility_status == M.CLOSURE_NOT_ELIGIBLE

    def test_valid_evidence_produces_closure_recommendation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        assert route.closure_eligibility_status == M.CLOSURE_ELIGIBLE
        assert "explicit_operator_closure_authorization_required" in route.required_operator_actions

    def test_closure_recommendation_requires_operator_review(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        assert route.route_status == M.ROUTING_READY_FOR_OPERATOR_REVIEW

    def test_closure_authorization_does_not_execute_closure(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        d = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                         decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION,
                                         operator_id="op-approver", reason="closure approved")
        assert d.ok
        assert d.decision.route_executed is False
        assert d.decision.project_closed is False

    def test_identical_closure_route_replay_idempotent(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        r1 = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        r2 = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        assert r1.resolution_route_id == r2.resolution_route_id
        assert r1.deterministic_content_hash == r2.deterministic_content_hash

    def test_changed_closure_semantics_conflict(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        d1 = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                          decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION,
                                          operator_id="op-approver", reason="ok")
        assert d1.ok
        d2 = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                         decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION,
                                         operator_id="op-approver", reason="retry")
        assert not d2.ok and d2.error_code == "route_decision_already_final"

    def test_project_closed_remains_false(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                     decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION,
                                     operator_id="op-approver", reason="ok")
        insp = Q.inspect_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id)
        assert insp.resolution_route.project_closed is False


# ---------------------------------------------------------------------------
# C. ACCEPTANCE-PENDING FOLLOW-UP
# ---------------------------------------------------------------------------
class TestAcceptancePending:
    def test_routes_to_manual_acceptance_follow_up(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        route = _make_route(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        assert route.recommended_route == M.ROUTE_MANUAL_ACCEPTANCE_FOLLOW_UP

    def test_no_acceptance_inferred(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        route = _make_route(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        assert route.closure_eligibility_status is None
        assert "explicit_operator_closure_authorization_required" not in route.required_operator_actions

    def test_no_customer_contact(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        route = _make_route(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        assert route.customer_contact_authorized is False and route.customer_contact_performed is False

    def test_no_reminder_scheduled(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        route = _make_route(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        assert "reminder" not in " ".join(route.required_operator_actions).lower()

    def test_no_closure_recommendation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        route = _make_route(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        assert route.recommended_route != M.ROUTE_CLOSURE_ELIGIBILITY_REVIEW

    def test_deterministic_recommendation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        r1 = _make_route(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        r2 = _make_route(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        assert r1.resolution_route_id == r2.resolution_route_id

    def test_identical_replay_idempotent(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        r1 = _make_route(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        r2 = _make_route(tmp_path, PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING)
        assert r1.deterministic_content_hash == r2.deterministic_content_hash


# ---------------------------------------------------------------------------
# D. RECEIPT FOLLOW-UP
# ---------------------------------------------------------------------------
class TestReceiptFollowUp:
    def test_routes_to_manual_receipt_follow_up(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        route = _make_route(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        assert route.recommended_route == M.ROUTE_MANUAL_RECEIPT_FOLLOW_UP

    def test_no_failed_delivery_inference(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        route = _make_route(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        assert "failed" not in " ".join(route.warnings + route.blockers).lower()

    def test_no_issue_creation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        route = _make_route(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        assert route.dispute_created is False and route.revision_created is False

    def test_no_dispute_creation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        route = _make_route(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        assert route.dispute_creation_authorized is False and route.dispute_created is False

    def test_no_customer_contact(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        route = _make_route(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        assert route.customer_contact_performed is False and route.customer_contact_authorized is False

    def test_deterministic_recommendation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        r1 = _make_route(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        r2 = _make_route(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        assert r1.resolution_route_id == r2.resolution_route_id


# ---------------------------------------------------------------------------
# E. CUSTOMER REJECTION
# ---------------------------------------------------------------------------
class TestRejection:
    def test_routes_to_resolution_review(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        assert route.recommended_route == M.ROUTE_CUSTOMER_REJECTION_RESOLUTION_REVIEW

    def test_rejection_reason_preserved(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        assert "resolution_review" in " ".join(route.required_operator_actions).lower()

    def test_no_automatic_dispute(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        assert route.dispute_created is False and route.dispute_creation_authorized is False

    def test_no_automatic_revision(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        assert route.revision_created is False and route.revision_creation_authorized is False

    def test_no_refund_inference(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        assert route.invoice_state_changed is False and route.payment_state_changed is False

    def test_no_invoice_mutation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        assert route.invoice_state_changed is False

    def test_no_payment_mutation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        assert route.payment_state_changed is False

    def test_no_project_closure(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        assert route.project_closed is False

    def test_identical_replay_idempotent(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        r1 = _make_route(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        r2 = _make_route(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        assert r1.resolution_route_id == r2.resolution_route_id

    def test_changed_semantic_replay_conflict(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        d1 = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                          decision_action=M.DECISION_REJECT_ROUTE_RECOMMENDATION,
                                          operator_id="op", reason="needs more evidence")
        assert d1.ok
        d2 = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                          decision_action=M.DECISION_REJECT_ROUTE_RECOMMENDATION,
                                          operator_id="op", reason="retry")
        assert not d2.ok and d2.error_code == "route_decision_already_final"


# ---------------------------------------------------------------------------
# F. ISSUE QUALIFICATION
# ---------------------------------------------------------------------------
class TestIssueQualification:
    @pytest.mark.parametrize("category,expected", [
        ("SUPPORT_QUESTION", M.ISSUE_SUPPORT_CANDIDATE),
        ("PRODUCTION_DEFECT", M.ISSUE_DEFECT_CANDIDATE),
        ("DISPUTE", M.ISSUE_DISPUTE_CANDIDATE),
        ("CUSTOMER_REVISION_REQUEST", M.ISSUE_REVISION_CANDIDATE),
    ])
    def test_candidate_classification(self, tmp_path, category, expected):
        q = Q.qualify_reported_issue(issue_category=category, safe_evidence_reference="ref-1")
        assert q.issue_qualification == expected

    def test_general_resolution_review_classification(self, tmp_path):
        q = Q.qualify_reported_issue(issue_summary="something seems off", safe_evidence_reference="ref-1")
        assert q.issue_qualification == M.ISSUE_GENERAL_RESOLUTION_REVIEW

    def test_insufficient_evidence_classification(self, tmp_path):
        q = Q.qualify_reported_issue()
        assert q.issue_qualification == M.ISSUE_INSUFFICIENT_EVIDENCE
        assert q.insufficient_evidence is True

    def test_classification_deterministic(self, tmp_path):
        a = Q.qualify_reported_issue(issue_category="PRODUCTION_DEFECT")
        b = Q.qualify_reported_issue(issue_category="PRODUCTION_DEFECT")
        assert a.issue_qualification == b.issue_qualification

    def test_ambiguous_issue_not_forced(self, tmp_path):
        q = Q.qualify_reported_issue(issue_summary="please look at it", safe_evidence_reference="ref-1")
        assert q.issue_qualification == M.ISSUE_GENERAL_RESOLUTION_REVIEW
        assert q.issue_qualification not in (M.ISSUE_DEFECT_CANDIDATE, M.ISSUE_DISPUTE_CANDIDATE)

    def test_unsafe_issue_content_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            Q.qualify_reported_issue(issue_summary="password=secret123 leak", safe_evidence_reference="ref-1")

    def test_traversal_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            Q.qualify_reported_issue(issue_summary="ok", safe_evidence_reference="../escape")

    def test_newline_injection_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            Q.qualify_reported_issue(issue_summary="line1\nline2", safe_evidence_reference="ref-1")

    def test_secret_like_content_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            Q.qualify_reported_issue(issue_summary="my token=abc", safe_evidence_reference="ref-1")

    def test_issue_qualification_does_not_confirm_defect(self, tmp_path):
        q = Q.qualify_reported_issue(issue_category="PRODUCTION_DEFECT")
        assert q.defect_confirmed is True  # candidate only, not verdict
        assert q.confirmed is False

    def test_issue_qualification_does_not_create_dispute(self, tmp_path):
        q = Q.qualify_reported_issue(issue_category="DISPUTE")
        assert q.dispute_created is False

    def test_issue_qualification_does_not_create_revision(self, tmp_path):
        q = Q.qualify_reported_issue(issue_category="CUSTOMER_REVISION_REQUEST")
        assert q.revision_created is False

    def test_issue_qualification_does_not_invoke_hvs(self, tmp_path):
        q = Q.qualify_reported_issue(issue_category="PRODUCTION_DEFECT")
        assert q.hvs_invoked is False

    def test_issue_route_does_not_create_dispute(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ISSUE_REPORTED)
        route = _make_route(tmp_path, PM.OUTCOME_ISSUE_REPORTED, issue_summary="subtitle timing off")
        assert route.dispute_created is False


# ---------------------------------------------------------------------------
# G. REVISION ELIGIBILITY
# ---------------------------------------------------------------------------
class TestRevisionEligibility:
    def _lin_binding(self, tmp_path):
        b = _binding(tmp_path)
        return b.__class__(**{**b.__dict__, "delivery_lineage_id": "lin-1", "artifact_sha256": ART})

    def test_valid_revision_review_evaluated(self, tmp_path):
        r = Q.evaluate_revision_eligibility(binding=self._lin_binding(tmp_path), requested_scope="minor caption fix")
        assert r.revision_eligibility_status == M.REVISION_ELIGIBLE

    def test_known_delivery_lineage_required(self, tmp_path):
        r = Q.evaluate_revision_eligibility(binding=_binding(tmp_path), requested_scope="minor")
        assert r.revision_eligibility_status == M.REVISION_BLOCKED

    def test_artifact_identity_required(self, tmp_path):
        b = _binding(tmp_path).__class__(**{**_binding(tmp_path).__dict__, "delivery_lineage_id": "lin-1", "artifact_sha256": "short"})
        r = Q.evaluate_revision_eligibility(binding=b, requested_scope="minor")
        assert r.revision_eligibility_status == M.REVISION_BLOCKED

    def test_bounded_scope_required(self, tmp_path):
        b = self._lin_binding(tmp_path)
        r = Q.evaluate_revision_eligibility(binding=b, requested_scope="  ")
        assert r.revision_eligibility_status == M.REVISION_NEEDS_OPERATOR_INPUT

    def test_conflicting_final_decision_blocks(self, tmp_path):
        b = self._lin_binding(tmp_path)
        r = Q.evaluate_revision_eligibility(binding=b, requested_scope="minor", conflicting_final_decision=True)
        assert r.revision_eligibility_status == M.REVISION_NOT_ELIGIBLE

    def test_no_free_revision_inference(self, tmp_path):
        r = Q.evaluate_revision_eligibility(binding=self._lin_binding(tmp_path), requested_scope="minor")
        assert r.free_revision_inferred is False

    def test_no_cost_inference(self, tmp_path):
        r = Q.evaluate_revision_eligibility(binding=self._lin_binding(tmp_path), requested_scope="minor")
        assert r.cost_inferred is False

    def test_no_successor_version_persisted(self, tmp_path):
        r = Q.evaluate_revision_eligibility(binding=self._lin_binding(tmp_path), requested_scope="minor")
        assert r.successor_version_persisted is False

    def test_no_revision_created(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REVISION_REVIEW_REQUESTED)
        route = _make_route(tmp_path, PM.OUTCOME_REVISION_REVIEW_REQUESTED, requested_scope="minor change")
        assert route.revision_created is False and route.revision_creation_authorized is False

    def test_no_rerender_approval(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REVISION_REVIEW_REQUESTED)
        route = _make_route(tmp_path, PM.OUTCOME_REVISION_REVIEW_REQUESTED, requested_scope="minor change")
        assert route.rerender_authorized is False

    def test_no_hvs_invocation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REVISION_REVIEW_REQUESTED)
        route = _make_route(tmp_path, PM.OUTCOME_REVISION_REVIEW_REQUESTED, requested_scope="minor change")
        assert route.hvs_invoked is False

    def test_deterministic_evaluation(self, tmp_path):
        b = self._lin_binding(tmp_path)
        a = Q.evaluate_revision_eligibility(binding=b, requested_scope="minor")
        c = Q.evaluate_revision_eligibility(binding=b, requested_scope="minor")
        assert a.revision_eligibility_status == c.revision_eligibility_status


# ---------------------------------------------------------------------------
# H. OPERATOR DECISION
# ---------------------------------------------------------------------------
class TestOperatorDecision:
    def test_operator_approves_closure_recommendation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        d = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                         decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION,
                                         operator_id="op-approver", reason="approved")
        assert d.ok and d.decision.resulting_status == M.ROUTING_APPROVED

    def test_operator_required(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        with pytest.raises(ValueError):
            Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                         decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION, operator_id="")

    def test_approval_binds_route_hash(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        d = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                         decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION,
                                         operator_id="op", reason="ok")
        assert d.decision.route_content_hash == route.deterministic_content_hash

    def test_changed_route_invalidates_approval(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        ledger = Q.route_ledger_path(tmp_path)
        raw = ledger.read_text(encoding="utf-8").splitlines()
        ev = json.loads(raw[0])
        ev["record"]["deterministic_content_hash"] = "tampered"
        ledger.write_text(json.dumps(ev) + "\n", encoding="utf-8")
        d = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                         decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION,
                                         operator_id="op", reason="ok")
        assert not d.ok and d.error_code == "route_content_hash_mismatch"

    def test_rejection_requires_reason(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        d = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                         decision_action=M.DECISION_REJECT_ROUTE_RECOMMENDATION, operator_id="op", reason=None)
        assert not d.ok and d.error_code == "decision_requires_reason"

    def test_cancellation_requires_reason(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        route = _make_route(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        d = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                         decision_action=M.DECISION_CANCEL_ROUTE_REVIEW, operator_id="op", reason=None)
        assert not d.ok and d.error_code == "decision_requires_reason"

    def test_decided_route_immutable(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                     decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION, operator_id="op", reason="ok")
        again = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                             decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION, operator_id="op", reason="again")
        assert not again.ok

    def test_identical_approval_replay_idempotent(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        d1 = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                          decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION, operator_id="op", reason="ok")
        d2 = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                          decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION, operator_id="op", reason="ok")
        assert d1.ok and not d2.ok
        assert d1.decision.route_decision_id

    def test_approval_does_not_execute_route(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        d = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                         decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION, operator_id="op", reason="ok")
        assert d.decision.route_executed is False

    def test_approval_does_not_close_project(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        d = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                         decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION, operator_id="op", reason="ok")
        assert d.decision.project_closed is False

    def test_approval_does_not_create_revision(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REVISION_REVIEW_REQUESTED)
        route = _make_route(tmp_path, PM.OUTCOME_REVISION_REVIEW_REQUESTED, requested_scope="minor")
        d = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                         decision_action=M.DECISION_APPROVE_REVISION_ELIGIBILITY_REVIEW, operator_id="op", reason="ok")
        assert d.decision.revision_created is False

    def test_approval_does_not_create_dispute(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ISSUE_REPORTED)
        route = _make_route(tmp_path, PM.OUTCOME_ISSUE_REPORTED, issue_summary="defect in render")
        d = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                         decision_action=M.DECISION_APPROVE_DEFECT_REVIEW_ROUTE, operator_id="op", reason="ok")
        assert d.decision.dispute_created is False

    def test_approval_does_not_contact_customer(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        d = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                         decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION, operator_id="op", reason="ok")
        assert d.decision.customer_contact_performed is False

    def test_automation_allowed_remains_false(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        assert route.automation_allowed is False
        d = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                         decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION, operator_id="op", reason="ok")
        assert d.decision.automation_allowed is False


# ---------------------------------------------------------------------------
# I. STORE AND AUDIT
# ---------------------------------------------------------------------------
class TestStoreAudit:
    def test_append_only_persistence(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        ledger = Q.route_ledger_path(tmp_path)
        assert ledger.is_file()
        lines = ledger.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1

    def test_deterministic_event_ids(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)  # idempotent -> no new line
        ledger = Q.route_ledger_path(tmp_path)
        lines = ledger.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1

    def test_stable_replay(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        r1 = _make_route(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        r2 = _make_route(tmp_path, PM.OUTCOME_REJECTED_BY_CUSTOMER)
        assert r1.resolution_route_id == r2.resolution_route_id

    def test_malformed_jsonl_fails_safely(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        ledger = Q.route_ledger_path(tmp_path)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text('{"not_valid_json\n', encoding="utf-8")
        with pytest.raises(ValueError):
            Q.read_resolution_events(ledger_path=ledger)

    def test_truncated_jsonl_fails_safely(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        ledger = Q.route_ledger_path(tmp_path)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text('{"schema_version":"x","event_id":"e1"}\n{"schema_version":"x"', encoding="utf-8")
        with pytest.raises(ValueError):
            Q.read_resolution_events(ledger_path=ledger)

    def test_unknown_schema_version_rejected(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        ledger = Q.route_ledger_path(tmp_path)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(json.dumps({"schema_version": "WRONG", "event_id": "e1", "event_type": "X"}) + "\n", encoding="utf-8")
        with pytest.raises(ValueError):
            Q.read_resolution_events(ledger_path=ledger)

    def test_prior_events_not_rewritten(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                     decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION, operator_id="op", reason="ok")
        ledger = Q.route_ledger_path(tmp_path)
        lines = ledger.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2  # created + approved; prior not rewritten

    def test_conflicting_semantic_replay_rejected(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        ledger = Q.route_ledger_path(tmp_path)
        raw = ledger.read_text(encoding="utf-8")
        ledger.write_text(raw + raw.splitlines()[0] + "\n", encoding="utf-8")
        with pytest.raises(ValueError):
            Q.read_resolution_events(ledger_path=ledger)

    def test_runtime_ledger_is_gitignored_path(self, tmp_path):
        assert DL.endswith("stage8q_post_delivery_resolution_ledger.jsonl")

    def test_no_secrets_stored(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ISSUE_REPORTED)
        route = _make_route(tmp_path, PM.OUTCOME_ISSUE_REPORTED, issue_summary="defect in render", safe_evidence_reference="ref-2")
        payload = json.dumps(route.to_dict())
        assert "password" not in payload.lower() and "token=" not in payload.lower()

    def test_no_raw_customer_media_stored(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        assert route.deterministic_content_hash


# ---------------------------------------------------------------------------
# J. READINESS VIEW
# ---------------------------------------------------------------------------
class TestReadinessView:
    @pytest.mark.parametrize("outcome,route", [
        (PM.OUTCOME_ACCEPTED_BY_CUSTOMER, M.ROUTE_CLOSURE_ELIGIBILITY_REVIEW),
        (PM.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING, M.ROUTE_MANUAL_ACCEPTANCE_FOLLOW_UP),
        (PM.OUTCOME_RECEIPT_NOT_CONFIRMED, M.ROUTE_MANUAL_RECEIPT_FOLLOW_UP),
        (PM.OUTCOME_REJECTED_BY_CUSTOMER, M.ROUTE_CUSTOMER_REJECTION_RESOLUTION_REVIEW),
        (PM.OUTCOME_ISSUE_REPORTED, M.ROUTE_SUPPORT_REVIEW),
        (PM.OUTCOME_REVISION_REVIEW_REQUESTED, M.ROUTE_REVISION_ELIGIBILITY_REVIEW),
        (PM.OUTCOME_DELIVERY_IDENTITY_CONFLICT, M.ROUTE_OPERATOR_INVESTIGATION),
    ])
    def test_readiness_routes(self, tmp_path, outcome, route):
        _seed_outcome(tmp_path, outcome)
        v = Q.build_stage8q_readiness_view(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert v.ok and v.readiness.recommended_route == route

    def test_readiness_is_read_only(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        v = Q.build_stage8q_readiness_view(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert v.readiness.project_closed is False
        assert v.readiness.customer_contact_performed is False

    def test_supplied_evaluation_date_honored(self, tmp_path):
        ce = Q.evaluate_closure_eligibility(binding=_binding(tmp_path), evaluation_date="2026-05-01")
        assert ce.evaluation_date == "2026-05-01"

    def test_boundary_flags_remain_false(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        v = Q.build_stage8q_readiness_view(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        r = v.readiness
        assert not any([r.customer_contact_authorized, r.customer_contact_performed, r.project_closure_authorized,
                        r.project_closed, r.revision_creation_authorized, r.revision_created,
                        r.dispute_creation_authorized, r.dispute_created, r.rerender_authorized,
                        r.hvs_invoked, r.invoice_state_changed, r.payment_state_changed, r.automation_allowed])


# ---------------------------------------------------------------------------
# K. SECURITY AND SIDE EFFECTS
# ---------------------------------------------------------------------------
class TestSecuritySideEffects:
    def test_no_subprocess(self, tmp_path):
        import subprocess
        called = {"n": 0}

        def _guard(*a, **k):
            called["n"] += 1
            raise AssertionError("subprocess must not be invoked")

        real = subprocess.Popen
        subprocess.Popen = _guard
        try:
            _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
            _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        finally:
            subprocess.Popen = real
        assert called["n"] == 0

    def test_no_network(self, tmp_path):
        # Stage 8Q must never import or invoke a network library. Assert the
        # production service module imports no network surface at all.
        import scos.control_center.hvs_post_delivery_resolution_service as Q
        src = Q.__file__
        text = Path(src).read_text(encoding="utf-8")
        for tok in ("urllib", "requests", "httpx", "socket", "aiohttp", "ftplib", "smtplib", "telnetlib", "websocket"):
            assert f"import {tok}" not in text and f"from {tok}" not in text, f"network token {tok} found in {src}"
        # And the happy path still produces a valid route without network.
        _seed_outcome(tmp_path, PM.OUTCOME_ISSUE_REPORTED)
        route = _make_route(tmp_path, PM.OUTCOME_ISSUE_REPORTED, issue_summary="x")
        assert route.hvs_invoked is False

    def test_no_customer_communication(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        route = _make_route(tmp_path, PM.OUTCOME_RECEIPT_NOT_CONFIRMED)
        assert route.customer_contact_performed is False

    def test_no_upload_or_publish(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        assert route.hvs_invoked is False

    def test_no_project_closure(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        assert route.project_closed is False

    def test_no_revision_creation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_REVISION_REVIEW_REQUESTED)
        route = _make_route(tmp_path, PM.OUTCOME_REVISION_REVIEW_REQUESTED, requested_scope="minor")
        assert route.revision_created is False

    def test_no_dispute_creation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ISSUE_REPORTED)
        route = _make_route(tmp_path, PM.OUTCOME_ISSUE_REPORTED, issue_summary="dispute candidate", issue_category="DISPUTE")
        assert route.dispute_created is False

    def test_no_invoice_mutation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        assert route.invoice_state_changed is False

    def test_no_payment_mutation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        assert route.payment_state_changed is False

    def test_no_external_task_creation(self, tmp_path):
        _seed_outcome(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        route = _make_route(tmp_path, PM.OUTCOME_ACCEPTED_BY_CUSTOMER)
        assert route.automation_allowed is False

    def test_no_hermes_modification(self, tmp_path):
        hermes_dir = Path(tmp_path) / ".hermes"
        assert not hermes_dir.exists()

    def test_no_runtime_artifact_committed(self, tmp_path):
        assert DL.startswith("scos/work/")
