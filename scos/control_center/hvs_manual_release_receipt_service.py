"""Stage 8F manual release execution, customer receipt confirmation, and
post-delivery audit closure service; evidence recording only, no HVS execution,
no outbound transport, no customer contact.

Consumes the Stage 8E release evidence (acceptance / authorization / final
closure / readiness) read-only via the public Stage 8E service functions, then
records:

  A. that an authorized revised delivery was released to the customer through a
     manual channel (evidence only — no transport executed),
  B. that the customer confirmed receipt (evidence only — no contact made),
  C. the deterministic post-delivery audit readiness and final closure.

The service:
  * loads Stage 8E authorization / final closure / readiness read-only,
  * validates lineage and state transitions,
  * enforces deterministic idempotency,
  * appends append-only audit evidence,
  * returns structured results,
  * preserves exact rejection reasons,
  * avoids broad exception swallowing,
  * performs no customer contact, no network, no HVS invocation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hvs_manual_release_receipt_models import (
    AUDIT_CLOSED,
    AUDIT_OPEN,
    AUDIT_READY,
    AUDIT_REJECTED,
    POST_DELIVERY_SCHEMA_VERSION,
    CustomerReceiptConfirmation,
    ManualReleaseExecution,
    PostDeliveryAuditClosure,
    build_audit_id,
    build_receipt_id,
    build_release_id,
    build_release_idempotency_key,
)
from .hvs_manual_release_receipt_store import (
    append_post_delivery_event,
    make_post_delivery_event,
    post_delivery_audit_path,
    read_post_delivery_events,
)
from .hvs_revised_delivery_release_models import (
    AUTH_AUTHORIZED,
    AUTH_EXPIRED,
    AUTH_REVOKED,
)
from .hvs_revised_delivery_release_service import (
    evaluate_release_readiness,
    inspect_final_closure,
    inspect_release_lineage,
)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------
@dataclass
class PostDeliveryServiceResult:
    ok: bool
    release: ManualReleaseExecution | None = None
    receipt: CustomerReceiptConfirmation | None = None
    audit: PostDeliveryAuditClosure | None = None
    duplicate_of: str | None = None
    existing_id: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    hvs_invoked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": POST_DELIVERY_SCHEMA_VERSION,
            "release": self.release.to_dict() if self.release else None,
            "receipt": self.receipt.to_dict() if self.receipt else None,
            "audit": self.audit.to_dict() if self.audit else None,
            "duplicate_of": self.duplicate_of,
            "existing_id": self.existing_id,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "hvs_invoked": self.hvs_invoked,
            "automation_allowed": False,
        }


def _deny(*, code: str, detail: str) -> PostDeliveryServiceResult:
    return PostDeliveryServiceResult(False, error_code=code, error_detail=detail)


# ---------------------------------------------------------------------------
# Read-only Stage 8E lineage loaders (no mutation of prior-stage stores)
# ---------------------------------------------------------------------------
def _load_authorization(*, repo_root: Path, authorization_id: str):
    from .hvs_revised_delivery_release_service import _authorizations_by_id

    return _authorizations_by_id(repo_root=repo_root).get(authorization_id)


def _effective_authorization_status(*, repo_root: Path, authorization_id: str) -> str | None:
    """Return the effective authorization status from the 8E ledger.

    Reads the immutable authorization record status and honors a REVOKED
    terminal event. Returns None if the authorization does not exist.
    """
    from .hvs_revised_delivery_release_models import EVT_RELEASE_AUTHORIZATION_REVOKED
    from .hvs_revised_delivery_release_store import read_release_events

    auth = _load_authorization(repo_root=repo_root, authorization_id=authorization_id)
    if auth is None:
        return None
    for event in read_release_events(audit_log_path=_release_8e_path(repo_root)):
        if (
            event.subject_id == authorization_id
            and event.event_type == EVT_RELEASE_AUTHORIZATION_REVOKED
        ):
            return AUTH_REVOKED
    return auth.status


def _release_8e_path(repo_root: Path):
    from .hvs_revised_delivery_release_store import release_audit_path

    return release_audit_path(repo_root)


def _releases_by_authorization(*, repo_root: Path) -> dict[str, ManualReleaseExecution]:
    out: dict[str, ManualReleaseExecution] = {}
    for event in read_post_delivery_events(audit_log_path=post_delivery_audit_path(repo_root)):
        if event.event_type == "MANUAL_RELEASE_RECORDED":
            rec = ManualReleaseExecution(**event.record)
            out[rec.authorization_id] = rec
    return out


def _release_by_id(*, repo_root: Path, release_id: str) -> ManualReleaseExecution | None:
    for event in read_post_delivery_events(audit_log_path=post_delivery_audit_path(repo_root)):
        if event.event_type == "MANUAL_RELEASE_RECORDED" and event.subject_id == release_id:
            return ManualReleaseExecution(**event.record)
    return None


def _receipts_by_release(*, repo_root: Path) -> dict[str, CustomerReceiptConfirmation]:
    out: dict[str, CustomerReceiptConfirmation] = {}
    for event in read_post_delivery_events(audit_log_path=post_delivery_audit_path(repo_root)):
        if event.event_type == "CUSTOMER_RECEIPT_CONFIRMED":
            rec = CustomerReceiptConfirmation(**event.record)
            out[rec.release_id] = rec
    return out


def _audits_by_revision(*, repo_root: Path) -> dict[str, PostDeliveryAuditClosure]:
    out: dict[str, PostDeliveryAuditClosure] = {}
    for event in read_post_delivery_events(audit_log_path=post_delivery_audit_path(repo_root)):
        if event.event_type == "POST_DELIVERY_AUDIT_CLOSED":
            rec = PostDeliveryAuditClosure(**event.record)
            out[rec.revision_id] = rec
    return out


def _audit_exists(*, repo_root: Path, audit_id: str) -> bool:
    for event in read_post_delivery_events(audit_log_path=post_delivery_audit_path(repo_root)):
        if event.subject_id == audit_id:
            return True
    return False


# ---------------------------------------------------------------------------
# A. Manual release execution recording
# ---------------------------------------------------------------------------
def record_manual_release(
    *,
    authorization_id: str,
    released_by: str,
    release_channel: str,
    released_formats: tuple[str, ...],
    customer_reference: str,
    release_method_reference: str,
    operator_id: str,
    repo_root: Path,
    recorded_at: str,
    evidence_references: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> PostDeliveryServiceResult:
    """Record that an authorized revised delivery was manually released.

    Evidence recording only — no transport is executed, no customer is
    contacted. Fails closed on missing / mismatched / conflicting lineage.
    """
    auth = _load_authorization(repo_root=repo_root, authorization_id=authorization_id)
    if auth is None:
        return _deny(code="AUTHORIZATION_NOT_FOUND", detail="referenced authorization does not exist")

    status = _effective_authorization_status(repo_root=repo_root, authorization_id=authorization_id)
    if status != AUTH_AUTHORIZED:
        return _deny(
            code="AUTHORIZATION_NOT_AUTHORIZED",
            detail=f"authorization is not in an authorized state (status={status})",
        )

    # Original delivery id is carried by the Stage 8E acceptance, not the
    # authorization record; load it to bind the full lineage.
    from .hvs_revised_delivery_release_service import _load_acceptance_by_id

    acceptance = _load_acceptance_by_id(repo_root=repo_root, acceptance_id=auth.acceptance_id)
    if acceptance is None:
        return _deny(code="ACCEPTANCE_NOT_FOUND", detail="referenced acceptance does not exist")
    original_delivery_id = acceptance.original_delivery_id

    release_id = build_release_id(
        authorization_id=auth.authorization_id,
        acceptance_id=auth.acceptance_id,
        revision_id=auth.revision_id,
        revised_delivery_id=auth.revised_delivery_id,
        original_delivery_id=original_delivery_id,
        released_formats=tuple(released_formats),
        release_channel=release_channel,
        customer_reference=customer_reference,
        release_method_reference=release_method_reference,
    )

    existing = _releases_by_authorization(repo_root=repo_root).get(authorization_id)
    if existing is not None:
        if existing.release_id == release_id:
            return PostDeliveryServiceResult(
                True, release=existing, duplicate_of=existing.release_id, existing_id=existing.release_id
            )
        return _deny(
            code="CONFLICTING_RELEASE",
            detail="a different manual release already exists for this authorization",
        )

    idempotency_key = build_release_idempotency_key(
        release_id=release_id,
        authorization_id=auth.authorization_id,
        acceptance_id=auth.acceptance_id,
        revision_id=auth.revision_id,
        revised_delivery_id=auth.revised_delivery_id,
        original_delivery_id=original_delivery_id,
        project_id=auth.project_id,
        correlation_id=auth.correlation_id,
        released_formats=tuple(released_formats),
        release_channel=release_channel,
        customer_reference=customer_reference,
        status="RECORDED",
    )

    # Format + channel + customer-reference guards (also enforced by model).
    released_formats = tuple(sorted(released_formats))
    for fmt in released_formats:
        if fmt not in auth.approved_formats:
            return _deny(
                code="RELEASE_FORMAT_NOT_AUTHORIZED",
                detail=f"format {fmt!r} is not covered by the authorization scope",
            )
    if release_channel not in auth.allowed_delivery_channels:
        return _deny(
            code="RELEASE_CHANNEL_NOT_AUTHORIZED",
            detail=f"channel {release_channel!r} is not allowed by the authorization",
        )
    if customer_reference != auth.customer_reference:
        return _deny(
            code="CUSTOMER_REFERENCE_MISMATCH",
            detail="customer reference does not match the authorization",
        )

    try:
        release = ManualReleaseExecution(
            schema_version=POST_DELIVERY_SCHEMA_VERSION,
            release_id=release_id,
            authorization_id=auth.authorization_id,
            acceptance_id=auth.acceptance_id,
            revision_id=auth.revision_id,
            revised_delivery_id=auth.revised_delivery_id,
            original_delivery_id=original_delivery_id,
            project_id=auth.project_id,
            correlation_id=auth.correlation_id,
            released_by=released_by,
            released_at=recorded_at,
            release_channel=release_channel,
            released_formats=released_formats,
            customer_reference=customer_reference,
            release_method_reference=release_method_reference,
            status="RECORDED",
            idempotency_key=idempotency_key,
            evidence_references=tuple(evidence_references),
            metadata=dict(metadata or {}),
            created_at=recorded_at,
        )
    except ValueError as exc:
        return _deny(code="RELEASE_VALIDATION", detail=str(exc))

    event = make_post_delivery_event(
        event_type="MANUAL_RELEASE_RECORDED",
        subject_id=release.release_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=release.to_dict(),
    )
    try:
        append_post_delivery_event(audit_log_path=post_delivery_audit_path(repo_root), event=event)
    except ValueError as exc:
        if "conflicting duplicate" in str(exc):
            return _deny(code="CONFLICTING_REQUEST", detail=str(exc))
        raise
    return PostDeliveryServiceResult(True, release=release)


# ---------------------------------------------------------------------------
# B. Customer receipt confirmation
# ---------------------------------------------------------------------------
def record_customer_receipt(
    *,
    release_id: str,
    confirmed_by: str,
    receipt_status: str,
    received_formats: tuple[str, ...],
    customer_reference: str,
    confirmation_reference: str,
    operator_id: str,
    repo_root: Path,
    recorded_at: str,
    receipt_channel: str | None = None,
    receipt_notes: str | None = None,
    evidence_references: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> PostDeliveryServiceResult:
    """Record that the customer confirmed receipt of the released delivery.

    Evidence recording only — no customer contact, no transport. Fails closed on
    missing release / mismatched lineage / conflicting receipt.
    """
    release = _release_by_id(repo_root=repo_root, release_id=release_id)
    if release is None:
        return _deny(code="RELEASE_NOT_FOUND", detail="referenced manual release does not exist")

    receipt_id = build_receipt_id(
        release_id=release.release_id,
        authorization_id=release.authorization_id,
        acceptance_id=release.acceptance_id,
        revision_id=release.revision_id,
        revised_delivery_id=release.revised_delivery_id,
        received_formats=tuple(received_formats),
        receipt_status=receipt_status,
        customer_reference=customer_reference,
    )

    existing = _receipts_by_release(repo_root=repo_root).get(release_id)
    if existing is not None:
        if existing.receipt_id == receipt_id:
            return PostDeliveryServiceResult(
                True, receipt=existing, duplicate_of=existing.receipt_id, existing_id=existing.receipt_id
            )
        return _deny(
            code="CONFLICTING_RECEIPT",
            detail="a different receipt already exists for this release",
        )

    # Lineage guards.
    if customer_reference != release.customer_reference:
        return _deny(code="CUSTOMER_REFERENCE_MISMATCH", detail="customer reference does not match the release")
    for fmt in tuple(sorted(received_formats)):
        if fmt not in release.released_formats:
            return _deny(
                code="RECEIPT_FORMAT_NOT_RELEASED",
                detail=f"format {fmt!r} was not part of the released delivery",
            )

    try:
        receipt = CustomerReceiptConfirmation(
            schema_version=POST_DELIVERY_SCHEMA_VERSION,
            receipt_id=receipt_id,
            release_id=release.release_id,
            authorization_id=release.authorization_id,
            acceptance_id=release.acceptance_id,
            revision_id=release.revision_id,
            revised_delivery_id=release.revised_delivery_id,
            project_id=release.project_id,
            correlation_id=release.correlation_id,
            customer_reference=customer_reference,
            confirmed_by=confirmed_by,
            confirmed_at=recorded_at,
            receipt_status=receipt_status,
            received_formats=tuple(sorted(received_formats)),
            receipt_channel=receipt_channel,
            confirmation_reference=confirmation_reference,
            receipt_notes=receipt_notes,
            evidence_references=tuple(evidence_references),
            metadata=dict(metadata or {}),
            created_at=recorded_at,
        )
    except ValueError as exc:
        return _deny(code="RECEIPT_VALIDATION", detail=str(exc))

    event = make_post_delivery_event(
        event_type="CUSTOMER_RECEIPT_CONFIRMED",
        subject_id=receipt.receipt_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=receipt.to_dict(),
    )
    try:
        append_post_delivery_event(audit_log_path=post_delivery_audit_path(repo_root), event=event)
    except ValueError as exc:
        if "conflicting duplicate" in str(exc):
            return _deny(code="CONFLICTING_REQUEST", detail=str(exc))
        raise
    return PostDeliveryServiceResult(True, receipt=receipt)


# ---------------------------------------------------------------------------
# C. Post-delivery audit readiness + closure
# ---------------------------------------------------------------------------
def evaluate_post_delivery_audit(
    *,
    authorization_id: str,
    operator_id: str,
    repo_root: Path,
    recorded_at: str,
) -> PostDeliveryServiceResult:
    """Deterministically evaluate post-delivery audit readiness (fail-closed)."""
    auth = _load_authorization(repo_root=repo_root, authorization_id=authorization_id)
    if auth is None:
        return _deny(code="AUTHORIZATION_NOT_FOUND", detail="referenced authorization does not exist")

    from .hvs_revised_delivery_release_service import _load_acceptance_by_id

    acceptance = _load_acceptance_by_id(repo_root=repo_root, acceptance_id=auth.acceptance_id)
    original_delivery_id = acceptance.original_delivery_id if acceptance else None

    status = _effective_authorization_status(repo_root=repo_root, authorization_id=authorization_id)
    if status != AUTH_AUTHORIZED:
        return _deny(code="AUTHORIZATION_NOT_AUTHORIZED", detail=f"authorization status={status}")

    release = _releases_by_authorization(repo_root=repo_root).get(authorization_id)
    if release is None:
        return _deny(code="RELEASE_NOT_FOUND", detail="no recorded manual release for this authorization")

    receipt = _receipts_by_release(repo_root=repo_root).get(release.release_id)
    reasons: list[str] = []

    # Require that the receipt (if recorded) confirms the same lineage.
    if receipt is not None:
        if receipt.customer_reference != auth.customer_reference:
            reasons.append("receipt customer reference mismatch")
        if not set(receipt.received_formats).issubset(set(release.released_formats)):
            reasons.append("receipt references formats not released")

    # Cross-check against the 8E readiness decision for this authorization.
    readiness = evaluate_release_readiness(
        acceptance_id=auth.acceptance_id,
        authorization_id=auth.authorization_id,
        repo_root=repo_root,
        recorded_at=recorded_at,
    )
    if not readiness.release_ready:
        reasons.append("underlying Stage 8E release readiness is not satisfied")

    closure = inspect_final_closure(revision_id=auth.revision_id, repo_root=repo_root)
    if not closure.ok or closure.closure is None:
        reasons.append("Stage 8E final revision closure is missing")

    audit_ready = len(reasons) == 0
    decision = AUDIT_READY if audit_ready else AUDIT_REJECTED

    audit = PostDeliveryAuditClosure(
        schema_version=POST_DELIVERY_SCHEMA_VERSION,
        audit_id=build_audit_id(
            release_id=release.release_id,
            receipt_id=receipt.receipt_id if receipt else None,
            authorization_id=auth.authorization_id,
            acceptance_id=auth.acceptance_id,
            revision_id=auth.revision_id,
            dispatch_id=None,
            reconciliation_result_id=None,
            original_delivery_id=original_delivery_id,
            revised_delivery_id=auth.revised_delivery_id,
            project_id=auth.project_id,
            correlation_id=auth.correlation_id,
            audit_ready=audit_ready,
            closure_decision=decision,
        ),
        release_id=release.release_id,
        receipt_id=receipt.receipt_id if receipt else None,
        authorization_id=auth.authorization_id,
        acceptance_id=auth.acceptance_id,
        revision_id=auth.revision_id,
        dispatch_id=None,
        reconciliation_result_id=None,
        original_delivery_id=original_delivery_id,
        revised_delivery_id=auth.revised_delivery_id,
        project_id=auth.project_id,
        correlation_id=auth.correlation_id,
        audit_ready=audit_ready,
        closure_decision=decision,
        reasons=tuple(reasons),
        evidence_references=(),
        closed_by=operator_id,
        closed_at=recorded_at,
        created_at=recorded_at,
    )
    return PostDeliveryServiceResult(True, audit=audit)


def close_post_delivery_audit(
    *,
    authorization_id: str,
    operator_id: str,
    repo_root: Path,
    recorded_at: str,
    metadata: dict[str, Any] | None = None,
) -> PostDeliveryServiceResult:
    """Close the post-delivery audit (append-only; idempotent; conflict-rejected).

    Requires a satisfied post-delivery audit readiness evaluation. Creates the
    closure exactly once; identical replay returns the existing closure;
    conflicting closure under the same revision is rejected.
    """
    readiness = evaluate_post_delivery_audit(
        authorization_id=authorization_id,
        operator_id=operator_id,
        repo_root=repo_root,
        recorded_at=recorded_at,
    )
    if not readiness.ok or readiness.audit is None:
        return _deny(code="AUDIT_NOT_READY", detail="post-delivery audit is not ready to close")
    if not readiness.audit.audit_ready:
        return _deny(code="AUDIT_NOT_READY", detail="; ".join(readiness.audit.reasons))

    audit = readiness.audit
    # Re-finalize with CLOSED decision + metadata (immutable record).
    try:
        closure = PostDeliveryAuditClosure(
            schema_version=POST_DELIVERY_SCHEMA_VERSION,
            audit_id=audit.audit_id,
            release_id=audit.release_id,
            receipt_id=audit.receipt_id,
            authorization_id=audit.authorization_id,
            acceptance_id=audit.acceptance_id,
            revision_id=audit.revision_id,
            dispatch_id=audit.dispatch_id,
            reconciliation_result_id=audit.reconciliation_result_id,
            original_delivery_id=audit.original_delivery_id,
            revised_delivery_id=audit.revised_delivery_id,
            project_id=audit.project_id,
            correlation_id=audit.correlation_id,
            audit_ready=audit.audit_ready,
            closure_decision=AUDIT_CLOSED,
            reasons=audit.reasons,
            evidence_references=tuple(),
            closed_by=operator_id,
            closed_at=recorded_at,
            created_at=recorded_at,
        )
    except ValueError as exc:
        return _deny(code="AUDIT_VALIDATION", detail=str(exc))

    existing = _audits_by_revision(repo_root=repo_root).get(closure.revision_id)
    if existing is not None:
        if existing.audit_id == closure.audit_id:
            return PostDeliveryServiceResult(
                True, audit=existing, duplicate_of=existing.audit_id, existing_id=existing.audit_id
            )
        return _deny(
            code="CONFLICTING_AUDIT_CLOSURE",
            detail="a different post-delivery audit closure already exists for this revision",
        )

    event = make_post_delivery_event(
        event_type="POST_DELIVERY_AUDIT_CLOSED",
        subject_id=closure.audit_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=closure.to_dict(),
    )
    try:
        append_post_delivery_event(audit_log_path=post_delivery_audit_path(repo_root), event=event)
    except ValueError as exc:
        if "conflicting duplicate" in str(exc):
            return _deny(code="CONFLICTING_REQUEST", detail=str(exc))
        raise
    return PostDeliveryServiceResult(True, audit=closure)


# ---------------------------------------------------------------------------
# Inspect helpers
# ---------------------------------------------------------------------------
def inspect_manual_release(*, authorization_id: str, repo_root: Path) -> PostDeliveryServiceResult:
    release = _releases_by_authorization(repo_root=repo_root).get(authorization_id)
    if release is None:
        return _deny(code="RELEASE_NOT_FOUND", detail="no recorded manual release for this authorization")
    return PostDeliveryServiceResult(True, release=release)


def inspect_customer_receipt(*, release_id: str, repo_root: Path) -> PostDeliveryServiceResult:
    receipt = _receipts_by_release(repo_root=repo_root).get(release_id)
    if receipt is None:
        return _deny(code="RECEIPT_NOT_FOUND", detail="no recorded receipt for this release")
    return PostDeliveryServiceResult(True, receipt=receipt)


def inspect_post_delivery_lineage(*, project_id: str | None, repo_root: Path) -> dict[str, Any]:
    """Inspect the complete post-delivery lineage (Stage 8F + Stage 8E + 8D)."""
    releases = _releases_by_authorization(repo_root=repo_root)
    receipts = _receipts_by_release(repo_root=repo_root)
    audits = _audits_by_revision(repo_root=repo_root)
    return {
        "schema_version": POST_DELIVERY_SCHEMA_VERSION,
        "project_id": project_id,
        "releases": [r.to_dict() for r in releases.values()],
        "receipts": [r.to_dict() for r in receipts.values()],
        "audits": [a.to_dict() for a in audits.values()],
        "stage8e_lineage": inspect_release_lineage(project_id=project_id, repo_root=repo_root),
        "automation_allowed": False,
    }
