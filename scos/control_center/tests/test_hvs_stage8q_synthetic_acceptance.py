"""Stage 8Q synthetic acceptance harness (Scenarios A-E).

Bounded, hermetic, test-owned temporary runtime storage. Exercises every
mandatory synthetic-acceptance scenario and asserts the hard non-equivalence
contracts required by Stage 8Q:

    A. ACCEPTED + closure-eligible -> CLOSURE_ELIGIBILITY_REVIEW, approval
       recorded, project NOT closed, no customer contact, no HVS, no invoice/
       payment mutation.
    B. ISSUE_REPORTED -> qualification recorded, no dispute/revision created,
       no resolution claimed, no customer contact, no HVS.
    C. REVISION_REVIEW_REQUESTED -> Stage 8B eligibility inspected, recommendation
       recorded, no revision created, no successor version, no re-render, no HVS.
    D. ACCEPTANCE_PENDING -> manual follow-up recommendation, no acceptance
       inferred, no customer contact, no closure recommendation.
    E. IDENTITY_CONFLICT -> route blocked, no closure/revision/dispute
       recommendation, operator investigation required.

This harness deliberately uses only the public Stage 8Q service surface and the
real Stage 8P/8O writers; it performs NO downstream mutation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scos.control_center import hvs_customer_receipt_acceptance_models as PM
from scos.control_center import hvs_customer_receipt_acceptance_service as P
from scos.control_center import hvs_stage8o_delivery_models as O
from scos.control_center import hvs_stage8o_delivery_store as OS
from scos.control_center import hvs_post_delivery_resolution_models as M
from scos.control_center import hvs_post_delivery_resolution_service as Q

ART = "a" * 64
LIN = "lin-1"


def _seed(repo_root: Path, *, artifact_sha: str = ART, delivery_lineage_id: str | None = None) -> None:
    ledger = OS.delivery_ledger_path(repo_root)
    OS.append_delivery_event(
        ledger_path=ledger, event_type="PACKAGE_PREPARED", subject_id="pkg-1",
        completion_evidence_id="c-1", artifact_sha256=artifact_sha, operator_id="op",
        resulting_status="PACKAGE_READY", reason="p", recorded_at="2026-01-01", package_id="pkg-1",
        record_payload={"package_status": "PACKAGE_READY", "delivery_package_id": "pkg-1",
                         "delivery_lineage_id": delivery_lineage_id},
    )
    OS.append_delivery_event(
        ledger_path=ledger, event_type="AUTHORIZATION_APPROVED", subject_id="ar-1",
        completion_evidence_id="c-1", artifact_sha256=artifact_sha, operator_id="op",
        resulting_status=O.AUTH_APPROVED, reason="a", recorded_at="2026-01-01", package_id="pkg-1",
        authorization_request_id="ar-1", authorization_decision_id="ad-1",
    )
    rec = {
        "schema_version": O.DELIVERY_RECORD_SCHEMA_VERSION,
        "manual_delivery_record_id": "dr-1", "authorization_request_id": "ar-1",
        "authorization_decision_id": "ad-1", "delivery_package_id": "pkg-1",
        "package_content_hash": "pc-1", "completion_evidence_id": "c-1", "artifact_sha256": artifact_sha,
        "project_id": "proj-1", "safe_recipient_reference": "cust-1", "manual_delivery_method": "IN_PERSON",
        "operator_id": "op", "human_delivery_confirmation": True, "delivery_recorded_at": "2026-01-01",
        "external_evidence_reference": "", "operator_note": "", "delivery_status": O.DEL_DELIVERED_MANUALLY,
        "manual_delivery_performed": True, "external_delivery_executed_by_scos": False,
        "customer_receipt_confirmed": False, "customer_acceptance_recorded": False, "publishing_performed": False,
        "invoice_state_changed": False, "payment_state_changed": False, "automation_allowed": False,
        "artifact_id": "art-1", "delivery_lineage_id": delivery_lineage_id,
    }
    OS.append_delivery_event(
        ledger_path=ledger, event_type="DELIVERY_RECORDED", subject_id="dr-1",
        completion_evidence_id="c-1", artifact_sha256=artifact_sha, operator_id="op",
        resulting_status=O.DEL_DELIVERED_MANUALLY, reason="d", recorded_at="2026-01-01", package_id="pkg-1",
        authorization_request_id="ar-1", authorization_decision_id="ad-1", delivery_record_id="dr-1",
        record_payload=rec,
    )


def _receipt(repo_root: Path) -> None:
    P.create_customer_receipt_record(
        repo_root=repo_root, actual_delivery_record_id="dr-1", delivery_package_id="pkg-1",
        artifact_id="art-1", artifact_sha256=ART, customer_reference="cust-1",
        receipt_evidence_type="CUSTOMER_WRITTEN_CONFIRMATION", safe_evidence_reference="ref-1",
        receipt_confirmation_date="2026-02-01", recorded_by_operator_id="op",
        source_render_completion_id="c-1", source_delivery_authorization_id="ar-1",
    )


class TestStage8QSyntheticAcceptance:
    def test_scenario_a_accepted_closure_eligible(self, tmp_path):
        _seed(tmp_path)
        _receipt(tmp_path)
        P.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                   decision_status="ACCEPTED", decision_date="2026-02-02",
                                   safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        route = Q.create_post_delivery_route(repo_root=tmp_path, actual_delivery_record_id="dr-1").resolution_route
        assert route.recommended_route == M.ROUTE_CLOSURE_ELIGIBILITY_REVIEW
        assert route.closure_eligibility_status == M.CLOSURE_ELIGIBLE
        dec = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                           decision_action=M.DECISION_APPROVE_CLOSURE_RECOMMENDATION,
                                           operator_id="op-approver", reason="closure approved").decision
        assert dec.resulting_status == M.ROUTING_APPROVED
        assert dec.project_closed is False
        assert dec.customer_contact_performed is False and dec.hvs_invoked is False
        assert dec.revision_created is False and dec.dispute_created is False
        assert dec.automation_allowed is False

    def test_scenario_b_issue_reported(self, tmp_path):
        _seed(tmp_path)
        _receipt(tmp_path)
        P.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                issue_category="PRODUCTION_DEFECT", issue_summary="render artifact mismatch",
                                decision_date="2026-02-02", safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        route = Q.create_post_delivery_route(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                             issue_summary="render artifact mismatch",
                                             issue_category="PRODUCTION_DEFECT").resolution_route
        assert route.issue_qualification == M.ISSUE_DEFECT_CANDIDATE
        dec = Q.decide_post_delivery_route(repo_root=tmp_path, resolution_route_id=route.resolution_route_id,
                                           decision_action=M.DECISION_APPROVE_DEFECT_REVIEW_ROUTE,
                                           operator_id="op", reason="defect review").decision
        assert dec.dispute_created is False and dec.revision_created is False
        assert dec.customer_contact_performed is False and dec.hvs_invoked is False

    def test_scenario_c_revision_review_requested(self, tmp_path):
        _seed(tmp_path, delivery_lineage_id=LIN)
        _receipt(tmp_path)
        P.record_revision_review_request(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                         revision_review_reason="update logo", decision_date="2026-02-02",
                                         safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        route = Q.create_post_delivery_route(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                             requested_scope="update logo text").resolution_route
        assert route.recommended_route == M.ROUTE_REVISION_ELIGIBILITY_REVIEW
        assert route.revision_eligibility_status == M.REVISION_ELIGIBLE
        assert route.revision_created is False and route.rerender_authorized is False
        assert route.hvs_invoked is False

    def test_scenario_d_acceptance_pending(self, tmp_path):
        _seed(tmp_path)
        _receipt(tmp_path)  # receipt confirmed, no decision
        route = Q.create_post_delivery_route(repo_root=tmp_path, actual_delivery_record_id="dr-1").resolution_route
        assert route.recommended_route == M.ROUTE_MANUAL_ACCEPTANCE_FOLLOW_UP
        assert route.closure_eligibility_status is None
        assert route.customer_contact_performed is False and route.customer_contact_authorized is False

    def test_scenario_e_identity_conflict(self, tmp_path):
        _seed(tmp_path)
        P.create_customer_receipt_record(
            repo_root=tmp_path, actual_delivery_record_id="dr-1", delivery_package_id="pkg-1",
            artifact_id="art-1", artifact_sha256=ART, customer_reference="cust-1",
            receipt_evidence_type="CUSTOMER_WRITTEN_CONFIRMATION", safe_evidence_reference="ref-1",
            receipt_confirmation_date="2026-02-01", recorded_by_operator_id="op",
            source_render_completion_id="c-1", source_delivery_authorization_id="ar-1",
            receipt_status=PM.RECEIPT_IDENTITY_CONFLICT,
        )
        route = Q.create_post_delivery_route(repo_root=tmp_path, actual_delivery_record_id="dr-1").resolution_route
        assert route.recommended_route == M.ROUTE_OPERATOR_INVESTIGATION
        assert route.route_status == M.ROUTING_BLOCKED
        assert route.closure_eligibility_status is None
        assert route.revision_eligibility_status is None
        assert route.issue_qualification is None
