"""Stage 8C approval-gated re-render dispatch service; no HVS execution.

Converts an APPROVED Stage 8B revision into a deterministic, immutable
re-render dispatch request while preserving complete lineage and failing
closed on any missing, malformed, stale, mismatched, or ambiguous data.

The service:
  1. loads the Stage 8B revision state (via the existing revision service)
  2. validates the full approval gate (revision, approval, authorization,
     lineage consistency, format validity, not-cancelled, not-superseded)
  3. computes a deterministic idempotency identity from stable semantic inputs
  4. returns an existing dispatch on replay (no duplicate dispatch created)
  5. rejects conflicting duplicates under the same identity
  6. appends append-only audit evidence for every lifecycle transition
  7. delegates ONLY to the existing canonical manual-dispatch boundary flag
     (``RerenderAuthorizationPacket.manual_dispatch_required``); it does NOT
     construct a second HVS execution path, does NOT call the HVS CLI, and does
     NOT modify HVS source.

Domain logic is kept separate from CLI formatting and filesystem plumbing.
Pure functions (``evaluate_rerender_dispatch_gate``,
``compute_dispatch_request``) are importable and unit-testable without I/O.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hvs_rerender_dispatch_models import (
    ALLOWED_TARGET_FORMATS,
    RERENDER_DISPATCH_SCHEMA_VERSION,
    REVISION_APPROVED,
    REVISION_CANCELLED,
    REVISION_SUPERSEDED,
    RequestedChange,
    RerenderDispatchRequest,
    build_idempotency_key,
    change_fingerprint,
    dispatch_id_for,
)
from .hvs_rerender_dispatch_store import (
    append_rerender_dispatch_event,
    make_dispatch_event,
    rerender_dispatch_audit_path,
    read_rerender_dispatch_events,
)
from .hvs_revision_models import (
    APPROVED_FOR_RERENDER_PLANNING,
    CANCELLED,
    RERENDER_AUTHORIZATION_READY,
)


# ---------------------------------------------------------------------------
# Result contract
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RerenderDispatchResult:
    ok: bool
    dispatch: RerenderDispatchRequest | None = None
    duplicate_of: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    evidence_event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": RERENDER_DISPATCH_SCHEMA_VERSION,
            "dispatch": self.dispatch.to_dict() if self.dispatch else None,
            "duplicate_of": self.duplicate_of,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "evidence_event_id": self.evidence_event_id,
            "hvs_invoked": False,
            "manual_dispatch_required": True,
            "automation_allowed": False,
        }


def _deny(code: str, detail: str) -> RerenderDispatchResult:
    return RerenderDispatchResult(False, error_code=code, error_detail=detail)


# ---------------------------------------------------------------------------
# Pure approval-gate evaluation (no I/O)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _RevisionBundle:
    revision: dict[str, Any]
    authorization: dict[str, Any] | None
    decision: str | None
    decision_id: str | None


def evaluate_rerender_dispatch_gate(
    *,
    revision_id: str,
    revision: dict[str, Any],
    authorization: dict[str, Any] | None,
    decision: str | None,
    decision_id: str | None,
    delivery_id: str,
    approval_id: str,
    approval_decision_id: str,
    approved_by: str,
    target_formats: tuple[str, ...],
) -> tuple[bool, str | None, str | None]:
    """Return (granted, error_code, error_detail). Fails closed on any problem.

    Every required condition from the Stage 8C scope is checked explicitly:
      * revision record exists (caller guarantees by passing non-None revision)
      * revision is in an approvable state (APPROVED_FOR_RERENDER_PLANNING)
      * approval record exists (authorization present)
      * approval explicitly permits re-render (authorization ready)
      * approval refers to the same revision (authorization.revision_request_id)
      * approval refers to the same delivery (revision.delivery_record_id)
      * required lineage identifiers are consistent
      * revision has not been cancelled or superseded
      * requested target formats are valid
      * duplicate identity detection is handled by the caller
    """
    if not revision:
        return False, "REVISION_NOT_FOUND", "revision record does not exist"

    status = revision.get("status")
    if status == CANCELLED:
        return False, "REVISION_CANCELLED", "revision has been cancelled"
    if status == REVISION_SUPERSEDED:
        return False, "REVISION_SUPERSEDED", "revision has been superseded"
    # Dispatchable states: the revision must have been approved AND carry a
    # ready re-render authorization. In the Stage 8B flow the terminal approved
    # state is RERENDER_AUTHORIZATION_READY (set by create_rerender_authorization
    # after APPROVE_RERENDER_PLAN). APPROVED_FOR_RERENDER_PLANNING is accepted as
    # a defensive edge case (approved but authorization not yet persisted).
    if status not in (APPROVED_FOR_RERENDER_PLANNING, RERENDER_AUTHORIZATION_READY):
        return (
            False,
            "REVISION_NOT_APPROVED",
            f"revision status is {status!r}, expected one of "
            f"{APPROVED_FOR_RERENDER_PLANNING!r} or {RERENDER_AUTHORIZATION_READY!r}",
        )

    if not authorization:
        return False, "APPROVAL_REQUIRED", "re-render authorization is required"
    # Readiness is signalled by the authorization packet existing with the
    # canonical manual-dispatch permit. The Stage 8B ``RerenderAuthorizationPacket``
    # has no separate status field; presence + ``manual_dispatch_required`` is the
    # readiness contract (it is True only when create_rerender_authorization has
    # run successfully).
    if authorization.get("manual_dispatch_required") is not True:
        return (
            False,
            "APPROVAL_NOT_READY",
            "re-render authorization does not permit manual dispatch",
        )

    # Approval must refer to the SAME revision.
    if authorization.get("revision_request_id") != revision_id:
        return (
            False,
            "APPROVAL_REVISION_MISMATCH",
            "authorization refers to a different revision_request_id",
        )

    # Approval / decision must refer to the SAME delivery as the revision.
    rev_delivery = revision.get("delivery_record_id")
    if rev_delivery != delivery_id:
        return (
            False,
            "APPROVAL_DELIVERY_MISMATCH",
            "supplied delivery_id does not match the revision delivery_record_id",
        )
    if authorization.get("revision_request_id") != revision_id:
        return False, "LINEAGE_INCONSISTENT", "authorization lineage is inconsistent"

    # Decision must explicitly permit re-render.
    if decision != "APPROVE_RERENDER_PLAN":
        return (
            False,
            "APPROVAL_DECISION_NOT_PERMITTED",
            "approval decision does not permit re-render",
        )
    if decision_id != approval_decision_id:
        return (
            False,
            "APPROVAL_DECISION_MISMATCH",
            "supplied approval_decision_id does not match the recorded decision",
        )

    if not str(approved_by or "").strip():
        return False, "MISSING_APPROVED_BY", "approved_by operator id is required"

    # Requested target formats must be valid, non-empty, and de-duplicated.
    if not target_formats:
        return False, "NO_TARGET_FORMATS", "at least one target format is required"
    normalized = []
    for fmt in target_formats:
        if fmt not in ALLOWED_TARGET_FORMATS:
            return (
                False,
                "INVALID_TARGET_FORMAT",
                f"target format {fmt!r} is not an allowed delivery variant",
            )
        if fmt not in normalized:
            normalized.append(fmt)

    return True, None, None


# ---------------------------------------------------------------------------
# Deterministic dispatch-request construction (no I/O)
# ---------------------------------------------------------------------------
def compute_dispatch_request(
    *,
    revision: dict[str, Any],
    authorization: dict[str, Any],
    decision_id: str,
    approved_by: str,
    requested_by: str,
    target_formats: tuple[str, ...],
    requested_changes: tuple[RequestedChange, ...],
    reason: str,
    created_at: str,
) -> RerenderDispatchRequest:
    """Build the immutable dispatch request with a deterministic idempotency key."""
    revision_id = revision["revision_request_id"]
    delivery_id = revision["delivery_record_id"]
    fp = change_fingerprint(requested_changes)
    idem = build_idempotency_key(
        revision_id=revision_id,
        delivery_id=delivery_id,
        approval_decision_id=decision_id,
        target_formats=tuple(sorted(target_formats)),
        change_fingerprint=fp,
    )
    dispatch_id = dispatch_id_for(idem)
    return RerenderDispatchRequest(
        schema_version=RERENDER_DISPATCH_SCHEMA_VERSION,
        dispatch_id=dispatch_id,
        revision_id=revision_id,
        delivery_id=delivery_id,
        original_render_request_id=revision.get("lineage_id"),
        original_correlation_id=revision.get("source_lineage_id"),
        project_id=revision.get("project_id") or "unknown",
        requested_by=requested_by,
        approved_by=approved_by,
        approval_id=authorization.get("rerender_authorization_id"),
        approval_decision_id=decision_id,
        approval_timestamp=created_at,
        requested_changes=requested_changes,
        target_formats=tuple(sorted(target_formats)),
        reason=reason,
        created_at=created_at,
        correlation_id=revision.get("source_lineage_id") or revision_id,
        idempotency_key=idem,
        status="RERENDER_DISPATCH_CREATED",
        metadata={
            "lineage_id": revision.get("source_lineage_id"),
            "delivery_closure_id": revision.get("delivery_closure_id"),
            "artifact_sha256": revision.get("source_artifact_sha256"),
            "planned_successor_version_display": revision.get(
                "planned_successor_version_display"
            ),
            "rerender_authorization_id": authorization.get("rerender_authorization_id"),
            "manual_dispatch_required": bool(authorization.get("manual_dispatch_required", True)),
            "automation_allowed": False,
            "authoritative_dispatch_boundary": "manual_hvs_operator_handoff",
            "hvs_invoked": False,
        },
    )


# ---------------------------------------------------------------------------
# State-machine transition validation (no I/O)
# ---------------------------------------------------------------------------
_VALID_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "RERENDER_DISPATCH_REQUESTED": ("RERENDER_DISPATCH_REJECTED", "RERENDER_DISPATCH_CREATED"),
    "RERENDER_DISPATCH_REJECTED": (),
    "RERENDER_DISPATCH_CREATED": ("RERENDER_DISPATCH_DUPLICATE", "RERENDER_DISPATCH_FAILED", "RERENDER_DISPATCH_COMPLETED"),
    "RERENDER_DISPATCH_DUPLICATE": (),
    "RERENDER_DISPATCH_FAILED": ("RERENDER_DISPATCH_COMPLETED",),
    "RERENDER_DISPATCH_COMPLETED": (),
}


def is_valid_dispatch_transition(*, current: str, target: str) -> bool:
    if current not in _VALID_TRANSITIONS:
        return False
    if current == target:
        return False  # no self-transition
    return target in _VALID_TRANSITIONS[current]


def assert_dispatch_transition(*, current: str, target: str) -> None:
    if not is_valid_dispatch_transition(current=current, target=target):
        raise ValueError(
            f"invalid re-render dispatch transition: {current!r} -> {target!r}"
        )


# ---------------------------------------------------------------------------
# Service entry point (I/O: reads revision ledger, writes dispatch ledger)
# ---------------------------------------------------------------------------
def request_rerender_dispatch(
    *,
    revision_request_id: str,
    operator_id: str,
    target_formats: tuple[str, ...],
    requested_changes: tuple[RequestedChange, ...],
    reason: str,
    repo_root,
    recorded_at: str,
    requested_by: str | None = None,
    delivery_id: str | None = None,
    approval_id: str | None = None,
    approval_decision_id: str | None = None,
    approved_by: str | None = None,
) -> RerenderDispatchResult:
    """Convert an APPROVED Stage 8B revision into an immutable dispatch request.

    Loads the revision state via the existing Stage 8B service, validates the
    approval gate, computes the deterministic idempotency identity, returns an
    existing dispatch on replay, rejects conflicting duplicates, appends
    append-only audit evidence, and returns a structured result. Never invokes
    HVS and never hides rejection reasons.
    """
    if not revision_request_id or not str(operator_id or "").strip():
        return _deny("MISSING_REQUIRED_INPUT", "revision_request_id and operator_id are required")

    # Local import to avoid coupling at module import time.
    from .hvs_revision_service import _state as revision_state

    repo = Path(repo_root)
    state = revision_state(repo, revision_request_id)
    if state is None:
        return _deny("REVISION_NOT_FOUND", "revision request not found")

    revision = state["revision"]
    authorization = state.get("authorization")
    decision = state.get("decision")
    decision_id = state.get("decision_id")

    resolved_delivery_id = delivery_id or revision.get("delivery_record_id")
    resolved_approval_id = approval_id or (authorization or {}).get("rerender_authorization_id")
    resolved_decision_id = approval_decision_id or decision_id
    resolved_approved_by = approved_by or (authorization or {}).get("operator_id") or operator_id
    resolved_requested_by = requested_by or revision.get("requested_by_id") or "unknown"

    # Normalize + validate requested changes before gate evaluation.
    try:
        normalized_changes = tuple(
            RequestedChange(
                category=c.category,
                description=c.description,
                target_format=c.target_format,
                target_id=c.target_id,
            )
            for c in requested_changes
        )
    except ValueError as exc:
        return _deny("INVALID_REQUESTED_CHANGE", str(exc))

    granted, code, detail = evaluate_rerender_dispatch_gate(
        revision_id=revision_request_id,
        revision=revision,
        authorization=authorization,
        decision=decision,
        decision_id=decision_id,
        delivery_id=resolved_delivery_id,
        approval_id=resolved_approval_id or "",
        approval_decision_id=resolved_decision_id or "",
        approved_by=resolved_approved_by,
        target_formats=tuple(sorted(target_formats)),
    )
    if not granted:
        event = make_dispatch_event(
            event_type="RERENDER_DISPATCH_REJECTED",
            dispatch_id=dispatch_id_for(
                build_idempotency_key(
                    revision_id=revision_request_id,
                    delivery_id=resolved_delivery_id,
                    approval_decision_id=resolved_decision_id or "",
                    target_formats=tuple(sorted(target_formats)),
                    change_fingerprint=change_fingerprint(normalized_changes),
                )
            ),
            operator_id=operator_id,
            recorded_at=recorded_at,
            record={
                "revision_request_id": revision_request_id,
                "delivery_id": resolved_delivery_id,
                "error_code": code,
                "error_detail": detail,
            },
        )
        appended = append_rerender_dispatch_event(
            audit_log_path=rerender_dispatch_audit_path(repo), event=event
        )
        return RerenderDispatchResult(
            False,
            error_code=code,
            error_detail=detail,
            evidence_event_id=appended.event_id,
        )

    # Deterministic idempotency identity.
    idem = build_idempotency_key(
        revision_id=revision_request_id,
        delivery_id=resolved_delivery_id,
        approval_decision_id=resolved_decision_id or "",
        target_formats=tuple(sorted(target_formats)),
        change_fingerprint=change_fingerprint(normalized_changes),
    )
    dispatch_id = dispatch_id_for(idem)

    # Idempotency: replay returns the EXISTING dispatch (no duplicate created).
    existing = _find_existing_dispatch(repo_root=repo, idempotency_key=idem)
    if existing is not None:
        event = make_dispatch_event(
            event_type="RERENDER_DISPATCH_DUPLICATE",
            dispatch_id=dispatch_id,
            operator_id=operator_id,
            recorded_at=recorded_at,
            record={
                "idempotency_key": idem,
                "duplicate_of": existing.dispatch_id,
                "revision_request_id": revision_request_id,
            },
        )
        appended = append_rerender_dispatch_event(
            audit_log_path=rerender_dispatch_audit_path(repo), event=event
        )
        return RerenderDispatchResult(
            True,
            dispatch=existing,
            duplicate_of=existing.dispatch_id,
            evidence_event_id=appended.event_id,
        )

    # Conflicting duplicate detection: same identity but different semantic
    # payload must be rejected (guarded by idempotency key equality; here we
    # additionally reject a dispatch_id collision with non-equal content).
    conflicting = _find_existing_dispatch_by_dispatch_id(repo_root=repo, dispatch_id=dispatch_id)
    if conflicting is not None and conflicting.idempotency_key != idem:
        return RerenderDispatchResult(
            False,
            error_code="CONFLICTING_DISPATCH_IDENTITY",
            error_detail="dispatch id collision with inconsistent idempotency key",
        )

    dispatch = compute_dispatch_request(
        revision=revision,
        authorization=authorization,  # type: ignore[arg-type]
        decision_id=resolved_decision_id or "",
        approved_by=resolved_approved_by,
        requested_by=resolved_requested_by,
        target_formats=tuple(sorted(target_formats)),
        requested_changes=normalized_changes,
        reason=reason,
        created_at=recorded_at,
    )

    event = make_dispatch_event(
        event_type="RERENDER_DISPATCH_CREATED",
        dispatch_id=dispatch.dispatch_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=dispatch.to_dict(),
    )
    appended = append_rerender_dispatch_event(
        audit_log_path=rerender_dispatch_audit_path(repo), event=event
    )
    return RerenderDispatchResult(
        True, dispatch=dispatch, evidence_event_id=appended.event_id
    )


def _all_dispatches(repo_root: Path) -> list[RerenderDispatchRequest]:
    out: list[RerenderDispatchRequest] = []
    for event in read_rerender_dispatch_events(
        audit_log_path=rerender_dispatch_audit_path(repo_root)
    ):
        rec = event.record
        if "dispatch_id" not in rec:
            continue
        try:
            changes = tuple(RequestedChange(**c) for c in rec.get("requested_changes", []))
            out.append(
                RerenderDispatchRequest(
                    schema_version=rec["schema_version"],
                    dispatch_id=rec["dispatch_id"],
                    revision_id=rec["revision_id"],
                    delivery_id=rec["delivery_id"],
                    original_render_request_id=rec.get("original_render_request_id"),
                    original_correlation_id=rec.get("original_correlation_id"),
                    project_id=rec["project_id"],
                    requested_by=rec["requested_by"],
                    approved_by=rec["approved_by"],
                    approval_id=rec["approval_id"],
                    approval_decision_id=rec["approval_decision_id"],
                    approval_timestamp=rec["approval_timestamp"],
                    requested_changes=changes,
                    target_formats=tuple(rec["target_formats"]),
                    reason=rec["reason"],
                    created_at=rec["created_at"],
                    correlation_id=rec["correlation_id"],
                    idempotency_key=rec["idempotency_key"],
                    status=rec["status"],
                    metadata=rec.get("metadata", {}),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _find_existing_dispatch(*, repo_root: Path, idempotency_key: str):
    for d in _all_dispatches(repo_root):
        if d.idempotency_key == idempotency_key:
            return d
    return None


def _find_existing_dispatch_by_dispatch_id(*, repo_root: Path, dispatch_id: str):
    for d in _all_dispatches(repo_root):
        if d.dispatch_id == dispatch_id:
            return d
    return None


def inspect_rerender_dispatch(*, dispatch_id: str, repo_root) -> RerenderDispatchResult:
    repo = Path(repo_root)
    found = _find_existing_dispatch_by_dispatch_id(repo_root=repo, dispatch_id=dispatch_id)
    if found is None:
        return _deny("DISPATCH_NOT_FOUND", "re-render dispatch request not found")
    return RerenderDispatchResult(True, dispatch=found)


def read_dispatch_events(*, repo_root) -> tuple[Any, ...]:
    return read_rerender_dispatch_events(audit_log_path=rerender_dispatch_audit_path(Path(repo_root)))
