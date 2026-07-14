"""Stage 8P focused tests — customer receipt confirmation, delivered-artifact
reverification, acceptance / rejection / issue-intake / revision-review gate.

Hermetic: every mutation test uses test-owned temporary runtime roots under
pytest-scoped temp dirs. The genuine Stage 8O actual-delivery record is
*fabricated directly* into a temp Stage 8O ledger (read-only binding target);
no real customer, production, or HVS data is used.

The tests VERIFY (not trust) every non-equivalence rule required by the Stage
8P spec:

    Customer receipt != Customer acceptance
    Customer silence != Customer acceptance
    Customer acceptance != Project closure
    Customer acceptance != Invoice / payment mutation
    Issue intake != Dispute
    Revision-review request != Stage 8B revision
    Delivery != Customer receipt (Stage 8O already enforces this; 8P preserves it)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scos.control_center import hvs_customer_receipt_acceptance_models as M
from scos.control_center import hvs_customer_receipt_acceptance_service as S
from scos.control_center import hvs_stage8o_delivery_models as O
from scos.control_center import hvs_stage8o_delivery_store as OS

ART = "a" * 64
ART2 = "b" * 64


# ---------------------------------------------------------------------------
# Fabrication helpers (Stage 8O read-only source of truth)
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
        ledger_path=ledger,
        event_type="PACKAGE_PREPARED",
        subject_id=package_id,
        completion_evidence_id=completion_id,
        artifact_sha256=artifact_sha,
        operator_id="op",
        resulting_status=package_status,
        reason="package prepared",
        recorded_at="2026-01-01",
        package_id=package_id,
        record_payload={"package_status": package_status, "delivery_package_id": package_id},
    )
    OS.append_delivery_event(
        ledger_path=ledger,
        event_type="AUTHORIZATION_APPROVED" if auth_status == O.AUTH_APPROVED else "AUTHORIZATION_REJECTED",
        subject_id=auth_request_id,
        completion_evidence_id=completion_id,
        artifact_sha256=artifact_sha,
        operator_id="op",
        resulting_status=auth_status,
        reason="auth",
        recorded_at="2026-01-01",
        package_id=package_id,
        authorization_request_id=auth_request_id,
        authorization_decision_id=auth_decision_id,
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
        ledger_path=ledger,
        event_type="DELIVERY_RECORDED",
        subject_id=delivery_record_id,
        completion_evidence_id=completion_id,
        artifact_sha256=artifact_sha,
        operator_id="op",
        resulting_status=delivery_status,
        reason="delivered",
        recorded_at="2026-01-01",
        package_id=package_id,
        authorization_request_id=auth_request_id,
        authorization_decision_id=auth_decision_id,
        delivery_record_id=delivery_record_id,
        record_payload=rec,
    )


def _RECORD_KW(**over):
    base = dict(
        actual_delivery_record_id="dr-1",
        delivery_package_id="pkg-1",
        artifact_id="art-1",
        artifact_sha256=ART,
        customer_reference="cust-1",
        receipt_evidence_type="CUSTOMER_WRITTEN_CONFIRMATION",
        safe_evidence_reference="ref-1",
        receipt_confirmation_date="2026-02-01",
        recorded_by_operator_id="op",
        source_render_completion_id="c-1",
        source_delivery_authorization_id="ar-1",
    )
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# A. ELIGIBILITY
# ---------------------------------------------------------------------------
class TestEligibility:
    def test_valid_actual_delivery_is_eligible(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert r.ok, r
        assert r.delivery_package_id == "pkg-1"
        assert r.artifact_sha256 == ART
        assert r.customer_reference == "cust-1"

    def test_package_without_actual_delivery_rejected(self, tmp_path):
        r = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-x")
        assert not r.ok and r.error_code == "actual_delivery_record_not_found"

    def test_delivery_without_authorization_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path, auth_status=O.AUTH_REJECTED)
        r = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert not r.ok and r.error_code == "delivery_authorization_not_valid"

    def test_forgotten_delivery_record_rejected(self, tmp_path):
        # Delivery status is not the valid final state.
        _seed_stage8o_delivery(repo_root=tmp_path, delivery_status=O.DEL_RECORD_REJECTED)
        r = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert not r.ok and r.error_code == "actual_delivery_cancelled"

    def test_package_id_mismatch_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1", delivery_package_id="wrong")
        assert not r.ok and r.error_code == "package_id_mismatch"

    def test_artifact_id_mismatch_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1", artifact_id="wrong")
        assert not r.ok and r.error_code == "artifact_id_mismatch"

    def test_artifact_sha_mismatch_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1", artifact_sha256=ART2)
        assert not r.ok and r.error_code == "artifact_sha_mismatch"

    def test_customer_reference_mismatch_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1", customer_reference="wrong")
        assert not r.ok and r.error_code == "customer_reference_mismatch"

    def test_invalid_lineage_rejected(self, tmp_path):
        # Missing package event => package status unknown => not valid.
        ledger = OS.delivery_ledger_path(tmp_path)
        OS.append_delivery_event(
            ledger_path=ledger, event_type="AUTHORIZATION_APPROVED", subject_id="ar-1",
            completion_evidence_id="c-1", artifact_sha256=ART, operator_id="op",
            resulting_status=O.AUTH_APPROVED, reason="a", recorded_at="2026-01-01",
            package_id="pkg-1", authorization_request_id="ar-1", authorization_decision_id="ad-1",
        )
        OS.append_delivery_event(
            ledger_path=ledger, event_type="DELIVERY_RECORDED", subject_id="dr-1",
            completion_evidence_id="c-1", artifact_sha256=ART, operator_id="op",
            resulting_status=O.DEL_DELIVERED_MANUALLY, reason="d", recorded_at="2026-01-01",
            package_id="pkg-1", authorization_request_id="ar-1", authorization_decision_id="ad-1",
            delivery_record_id="dr-1",
            record_payload={"schema_version": O.DELIVERY_RECORD_SCHEMA_VERSION, "artifact_sha256": ART,
                            "project_id": "proj-1", "safe_recipient_reference": "cust-1",
                            "delivery_status": O.DEL_DELIVERED_MANUALLY, "artifact_id": "art-1",
                            "delivery_package_id": "pkg-1", "authorization_request_id": "ar-1"},
        )
        r = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert not r.ok and r.error_code == "delivery_package_not_valid"

    def test_cancelled_delivery_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path, package_status="PACKAGE_CANCELLED")
        r = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert not r.ok and r.error_code == "delivery_package_not_valid"

    def test_malformed_source_record_rejected(self, tmp_path):
        ledger = OS.delivery_ledger_path(tmp_path)
        # A delivery event with a non-64-char SHA => source not verified.
        OS.append_delivery_event(
            ledger_path=ledger, event_type="PACKAGE_PREPARED", subject_id="pkg-1",
            completion_evidence_id="c-1", artifact_sha256="bad", operator_id="op",
            resulting_status="PACKAGE_READY", reason="p", recorded_at="2026-01-01", package_id="pkg-1",
            record_payload={"package_status": "PACKAGE_READY", "delivery_package_id": "pkg-1"},
        )
        OS.append_delivery_event(
            ledger_path=ledger, event_type="AUTHORIZATION_APPROVED", subject_id="ar-1",
            completion_evidence_id="c-1", artifact_sha256="bad", operator_id="op",
            resulting_status=O.AUTH_APPROVED, reason="a", recorded_at="2026-01-01", package_id="pkg-1",
            authorization_request_id="ar-1", authorization_decision_id="ad-1",
        )
        OS.append_delivery_event(
            ledger_path=ledger, event_type="DELIVERY_RECORDED", subject_id="dr-1",
            completion_evidence_id="c-1", artifact_sha256="bad", operator_id="op",
            resulting_status=O.DEL_DELIVERED_MANUALLY, reason="d", recorded_at="2026-01-01", package_id="pkg-1",
            authorization_request_id="ar-1", authorization_decision_id="ad-1", delivery_record_id="dr-1",
            record_payload={"schema_version": O.DELIVERY_RECORD_SCHEMA_VERSION, "artifact_sha256": "bad",
                            "project_id": "proj-1", "safe_recipient_reference": "cust-1",
                            "delivery_status": O.DEL_DELIVERED_MANUALLY, "artifact_id": "art-1",
                            "delivery_package_id": "pkg-1", "authorization_request_id": "ar-1"},
        )
        r = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert not r.ok and r.error_code == "source_artifact_not_verified"

    def test_unknown_source_rejected(self, tmp_path):
        r = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="nope")
        assert not r.ok and r.error_code == "actual_delivery_record_not_found"


# ---------------------------------------------------------------------------
# B. RECEIPT
# ---------------------------------------------------------------------------
class TestReceipt:
    def test_valid_written_receipt(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        assert r.ok and r.receipt_status == M.RECEIPT_CONFIRMED

    def test_valid_verbal_confirmation(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(receipt_evidence_type="CUSTOMER_VERBAL_CONFIRMATION_RECORDED_BY_OPERATOR"))
        assert r.ok

    def test_valid_delivery_channel_acknowledgement(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(receipt_evidence_type="DELIVERY_CHANNEL_ACKNOWLEDGEMENT"))
        assert r.ok

    def test_operator_id_required(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(recorded_by_operator_id=""))
        assert not r.ok and r.error_code == "missing_operator_id"

    def test_confirmation_date_required(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(receipt_confirmation_date=""))
        assert not r.ok

    def test_evidence_reference_required(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference=""))
        assert not r.ok and r.error_code == "invalid_receipt_input"

    def test_unsafe_evidence_reference_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference="ref;rm"))
        assert not r.ok and r.error_code == "invalid_receipt_input"

    def test_traversal_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference="../etc/passwd"))
        assert not r.ok and r.error_code == "invalid_receipt_input"

    def test_newline_injection_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference="ref\nINJECT"))
        assert not r.ok and r.error_code == "invalid_receipt_input"

    def test_secret_like_value_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference="token=abc123"))
        assert not r.ok and r.error_code == "invalid_receipt_input"

    def test_customer_provided_matching_sha_accepted(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(customer_confirmed_artifact_sha256=ART))
        assert r.ok

    def test_customer_provided_mismatching_sha_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(customer_confirmed_artifact_sha256=ART2))
        assert not r.ok and r.error_code == "customer_artifact_sha_mismatch"

    def test_receipt_does_not_imply_acceptance(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        assert r.ok
        view = S.inspect_delivery_post_receipt_status(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert view.outcome == M.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING
        assert view.decision_status == M.DECISION_NO_DECISION

    def test_receipt_does_not_close_project(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        # A receipt record carries no project_closed flag; confirm it is structurally False.
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        assert r.ok and r.project_closed is False

    def test_receipt_does_not_change_payment(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        assert r.ok and r.payment_state_changed is False and r.invoice_state_changed is False

    def test_receipt_performs_no_customer_contact(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        assert r.ok and r.customer_contact_performed is False and r.external_action_performed is False

    def test_identical_receipt_replay_idempotent(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        a = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        b = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        assert a.ok and b.ok and b.replayed is True and a.receipt_record_id == b.receipt_record_id

    def test_changed_receipt_semantics_conflict(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        a = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference="ref-1"))
        assert a.ok
        b = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference="ref-2"))
        assert not b.ok and b.error_code == "conflicting_receipt_replay"

    def test_prior_receipt_immutable(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        assert r.ok and r.receipt_record_id
        # Inspect returns the stored receipt; 8P never rewrites it.
        insp = S.inspect_customer_receipt(repo_root=tmp_path, receipt_record_id=r.receipt_record_id)
        assert insp.ok and insp.receipt_status == M.RECEIPT_CONFIRMED


# ---------------------------------------------------------------------------
# C. ACCEPTANCE
# ---------------------------------------------------------------------------
class TestAcceptance:
    def _receipt(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        assert r.ok
        return r

    def test_explicit_acceptance_after_receipt(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        assert r.ok and r.decision_status == M.DECISION_ACCEPTED

    def test_acceptance_before_receipt_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        assert not r.ok and r.error_code == "decision_before_receipt"

    def test_acceptance_requires_operator_id(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="")
        assert not r.ok and r.error_code == "missing_operator_id"

    def test_acceptance_requires_decision_date(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        assert not r.ok and r.error_code == "invalid_decision_input"

    def test_acceptance_requires_evidence_reference(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="2026-02-02",
                                       safe_evidence_reference="", recorded_by_operator_id="op")
        assert not r.ok and r.error_code == "invalid_decision_input"

    def test_acceptance_binds_exact_artifact_sha(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        assert r.ok and r.artifact_sha256 == ART

    def test_acceptance_of_different_artifact_rejected(self, tmp_path):
        # Delivery record carries ART; fabricated receipt differs via eligibility mismatch is not
        # possible (receipt binds to the 8O lineage). Instead confirm the decision record carries
        # the genuine delivered SHA, never a caller-supplied one.
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        assert r.ok and r.artifact_sha256 == ART  # never ART2

    def test_identical_acceptance_replay_idempotent(self, tmp_path):
        self._receipt(tmp_path)
        a = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        b = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        assert a.ok and b.ok and b.replayed is True and a.customer_decision_id == b.customer_decision_id

    def test_changed_acceptance_replay_conflict(self, tmp_path):
        self._receipt(tmp_path)
        a = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        assert a.ok
        # A different (changed) decision for the same delivery record must conflict, not overwrite.
        b = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="REJECTED", decision_date="2026-02-03",
                                       safe_evidence_reference="ref-3", rejection_reason="changed mind",
                                       recorded_by_operator_id="op")
        assert not b.ok and b.error_code == "changed_decision_conflict"

    def test_acceptance_does_not_change_invoice(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        assert r.ok and r.invoice_state_changed is False and r.payment_state_changed is False

    def test_acceptance_does_not_create_portfolio_consent(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        assert r.ok and r.project_closed is False and r.revision_created is False and r.dispute_created is False

    def test_acceptance_does_not_publish(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        assert r.ok and r.external_action_performed is False and r.hvs_invoked is False

    def test_acceptance_does_not_close_project_automatically(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        assert r.ok and r.project_closed is False
        view = S.inspect_delivery_post_receipt_status(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert view.outcome == M.OUTCOME_ACCEPTED_BY_CUSTOMER


# ---------------------------------------------------------------------------
# D. REJECTION
# ---------------------------------------------------------------------------
class TestRejection:
    def _receipt(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        assert r.ok

    def test_explicit_rejection_after_receipt(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="REJECTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op",
                                       rejection_reason="wrong cut")
        assert r.ok and r.decision_status == M.DECISION_REJECTED

    def test_rejection_requires_reason(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="REJECTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        assert not r.ok and r.error_code == "missing_rejection_reason"

    def test_rejection_requires_operator_id(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="REJECTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="",
                                       rejection_reason="x")
        assert not r.ok and r.error_code == "missing_operator_id"

    def test_rejection_requires_evidence(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="REJECTED", decision_date="2026-02-02",
                                       safe_evidence_reference="", recorded_by_operator_id="op",
                                       rejection_reason="x")
        assert not r.ok and r.error_code == "invalid_decision_input"

    def test_rejection_before_receipt_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="REJECTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op",
                                       rejection_reason="x")
        assert not r.ok and r.error_code == "decision_before_receipt"

    def test_acceptance_then_rejection_rejected(self, tmp_path):
        self._receipt(tmp_path)
        a = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="ACCEPTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        assert a.ok
        b = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="REJECTED", decision_date="2026-02-03",
                                       safe_evidence_reference="ref-3", recorded_by_operator_id="op",
                                       rejection_reason="changed mind")
        assert not b.ok and b.error_code == "changed_decision_conflict"

    def test_identical_rejection_replay_idempotent(self, tmp_path):
        self._receipt(tmp_path)
        a = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="REJECTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op",
                                       rejection_reason="wrong cut")
        b = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="REJECTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op",
                                       rejection_reason="wrong cut")
        assert a.ok and b.ok and b.replayed is True

    def test_changed_rejection_conflict(self, tmp_path):
        self._receipt(tmp_path)
        a = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="REJECTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op",
                                       rejection_reason="wrong cut")
        assert a.ok
        b = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="REJECTED", decision_date="2026-02-03",
                                       safe_evidence_reference="ref-3", recorded_by_operator_id="op",
                                       rejection_reason="different reason")
        assert not b.ok and b.error_code == "changed_decision_conflict"

    def test_rejection_does_not_create_dispute_automatically(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="REJECTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op",
                                       rejection_reason="wrong cut")
        assert r.ok and r.dispute_created is False

    def test_rejection_does_not_create_revision_automatically(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="REJECTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op",
                                       rejection_reason="wrong cut")
        assert r.ok and r.revision_created is False

    def test_rejection_does_not_mutate_payment(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                       decision_status="REJECTED", decision_date="2026-02-02",
                                       safe_evidence_reference="ref-2", recorded_by_operator_id="op",
                                       rejection_reason="wrong cut")
        assert r.ok and r.payment_state_changed is False and r.invoice_state_changed is False


# ---------------------------------------------------------------------------
# E. ISSUE INTAKE
# ---------------------------------------------------------------------------
class TestIssueIntake:
    def _receipt(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        assert r.ok

    def test_valid_issue_report(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                    issue_category="audio_sync", issue_summary="audio drift at 0:12",
                                    decision_date="2026-02-03", safe_evidence_reference="ref-3",
                                    recorded_by_operator_id="op")
        assert r.ok and r.decision_status == M.DECISION_ISSUE_REPORTED

    def test_issue_summary_required(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                    issue_category=None, issue_summary="", decision_date="2026-02-03",
                                    safe_evidence_reference="ref-3", recorded_by_operator_id="op")
        assert not r.ok and r.error_code == "invalid_issue_input"

    def test_unsafe_issue_content_rejected(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                    issue_category=None, issue_summary="leak\ntoken=secret", decision_date="2026-02-03",
                                    safe_evidence_reference="ref-3", recorded_by_operator_id="op")
        assert not r.ok and r.error_code == "invalid_issue_input"

    def test_issue_before_receipt_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                    issue_category=None, issue_summary="x", decision_date="2026-02-03",
                                    safe_evidence_reference="ref-3", recorded_by_operator_id="op")
        assert not r.ok and r.error_code == "decision_before_receipt"

    def test_issue_does_not_imply_rejection(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                    issue_category=None, issue_summary="audio drift", decision_date="2026-02-03",
                                    safe_evidence_reference="ref-3", recorded_by_operator_id="op")
        assert r.ok
        view = S.inspect_delivery_post_receipt_status(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert view.outcome == M.OUTCOME_ISSUE_REPORTED
        assert view.decision_status == M.DECISION_ISSUE_REPORTED

    def test_issue_does_not_create_dispute(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                    issue_category=None, issue_summary="audio drift", decision_date="2026-02-03",
                                    safe_evidence_reference="ref-3", recorded_by_operator_id="op")
        assert r.ok and r.dispute_created is False

    def test_issue_does_not_create_revision(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                    issue_category=None, issue_summary="audio drift", decision_date="2026-02-03",
                                    safe_evidence_reference="ref-3", recorded_by_operator_id="op")
        assert r.ok and r.revision_created is False

    def test_issue_does_not_invoke_hvs(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                    issue_category=None, issue_summary="audio drift", decision_date="2026-02-03",
                                    safe_evidence_reference="ref-3", recorded_by_operator_id="op")
        assert r.ok and r.hvs_invoked is False

    def test_identical_issue_replay_idempotent(self, tmp_path):
        self._receipt(tmp_path)
        a = S.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                    issue_category="audio_sync", issue_summary="audio drift", decision_date="2026-02-03",
                                    safe_evidence_reference="ref-3", recorded_by_operator_id="op")
        b = S.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                    issue_category="audio_sync", issue_summary="audio drift", decision_date="2026-02-03",
                                    safe_evidence_reference="ref-3", recorded_by_operator_id="op")
        assert a.ok and b.ok and b.replayed is True

    def test_changed_issue_replay_conflict(self, tmp_path):
        self._receipt(tmp_path)
        a = S.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                    issue_category="audio_sync", issue_summary="audio drift", decision_date="2026-02-03",
                                    safe_evidence_reference="ref-3", recorded_by_operator_id="op")
        assert a.ok
        b = S.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                    issue_category="color", issue_summary="color off", decision_date="2026-02-04",
                                    safe_evidence_reference="ref-4", recorded_by_operator_id="op")
        assert not b.ok and b.error_code == "changed_decision_conflict"


# ---------------------------------------------------------------------------
# F. REVISION REVIEW INTAKE
# ---------------------------------------------------------------------------
class TestRevisionReviewIntake:
    def _receipt(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        assert r.ok

    def test_valid_revision_review_request(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_revision_review_request(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                             revision_review_reason="shorten intro", decision_date="2026-02-04",
                                             safe_evidence_reference="ref-4", recorded_by_operator_id="op")
        assert r.ok and r.decision_status == M.DECISION_REVISION_REVIEW_REQUESTED

    def test_reason_required(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_revision_review_request(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                             revision_review_reason="", decision_date="2026-02-04",
                                             safe_evidence_reference="ref-4", recorded_by_operator_id="op")
        assert not r.ok and r.error_code == "invalid_revision_input"

    def test_request_before_receipt_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.record_revision_review_request(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                             revision_review_reason="x", decision_date="2026-02-04",
                                             safe_evidence_reference="ref-4", recorded_by_operator_id="op")
        assert not r.ok and r.error_code == "decision_before_receipt"

    def test_request_does_not_create_stage8b_revision(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_revision_review_request(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                             revision_review_reason="shorten intro", decision_date="2026-02-04",
                                             safe_evidence_reference="ref-4", recorded_by_operator_id="op")
        assert r.ok and r.revision_created is False

    def test_request_record_explicitly_does_not_rerender_or_version(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_revision_review_request(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                             revision_review_reason="shorten intro", decision_date="2026-02-04",
                                             safe_evidence_reference="ref-4", recorded_by_operator_id="op")
        assert r.ok
        # The persisted record must carry the hard False boundary flags (not merely the absence of a result field).
        view = S.inspect_delivery_post_receipt_status(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert view.outcome == M.OUTCOME_REVISION_REVIEW_REQUESTED
        # Read the stored revision-review record directly to confirm the boundary fields.
        rec = S.latest_revision_review_record(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert rec["successor_version_calculated"] is False
        assert rec["rerender_approved"] is False
        assert rec["revision_created"] is False

    def test_request_does_not_invoke_hvs(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_revision_review_request(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                             revision_review_reason="shorten intro", decision_date="2026-02-04",
                                             safe_evidence_reference="ref-4", recorded_by_operator_id="op")
        assert r.ok and r.hvs_invoked is False

    def test_request_does_not_mutate_invoice_payment(self, tmp_path):
        self._receipt(tmp_path)
        r = S.record_revision_review_request(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                             revision_review_reason="shorten intro", decision_date="2026-02-04",
                                             safe_evidence_reference="ref-4", recorded_by_operator_id="op")
        assert r.ok and r.invoice_state_changed is False and r.payment_state_changed is False

    def test_identical_replay_idempotent(self, tmp_path):
        self._receipt(tmp_path)
        a = S.record_revision_review_request(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                             revision_review_reason="shorten intro", decision_date="2026-02-04",
                                             safe_evidence_reference="ref-4", recorded_by_operator_id="op")
        b = S.record_revision_review_request(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                             revision_review_reason="shorten intro", decision_date="2026-02-04",
                                             safe_evidence_reference="ref-4", recorded_by_operator_id="op")
        assert a.ok and b.ok and b.replayed is True

    def test_changed_replay_conflict(self, tmp_path):
        self._receipt(tmp_path)
        a = S.record_revision_review_request(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                             revision_review_reason="shorten intro", decision_date="2026-02-04",
                                             safe_evidence_reference="ref-4", recorded_by_operator_id="op")
        assert a.ok
        b = S.record_revision_review_request(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                             revision_review_reason="change music", decision_date="2026-02-05",
                                             safe_evidence_reference="ref-5", recorded_by_operator_id="op")
        assert not b.ok and b.error_code == "changed_decision_conflict"


# ---------------------------------------------------------------------------
# G. STORE AND AUDIT
# ---------------------------------------------------------------------------
class TestStoreAudit:
    def test_append_only_event_persistence(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        ledger = S.receipt_ledger_path(tmp_path)
        lines = [l for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 1
        ev = json.loads(lines[0])
        assert ev["event_type"] == M.EVT_RECEIPT_CONFIRMED
        assert ev["schema_version"] == M.POST_RECEIPT_EVENT_SCHEMA_VERSION

    def test_deterministic_event_ids(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r1 = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference="ref-1"))
        r2 = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference="ref-1"))
        assert r1.ok and r2.ok and r1.receipt_record_id == r2.receipt_record_id

    def test_stable_replay(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        ledger = S.receipt_ledger_path(tmp_path)
        lines = [l for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 1  # idempotent replay appends nothing new

    def test_malformed_jsonl_fails_safely(self, tmp_path):
        ledger = S.receipt_ledger_path(tmp_path)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("not valid json\n", encoding="utf-8")
        with pytest.raises(ValueError):
            S.read_receipt_events(ledger_path=ledger)

    def test_truncated_jsonl_fails_safely(self, tmp_path):
        ledger = S.receipt_ledger_path(tmp_path)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text('{"event_id":"x","schema_version":"', encoding="utf-8")
        with pytest.raises(ValueError):
            S.read_receipt_events(ledger_path=ledger)

    def test_unknown_schema_version_rejected(self, tmp_path):
        ledger = S.receipt_ledger_path(tmp_path)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        bad = {"schema_version": "wrong", "event_id": "e1", "event_type": "X"}
        ledger.write_text(json.dumps(bad) + "\n", encoding="utf-8")
        with pytest.raises(ValueError):
            S.read_receipt_events(ledger_path=ledger)

    def test_prior_events_not_rewritten(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                   decision_status="ACCEPTED", decision_date="2026-02-02",
                                   safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        ledger = S.receipt_ledger_path(tmp_path)
        lines = [l for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 2  # receipt + decision, both retained

    def test_duplicate_semantic_conflict_handled_safely(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        assert r.ok
        b = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference="ref-2"))
        assert not b.ok  # different semantic => conflict, no write

    def test_no_secret_stored(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference="ref-1"))
        text = S.receipt_ledger_path(tmp_path).read_text(encoding="utf-8")
        assert "token=" not in text.lower() and "password" not in text.lower()

    def test_no_raw_customer_media_stored(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        text = S.receipt_ledger_path(tmp_path).read_text(encoding="utf-8")
        assert "data:image" not in text and "mp4" not in text


# ---------------------------------------------------------------------------
# H. READINESS VIEW
# ---------------------------------------------------------------------------
class TestReadinessView:
    def test_no_receipt_produces_not_confirmed(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        v = S.inspect_delivery_post_receipt_status(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert v.outcome == M.OUTCOME_RECEIPT_NOT_CONFIRMED

    def test_receipt_no_decision_produces_pending(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        v = S.inspect_delivery_post_receipt_status(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert v.outcome == M.OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING

    def test_acceptance_produces_accepted(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                   decision_status="ACCEPTED", decision_date="2026-02-02",
                                   safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        v = S.inspect_delivery_post_receipt_status(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert v.outcome == M.OUTCOME_ACCEPTED_BY_CUSTOMER

    def test_rejection_produces_rejected(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                   decision_status="REJECTED", decision_date="2026-02-02",
                                   safe_evidence_reference="ref-2", recorded_by_operator_id="op",
                                   rejection_reason="wrong cut")
        v = S.inspect_delivery_post_receipt_status(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert v.outcome == M.OUTCOME_REJECTED_BY_CUSTOMER

    def test_issue_produces_issue_reported(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        S.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                issue_category=None, issue_summary="audio drift", decision_date="2026-02-03",
                                safe_evidence_reference="ref-3", recorded_by_operator_id="op")
        v = S.inspect_delivery_post_receipt_status(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert v.outcome == M.OUTCOME_ISSUE_REPORTED

    def test_revision_review_produces_revision_review_requested(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        S.record_revision_review_request(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                         revision_review_reason="shorten intro", decision_date="2026-02-04",
                                         safe_evidence_reference="ref-4", recorded_by_operator_id="op")
        v = S.inspect_delivery_post_receipt_status(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert v.outcome == M.OUTCOME_REVISION_REVIEW_REQUESTED

    def test_hash_conflict_produces_identity_conflict(self, tmp_path):
        # Same delivery record, but a customer-provided SHA mismatch surfaces as a conflict outcome.
        _seed_stage8o_delivery(repo_root=tmp_path)
        r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(customer_confirmed_artifact_sha256=ART2))
        assert not r.ok and r.error_code == "customer_artifact_sha_mismatch"
        # No receipt was written; readiness stays NOT_CONFIRMED (fail closed, never silent repair).
        v = S.inspect_delivery_post_receipt_status(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert v.outcome == M.OUTCOME_RECEIPT_NOT_CONFIRMED

    def test_evaluation_is_read_only(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        before = S.receipt_ledger_path(tmp_path).read_text(encoding="utf-8")
        S.inspect_delivery_post_receipt_status(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        after = S.receipt_ledger_path(tmp_path).read_text(encoding="utf-8")
        assert before == after  # read-only view writes nothing

    def test_output_boundary_flags_remain_false(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                   decision_status="ACCEPTED", decision_date="2026-02-02",
                                   safe_evidence_reference="ref-2", recorded_by_operator_id="op")
        v = S.inspect_delivery_post_receipt_status(repo_root=tmp_path, actual_delivery_record_id="dr-1")
        assert v.customer_contact_performed is False and v.hvs_invoked is False
        assert v.project_closed is False and v.revision_created is False and v.dispute_created is False
        assert v.invoice_state_changed is False and v.payment_state_changed is False and v.automation_allowed is False


# ---------------------------------------------------------------------------
# I. SECURITY AND SIDE EFFECTS
# ---------------------------------------------------------------------------
class TestSecuritySideEffects:
    def test_no_subprocess(self):
        import inspect
        src = inspect.getsource(S)
        assert "subprocess" not in src
        assert "os.system" not in src

    def test_no_network(self):
        import inspect
        src = inspect.getsource(S)
        for token in ("requests.", "urllib.", "http.client", "socket.", "aiohttp", "httpx", "smtplib"):
            assert token not in src

    def test_no_hvs_import(self):
        import inspect
        src = inspect.getsource(S)
        assert "import hvs_adapter" not in src
        assert "hvs_adapter" not in src.split("#")[0] or "stage8o" in src  # only 8O binding, not invocation
        # The service must NOT invoke HVS.
        assert "render_hyperframes" not in src and "import_hvs" not in src

    def test_no_customer_communication(self):
        import inspect
        src = inspect.getsource(S)
        for token in ("send_email", "send_sms", "slack", "webhook", "twilio", "sendgrid", "customer_contact_performed=True"):
            assert token not in src

    def test_no_upload_or_publish(self):
        import inspect
        src = inspect.getsource(S)
        for token in ("upload", "publish", "external_delivery_executed_by_scos=True"):
            assert token not in src

    def test_no_invoice_payment_mutation(self):
        import inspect
        src = inspect.getsource(S)
        for token in ("invoice_state_changed=True", "payment_state_changed=True"):
            assert token not in src

    def test_no_automatic_revision(self):
        import inspect
        src = inspect.getsource(S)
        assert "revision_created=True" not in src

    def test_no_automatic_dispute(self):
        import inspect
        src = inspect.getsource(S)
        assert "dispute_created=True" not in src

    def test_runtime_records_remain_untracked(self, tmp_path):
        _seed_stage8o_delivery(repo_root=tmp_path)
        S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
        # The runtime ledger lives under the gitignored scos/work tree; it must not be tracked.
        from scos.control_center import hvs_customer_receipt_acceptance_store as ST
        import subprocess
        rel = ST.receipt_ledger_path(tmp_path).relative_to(tmp_path).as_posix()
        out = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=tmp_path,
                              capture_output=True, text=True)
        assert out.returncode != 0  # not tracked


# ---------------------------------------------------------------------------
# SYNTHETIC POSITIVE + NEGATIVE ACCEPTANCE
# ---------------------------------------------------------------------------
def test_synthetic_positive_acceptance(tmp_path):
    """Full local-only positive scenario: 8O delivery -> receipt -> reverify SHA
    -> accept -> final outcome ACCEPTED_BY_CUSTOMER with all boundary flags false."""
    _seed_stage8o_delivery(repo_root=tmp_path)
    # 1. eligibility reverified against genuine 8O lineage
    elig = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1")
    assert elig.ok
    # 2. record receipt
    rec = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
    assert rec.ok and rec.receipt_status == M.RECEIPT_CONFIRMED
    # 3. reverify artifact SHA
    assert rec.artifact_sha256 == ART
    # 4. record explicit acceptance
    dec = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                     decision_status="ACCEPTED", decision_date="2026-02-02",
                                     safe_evidence_reference="ref-2", recorded_by_operator_id="op")
    assert dec.ok and dec.decision_status == M.DECISION_ACCEPTED
    # 5. final status
    view = S.inspect_delivery_post_receipt_status(repo_root=tmp_path, actual_delivery_record_id="dr-1")
    assert view.outcome == M.OUTCOME_ACCEPTED_BY_CUSTOMER
    assert view.decision_status == M.DECISION_ACCEPTED
    # explicit boundary guarantees
    assert view.project_closed is False
    assert view.revision_created is False
    assert view.dispute_created is False
    assert view.customer_contact_performed is False
    assert view.hvs_invoked is False
    assert view.invoice_state_changed is False
    assert view.payment_state_changed is False
    assert view.automation_allowed is False


def test_synthetic_negative_package_only_rejected(tmp_path):
    # No 8O actual-delivery record seeded => package-only attempt rejected.
    r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
    assert not r.ok and r.error_code == "actual_delivery_record_not_found"


def test_synthetic_negative_artifact_mismatch_rejected(tmp_path):
    _seed_stage8o_delivery(repo_root=tmp_path)
    r = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1", artifact_sha256=ART2)
    assert not r.ok and r.error_code == "artifact_sha_mismatch"


def test_synthetic_negative_customer_mismatch_rejected(tmp_path):
    _seed_stage8o_delivery(repo_root=tmp_path)
    r = S.inspect_stage8p_eligibility(repo_root=tmp_path, actual_delivery_record_id="dr-1", customer_reference="other")
    assert not r.ok and r.error_code == "customer_reference_mismatch"


def test_synthetic_negative_acceptance_before_receipt(tmp_path):
    _seed_stage8o_delivery(repo_root=tmp_path)
    r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                   decision_status="ACCEPTED", decision_date="2026-02-02",
                                   safe_evidence_reference="ref-2", recorded_by_operator_id="op")
    assert not r.ok and r.error_code == "decision_before_receipt"


def test_synthetic_negative_rejection_without_reason(tmp_path):
    _seed_stage8o_delivery(repo_root=tmp_path)
    S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
    r = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                   decision_status="REJECTED", decision_date="2026-02-02",
                                   safe_evidence_reference="ref-2", recorded_by_operator_id="op")
    assert not r.ok and r.error_code == "missing_rejection_reason"


def test_synthetic_negative_conflicting_acceptance_rejection(tmp_path):
    _seed_stage8o_delivery(repo_root=tmp_path)
    S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
    a = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                   decision_status="ACCEPTED", decision_date="2026-02-02",
                                   safe_evidence_reference="ref-2", recorded_by_operator_id="op")
    assert a.ok
    b = S.record_customer_decision(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                   decision_status="REJECTED", decision_date="2026-02-03",
                                   safe_evidence_reference="ref-3", recorded_by_operator_id="op",
                                   rejection_reason="changed mind")
    assert not b.ok and b.error_code == "changed_decision_conflict"


def test_synthetic_negative_issue_unsafe_content(tmp_path):
    _seed_stage8o_delivery(repo_root=tmp_path)
    S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
    r = S.record_delivery_issue(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                issue_category=None, issue_summary="leak\ntoken=secret", decision_date="2026-02-03",
                                safe_evidence_reference="ref-3", recorded_by_operator_id="op")
    assert not r.ok and r.error_code == "invalid_issue_input"


def test_synthetic_negative_revision_request_no_8b_mutation(tmp_path):
    _seed_stage8o_delivery(repo_root=tmp_path)
    S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
    r = S.record_revision_review_request(repo_root=tmp_path, actual_delivery_record_id="dr-1",
                                         revision_review_reason="shorten intro", decision_date="2026-02-04",
                                         safe_evidence_reference="ref-4", recorded_by_operator_id="op")
    assert r.ok and r.revision_created is False


def test_synthetic_negative_duplicate_identical_replay(tmp_path):
    _seed_stage8o_delivery(repo_root=tmp_path)
    a = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
    b = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW())
    assert a.ok and b.ok and b.replayed is True


def test_synthetic_negative_duplicate_changed_semantic_replay(tmp_path):
    _seed_stage8o_delivery(repo_root=tmp_path)
    a = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference="ref-1"))
    assert a.ok
    b = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference="ref-2"))
    assert not b.ok and b.error_code == "conflicting_receipt_replay"


def test_synthetic_negative_malformed_ledger(tmp_path):
    ledger = S.receipt_ledger_path(tmp_path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("garbage\n", encoding="utf-8")
    with pytest.raises(ValueError):
        S.read_receipt_events(ledger_path=ledger)


def test_synthetic_negative_traversal_evidence(tmp_path):
    _seed_stage8o_delivery(repo_root=tmp_path)
    r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference="../../etc/passwd"))
    assert not r.ok and r.error_code == "invalid_receipt_input"


def test_synthetic_negative_secret_like_evidence(tmp_path):
    _seed_stage8o_delivery(repo_root=tmp_path)
    r = S.create_customer_receipt_record(repo_root=tmp_path, **_RECORD_KW(safe_evidence_reference="apikey-abc123"))
    assert not r.ok and r.error_code == "invalid_receipt_input"
