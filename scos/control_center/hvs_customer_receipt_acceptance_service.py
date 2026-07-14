"""SCOS <-> HVS — Stage 8P customer-receipt / acceptance / issue-intake service.

Orchestrates the post-delivery evidence + decision-intake gate:

    inspect_stage8p_eligibility           reverify Stage 8O lineage before mutation
    create_customer_receipt_record        operator-recorded receipt confirmation
    inspect_customer_receipt              read-only receipt inspection
    record_customer_decision              ACCEPTED / REJECTED (bound to receipt)
    record_delivery_issue                 issue intake (no dispute / revision)
    record_revision_review_request        revision review request (no revision)
    inspect_delivery_post_receipt_status  read-only readiness / outcome view
    build_acceptance_readiness_view       read-only aggregate view

Every mutation:
1. re-verifies the Stage 8O actual-delivery lineage (read-only),
2. validates inputs,
3. enforces the state transition,
4. detects idempotent replay,
5. detects conflict (fail closed),
6. appends a deterministic append-only event,
7. returns structured output with explicit all-false boundary flags.

Stage 8P never contacts a customer, performs transport, invokes HVS, renders,
creates a revision or dispute automatically, or mutates invoice / payment
state. Local-first, deterministic, stdlib-only. ``automation_allowed`` is
always ``False``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hvs_customer_receipt_acceptance_models import (
    ALLOWED_DECISION_STATUSES,
    ALLOWED_RECEIPT_EVIDENCE_TYPES,
    ALLOWED_RECEIPT_STATUSES,
    DECISION_ACCEPTED,
    DECISION_ISSUE_REPORTED,
    DECISION_NO_DECISION,
    DECISION_REJECTED,
    DECISION_REVISION_REVIEW_REQUESTED,
    EVT_CUSTOMER_ACCEPTED,
    EVT_CUSTOMER_ISSUE_REPORTED,
    EVT_CUSTOMER_REJECTED,
    EVT_CUSTOMER_REVISION_REVIEW_REQUESTED,
    EVT_RECEIPT_CONFIRMED,
    EVT_RECEIPT_REJECTED,
    OUTCOME_ACCEPTED_BY_CUSTOMER,
    OUTCOME_DELIVERY_IDENTITY_CONFLICT,
    OUTCOME_ISSUE_REPORTED,
    OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING,
    OUTCOME_RECEIPT_NOT_CONFIRMED,
    OUTCOME_REJECTED_BY_CUSTOMER,
    OUTCOME_REVISION_REVIEW_REQUESTED,
    READINESS_SCHEMA_VERSION,
    RECEIPT_CONFIRMED,
    RECEIPT_IDENTITY_CONFLICT,
    RECEIPT_RECORD_SCHEMA_VERSION,
    RECEIPT_REJECTED_AS_INVALID,
    DECISION_RECORD_SCHEMA_VERSION,
    ISSUE_INTAKE_SCHEMA_VERSION,
    REVISION_REVIEW_SCHEMA_VERSION,
    CustomerDecisionRecord,
    CustomerReceiptAcceptanceEvent,
    CustomerReceiptRecord,
    DeliveryAcceptanceReadiness,
    DeliveryIssueIntake,
    RevisionReviewIntake,
    _bounded_optional,
    _immutable_hash,
    _require_date,
    _require_evidence_reference,
    _require_issue_summary,
    _require_member,
    _require_operator_id,
    customer_decision_id,
    issue_intake_id,
    receipt_record_id,
    record_content_hash,
    revision_review_id,
)
from .hvs_customer_receipt_acceptance_store import (
    append_receipt_event,
    events_for_actual_delivery,
    latest_event_for_aggregate,
    latest_event_by_type,
    read_receipt_events,
    receipt_ledger_path,
)
# Reuse the genuine Stage 8O delivery record as the single source of truth.
from .hvs_stage8o_delivery_models import (
    AUTH_APPROVED,
    DEL_DELIVERED_MANUALLY,
    DEL_RECORD_CONFLICTED,
    DEL_RECORD_REJECTED,
    PKG_CANCELLED,
    PKG_CONFLICTED,
    PKG_DRAFT,
    PKG_FAILED,
)
from .hvs_stage8o_delivery_store import delivery_ledger_path as stage8o_ledger_path
from .hvs_stage8o_delivery_service import inspect_actual_manual_delivery


# Stage 8O package states that permit a valid downstream delivery.
_PACKAGE_VALID_STATES = (
    "PACKAGE_PREPARED",
    "PACKAGE_MATERIALIZING",
    "PACKAGE_MATERIALIZED",
    "PACKAGE_VERIFYING",
    "PACKAGE_READY",
)


@dataclass(frozen=True)
class Stage8PServiceResult:
    ok: bool
    actual_delivery_record_id: str | None = None
    receipt_record_id: str | None = None
    customer_decision_id: str | None = None
    issue_intake_id: str | None = None
    revision_review_id: str | None = None
    receipt_status: str | None = None
    decision_status: str | None = None
    outcome: str | None = None
    delivery_package_id: str | None = None
    artifact_id: str | None = None
    artifact_sha256: str | None = None
    customer_reference: str | None = None
    safe_evidence_reference: str | None = None
    replayed: bool = False
    error_code: str | None = None
    error_detail: str | None = None
    # Explicit all-false boundary / truth flags.
    customer_contact_performed: bool = False
    external_action_performed: bool = False
    hvs_invoked: bool = False
    project_closed: bool = False
    revision_created: bool = False
    dispute_created: bool = False
    invoice_state_changed: bool = False
    payment_state_changed: bool = False
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "actual_delivery_record_id": self.actual_delivery_record_id,
            "receipt_record_id": self.receipt_record_id,
            "customer_decision_id": self.customer_decision_id,
            "issue_intake_id": self.issue_intake_id,
            "revision_review_id": self.revision_review_id,
            "receipt_status": self.receipt_status,
            "decision_status": self.decision_status,
            "outcome": self.outcome,
            "delivery_package_id": self.delivery_package_id,
            "artifact_id": self.artifact_id,
            "artifact_sha256": self.artifact_sha256,
            "customer_reference": self.customer_reference,
            "safe_evidence_reference": self.safe_evidence_reference,
            "replayed": self.replayed,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "customer_contact_performed": self.customer_contact_performed,
            "external_action_performed": self.external_action_performed,
            "hvs_invoked": self.hvs_invoked,
            "project_closed": self.project_closed,
            "revision_created": self.revision_created,
            "dispute_created": self.dispute_created,
            "invoice_state_changed": self.invoice_state_changed,
            "payment_state_changed": self.payment_state_changed,
            "automation_allowed": self.automation_allowed,
        }


def _deny(
    *,
    error_code: str,
    error_detail: str,
    **extra: Any,
) -> Stage8PServiceResult:
    return Stage8PServiceResult(ok=False, error_code=error_code, error_detail=error_detail, **extra)


# ---------------------------------------------------------------------------
# Stage 8O lineage loading (read-only)
# ---------------------------------------------------------------------------
def _load_8o_actual_delivery(*, repo_root: Any, actual_delivery_record_id: str) -> dict[str, Any] | None:
    ledger = stage8o_ledger_path(repo_root)
    from .hvs_stage8o_delivery_store import read_delivery_events as _read_8o

    for ev in _read_8o(ledger_path=ledger):
        if ev.get("event_type") == "DELIVERY_RECORDED" and ev.get("subject_id") == actual_delivery_record_id:
            return ev.get("record") or {}
    return None


def _stage8o_authorization_status(*, repo_root: Any, authorization_request_id: str) -> str | None:
    from .hvs_stage8o_delivery_store import read_delivery_events as _read_8o

    ledger = stage8o_ledger_path(repo_root)
    status = None
    for ev in _read_8o(ledger_path=ledger):
        if ev.get("event_type", "").startswith("AUTHORIZATION_") and ev.get("authorization_request_id") == authorization_request_id:
            status = ev.get("resulting_status")
    return status


def _stage8o_package_status(*, repo_root: Any, package_id: str) -> str | None:
    from .hvs_stage8o_delivery_store import read_delivery_events as _read_8o

    ledger = stage8o_ledger_path(repo_root)
    status = None
    for ev in _read_8o(ledger_path=ledger):
        if ev.get("event_type") == "PACKAGE_PREPARED" and ev.get("package_id") == package_id:
            status = (ev.get("record") or {}).get("package_status")
    return status


# ---------------------------------------------------------------------------
# Eligibility reverification
# ---------------------------------------------------------------------------
def inspect_stage8p_eligibility(
    *,
    repo_root: Any,
    actual_delivery_record_id: str,
    delivery_package_id: str | None = None,
    artifact_id: str | None = None,
    artifact_sha256: str | None = None,
    customer_reference: str | None = None,
) -> Stage8PServiceResult:
    if not str(actual_delivery_record_id or "").strip():
        return _deny(error_code="missing_actual_delivery_record_id", error_detail="actual_delivery_record_id is required")
    rec = _load_8o_actual_delivery(repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id)
    if rec is None:
        return _deny(
            error_code="actual_delivery_record_not_found",
            error_detail="no Stage 8O actual-delivery record for this id",
            actual_delivery_record_id=actual_delivery_record_id,
        )
    # Final + valid delivery status (never forged / rejected / conflicted).
    status = rec.get("delivery_status")
    if status != DEL_DELIVERED_MANUALLY:
        if status in (DEL_RECORD_REJECTED, DEL_RECORD_CONFLICTED):
            return _deny(
                error_code="actual_delivery_cancelled",
                error_detail="Stage 8O actual-delivery record is not a final valid delivery",
                actual_delivery_record_id=actual_delivery_record_id,
            )
        return _deny(
            error_code="actual_delivery_not_final",
            error_detail="Stage 8O actual-delivery record is not in a final delivered state",
            actual_delivery_record_id=actual_delivery_record_id,
        )
    # Authorization must remain valid + APPROVED.
    auth_status = _stage8o_authorization_status(
        repo_root=repo_root, authorization_request_id=rec.get("authorization_request_id", "")
    )
    if auth_status != AUTH_APPROVED:
        return _deny(
            error_code="delivery_authorization_not_valid",
            error_detail="bound Stage 8O delivery authorization is not APPROVED_FOR_MANUAL_DELIVERY",
            actual_delivery_record_id=actual_delivery_record_id,
        )
    # Delivery package must remain valid (not draft/cancelled/failed/conflicted).
    pkg_status = _stage8o_package_status(repo_root=repo_root, package_id=rec.get("delivery_package_id", ""))
    if pkg_status is None or pkg_status in (PKG_DRAFT, PKG_CANCELLED, PKG_FAILED, PKG_CONFLICTED):
        return _deny(
            error_code="delivery_package_not_valid",
            error_detail="bound Stage 8O delivery package is not in a valid state",
            actual_delivery_record_id=actual_delivery_record_id,
        )
    # Source artifact must remain VERIFIED with a 64-char SHA (legacy/unknown -> fail closed).
    src_sha = str(rec.get("artifact_sha256") or "")
    if len(src_sha) != 64:
        return _deny(
            error_code="source_artifact_not_verified",
            error_detail="bound Stage 8O artifact SHA-256 is missing or malformed",
            actual_delivery_record_id=actual_delivery_record_id,
        )

    # Optional supplied fields must match the Stage 8O lineage exactly.
    if delivery_package_id is not None and delivery_package_id != rec.get("delivery_package_id"):
        return _deny(
            error_code="package_id_mismatch",
            error_detail="supplied delivery_package_id does not match the Stage 8O record",
            actual_delivery_record_id=actual_delivery_record_id,
        )
    if artifact_id is not None and artifact_id != rec.get("artifact_id"):
        return _deny(
            error_code="artifact_id_mismatch",
            error_detail="supplied artifact_id does not match the Stage 8O record",
            actual_delivery_record_id=actual_delivery_record_id,
        )
    if artifact_sha256 is not None and artifact_sha256.lower() != src_sha.lower():
        return _deny(
            error_code="artifact_sha_mismatch",
            error_detail="supplied artifact SHA-256 does not match the Stage 8O record",
            actual_delivery_record_id=actual_delivery_record_id,
        )
    if customer_reference is not None and customer_reference != rec.get("safe_recipient_reference"):
        return _deny(
            error_code="customer_reference_mismatch",
            error_detail="supplied customer_reference does not match the Stage 8O recipient",
            actual_delivery_record_id=actual_delivery_record_id,
        )

    return Stage8PServiceResult(
        ok=True,
        actual_delivery_record_id=actual_delivery_record_id,
        delivery_package_id=rec.get("delivery_package_id"),
        artifact_id=rec.get("artifact_id"),
        artifact_sha256=src_sha,
        customer_reference=rec.get("safe_recipient_reference"),
    )


# ---------------------------------------------------------------------------
# Receipt record
# ---------------------------------------------------------------------------
def create_customer_receipt_record(
    *,
    repo_root: Any,
    actual_delivery_record_id: str,
    delivery_package_id: str,
    artifact_id: str,
    artifact_sha256: str,
    customer_reference: str,
    receipt_evidence_type: str,
    safe_evidence_reference: str,
    receipt_confirmation_date: str,
    recorded_by_operator_id: str,
    customer_confirmed_artifact_sha256: str | None = None,
    source_render_completion_id: str = "",
    source_delivery_authorization_id: str = "",
    source_delivery_lineage_id: str | None = None,
    receipt_status: str = RECEIPT_CONFIRMED,
    informational_recorded_at: str = "",
) -> Stage8PServiceResult:
    if not str(recorded_by_operator_id or "").strip():
        return _deny(error_code="missing_operator_id", error_detail="recorded_by_operator_id is required")
    _require_member(receipt_evidence_type, ALLOWED_RECEIPT_EVIDENCE_TYPES, "invalid_receipt_evidence_type", "unsupported receipt evidence type")
    _require_member(receipt_status, ALLOWED_RECEIPT_STATUSES, "invalid_receipt_status", "unsupported receipt status")
    try:
        operator_id = _require_operator_id(recorded_by_operator_id)
        pkg_id = _bounded_optional(delivery_package_id, max_len=256, field_name="delivery_package_id")
        art_id = _bounded_optional(artifact_id, max_len=256, field_name="artifact_id")
        art_sha = _immutable_hash(artifact_sha256)
        cust_ref = _bounded_optional(customer_reference, max_len=256, field_name="customer_reference")
        if not cust_ref:
            raise ValueError("customer_reference is required")
        ev_ref = _require_evidence_reference(safe_evidence_reference)
        conf_date = _require_date(receipt_confirmation_date, field_name="receipt_confirmation_date")
    except ValueError as exc:
        return _deny(error_code="invalid_receipt_input", error_detail=str(exc))

    # Re-verify the full Stage 8O lineage before writing.
    elig = inspect_stage8p_eligibility(
        repo_root=repo_root,
        actual_delivery_record_id=actual_delivery_record_id,
        delivery_package_id=pkg_id,
        artifact_id=art_id,
        artifact_sha256=art_sha,
        customer_reference=cust_ref,
    )
    if not elig.ok:
        return elig

    # Optional customer-supplied artifact SHA must match the delivered artifact.
    cust_sha = None
    if customer_confirmed_artifact_sha256:
        try:
            cust_sha = _immutable_hash(customer_confirmed_artifact_sha256)
        except ValueError as exc:
            return _deny(error_code="invalid_receipt_input", error_detail=f"customer_confirmed_artifact_sha256: {exc}")
        if cust_sha.lower() != art_sha.lower():
            return _deny(
                error_code="customer_artifact_sha_mismatch",
                error_detail="customer-supplied artifact SHA-256 does not match the delivered artifact",
                actual_delivery_record_id=actual_delivery_record_id,
            )

    # No conflicting receipt may already exist for this delivery record.
    ledger = receipt_ledger_path(repo_root)
    rid = receipt_record_id(
        actual_delivery_record_id=actual_delivery_record_id,
        delivery_package_id=pkg_id,
        artifact_sha256=art_sha,
        customer_reference=cust_ref,
        receipt_evidence_type=receipt_evidence_type,
        safe_evidence_reference=ev_ref,
    )
    existing_events = events_for_actual_delivery(
        ledger_path=ledger, actual_delivery_record_id=actual_delivery_record_id
    )
    for ev in existing_events:
        if ev.get("event_type") in (EVT_RECEIPT_CONFIRMED, EVT_RECEIPT_REJECTED):
            if ev["aggregate_id"] == rid:
                # Identical semantic replay => idempotent.
                rec = CustomerReceiptRecord(**(ev["record"] or {}))
                return Stage8PServiceResult(
                    ok=True,
                    actual_delivery_record_id=actual_delivery_record_id,
                    receipt_record_id=rid,
                    receipt_status=rec.receipt_status,
                    delivery_package_id=pkg_id,
                    artifact_id=art_id,
                    artifact_sha256=art_sha,
                    customer_reference=cust_ref,
                    safe_evidence_reference=ev_ref,
                    replayed=True,
                )
            # A different receipt already exists for this delivery record.
            return _deny(
                error_code="conflicting_receipt_replay",
                error_detail="a different receipt record already exists for this delivery record",
                actual_delivery_record_id=actual_delivery_record_id,
            )

    receipt_dict = {
        "schema_version": RECEIPT_RECORD_SCHEMA_VERSION,
        "receipt_record_id": rid,
        "project_id": _load_8o_actual_delivery(
            repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id
        ).get("project_id", ""),
        "customer_reference": cust_ref,
        "source_render_completion_id": _bounded_optional(source_render_completion_id, max_len=256, field_name="source_render_completion_id"),
        "source_delivery_package_id": pkg_id,
        "source_delivery_authorization_id": _bounded_optional(source_delivery_authorization_id, max_len=256, field_name="source_delivery_authorization_id"),
        "source_actual_delivery_record_id": actual_delivery_record_id,
        "source_delivery_lineage_id": _bounded_optional(source_delivery_lineage_id, max_len=256, field_name="source_delivery_lineage_id") or None,
        "artifact_id": art_id,
        "artifact_sha256": art_sha,
        "receipt_status": receipt_status,
        "receipt_evidence_type": receipt_evidence_type,
        "safe_evidence_reference": ev_ref,
        "customer_confirmed_artifact_sha256": cust_sha,
        "receipt_confirmation_date": conf_date,
        "recorded_by_operator_id": operator_id,
        "customer_contact_performed": False,
        "external_action_performed": False,
        "automation_allowed": False,
        "informational_recorded_at": informational_recorded_at,
    }
    record = CustomerReceiptRecord(
        **{
            **receipt_dict,
            "deterministic_content_hash": record_content_hash(receipt_dict),
        }
    )
    append_receipt_event(
        ledger_path=ledger,
        event_type=EVT_RECEIPT_CONFIRMED if receipt_status == RECEIPT_CONFIRMED else EVT_RECEIPT_REJECTED,
        aggregate_id=rid,
        project_id=record.project_id,
        actual_delivery_record_id=actual_delivery_record_id,
        artifact_sha256=art_sha,
        operator_id=operator_id,
        resulting_status=record.receipt_status,
        recorded_at=informational_recorded_at,
        package_id=pkg_id,
        record_payload=record.to_dict(),
    )
    return Stage8PServiceResult(
        ok=True,
        actual_delivery_record_id=actual_delivery_record_id,
        receipt_record_id=rid,
        receipt_status=record.receipt_status,
        delivery_package_id=pkg_id,
        artifact_id=art_id,
        artifact_sha256=art_sha,
        customer_reference=cust_ref,
        safe_evidence_reference=ev_ref,
    )


def inspect_customer_receipt(*, repo_root: Any, receipt_record_id: str) -> Stage8PServiceResult:
    ledger = receipt_ledger_path(repo_root)
    ev = latest_event_for_aggregate(ledger_path=ledger, aggregate_id=receipt_record_id)
    if ev is None:
        return _deny(error_code="receipt_record_not_found", error_detail="receipt record not found")
    rec = CustomerReceiptRecord(**(ev["record"] or {}))
    return Stage8PServiceResult(
        ok=True,
        actual_delivery_record_id=rec.source_actual_delivery_record_id,
        receipt_record_id=rec.receipt_record_id,
        receipt_status=rec.receipt_status,
        delivery_package_id=rec.source_delivery_package_id,
        artifact_id=rec.artifact_id,
        artifact_sha256=rec.artifact_sha256,
        customer_reference=rec.customer_reference,
        safe_evidence_reference=rec.safe_evidence_reference,
    )


# ---------------------------------------------------------------------------
# Helpers: find confirmed receipt + latest final decision for a delivery record
# ---------------------------------------------------------------------------
def _latest_receipt_record(*, repo_root: Any, actual_delivery_record_id: str) -> dict[str, Any] | None:
    ledger = receipt_ledger_path(repo_root)
    for ev in events_for_actual_delivery(ledger_path=ledger, actual_delivery_record_id=actual_delivery_record_id):
        if ev.get("event_type") in (EVT_RECEIPT_CONFIRMED, EVT_RECEIPT_REJECTED):
            rec = ev.get("record") or {}
            if rec.get("receipt_status") == RECEIPT_CONFIRMED:
                return rec
    return None


def _latest_final_decision(*, repo_root: Any, actual_delivery_record_id: str) -> dict[str, Any] | None:
    ledger = receipt_ledger_path(repo_root)
    decision = None
    for ev in events_for_actual_delivery(ledger_path=ledger, actual_delivery_record_id=actual_delivery_record_id):
        if ev.get("event_type") in (
            EVT_CUSTOMER_ACCEPTED,
            EVT_CUSTOMER_REJECTED,
            EVT_CUSTOMER_ISSUE_REPORTED,
            EVT_CUSTOMER_REVISION_REVIEW_REQUESTED,
        ):
            decision = ev.get("record") or {}
    return decision


def latest_revision_review_record(*, repo_root: Any, actual_delivery_record_id: str) -> dict[str, Any] | None:
    ledger = receipt_ledger_path(repo_root)
    for ev in reversed(list(events_for_actual_delivery(ledger_path=ledger, actual_delivery_record_id=actual_delivery_record_id))):
        if ev.get("event_type") == EVT_CUSTOMER_REVISION_REVIEW_REQUESTED:
            return ev.get("record") or {}
    return None


def _latest_intake_event(*, repo_root: Any, actual_delivery_record_id: str) -> dict[str, Any] | None:
    """Latest issue / revision-review intake event for a delivery record (changed-replay guard)."""
    ledger = receipt_ledger_path(repo_root)
    intake = None
    for ev in events_for_actual_delivery(ledger_path=ledger, actual_delivery_record_id=actual_delivery_record_id):
        if ev.get("event_type") in (
            EVT_CUSTOMER_ISSUE_REPORTED,
            EVT_CUSTOMER_REVISION_REVIEW_REQUESTED,
        ):
            intake = ev
    return intake


def _require_confirmed_receipt(*, repo_root: Any, actual_delivery_record_id: str) -> dict[str, Any] | None:
    rec = _latest_receipt_record(repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id)
    if rec is None:
        return None
    return rec


# ---------------------------------------------------------------------------
# Customer decision (ACCEPTED / REJECTED)
# ---------------------------------------------------------------------------
def record_customer_decision(
    *,
    repo_root: Any,
    actual_delivery_record_id: str,
    decision_status: str,
    decision_date: str,
    safe_evidence_reference: str,
    recorded_by_operator_id: str,
    acceptance_scope: str | None = None,
    rejection_reason: str | None = None,
    informational_recorded_at: str = "",
) -> Stage8PServiceResult:
    if decision_status not in (DECISION_ACCEPTED, DECISION_REJECTED):
        return _deny(error_code="invalid_decision_status", error_detail="decision_status must be ACCEPTED or REJECTED")
    if not str(recorded_by_operator_id or "").strip():
        return _deny(error_code="missing_operator_id", error_detail="recorded_by_operator_id is required")
    try:
        operator_id = _require_operator_id(recorded_by_operator_id)
        dec_date = _require_date(decision_date, field_name="decision_date")
        ev_ref = _require_evidence_reference(safe_evidence_reference)
    except ValueError as exc:
        return _deny(error_code="invalid_decision_input", error_detail=str(exc))

    receipt = _require_confirmed_receipt(repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id)
    if receipt is None:
        return _deny(
            error_code="decision_before_receipt",
            error_detail="a confirmed customer receipt is required before recording a decision",
            actual_delivery_record_id=actual_delivery_record_id,
        )

    if decision_status == DECISION_REJECTED:
        if not str(rejection_reason or "").strip():
            return _deny(error_code="missing_rejection_reason", error_detail="rejection_reason is required")
        try:
            rejection_reason = _require_issue_summary(rejection_reason, max_len=512)
        except ValueError as exc:
            return _deny(error_code="invalid_rejection_reason", error_detail=str(exc))
    else:
        if acceptance_scope:
            acceptance_scope = _bounded_optional(acceptance_scope, max_len=256, field_name="acceptance_scope")

    semantic = (
        f"reject:{rejection_reason}"
        if decision_status == DECISION_REJECTED
        else f"accept:{acceptance_scope or ''}"
    )
    did = customer_decision_id(
        receipt_record_id=receipt["receipt_record_id"],
        actual_delivery_record_id=actual_delivery_record_id,
        artifact_sha256=receipt["artifact_sha256"],
        decision_status=decision_status,
        semantic_content=semantic,
        safe_evidence_reference=ev_ref,
    )

    # Conflict: a different final decision already exists for this delivery record.
    # The deterministic decision id encodes status + reason/evidence, so an exact
    # replay lands on the same id (handled below as idempotent), while any changed
    # final decision (e.g. different rejection reason or evidence) conflicts.
    existing = _latest_final_decision(repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id)
    if existing is not None and existing.get("customer_decision_id") != did:
        if existing.get("decision_status") not in (DECISION_ISSUE_REPORTED, DECISION_REVISION_REVIEW_REQUESTED):
            return _deny(
                error_code="changed_decision_conflict",
                error_detail="a different final customer decision already exists for this delivery record",
                actual_delivery_record_id=actual_delivery_record_id,
            )

    # Idempotent replay check.
    ledger = receipt_ledger_path(repo_root)
    ev = latest_event_for_aggregate(ledger_path=ledger, aggregate_id=did)
    if ev is not None:
        rec = CustomerDecisionRecord(**(ev["record"] or {}))
        return Stage8PServiceResult(
            ok=True,
            actual_delivery_record_id=actual_delivery_record_id,
            customer_decision_id=did,
            receipt_record_id=receipt["receipt_record_id"],
            decision_status=rec.decision_status,
            delivery_package_id=rec.delivery_package_id,
            artifact_id=rec.artifact_id,
            artifact_sha256=rec.artifact_sha256,
            customer_reference=rec.customer_reference,
            safe_evidence_reference=ev_ref,
            replayed=True,
        )

    record = CustomerDecisionRecord(
        schema_version=DECISION_RECORD_SCHEMA_VERSION,
        customer_decision_id=did,
        receipt_record_id=receipt["receipt_record_id"],
        actual_delivery_record_id=actual_delivery_record_id,
        delivery_package_id=receipt["source_delivery_package_id"],
        project_id=receipt["project_id"],
        customer_reference=receipt["customer_reference"],
        artifact_id=receipt["artifact_id"],
        artifact_sha256=receipt["artifact_sha256"],
        decision_status=decision_status,
        decision_date=dec_date,
        acceptance_scope=acceptance_scope,
        rejection_reason=rejection_reason,
        issue_summary=None,
        revision_review_reason=None,
        safe_evidence_reference=ev_ref,
        recorded_by_operator_id=operator_id,
        project_closed=False,
        revision_created=False,
        dispute_created=False,
        invoice_state_changed=False,
        payment_state_changed=False,
        customer_contact_performed=False,
        external_action_performed=False,
        automation_allowed=False,
        deterministic_content_hash=record_content_hash(
            {
                "receipt_record_id": receipt["receipt_record_id"],
                "decision_status": decision_status,
                "semantic_content": semantic,
                "safe_evidence_reference": ev_ref,
            }
        ),
        informational_recorded_at=informational_recorded_at,
    )
    append_receipt_event(
        ledger_path=ledger,
        event_type=EVT_CUSTOMER_ACCEPTED if decision_status == DECISION_ACCEPTED else EVT_CUSTOMER_REJECTED,
        aggregate_id=did,
        project_id=record.project_id,
        actual_delivery_record_id=actual_delivery_record_id,
        artifact_sha256=record.artifact_sha256,
        operator_id=operator_id,
        resulting_status=record.decision_status,
        recorded_at=informational_recorded_at,
        package_id=record.delivery_package_id,
        record_payload=record.to_dict(),
    )
    return Stage8PServiceResult(
        ok=True,
        actual_delivery_record_id=actual_delivery_record_id,
        customer_decision_id=did,
        receipt_record_id=receipt["receipt_record_id"],
        decision_status=record.decision_status,
        delivery_package_id=record.delivery_package_id,
        artifact_id=record.artifact_id,
        artifact_sha256=record.artifact_sha256,
        customer_reference=record.customer_reference,
        safe_evidence_reference=ev_ref,
    )


# ---------------------------------------------------------------------------
# Issue intake (no dispute / revision)
# ---------------------------------------------------------------------------
def record_delivery_issue(
    *,
    repo_root: Any,
    actual_delivery_record_id: str,
    issue_category: str | None,
    issue_summary: str,
    decision_date: str,
    safe_evidence_reference: str,
    recorded_by_operator_id: str,
    informational_recorded_at: str = "",
) -> Stage8PServiceResult:
    if not str(recorded_by_operator_id or "").strip():
        return _deny(error_code="missing_operator_id", error_detail="recorded_by_operator_id is required")
    try:
        operator_id = _require_operator_id(recorded_by_operator_id)
        dec_date = _require_date(decision_date, field_name="decision_date")
        ev_ref = _require_evidence_reference(safe_evidence_reference)
        summary = _require_issue_summary(issue_summary)
    except ValueError as exc:
        return _deny(error_code="invalid_issue_input", error_detail=str(exc))

    receipt = _require_confirmed_receipt(repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id)
    if receipt is None:
        return _deny(
            error_code="decision_before_receipt",
            error_detail="a confirmed customer receipt is required before recording an issue",
            actual_delivery_record_id=actual_delivery_record_id,
        )
    if issue_category is not None:
        issue_category = _bounded_optional(issue_category, max_len=128, field_name="issue_category")

    iid = issue_intake_id(
        receipt_record_id=receipt["receipt_record_id"],
        actual_delivery_record_id=actual_delivery_record_id,
        issue_summary=summary,
        safe_evidence_reference=ev_ref,
    )
    ledger = receipt_ledger_path(repo_root)
    ev = latest_event_for_aggregate(ledger_path=ledger, aggregate_id=iid)
    if ev is not None:
        rec = DeliveryIssueIntake(**(ev["record"] or {}))
        return Stage8PServiceResult(
            ok=True,
            actual_delivery_record_id=actual_delivery_record_id,
            issue_intake_id=iid,
            receipt_record_id=receipt["receipt_record_id"],
            decision_status=DECISION_ISSUE_REPORTED,
            replayed=True,
        )

    # Changed-replay conflict: a different issue / revision-review intake already exists.
    existing_intake = _latest_intake_event(repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id)
    if existing_intake is not None:
        return _deny(
            error_code="changed_decision_conflict",
            error_detail="a different issue / revision-review intake already exists for this delivery record",
            actual_delivery_record_id=actual_delivery_record_id,
        )

    record = DeliveryIssueIntake(
        schema_version=ISSUE_INTAKE_SCHEMA_VERSION,
        issue_intake_id=iid,
        receipt_record_id=receipt["receipt_record_id"],
        customer_decision_id=None,
        actual_delivery_record_id=actual_delivery_record_id,
        delivery_package_id=receipt["source_delivery_package_id"],
        project_id=receipt["project_id"],
        customer_reference=receipt["customer_reference"],
        artifact_id=receipt["artifact_id"],
        artifact_sha256=receipt["artifact_sha256"],
        issue_category=issue_category,
        issue_summary=summary,
        decision_date=dec_date,
        safe_evidence_reference=ev_ref,
        recorded_by_operator_id=operator_id,
        dispute_created=False,
        revision_created=False,
        customer_contact_performed=False,
        external_action_performed=False,
        automation_allowed=False,
        deterministic_content_hash=record_content_hash(
            {
                "issue_summary": summary,
                "safe_evidence_reference": ev_ref,
            }
        ),
        informational_recorded_at=informational_recorded_at,
    )
    append_receipt_event(
        ledger_path=ledger,
        event_type=EVT_CUSTOMER_ISSUE_REPORTED,
        aggregate_id=iid,
        project_id=record.project_id,
        actual_delivery_record_id=actual_delivery_record_id,
        artifact_sha256=record.artifact_sha256,
        operator_id=operator_id,
        resulting_status=DECISION_ISSUE_REPORTED,
        recorded_at=informational_recorded_at,
        package_id=record.delivery_package_id,
        record_payload=record.to_dict(),
    )
    return Stage8PServiceResult(
        ok=True,
        actual_delivery_record_id=actual_delivery_record_id,
        issue_intake_id=iid,
        receipt_record_id=receipt["receipt_record_id"],
        decision_status=DECISION_ISSUE_REPORTED,
        delivery_package_id=record.delivery_package_id,
        artifact_id=record.artifact_id,
        artifact_sha256=record.artifact_sha256,
        customer_reference=record.customer_reference,
        safe_evidence_reference=ev_ref,
    )


# ---------------------------------------------------------------------------
# Revision-review request (no revision / re-render / HVS)
# ---------------------------------------------------------------------------
def record_revision_review_request(
    *,
    repo_root: Any,
    actual_delivery_record_id: str,
    revision_review_reason: str,
    decision_date: str,
    safe_evidence_reference: str,
    recorded_by_operator_id: str,
    informational_recorded_at: str = "",
) -> Stage8PServiceResult:
    if not str(recorded_by_operator_id or "").strip():
        return _deny(error_code="missing_operator_id", error_detail="recorded_by_operator_id is required")
    try:
        operator_id = _require_operator_id(recorded_by_operator_id)
        dec_date = _require_date(decision_date, field_name="decision_date")
        ev_ref = _require_evidence_reference(safe_evidence_reference)
        reason = _require_issue_summary(revision_review_reason)
    except ValueError as exc:
        return _deny(error_code="invalid_revision_input", error_detail=str(exc))

    receipt = _require_confirmed_receipt(repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id)
    if receipt is None:
        return _deny(
            error_code="decision_before_receipt",
            error_detail="a confirmed customer receipt is required before recording a revision review request",
            actual_delivery_record_id=actual_delivery_record_id,
        )

    rid = revision_review_id(
        receipt_record_id=receipt["receipt_record_id"],
        actual_delivery_record_id=actual_delivery_record_id,
        revision_review_reason=reason,
        safe_evidence_reference=ev_ref,
    )
    ledger = receipt_ledger_path(repo_root)
    ev = latest_event_for_aggregate(ledger_path=ledger, aggregate_id=rid)
    if ev is not None:
        rec = RevisionReviewIntake(**(ev["record"] or {}))
        return Stage8PServiceResult(
            ok=True,
            actual_delivery_record_id=actual_delivery_record_id,
            revision_review_id=rid,
            receipt_record_id=receipt["receipt_record_id"],
            decision_status=DECISION_REVISION_REVIEW_REQUESTED,
            replayed=True,
        )

    # Changed-replay conflict: a different issue / revision-review intake already exists.
    existing_intake = _latest_intake_event(repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id)
    if existing_intake is not None:
        return _deny(
            error_code="changed_decision_conflict",
            error_detail="a different issue / revision-review intake already exists for this delivery record",
            actual_delivery_record_id=actual_delivery_record_id,
        )

    record = RevisionReviewIntake(
        schema_version=REVISION_REVIEW_SCHEMA_VERSION,
        revision_review_id=rid,
        receipt_record_id=receipt["receipt_record_id"],
        customer_decision_id=None,
        actual_delivery_record_id=actual_delivery_record_id,
        delivery_package_id=receipt["source_delivery_package_id"],
        project_id=receipt["project_id"],
        customer_reference=receipt["customer_reference"],
        artifact_id=receipt["artifact_id"],
        artifact_sha256=receipt["artifact_sha256"],
        revision_review_reason=reason,
        decision_date=dec_date,
        safe_evidence_reference=ev_ref,
        recorded_by_operator_id=operator_id,
        revision_created=False,
        successor_version_calculated=False,
        rerender_approved=False,
        hvs_invoked=False,
        invoice_state_changed=False,
        payment_state_changed=False,
        customer_contact_performed=False,
        external_action_performed=False,
        automation_allowed=False,
        deterministic_content_hash=record_content_hash(
            {
                "revision_review_reason": reason,
                "safe_evidence_reference": ev_ref,
            }
        ),
        informational_recorded_at=informational_recorded_at,
    )
    append_receipt_event(
        ledger_path=ledger,
        event_type=EVT_CUSTOMER_REVISION_REVIEW_REQUESTED,
        aggregate_id=rid,
        project_id=record.project_id,
        actual_delivery_record_id=actual_delivery_record_id,
        artifact_sha256=record.artifact_sha256,
        operator_id=operator_id,
        resulting_status=DECISION_REVISION_REVIEW_REQUESTED,
        recorded_at=informational_recorded_at,
        package_id=record.delivery_package_id,
        record_payload=record.to_dict(),
    )
    return Stage8PServiceResult(
        ok=True,
        actual_delivery_record_id=actual_delivery_record_id,
        revision_review_id=rid,
        receipt_record_id=receipt["receipt_record_id"],
        decision_status=DECISION_REVISION_REVIEW_REQUESTED,
        delivery_package_id=record.delivery_package_id,
        artifact_id=record.artifact_id,
        artifact_sha256=record.artifact_sha256,
        customer_reference=record.customer_reference,
        safe_evidence_reference=ev_ref,
    )


# ---------------------------------------------------------------------------
# Read-only readiness / outcome view
# ---------------------------------------------------------------------------
def build_acceptance_readiness_view(*, repo_root: Any, actual_delivery_record_id: str) -> DeliveryAcceptanceReadiness:
    ledger = receipt_ledger_path(repo_root)
    events = events_for_actual_delivery(ledger_path=ledger, actual_delivery_record_id=actual_delivery_record_id)
    receipt = None
    decision_record = None
    decision_event_type = None
    for ev in events:
        et = ev.get("event_type")
        if et in (EVT_RECEIPT_CONFIRMED, EVT_RECEIPT_REJECTED):
            rec = ev.get("record") or {}
            if receipt is None or rec.get("receipt_record_id", "") >= receipt.get("receipt_record_id", ""):
                receipt = rec
        elif et in (
            EVT_CUSTOMER_ACCEPTED,
            EVT_CUSTOMER_REJECTED,
            EVT_CUSTOMER_ISSUE_REPORTED,
            EVT_CUSTOMER_REVISION_REVIEW_REQUESTED,
        ):
            # Issue / revision-review intake records carry no decision_status; derive
            # the category from the reliable event type instead of the record shape.
            decision_record = ev.get("record") or {}
            decision_event_type = et

    if receipt is None:
        outcome = OUTCOME_RECEIPT_NOT_CONFIRMED
        decision_status = DECISION_NO_DECISION
    elif receipt.get("receipt_status") in (RECEIPT_IDENTITY_CONFLICT, RECEIPT_REJECTED_AS_INVALID):
        outcome = OUTCOME_DELIVERY_IDENTITY_CONFLICT
        decision_status = DECISION_NO_DECISION
    elif decision_event_type is None:
        outcome = OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING
        decision_status = DECISION_NO_DECISION
    else:
        if decision_event_type == EVT_CUSTOMER_ACCEPTED:
            outcome = OUTCOME_ACCEPTED_BY_CUSTOMER
            decision_status = DECISION_ACCEPTED
        elif decision_event_type == EVT_CUSTOMER_REJECTED:
            outcome = OUTCOME_REJECTED_BY_CUSTOMER
            decision_status = DECISION_REJECTED
        elif decision_event_type == EVT_CUSTOMER_ISSUE_REPORTED:
            outcome = OUTCOME_ISSUE_REPORTED
            decision_status = DECISION_ISSUE_REPORTED
        elif decision_event_type == EVT_CUSTOMER_REVISION_REVIEW_REQUESTED:
            outcome = OUTCOME_REVISION_REVIEW_REQUESTED
            decision_status = DECISION_REVISION_REVIEW_REQUESTED
        else:  # pragma: no cover - guarded above
            outcome = OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING
            decision_status = DECISION_NO_DECISION

    return DeliveryAcceptanceReadiness(
        schema_version=READINESS_SCHEMA_VERSION,
        actual_delivery_record_id=actual_delivery_record_id,
        project_id=(receipt or {}).get("project_id", "") or (decision_record or {}).get("project_id", ""),
        customer_reference=(receipt or {}).get("customer_reference", "") or (decision_record or {}).get("customer_reference", ""),
        artifact_id=(receipt or {}).get("artifact_id", "") or (decision_record or {}).get("artifact_id", ""),
        artifact_sha256=(receipt or {}).get("artifact_sha256", "") or (decision_record or {}).get("artifact_sha256", ""),
        receipt_status=(receipt or {}).get("receipt_status", "NOT_RECORDED"),
        receipt_record_id=(receipt or {}).get("receipt_record_id"),
        decision_status=decision_status,
        customer_decision_id=(decision_record or {}).get("customer_decision_id"),
        outcome=outcome,
    )


def inspect_delivery_post_receipt_status(*, repo_root: Any, actual_delivery_record_id: str) -> Stage8PServiceResult:
    view = build_acceptance_readiness_view(repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id)
    return Stage8PServiceResult(
        ok=True,
        actual_delivery_record_id=actual_delivery_record_id,
        receipt_status=view.receipt_status,
        decision_status=view.decision_status,
        outcome=view.outcome,
        delivery_package_id=view.artifact_id and None,  # not applicable; kept minimal
        artifact_id=view.artifact_id,
        artifact_sha256=view.artifact_sha256,
        customer_reference=view.customer_reference,
    )
