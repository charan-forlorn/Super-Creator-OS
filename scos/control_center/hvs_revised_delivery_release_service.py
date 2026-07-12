"""Stage 8E revised-delivery acceptance, customer release authorization, and
final revision closure service; no HVS execution, no outbound transport.

Consumes the Stage 8D reconciled revised delivery (read-only, via public Stage
8D ledger helpers) and deterministically drives it through:

  1. revised-delivery acceptance review (internal)
  2. explicit customer-release authorization (evidence only)
  3. deterministic release-readiness evaluation (fail-closed)
  4. final revision closure (append-only, idempotent, conflict-rejected)

The service never invokes HVS, never renders media, never creates a second
delivery-version / revision / dispatch / reconciliation / approval / audit
subsystem, performs NO customer contact, and executes NO delivery transport.

Domain logic is kept separate from CLI formatting and filesystem plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hvs_delivery_lineage_service import inspect_delivery_lineage
from .hvs_rerender_dispatch_models import REVISION_SUPERSEDED as DISPATCH_REVISION_SUPERSEDED
from .hvs_rerender_dispatch_service import inspect_rerender_dispatch
from .hvs_rerender_result_models import (
    EVT_DELIVERY_SUPERSEDED,
    EVT_REVISED_DELIVERY_CREATED,
    EVT_RERENDER_RESULT_ACCEPTED,
    EVT_RERENDER_RESULT_REJECTED,
    EVT_RERENDER_FAILED,
    RevisedDeliveryRecord,
    SupersessionRecord,
)
from .hvs_rerender_result_reconciliation_service import (
    EVT_REVISION_COMPLETED,
)
from .hvs_rerender_result_store import (
    read_reconciliation_events,
    reconciliation_audit_path,
)
from .hvs_revised_delivery_release_models import (
    ACCEPTANCE_ACCEPTED,
    ACCEPTANCE_CANCELLED,
    ACCEPTANCE_PARTIALLY_ACCEPTED,
    ACCEPTANCE_PENDING_REVIEW,
    ACCEPTANCE_REJECTED,
    ACCEPTANCE_SUPERSEDED,
    AUTH_AUTHORIZED,
    AUTH_CANCELLED,
    AUTH_EXPIRED,
    AUTH_PENDING,
    AUTH_REJECTED,
    AUTH_REVOKED,
    AUTH_SUPERSEDED,
    EVT_CONFLICTING_REQUEST_REJECTED,
    EVT_RELEASE_AUTHORIZATION_REVOKED,
    EVT_RELEASE_AUTHORIZED,
    EVT_RELEASE_READINESS_REJECTED,
    EVT_REVISED_DELIVERY_ACCEPTED,
    EVT_REVISED_DELIVERY_PARTIALLY_ACCEPTED,
    EVT_REVISED_DELIVERY_REJECTED,
    EVT_REVISION_FINALLY_CLOSED,
    RELEASE_SCHEMA_VERSION,
    CustomerReleaseAuthorization,
    FinalRevisionClosure,
    ReleaseAuditEvent,
    ReleaseReadinessDecision,
    RevisedDeliveryAcceptance,
    build_acceptance_id,
    build_authorization_id,
    build_authorization_idempotency_key,
    build_closure_id,
    build_readiness_id,
)
from .hvs_revised_delivery_release_store import (
    append_release_event,
    make_release_event,
    read_release_events,
    release_audit_path,
)
from .hvs_revision_models import CANCELLED, REJECTED
from .hvs_revision_service import _state as revision_state

# Revision states that still permit release under Stage 8E. The Stage 8D
# closure is recorded in the Stage 8D ledger (not the Stage 8B ledger), so the
# Stage 8B revision state remains in an approved/render-authorized state; it is
# release-eligible as long as it has not been cancelled, rejected, or
# superseded by an incompatible revision.
_RELEASE_ELIGIBLE_REVISION_STATUSES = (
    "APPROVED_FOR_RERENDER_PLANNING",
    "RERENDER_AUTHORIZATION_READY",
)


@dataclass(frozen=True)
class ReleaseServiceResult:
    ok: bool
    acceptance: RevisedDeliveryAcceptance | None = None
    authorization: CustomerReleaseAuthorization | None = None
    readiness: ReleaseReadinessDecision | None = None
    closure: FinalRevisionClosure | None = None
    duplicate_of: str | None = None
    existing_id: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    hvs_invoked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": RELEASE_SCHEMA_VERSION,
            "acceptance": self.acceptance.to_dict() if self.acceptance else None,
            "authorization": self.authorization.to_dict() if self.authorization else None,
            "readiness": self.readiness.to_dict() if self.readiness else None,
            "closure": self.closure.to_dict() if self.closure else None,
            "duplicate_of": self.duplicate_of,
            "existing_id": self.existing_id,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "hvs_invoked": self.hvs_invoked,
            "automation_allowed": False,
        }


def _deny(*, code: str, detail: str) -> ReleaseServiceResult:
    return ReleaseServiceResult(False, error_code=code, error_detail=detail)


# ---------------------------------------------------------------------------
# Read-only Stage 8D lineage loaders (no mutation of prior-stage stores)
# ---------------------------------------------------------------------------
def _load_revised_delivery(*, repo_root: Path, revised_delivery_id: str) -> RevisedDeliveryRecord | None:
    for event in read_reconciliation_events(audit_log_path=reconciliation_audit_path(repo_root)):
        if event.event_type == EVT_REVISED_DELIVERY_CREATED:
            rec = event.record
            if rec.get("revised_delivery_id") == revised_delivery_id:
                return RevisedDeliveryRecord(**rec)
    return None


def _load_supersession(*, repo_root: Path, revised_delivery_id: str) -> SupersessionRecord | None:
    revised = _load_revised_delivery(repo_root=repo_root, revised_delivery_id=revised_delivery_id)
    if revised is None:
        return None
    for event in read_reconciliation_events(audit_log_path=reconciliation_audit_path(repo_root)):
        if event.event_type == EVT_DELIVERY_SUPERSEDED:
            rec = event.record
            if rec.get("superseding_delivery_record_id") == revised.new_delivery_record_id:
                return SupersessionRecord(**rec)
    return None


def _reconciliation_succeeded(*, repo_root: Path, result_id: str) -> bool:
    """True only if the Stage 8D ledger shows an accepted (not failed/rejected)
    result for this result id."""
    accepted = False
    for event in read_reconciliation_events(audit_log_path=reconciliation_audit_path(repo_root)):
        if event.event_type == EVT_RERENDER_RESULT_ACCEPTED and event.result_id == result_id:
            accepted = True
        elif event.event_type in (EVT_RERENDER_RESULT_REJECTED, EVT_RERENDER_FAILED) and event.result_id == result_id:
            return False
    return accepted


def _revision_closed_by_8d(*, repo_root: Path, revision_id: str) -> bool:
    for event in read_reconciliation_events(audit_log_path=reconciliation_audit_path(repo_root)):
        if event.event_type == EVT_REVISION_COMPLETED and event.record.get("revision_id") == revision_id:
            return True
    return False


# ---------------------------------------------------------------------------
# Stage 8E acceptance / authorization / closure event loaders
# ---------------------------------------------------------------------------
def _load_acceptance_by_id(*, repo_root: Path, acceptance_id: str) -> RevisedDeliveryAcceptance | None:
    for event in read_release_events(audit_log_path=release_audit_path(repo_root)):
        if event.event_type in (
            EVT_REVISED_DELIVERY_ACCEPTED,
            EVT_REVISED_DELIVERY_PARTIALLY_ACCEPTED,
            EVT_REVISED_DELIVERY_REJECTED,
        ):
            if event.subject_id == acceptance_id:
                return RevisedDeliveryAcceptance(**event.record)
    return None


def _acceptances_by_revision(*, repo_root: Path) -> dict[str, RevisedDeliveryAcceptance]:
    out: dict[str, RevisedDeliveryAcceptance] = {}
    for event in read_release_events(audit_log_path=release_audit_path(repo_root)):
        if event.event_type in (
            EVT_REVISED_DELIVERY_ACCEPTED,
            EVT_REVISED_DELIVERY_PARTIALLY_ACCEPTED,
            EVT_REVISED_DELIVERY_REJECTED,
        ):
            rec = event.record
            acc = RevisedDeliveryAcceptance(**rec)
            # Keep only the latest terminal acceptance per revision.
            prior = out.get(acc.revision_id)
            if prior is None or prior.created_at <= acc.created_at:
                out[acc.revision_id] = acc
    return out


def _authorizations_by_id(*, repo_root: Path) -> dict[str, CustomerReleaseAuthorization]:
    out: dict[str, CustomerReleaseAuthorization] = {}
    for event in read_release_events(audit_log_path=release_audit_path(repo_root)):
        if event.event_type == EVT_RELEASE_AUTHORIZED:
            rec = event.record
            auth = CustomerReleaseAuthorization(**rec)
            out[auth.authorization_id] = auth
    return out


def _effective_authorization_status(*, authorization: CustomerReleaseAuthorization, repo_root: Path) -> str:
    """Derive the effective authorization status from append-only events.

    The immutable authorization record always carries its *created* status
    (AUTHORIZED). A terminal REVOKED event recorded against the same
    authorization id takes precedence. Expired / cancelled / superseded states
    are not emitted as separate events by Stage 8E; they are reflected in the
    immutable record status and evaluated directly by the readiness gate.
    """
    for event in read_release_events(audit_log_path=release_audit_path(repo_root)):
        if event.subject_id == authorization.authorization_id:
            if event.event_type == EVT_RELEASE_AUTHORIZATION_REVOKED:
                return AUTH_REVOKED
    return authorization.status


def _conflicting_authorization_exists(
    *, repo_root: Path, acceptance: RevisedDeliveryAcceptance, authorization_id: str | None
) -> bool:
    """A different active authorization for the same acceptance/lineage is a
    conflict (only one active authorization per acceptance)."""
    for auth in _authorizations_by_id(repo_root=repo_root).values():
        if auth.authorization_id == (authorization_id or ""):
            continue
        if auth.acceptance_id != acceptance.acceptance_id:
            continue
        status = _effective_authorization_status(authorization=auth, repo_root=repo_root)
        if status == AUTH_AUTHORIZED:
            return True
    return False


# ---------------------------------------------------------------------------
# 1. Revised-delivery acceptance
# ---------------------------------------------------------------------------
def record_revised_delivery_acceptance(
    *,
    reconciliation_result_id: str,
    revised_delivery_id: str,
    reviewer_id: str,
    accepted_formats: tuple[str, ...],
    rejection_codes: tuple[str, ...] = (),
    rejected_formats: tuple[str, ...] = (),
    quality_gate_reference: str,
    artifact_integrity_reference: str,
    acceptance_status: str = ACCEPTANCE_ACCEPTED,
    review_notes: str | None = None,
    evidence_references: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
    operator_id: str,
    repo_root,
    recorded_at: str,
) -> ReleaseServiceResult:
    if not str(operator_id or "").strip() or not str(reviewer_id or "").strip():
        return _deny(code="MISSING_REQUIRED_INPUT", detail="operator_id and reviewer_id are required")
    if not str(quality_gate_reference or "").strip():
        return _deny(code="MISSING_QUALITY_GATE", detail="quality_gate_reference is required")
    if not str(artifact_integrity_reference or "").strip():
        return _deny(code="MISSING_INTEGRITY_EVIDENCE", detail="artifact_integrity_reference is required")

    repo = Path(repo_root)

    # --- Load canonical Stage 8D lineage (read-only) ------------------------
    revised = _load_revised_delivery(repo_root=repo, revised_delivery_id=revised_delivery_id)
    if revised is None:
        return _deny(code="REVISED_DELIVERY_NOT_FOUND", detail="referenced revised delivery does not exist")
    supersession = _load_supersession(repo_root=repo, revised_delivery_id=revised_delivery_id)
    if supersession is None:
        return _deny(code="SUPERSESSION_LINEAGE_MISSING", detail="no supersession evidence for the revised delivery")
    if not _reconciliation_succeeded(repo_root=repo, result_id=reconciliation_result_id):
        return _deny(code="RECONCILIATION_NOT_SUCCESSFUL", detail="referenced reconciliation result is missing or not successful")
    if not _revision_closed_by_8d(repo_root=repo, revision_id=revised.revision_id):
        return _deny(code="REVISION_NOT_CLOSED", detail="Stage 8D revision closure is missing")

    dispatch_lookup = inspect_rerender_dispatch(dispatch_id=revised.dispatch_id, repo_root=repo)
    if not dispatch_lookup.ok or dispatch_lookup.dispatch is None:
        return _deny(code="DISPATCH_NOT_FOUND", detail="referenced Stage 8C dispatch does not exist")
    dispatch = dispatch_lookup.dispatch.to_dict()
    reconciled_formats = tuple(sorted(dispatch.get("target_formats", ())))

    # --- Acceptance gate ---------------------------------------------------
    effective_status = acceptance_status
    if effective_status not in (
        ACCEPTANCE_ACCEPTED,
        ACCEPTANCE_PARTIALLY_ACCEPTED,
        ACCEPTANCE_REJECTED,
    ):
        return _deny(code="INVALID_ACCEPTANCE_STATUS", detail="acceptance_status must be ACCEPTED, PARTIALLY_ACCEPTED, or REJECTED")

    accepted_set = set(f.lower() for f in accepted_formats)
    rejected_set = set(f.lower() for f in rejected_formats)
    reconciled_set = set(reconciled_formats)

    # Accepted formats must not exceed reconciled output formats.
    if not accepted_set.issubset(reconciled_set):
        return _deny(
            code="UNSUPPORTED_ACCEPTED_FORMAT",
            detail="accepted formats exceed reconciled output formats",
        )
    if not rejected_set.issubset(reconciled_set):
        return _deny(
            code="UNSUPPORTED_REJECTED_FORMAT",
            detail="rejected formats exceed reconciled output formats",
        )
    if effective_status == ACCEPTANCE_ACCEPTED and accepted_set != reconciled_set:
        return _deny(
            code="INCOMPLETE_ACCEPTANCE",
            detail="full acceptance requires all reconciled formats to be accepted",
        )
    if effective_status == ACCEPTANCE_PARTIALLY_ACCEPTED and not accepted_set:
        return _deny(code="EMPTY_PARTIAL_ACCEPTANCE", detail="partial acceptance requires at least one accepted format")
    if effective_status == ACCEPTANCE_REJECTED and not rejection_codes:
        return _deny(code="MISSING_REJECTION_CODE", detail="rejection requires rejection codes")

    # Lineage integrity.
    if revised.supersession_status != "SUPERSEDED":
        return _deny(code="REVISED_DELIVERY_NOT_ACTIVE_SUCCESSOR", detail="revised delivery is not the active successor")
    if supersession.superseding_delivery_record_id != revised.new_delivery_record_id:
        return _deny(code="SUPERSESSION_DELIVERY_MISMATCH", detail="supersession does not reference the revised delivery")
    if supersession.superseding_version_sequence <= supersession.superseded_version_sequence:
        return _deny(code="SUPERSESSION_CYCLE", detail="supersession version ordering is invalid")

    # Revision state.
    state = revision_state(repo, revised.revision_id)
    revision = state["revision"] if state else None
    if revision is None:
        return _deny(code="REVISION_NOT_FOUND", detail="referenced revision record does not exist")
    if revision.get("revision_request_id") != revised.revision_id:
        return _deny(code="REVISION_MISMATCH", detail="revision id mismatch")
    if revision.get("status") == CANCELLED:
        return _deny(code="REVISION_CANCELLED", detail="revision has been cancelled")
    if revision.get("status") == REJECTED:
        return _deny(code="REVISION_REJECTED", detail="revision has been rejected")
    if revision.get("status") == DISPATCH_REVISION_SUPERSEDED:
        return _deny(code="REVISION_SUPERSEDED", detail="revision has been superseded")
    if revision.get("status") not in _RELEASE_ELIGIBLE_REVISION_STATUSES:
        return _deny(code="REVISION_NOT_RELEASE_ELIGIBLE", detail="revision is not in a release-eligible state")

    # Project / correlation / delivery identity consistency.
    if revised.original_delivery_id != supersession.superseded_delivery_record_id:
        return _deny(code="ORIGINAL_DELIVERY_MISMATCH", detail="original delivery identity mismatch")
    project_id = revision.get("project_id")
    correlation_id = dispatch.get("correlation_id")
    if not project_id or not correlation_id:
        return _deny(code="MISSING_LINEAGE_IDENTIFIER", detail="project or correlation identifier missing")

    # --- Idempotency + conflict --------------------------------------------
    acceptance_id = build_acceptance_id(
        reconciliation_result_id=reconciliation_result_id,
        revised_delivery_id=revised_delivery_id,
        revision_id=revised.revision_id,
        dispatch_id=revised.dispatch_id,
        original_delivery_id=revised.original_delivery_id,
        accepted_formats=tuple(sorted(accepted_formats)),
        rejected_formats=tuple(sorted(rejected_formats)),
        reviewer_id=reviewer_id,
        quality_gate_reference=quality_gate_reference,
        artifact_integrity_reference=artifact_integrity_reference,
        acceptance_status=effective_status,
    )
    existing = _acceptances_by_revision(repo_root=repo)
    prior = existing.get(revised.revision_id)
    if prior is not None:
        if prior.acceptance_id == acceptance_id:
            # Identical replay -> return existing, no duplicate event.
            return ReleaseServiceResult(
                True,
                acceptance=prior,
                duplicate_of=prior.acceptance_id,
                existing_id=prior.acceptance_id,
            )
        if prior.acceptance_status in (ACCEPTANCE_CANCELLED, ACCEPTANCE_SUPERSEDED):
            return _deny(code="PRIOR_ACCEPTANCE_TERMINAL", detail="prior acceptance is terminal and cannot be overwritten")
        # Conflicting acceptance under the same revision.
        _append(
            repo_root=repo,
            event_type=EVT_CONFLICTING_REQUEST_REJECTED,
            subject_id=acceptance_id,
            operator_id=operator_id,
            recorded_at=recorded_at,
            record={"conflict_with": prior.acceptance_id, "revision_id": revised.revision_id},
        )
        return _deny(code="ACCEPTANCE_CONFLICT", detail="a different acceptance already exists for this revision")

    try:
        acceptance = RevisedDeliveryAcceptance(
            schema_version=RELEASE_SCHEMA_VERSION,
            acceptance_id=acceptance_id,
            revision_id=revised.revision_id,
            dispatch_id=revised.dispatch_id,
            reconciliation_result_id=reconciliation_result_id,
            original_delivery_id=revised.original_delivery_id,
            revised_delivery_id=revised_delivery_id,
            project_id=project_id,
            correlation_id=correlation_id,
            reviewer_id=reviewer_id,
            review_started_at=recorded_at,
            reviewed_at=recorded_at,
            acceptance_status=effective_status,
            accepted_formats=tuple(sorted(accepted_formats)),
            rejected_formats=tuple(sorted(rejected_formats)),
            quality_gate_reference=quality_gate_reference,
            artifact_integrity_reference=artifact_integrity_reference,
            review_notes=review_notes,
            rejection_codes=tuple(rejection_codes),
            evidence_references=tuple(evidence_references),
            metadata=dict(metadata or {}),
            created_at=recorded_at,
        )
    except ValueError as exc:
        return _deny(code="ACCEPTANCE_VALIDATION", detail=str(exc))
    event_type = (
        EVT_REVISED_DELIVERY_ACCEPTED if effective_status == ACCEPTANCE_ACCEPTED
        else EVT_REVISED_DELIVERY_PARTIALLY_ACCEPTED if effective_status == ACCEPTANCE_PARTIALLY_ACCEPTED
        else EVT_REVISED_DELIVERY_REJECTED
    )
    append_release_event(
        audit_log_path=release_audit_path(repo),
        event=make_release_event(
            event_type=event_type,
            subject_id=acceptance_id,
            operator_id=operator_id,
            recorded_at=recorded_at,
            record=acceptance.to_dict(),
        ),
    )
    return ReleaseServiceResult(True, acceptance=acceptance)


# ---------------------------------------------------------------------------
# 2. Customer release authorization (evidence only; no customer contact)
# ---------------------------------------------------------------------------
def create_customer_release_authorization(
    *,
    acceptance_id: str,
    authorized_by: str,
    authorization_scope: tuple[str, ...],
    approved_formats: tuple[str, ...],
    allowed_delivery_channels: tuple[str, ...],
    customer_reference: str,
    approval_basis: str,
    policy_version: str,
    expiry_at: str,
    evidence_references: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
    operator_id: str,
    repo_root,
    recorded_at: str,
) -> ReleaseServiceResult:
    if not str(operator_id or "").strip() or not str(authorized_by or "").strip():
        return _deny(code="MISSING_REQUIRED_INPUT", detail="operator_id and authorized_by are required")
    if not str(customer_reference or "").strip():
        return _deny(code="MISSING_CUSTOMER_REFERENCE", detail="customer_reference is required")
    if not str(approval_basis or "").strip():
        return _deny(code="MISSING_APPROVAL_BASIS", detail="approval_basis is required")
    if not str(policy_version or "").strip():
        return _deny(code="MISSING_POLICY_VERSION", detail="policy_version is required")
    if not str(expiry_at or "").strip():
        return _deny(code="MISSING_EXPIRY", detail="expiry_at is required")

    repo = Path(repo_root)

    # --- Load the acceptance ----------------------------------------------
    acceptance = _load_acceptance_by_id(repo_root=repo, acceptance_id=acceptance_id)
    if acceptance is None:
        return _deny(code="ACCEPTANCE_NOT_FOUND", detail="referenced acceptance does not exist")
    if acceptance.acceptance_status != ACCEPTANCE_ACCEPTED:
        return _deny(
            code="ACCEPTANCE_NOT_FULLY_ACCEPTED",
            detail="authorization requires a fully ACCEPTED delivery",
        )
    accepted_set = set(acceptance.accepted_formats)
    scope_set = set(f.lower() for f in authorization_scope)
    approved_set = set(f.lower() for f in approved_formats)
    if not scope_set.issubset(accepted_set):
        return _deny(code="SCOPE_EXCEEDS_ACCEPTED", detail="authorization scope exceeds accepted formats")
    if not approved_set.issubset(accepted_set):
        return _deny(code="APPROVED_FORMATS_EXCEED_ACCEPTED", detail="approved formats exceed accepted formats")

    # Idempotency + conflict.
    idem = build_authorization_idempotency_key(
        acceptance_id=acceptance_id,
        authorization_scope=tuple(sorted(authorization_scope)),
        approved_formats=tuple(sorted(approved_formats)),
        allowed_delivery_channels=tuple(sorted(allowed_delivery_channels)),
        customer_reference=customer_reference,
        authorized_by=authorized_by,
        approval_basis=approval_basis,
        policy_version=policy_version,
    )
    authorization_id = build_authorization_id(
        acceptance_id=acceptance_id,
        authorization_scope=tuple(sorted(authorization_scope)),
        approved_formats=tuple(sorted(approved_formats)),
        allowed_delivery_channels=tuple(sorted(allowed_delivery_channels)),
        customer_reference=customer_reference,
        authorized_by=authorized_by,
        approval_basis=approval_basis,
        policy_version=policy_version,
    )
    existing_auth = _authorizations_by_id(repo_root=repo)
    if authorization_id in existing_auth:
        prior = existing_auth[authorization_id]
        status = _effective_authorization_status(authorization=prior, repo_root=repo)
        if status == AUTH_AUTHORIZED:
            return ReleaseServiceResult(True, authorization=prior, duplicate_of=authorization_id, existing_id=authorization_id)
        # A prior authorization that was revoked/expired/cancelled under the
        # same semantic identity must not be silently resurrected.
        return _deny(
            code="AUTHORIZATION_PRIOR_TERMINAL",
            detail=f"prior authorization is in terminal state {status}",
        )
    if _conflicting_authorization_exists(repo_root=repo, acceptance=acceptance, authorization_id=None):
        _append(
            repo_root=repo,
            event_type=EVT_CONFLICTING_REQUEST_REJECTED,
            subject_id=authorization_id,
            operator_id=operator_id,
            recorded_at=recorded_at,
            record={"acceptance_id": acceptance_id},
        )
        return _deny(code="CONFLICTING_AUTHORIZATION", detail="an active authorization already exists for this acceptance")

    try:
        authorization = CustomerReleaseAuthorization(
            schema_version=RELEASE_SCHEMA_VERSION,
            authorization_id=authorization_id,
            acceptance_id=acceptance_id,
            revision_id=acceptance.revision_id,
            revised_delivery_id=acceptance.revised_delivery_id,
            project_id=acceptance.project_id,
            correlation_id=acceptance.correlation_id,
            authorized_by=authorized_by,
            authorized_at=recorded_at,
            authorization_scope=tuple(sorted(authorization_scope)),
            approved_formats=tuple(sorted(approved_formats)),
            allowed_delivery_channels=tuple(sorted(allowed_delivery_channels)),
            customer_reference=customer_reference,
            expiry_at=expiry_at,
            approval_basis=approval_basis,
            policy_version=policy_version,
            status=AUTH_AUTHORIZED,
            idempotency_key=idem,
            evidence_references=tuple(evidence_references),
            metadata=dict(metadata or {}),
            created_at=recorded_at,
        )
    except ValueError as exc:
        return _deny(code="AUTHORIZATION_VALIDATION", detail=str(exc))
    append_release_event(
        audit_log_path=release_audit_path(repo),
        event=make_release_event(
            event_type=EVT_RELEASE_AUTHORIZED,
            subject_id=authorization_id,
            operator_id=operator_id,
            recorded_at=recorded_at,
            record=authorization.to_dict(),
        ),
    )
    return ReleaseServiceResult(True, authorization=authorization)


def revoke_customer_release_authorization(
    *,
    authorization_id: str,
    reason: str | None,
    operator_id: str,
    repo_root,
    recorded_at: str,
) -> ReleaseServiceResult:
    """Explicit revocation (append-only). The immutable authorization record is
    preserved; a terminal REVOKED event makes it inactive for readiness."""
    if not str(operator_id or "").strip():
        return _deny(code="MISSING_REQUIRED_INPUT", detail="operator_id is required")
    repo = Path(repo_root)
    auth = _authorizations_by_id(repo_root=repo).get(authorization_id)
    if auth is None:
        return _deny(code="AUTHORIZATION_NOT_FOUND", detail="authorization does not exist")
    status = _effective_authorization_status(authorization=auth, repo_root=repo)
    if status != AUTH_AUTHORIZED:
        return _deny(code="AUTHORIZATION_NOT_ACTIVE", detail=f"authorization is already in state {status}")
    append_release_event(
        audit_log_path=release_audit_path(repo),
        event=make_release_event(
            event_type=EVT_RELEASE_AUTHORIZATION_REVOKED,
            subject_id=authorization_id,
            operator_id=operator_id,
            recorded_at=recorded_at,
            record={"reason": reason or "operator revocation", "authorization_id": authorization_id},
        ),
    )
    return ReleaseServiceResult(True, authorization=auth)


# ---------------------------------------------------------------------------
# 3. Release-readiness evaluation (deterministic, fail-closed)
# ---------------------------------------------------------------------------
def evaluate_release_readiness(
    *,
    acceptance_id: str,
    authorization_id: str | None,
    repo_root,
    recorded_at: str,
) -> ReleaseReadinessDecision:
    repo = Path(repo_root)
    reasons: list[str] = []
    acceptance = _load_acceptance_by_id(repo_root=repo, acceptance_id=acceptance_id)
    revision_id = acceptance.revision_id if acceptance else None
    dispatch_id = acceptance.dispatch_id if acceptance else None
    recon_id = acceptance.reconciliation_result_id if acceptance else None
    revised_id = acceptance.revised_delivery_id if acceptance else None
    original_id = acceptance.original_delivery_id if acceptance else None
    project_id = acceptance.project_id if acceptance else None
    correlation_id = acceptance.correlation_id if acceptance else None

    if acceptance is None:
        reasons.append("ACCEPTANCE_NOT_FOUND")
    elif acceptance.acceptance_status != ACCEPTANCE_ACCEPTED:
        reasons.append("ACCEPTANCE_NOT_FULLY_ACCEPTED")
    if acceptance is not None and not acceptance.artifact_integrity_reference:
        reasons.append("MISSING_INTEGRITY_EVIDENCE")

    authorization = None
    if authorization_id:
        authorization = _authorizations_by_id(repo_root=repo).get(authorization_id)
        if authorization is None:
            reasons.append("AUTHORIZATION_NOT_FOUND")
    else:
        # No authorization supplied: not ready unless exactly one active exists.
        active = [
            a for a in _authorizations_by_id(repo_root=repo).values()
            if _effective_authorization_status(authorization=a, repo_root=repo) == AUTH_AUTHORIZED
            and a.acceptance_id == acceptance_id
        ]
        if acceptance is None or not active:
            reasons.append("AUTHORIZATION_MISSING")
        elif len(active) > 1:
            reasons.append("CONFLICTING_AUTHORIZATION")
        else:
            authorization = active[0]

    auth_status = None
    if authorization is not None:
        auth_status = _effective_authorization_status(authorization=authorization, repo_root=repo)
        if auth_status != AUTH_AUTHORIZED:
            reasons.append(f"AUTHORIZATION_{auth_status}")
        elif authorization.acceptance_id != (acceptance.acceptance_id if acceptance else None):
            reasons.append("AUTHORIZATION_ACCEPTANCE_MISMATCH")
        elif authorization.revision_id != (acceptance.revision_id if acceptance else None):
            reasons.append("AUTHORIZATION_REVISION_MISMATCH")
        elif authorization.revised_delivery_id != (acceptance.revised_delivery_id if acceptance else None):
            reasons.append("AUTHORIZATION_DELIVERY_MISMATCH")
        elif authorization.project_id != (acceptance.project_id if acceptance else None):
            reasons.append("AUTHORIZATION_PROJECT_MISMATCH")
        elif authorization.correlation_id != (acceptance.correlation_id if acceptance else None):
            reasons.append("AUTHORIZATION_CORRELATION_MISMATCH")
        else:
            accepted_set = set(authorization.approved_formats)
            if not set(authorization.authorization_scope).issubset(accepted_set):
                reasons.append("AUTHORIZATION_SCOPE_MISMATCH")

    # Lineage completeness (only if acceptance exists).
    if acceptance is not None:
        revised = _load_revised_delivery(repo_root=repo, revised_delivery_id=acceptance.revised_delivery_id)
        if revised is None:
            reasons.append("REVISED_DELIVERY_NOT_FOUND")
        else:
            if not _reconciliation_succeeded(repo_root=repo, result_id=acceptance.reconciliation_result_id):
                reasons.append("RECONCILIATION_NOT_SUCCESSFUL")
            supersession = _load_supersession(repo_root=repo, revised_delivery_id=acceptance.revised_delivery_id)
            if supersession is None:
                reasons.append("SUPERSESSION_LINEAGE_MISSING")
            elif supersession.superseding_version_sequence <= supersession.superseded_version_sequence:
                reasons.append("SUPERSESSION_CYCLE")
            if revised.supersession_status != "SUPERSEDED":
                reasons.append("REVISED_DELIVERY_NOT_ACTIVE_SUCCESSOR")
            # Original delivery must remain registered/preserved.
            orig = inspect_delivery_lineage(delivery_record_id=acceptance.original_delivery_id, repo_root=repo)
            if not orig.ok or orig.lineage is None:
                reasons.append("ORIGINAL_DELIVERY_NOT_PRESERVED")
            # Revision release-eligible.
            state = revision_state(repo, acceptance.revision_id)
            revision = state["revision"] if state else None
            if revision is None:
                reasons.append("REVISION_NOT_FOUND")
            elif revision.get("status") not in _RELEASE_ELIGIBLE_REVISION_STATUSES:
                reasons.append("REVISION_NOT_RELEASE_ELIGIBLE")
            if not _revision_closed_by_8d(repo_root=repo, revision_id=acceptance.revision_id):
                reasons.append("REVISION_NOT_CLOSED")

    release_ready = len(reasons) == 0
    return ReleaseReadinessDecision(
        schema_version=RELEASE_SCHEMA_VERSION,
        decision_id=build_readiness_id(acceptance_id=acceptance_id, authorization_id=authorization_id),
        release_ready=release_ready,
        revision_id=revision_id,
        dispatch_id=dispatch_id,
        reconciliation_result_id=recon_id,
        acceptance_id=acceptance_id if acceptance else None,
        authorization_id=authorization.authorization_id if authorization else None,
        revised_delivery_id=revised_id,
        original_delivery_id=original_id,
        project_id=project_id,
        correlation_id=correlation_id,
        reasons=tuple(reasons),
        evaluated_at=recorded_at,
        metadata={},
    )


# ---------------------------------------------------------------------------
# 4. Final revision closure
# ---------------------------------------------------------------------------
def close_final_revision(
    *,
    acceptance_id: str,
    authorization_id: str | None,
    operator_id: str,
    repo_root,
    recorded_at: str,
) -> ReleaseServiceResult:
    if not str(operator_id or "").strip():
        return _deny(code="MISSING_REQUIRED_INPUT", detail="operator_id is required")
    repo = Path(repo_root)

    readiness = evaluate_release_readiness(
        acceptance_id=acceptance_id,
        authorization_id=authorization_id,
        repo_root=repo,
        recorded_at=recorded_at,
    )
    if not readiness.release_ready:
        # Record a rejected readiness event for auditability, then deny.
        append_release_event(
            audit_log_path=release_audit_path(repo),
            event=make_release_event(
                event_type=EVT_RELEASE_READINESS_REJECTED,
                subject_id=acceptance_id,
                operator_id=operator_id,
                recorded_at=recorded_at,
                record={"reasons": list(readiness.reasons)},
            ),
        )
        return _deny(code="RELEASE_NOT_READY", detail="; ".join(readiness.reasons))

    acceptance = _load_acceptance_by_id(repo_root=repo, acceptance_id=acceptance_id)
    authorization = _authorizations_by_id(repo_root=repo).get(readiness.authorization_id)
    assert acceptance is not None and authorization is not None

    closure_id = build_closure_id(
        revision_id=acceptance.revision_id,
        acceptance_id=acceptance.acceptance_id,
        authorization_id=authorization.authorization_id,
        reconciliation_result_id=acceptance.reconciliation_result_id,
    )
    # Idempotency: identical closure content returns existing.
    for event in read_release_events(audit_log_path=release_audit_path(repo)):
        if event.event_type == EVT_REVISION_FINALLY_CLOSED and event.subject_id == closure_id:
            return ReleaseServiceResult(
                True,
                closure=FinalRevisionClosure(**event.record),
                duplicate_of=closure_id,
                existing_id=closure_id,
            )
    # Conflict: a different terminal closure for the same revision.
    for event in read_release_events(audit_log_path=release_audit_path(repo)):
        if event.event_type == EVT_REVISION_FINALLY_CLOSED:
            rec = event.record
            if rec.get("revision_id") == acceptance.revision_id and rec.get("closure_id") != closure_id:
                _append(
                    repo_root=repo,
                    event_type=EVT_CONFLICTING_REQUEST_REJECTED,
                    subject_id=closure_id,
                    operator_id=operator_id,
                    recorded_at=recorded_at,
                    record={"conflict_with": rec.get("closure_id")},
                )
                return _deny(code="CLOSURE_CONFLICT", detail="a conflicting final closure already exists for this revision")

    closure = FinalRevisionClosure(
        schema_version=RELEASE_SCHEMA_VERSION,
        closure_id=closure_id,
        revision_id=acceptance.revision_id,
        approval_id=None,
        dispatch_id=acceptance.dispatch_id,
        reconciliation_result_id=acceptance.reconciliation_result_id,
        original_delivery_id=acceptance.original_delivery_id,
        revised_delivery_id=acceptance.revised_delivery_id,
        acceptance_id=acceptance.acceptance_id,
        authorization_id=authorization.authorization_id,
        release_ready=True,
        correlation_id=acceptance.correlation_id,
        evidence_references=(
            acceptance.artifact_integrity_reference,
            authorization.authorization_id,
        ),
        closed_at=recorded_at,
        created_at=recorded_at,
    )
    append_release_event(
        audit_log_path=release_audit_path(repo),
        event=make_release_event(
            event_type=EVT_REVISION_FINALLY_CLOSED,
            subject_id=closure_id,
            operator_id=operator_id,
            recorded_at=recorded_at,
            record=closure.to_dict(),
        ),
    )
    return ReleaseServiceResult(True, closure=closure)


# ---------------------------------------------------------------------------
# Inspect helpers
# ---------------------------------------------------------------------------
def inspect_acceptance(*, acceptance_id: str, repo_root) -> ReleaseServiceResult:
    acc = _load_acceptance_by_id(repo_root=Path(repo_root), acceptance_id=acceptance_id)
    if acc is None:
        return _deny(code="ACCEPTANCE_NOT_FOUND", detail="acceptance not found")
    return ReleaseServiceResult(True, acceptance=acc)


def inspect_authorization(*, authorization_id: str, repo_root) -> ReleaseServiceResult:
    auth = _authorizations_by_id(repo_root=Path(repo_root)).get(authorization_id)
    if auth is None:
        return _deny(code="AUTHORIZATION_NOT_FOUND", detail="authorization not found")
    return ReleaseServiceResult(True, authorization=auth)


def inspect_final_closure(*, revision_id: str, repo_root) -> ReleaseServiceResult:
    for event in read_release_events(audit_log_path=release_audit_path(Path(repo_root))):
        if event.event_type == EVT_REVISION_FINALLY_CLOSED and event.record.get("revision_id") == revision_id:
            return ReleaseServiceResult(True, closure=FinalRevisionClosure(**event.record))
    return _deny(code="CLOSURE_NOT_FOUND", detail="final closure not found")


def inspect_release_lineage(*, project_id: str | None, repo_root) -> dict[str, Any]:
    """Return the complete revised-delivery release lineage for a project or
    revision (read-only)."""
    events = read_release_events(audit_log_path=release_audit_path(Path(repo_root)))
    acceptances: list[dict[str, Any]] = []
    authorizations: list[dict[str, Any]] = []
    closures: list[dict[str, Any]] = []
    for e in events:
        rec = e.record
        if e.event_type in (
            EVT_REVISED_DELIVERY_ACCEPTED,
            EVT_REVISED_DELIVERY_PARTIALLY_ACCEPTED,
            EVT_REVISED_DELIVERY_REJECTED,
        ):
            acc = RevisedDeliveryAcceptance(**rec)
            if project_id is None or acc.project_id == project_id:
                acceptances.append(acc.to_dict())
        elif e.event_type == EVT_RELEASE_AUTHORIZED:
            auth = CustomerReleaseAuthorization(**rec)
            if project_id is None or auth.project_id == project_id:
                authorizations.append(auth.to_dict())
        elif e.event_type == EVT_REVISION_FINALLY_CLOSED:
            if project_id is None or rec.get("project_id") == project_id:
                closures.append(rec)
    return {
        "ok": True,
        "count": len(acceptances) + len(authorizations) + len(closures),
        "acceptances": acceptances,
        "authorizations": authorizations,
        "closures": closures,
    }


# ---------------------------------------------------------------------------
# Internal append helper
# ---------------------------------------------------------------------------
def _append(*, repo_root: Path, event_type: str, subject_id: str, operator_id: str, recorded_at: str, record: dict[str, Any]) -> None:
    append_release_event(
        audit_log_path=release_audit_path(repo_root),
        event=make_release_event(
            event_type=event_type,
            subject_id=subject_id,
            operator_id=operator_id,
            recorded_at=recorded_at,
            record=record,
        ),
    )
