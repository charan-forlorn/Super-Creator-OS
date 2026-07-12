"""Stage 8D re-render result reconciliation service; no HVS execution.

Consumes the result of a Stage 8C approved re-render dispatch and
deterministically reconciles it into the SCOS delivery and revision lineage.

The service:
  1. loads the Stage 8C dispatch (via the existing 8C inspect function)
  2. loads the Stage 8B revision state (via the existing 8B ``_state``)
  3. loads the existing original delivery lineage (via Stage 8A.1)
  4. validates result lineage + integrity against the dispatch/revision
  5. performs deterministic idempotency checks (no duplicate state)
  6. creates the revised delivery version via the existing Stage 8A.1 lineage
     registration (exactly one v2 record; no second subsystem)
  7. appends append-only supersession evidence (original is immutable)
  8. closes the revision (append-only, idempotent, conflict-rejected)
  9. updates the Stage 8C dispatch lifecycle (canonical COMPLETED event)
 10. returns a structured reconciliation result with exact rejection reasons

It NEVER invokes HVS, NEVER renders media, NEVER creates a second
delivery-version subsystem, and NEVER mutates prior immutable records silently.
Domain logic is kept separate from CLI formatting and filesystem plumbing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hvs_delivery_lineage_models import (  # noqa: F401
    BASIS_SUCCESSOR_OF_REGISTERED_DELIVERY,
    DeliveryLineageRegistrationRequest,
)
from .hvs_delivery_lineage_service import (
    derive_successor_version,
    inspect_delivery_lineage,
    register_delivery_lineage,
)
from .hvs_rerender_dispatch_models import DISPATCH_COMPLETED as RERENDER_DISPATCH_COMPLETED
from .hvs_rerender_dispatch_service import inspect_rerender_dispatch
from .hvs_rerender_dispatch_store import (
    append_rerender_dispatch_event,
    make_dispatch_event,
    rerender_dispatch_audit_path,
)
from .hvs_rerender_result_models import (
    RERENDER_DISPATCH_RESULT_ACCEPTABLE,
    RERENDER_RESULT_EVENT_SCHEMA_VERSION,
    RERENDER_RESULT_FAILED,
    RERENDER_RESULT_RETRYABLE,
    RERENDER_RESULT_SCHEMA_VERSION,
    RERENDER_RESULT_SUCCEEDED,
    EVT_DELIVERY_SUPERSEDED,
    EVT_RECONCILIATION_CONFLICT,
    EVT_RECONCILIATION_DUPLICATE,
    EVT_REVISED_DELIVERY_CREATED,
    EVT_RERENDER_FAILED,
    EVT_RERENDER_RESULT_ACCEPTED,
    EVT_RERENDER_RESULT_RECEIVED,
    EVT_RERENDER_RESULT_REJECTED,
    EVT_REVISION_COMPLETED,
    RevisedDeliveryRecord,
    RerenderResult,
    SupersessionRecord,
    build_revised_delivery_id,
    build_result_idempotency_key,
    build_supersession_id,
    result_id_for,
)
from .hvs_rerender_result_store import (
    append_reconciliation_event,
    make_reconciliation_event,
    read_reconciliation_events,
    reconciliation_audit_path,
)
from .hvs_revision_models import CANCELLED
from .hvs_rerender_dispatch_models import REVISION_SUPERSEDED
from .hvs_revision_service import _state as revision_state


# ---------------------------------------------------------------------------
# Result contract
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RerenderReconciliationResult:
    ok: bool
    result: RerenderResult | None = None
    duplicate_of: str | None = None
    revised_delivery: RevisedDeliveryRecord | None = None
    supersession: SupersessionRecord | None = None
    revision_closed: bool = False
    dispatch_completed: bool = False
    existing_reconciliation_id: str | None = None
    reconciliation_id: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    evidence_event_id: str | None = None
    hvs_invoked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": RERENDER_RESULT_SCHEMA_VERSION,
            "result": self.result.to_dict() if self.result else None,
            "duplicate_of": self.duplicate_of,
            "revised_delivery": self.revised_delivery.to_dict() if self.revised_delivery else None,
            "supersession": self.supersession.to_dict() if self.supersession else None,
            "revision_closed": self.revision_closed,
            "dispatch_completed": self.dispatch_completed,
            "reconciliation_id": self.reconciliation_id,
            "existing_reconciliation_id": self.existing_reconciliation_id,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "evidence_event_id": self.evidence_event_id,
            "hvs_invoked": self.hvs_invoked,
            "automation_allowed": False,
        }


def _deny(*, code: str, detail: str) -> RerenderReconciliationResult:
    return RerenderReconciliationResult(False, error_code=code, error_detail=detail)


# ---------------------------------------------------------------------------
# Pure acceptance-gate evaluation (no I/O)
# ---------------------------------------------------------------------------
def evaluate_rerender_result_gate(
    *,
    result: RerenderResult,
    dispatch: dict[str, Any],
    revision: dict[str, Any] | None,
    original_lineage: dict[str, Any] | None,
) -> tuple[bool, str | None, str | None]:
    """Return (granted, error_code, error_detail). Fails closed on any problem.

    Validates the full required lineage + integrity contract between the
    externally-produced re-render result and the Stage 8C dispatch / Stage 8B
    revision / original delivery lineage.
    """
    # Dispatch must still be awaiting a result (terminal states rejected).
    dispatch_status = dispatch.get("status")
    if dispatch_status != RERENDER_DISPATCH_RESULT_ACCEPTABLE:
        return (
            False,
            "RESULT_RECEIVED_FOR_INVALID_DISPATCH_STATE",
            f"dispatch is in state {dispatch_status!r}, not result-acceptable",
        )

    # Lineage identity across result / dispatch / revision. A result claiming a
    # revision that does not match the approved dispatch is rejected as a
    # REVISION_MISMATCH before any record lookup (fail closed).
    if result.dispatch_id != dispatch.get("dispatch_id"):
        return False, "DISPATCH_MISMATCH", "result dispatch_id does not match the dispatch"
    if result.revision_id != dispatch.get("revision_id"):
        return False, "REVISION_MISMATCH", "result revision_id does not match the dispatch revision"
    if revision is None:
        return False, "REVISION_NOT_FOUND", "referenced revision record does not exist"
    if result.revision_id != revision.get("revision_request_id"):
        return False, "REVISION_MISMATCH", "result revision_id does not match the revision record"
    if revision.get("status") == CANCELLED:
        return False, "REVISION_CANCELLED", "revision has been cancelled"
    if revision.get("status") == REVISION_SUPERSEDED:
        return False, "REVISION_SUPERSEDED", "revision has been superseded"
    if result.original_delivery_id != dispatch.get("delivery_id"):
        return False, "DELIVERY_MISMATCH", "result original_delivery_id does not match the dispatch delivery"
    if result.project_id != revision.get("project_id"):
        return False, "PROJECT_MISMATCH", "result project_id does not match the revision project"
    if result.correlation_id != dispatch.get("correlation_id"):
        return False, "CORRELATION_MISMATCH", "result correlation_id does not match the dispatch correlation"

    # Output formats must match the approved dispatch (canonical ordering).
    if tuple(sorted(result.output_formats)) != tuple(sorted(dispatch.get("target_formats", ()))):
        return False, "OUTPUT_FORMAT_MISMATCH", "result output formats do not match the approved dispatch"

    # Original delivery lineage must be registered before it can be superseded.
    if original_lineage is None:
        return (
            False,
            "DELIVERY_LINEAGE_UNKNOWN",
            "original delivery lineage is not registered; cannot supersede",
        )

    return True, None, None


# ---------------------------------------------------------------------------
# Deterministic idempotency helpers (no I/O)
# ---------------------------------------------------------------------------
def compute_result_identity(*, result: RerenderResult) -> tuple[str, str]:
    idem = build_result_idempotency_key(
        result_id=result.result_id,
        dispatch_id=result.dispatch_id,
        revision_id=result.revision_id,
        original_delivery_id=result.original_delivery_id,
        project_id=result.project_id,
        correlation_id=result.correlation_id,
        status=result.status,
        new_render_request_id=result.new_render_request_id,
        output_formats=tuple(result.output_formats),
        artifact_references=tuple(result.artifact_references),
        checksums=dict(result.checksums),
    )
    return idem, result_id_for(idempotency_key=idem)


def _accepted_reconciliations(*, repo_root: Path) -> dict[str, dict[str, Any]]:
    """Map idempotency_key -> accepted reconciliation record (replay/conflict)."""
    out: dict[str, dict[str, Any]] = {}
    for event in read_reconciliation_events(audit_log_path=reconciliation_audit_path(repo_root)):
        if event.event_type in (EVT_RERENDER_RESULT_ACCEPTED, EVT_RECONCILIATION_DUPLICATE):
            rec = event.record or {}
            idem = rec.get("idempotency_key")
            if idem and idem not in out:
                out[idem] = rec
    return out


# ---------------------------------------------------------------------------
# Service entry point
# ---------------------------------------------------------------------------
def reconcile_rerender_result(
    *,
    result: RerenderResult,
    operator_id: str,
    repo_root,
    recorded_at: str,
    new_delivery_record_id: str | None = None,
) -> RerenderReconciliationResult:
    """Reconcile a Stage 8C re-render result into SCOS delivery + revision lineage.

    Loads the dispatch and revision, validates lineage + integrity, performs
    deterministic idempotency checks, creates the revised delivery version (via
    Stage 8A.1) on success, appends supersession evidence, closes the revision,
    and updates the dispatch lifecycle — all append-only. Never invokes HVS.
    """
    if not result or not str(operator_id or "").strip():
        return _deny(code="MISSING_REQUIRED_INPUT", detail="result and operator_id are required")

    repo = Path(repo_root)

    # --- Load dispatch (read-only) ----------------------------------------
    dispatch_lookup = inspect_rerender_dispatch(dispatch_id=result.dispatch_id, repo_root=repo)
    if not dispatch_lookup.ok or dispatch_lookup.dispatch is None:
        _reject(
            repo_root=repo,
            result=result,
            operator_id=operator_id,
            recorded_at=recorded_at,
            code="DISPATCH_NOT_FOUND",
            detail="referenced Stage 8C dispatch does not exist",
        )
        return _deny(code="DISPATCH_NOT_FOUND", detail="referenced Stage 8C dispatch does not exist")

    # --- Deterministic identity + idempotency ------------------------------
    idem, result_id = compute_result_identity(result=result)
    accepted = _accepted_reconciliations(repo_root=repo)
    if idem in accepted:
        prior = accepted[idem]
        # Identical accepted reconciliation -> return existing (no duplicate).
        recon = _reconstruct_reconciliation(repo_root=repo, reconciliation_id=prior.get("reconciliation_id"), result=result)
        return recon
    # Conflicting accepted result for the SAME dispatch (different identity).
    for other_idem, prior in accepted.items():
        if prior.get("dispatch_id") == result.dispatch_id and other_idem != idem:
            _reject(
                repo_root=repo,
                result=result,
                operator_id=operator_id,
                recorded_at=recorded_at,
                code="RECONCILIATION_CONFLICT",
                detail="a different accepted result already exists for this dispatch",
            )
            return _deny(code="RECONCILIATION_CONFLICT", detail="conflicting accepted result for this dispatch")

    # --- Load revision + original lineage (read-only) ----------------------
    state = revision_state(repo, result.revision_id)
    revision = state["revision"] if state else None
    original_lineage = None
    lineage_result = inspect_delivery_lineage(
        delivery_record_id=result.original_delivery_id, repo_root=repo
    )
    if lineage_result.ok and lineage_result.lineage is not None:
        original_lineage = lineage_result.lineage.to_dict()

    dispatch = dispatch_lookup.dispatch.to_dict()

    # --- Failure path (no delivery / supersession / closure) ---------------
    if result.status == RERENDER_RESULT_FAILED:
        terminal = result.retryability != RERENDER_RESULT_RETRYABLE
        code = "RERENDER_RESULT_TERMINAL_FAILURE" if terminal else "RERENDER_RESULT_RETRYABLE_FAILURE"
        event = make_reconciliation_event(
            event_type=EVT_RERENDER_FAILED,
            result_id=result_id,
            dispatch_id=result.dispatch_id,
            operator_id=operator_id,
            recorded_at=recorded_at,
            record={
                "idempotency_key": idem,
                "result_id": result_id,
                "dispatch_id": result.dispatch_id,
                "revision_id": result.revision_id,
                "failure_code": result.failure_code,
                "failure_reason": result.failure_reason,
                "retryability": result.retryability,
                "terminal": terminal,
                "delivery_created": False,
            },
        )
        appended = append_reconciliation_event(audit_log_path=reconciliation_audit_path(repo), event=event)
        return RerenderReconciliationResult(
            False,
            result=result,
            error_code=code,
            error_detail=result.failure_reason or "re-render result reported failure",
            evidence_event_id=appended.event_id,
            hvs_invoked=False,
        )

    # --- Acceptance gate ---------------------------------------------------
    granted, code, detail = evaluate_rerender_result_gate(
        result=result,
        dispatch=dispatch,
        revision=revision,
        original_lineage=original_lineage,
    )
    if not granted:
        _reject(
            repo_root=repo,
            result=result,
            operator_id=operator_id,
            recorded_at=recorded_at,
            code=code,
            detail=detail,
        )
        return _deny(code=code, detail=detail)

    # --- Pre-check revision closure conflict BEFORE any delivery mutation ----
    # A conflicting closure (a prior completed reconciliation for this revision
    # under a different accepted result) must be rejected without creating a
    # revised delivery or supersession evidence.
    for event in read_reconciliation_events(audit_log_path=reconciliation_audit_path(repo)):
        if event.event_type == EVT_REVISION_COMPLETED and event.record.get("revision_id") == result.revision_id:
            if event.record.get("accepted_result_id") != result_id:
                _reject(
                    repo_root=repo,
                    result=result,
                    operator_id=operator_id,
                    recorded_at=recorded_at,
                    code="REVISION_CLOSURE_CONFLICT",
                    detail="a conflicting revision closure already exists for this revision",
                )
                return _deny(
                    code="REVISION_CLOSURE_CONFLICT",
                    detail="conflicting revision closure already exists for this revision",
                )
            # Idempotent replay of the same closure: safe to continue.
            break

    # --- Determine the new delivery record id ------------------------------
    target_new_delivery = new_delivery_record_id or result.new_render_request_id
    if not target_new_delivery:
        _reject(
            repo_root=repo,
            result=result,
            operator_id=operator_id,
            recorded_at=recorded_at,
            code="MISSING_NEW_DELIVERY_RECORD",
            detail="a new delivery record id is required to register the revised version",
        )
        return _deny(code="MISSING_NEW_DELIVERY_RECORD", detail="new delivery record id is required")

    # --- Determine the successor version deterministically (Stage 8A.1) -----
    parent = original_lineage
    planned = derive_successor_version(lineage_record=lineage_result.lineage)
    new_version = planned.successor_plan.planned_successor_version

    # --- Create the revised delivery version via Stage 8A.1 (exactly one) --
    reg = register_delivery_lineage(
        request=DeliveryLineageRegistrationRequest(
            delivery_record_id=target_new_delivery,
            delivery_version=new_version,
            operator_id=operator_id,
            registration_basis=BASIS_SUCCESSOR_OF_REGISTERED_DELIVERY,
            confirm_legacy_version=True,
            parent_lineage_id=parent["lineage_id"],
            evidence_reference=result.evidence_references[0] if result.evidence_references else result.result_id,
        ),
        repo_root=repo,
        recorded_at=recorded_at,
    )
    if not reg.ok or reg.lineage is None:
        _reject(
            repo_root=repo,
            result=result,
            operator_id=operator_id,
            recorded_at=recorded_at,
            code=reg.error_code or "REVISED_DELIVERY_REGISTRATION_FAILED",
            detail=reg.error_detail or "revised delivery lineage registration failed",
        )
        return _deny(code=reg.error_code or "REVISED_DELIVERY_REGISTRATION_FAILED", detail=reg.error_detail or "registration failed")

    lineage = reg.lineage

    # --- Append-only supersession evidence (original is immutable) ---------
    supersession = SupersessionRecord(
        schema_version=RERENDER_RESULT_SCHEMA_VERSION,
        supersession_id=build_supersession_id(
            superseding_delivery_record_id=target_new_delivery,
            superseded_delivery_record_id=result.original_delivery_id,
        ),
        revised_delivery_id=build_revised_delivery_id(idempotency_key=idem, new_delivery_record_id=target_new_delivery),
        superseding_lineage_id=lineage.lineage_id,
        superseding_delivery_record_id=target_new_delivery,
        superseding_version_sequence=lineage.delivery_version_sequence,
        superseded_delivery_record_id=result.original_delivery_id,
        superseded_lineage_id=parent.get("lineage_id"),
        superseded_version_sequence=parent["delivery_version_sequence"],
        revision_id=result.revision_id,
        dispatch_id=result.dispatch_id,
        accepted_result_id=result_id,
        created_at=recorded_at,
    )
    # Guard against supersession loops / self-supersession.
    if supersession.superseding_delivery_record_id == supersession.superseded_delivery_record_id:
        return _deny(code="SUPERSESSION_SELF_LOOP", detail="a delivery cannot supersede itself")
    if supersession.superseding_version_sequence <= supersession.superseded_version_sequence:
        return _deny(code="SUPERSESSION_CYCLE", detail="superseding version must be strictly greater")

    revised_delivery = RevisedDeliveryRecord(
        schema_version=RERENDER_RESULT_SCHEMA_VERSION,
        revised_delivery_id=supersession.revised_delivery_id,
        new_delivery_record_id=target_new_delivery,
        revision_version_sequence=lineage.delivery_version_sequence,
        revision_version_display=lineage.delivery_version_display,
        original_delivery_id=result.original_delivery_id,
        superseded_delivery_id=result.original_delivery_id,
        revision_id=result.revision_id,
        dispatch_id=result.dispatch_id,
        accepted_result_id=result_id,
        lineage_id=lineage.lineage_id,
        artifact_id=lineage.artifact_id,
        artifact_sha256=lineage.artifact_sha256,
        created_at=recorded_at,
        supersession_status="SUPERSEDED",
    )

    # --- Revision closure (append-only, idempotent, conflict-rejected) ------
    revision_closed = _close_revision(
        repo_root=repo,
        result=result,
        result_id=result_id,
        revised_delivery=revised_delivery,
        operator_id=operator_id,
        recorded_at=recorded_at,
    )

    # --- Dispatch lifecycle (canonical Stage 8C COMPLETED event) -----------
    dispatch_completed = _complete_dispatch(
        repo_root=repo,
        dispatch_id=result.dispatch_id,
        result=result,
        result_id=result_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
    )

    # --- Emit Stage 8D lifecycle events (append-only) ----------------------
    recon_id = _stable_recon_id(idem, result_id)
    ev_accepted = make_reconciliation_event(
        event_type=EVT_RERENDER_RESULT_ACCEPTED,
        result_id=result_id,
        dispatch_id=result.dispatch_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record={
            "idempotency_key": idem,
            "reconciliation_id": recon_id,
            "result_id": result_id,
            "dispatch_id": result.dispatch_id,
            "revision_id": result.revision_id,
            "new_delivery_record_id": target_new_delivery,
            "revised_delivery_id": revised_delivery.revised_delivery_id,
            "supersession_id": supersession.supersession_id,
            "revision_closed": revision_closed,
            "dispatch_completed": dispatch_completed,
        },
    )
    append_reconciliation_event(audit_log_path=reconciliation_audit_path(repo), event=ev_accepted)
    append_reconciliation_event(
        audit_log_path=reconciliation_audit_path(repo),
        event=make_reconciliation_event(
            event_type=EVT_REVISED_DELIVERY_CREATED,
            result_id=result_id,
            dispatch_id=result.dispatch_id,
            operator_id=operator_id,
            recorded_at=recorded_at,
            record=revised_delivery.to_dict(),
        ),
    )
    append_reconciliation_event(
        audit_log_path=reconciliation_audit_path(repo),
        event=make_reconciliation_event(
            event_type=EVT_DELIVERY_SUPERSEDED,
            result_id=result_id,
            dispatch_id=result.dispatch_id,
            operator_id=operator_id,
            recorded_at=recorded_at,
            record=supersession.to_dict(),
        ),
    )

    return RerenderReconciliationResult(
        True,
        result=result,
        revised_delivery=revised_delivery,
        supersession=supersession,
        revision_closed=revision_closed,
        dispatch_completed=dispatch_completed,
        reconciliation_id=recon_id,
        evidence_event_id=ev_accepted.event_id,
        hvs_invoked=False,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _reject(
    *,
    repo_root: Path,
    result: RerenderResult,
    operator_id: str,
    recorded_at: str,
    code: str,
    detail: str,
) -> None:
    idem, result_id = compute_result_identity(result=result)
    append_reconciliation_event(
        audit_log_path=reconciliation_audit_path(repo_root),
        event=make_reconciliation_event(
            event_type=EVT_RERENDER_RESULT_REJECTED,
            result_id=result_id,
            dispatch_id=result.dispatch_id,
            operator_id=operator_id,
            recorded_at=recorded_at,
            record={
                "idempotency_key": idem,
                "result_id": result_id,
                "error_code": code,
                "error_detail": detail,
            },
        ),
    )


def _stable_recon_id(idem: str, result_id: str) -> str:
    import hashlib

    canonical = json.dumps(
        {"idem": idem, "result_id": result_id},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"scos-hvs-recon-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _reconstruct_reconciliation(
    *, repo_root: Path, reconciliation_id: str | None, result: RerenderResult
) -> RerenderReconciliationResult:
    """Rebuild a reconciliation result from append-only audit events (idempotent replay)."""
    revised: RevisedDeliveryRecord | None = None
    supersession: SupersessionRecord | None = None
    recon_event = None
    for event in read_reconciliation_events(audit_log_path=reconciliation_audit_path(Path(repo_root))):
        et = event.event_type
        rec = event.record or {}
        if et == EVT_RERENDER_RESULT_ACCEPTED and rec.get("reconciliation_id") == reconciliation_id:
            recon_event = event
        elif et == EVT_REVISED_DELIVERY_CREATED and rec.get("revised_delivery_id"):
            revised = RevisedDeliveryRecord(**rec)
        elif et == EVT_DELIVERY_SUPERSEDED and rec.get("supersession_id"):
            supersession = SupersessionRecord(**rec)
    if recon_event is None:
        return _deny(code="RECONCILIATION_NOT_FOUND", detail="reconciliation not found")
    return RerenderReconciliationResult(
        True,
        result=result,
        duplicate_of=reconciliation_id,
        revised_delivery=revised,
        supersession=supersession,
        revision_closed=True,
        dispatch_completed=True,
        existing_reconciliation_id=reconciliation_id,
        reconciliation_id=reconciliation_id,
        evidence_event_id=recon_event.event_id,
        hvs_invoked=False,
    )


def _close_revision(
    *,
    repo_root: Path,
    result: RerenderResult,
    result_id: str,
    revised_delivery: RevisedDeliveryRecord,
    operator_id: str,
    recorded_at: str,
) -> bool:
    """Append-only, idempotent revision closure for Stage 8D.

    The Stage 8B revision ledger has no terminal 'completed' state, so closure
    is recorded in the Stage 8D reconciliation ledger. Replaying the same
    closure returns the existing event; a conflicting closure (different
    result) is rejected.
    """
    for event in read_reconciliation_events(audit_log_path=reconciliation_audit_path(repo_root)):
        if event.event_type == EVT_REVISION_COMPLETED and event.record.get("revision_id") == result.revision_id:
            if event.record.get("accepted_result_id") == result_id:
                return True  # idempotent replay
            raise ValueError("conflicting revision closure already exists for this revision")
    append_reconciliation_event(
        audit_log_path=reconciliation_audit_path(repo_root),
        event=make_reconciliation_event(
            event_type=EVT_REVISION_COMPLETED,
            result_id=result_id,
            dispatch_id=result.dispatch_id,
            operator_id=operator_id,
            recorded_at=recorded_at,
            record={
                "revision_id": result.revision_id,
                "accepted_result_id": result_id,
                "new_delivery_version": revised_delivery.revision_version_display,
                "new_delivery_record_id": revised_delivery.new_delivery_record_id,
                "previous_delivery_record_id": revised_delivery.original_delivery_id,
                "dispatch_id": result.dispatch_id,
                "supersession_id": revised_delivery.revised_delivery_id,
            },
        ),
    )
    return True


def _complete_dispatch(
    *,
    repo_root: Path,
    dispatch_id: str,
    result: RerenderResult,
    result_id: str,
    operator_id: str,
    recorded_at: str,
) -> bool:
    """Append the canonical Stage 8C RERENDER_DISPATCH_COMPLETED lifecycle event."""
    event = make_dispatch_event(
        event_type=RERENDER_DISPATCH_COMPLETED,
        dispatch_id=dispatch_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record={
            "result_id": result_id,
            "status": result.status,
            "new_delivery_record_id": result.new_render_request_id,
        },
    )
    existing = append_rerender_dispatch_event(
        audit_log_path=rerender_dispatch_audit_path(repo_root), event=event
    )
    return existing.event_id == event.event_id


def inspect_reconciliation(*, reconciliation_id: str, repo_root) -> RerenderReconciliationResult:
    """Inspect a Stage 8D reconciliation by id (no mutation)."""
    for event in read_reconciliation_events(audit_log_path=reconciliation_audit_path(Path(repo_root))):
        if event.event_type == EVT_RERENDER_RESULT_ACCEPTED and event.record.get("reconciliation_id") == reconciliation_id:
            rec = event.record
            return RerenderReconciliationResult(
                True,
                reconciliation_id=reconciliation_id,
                existing_reconciliation_id=reconciliation_id,
                evidence_event_id=event.event_id,
                hvs_invoked=False,
            )
    return _deny(code="RECONCILIATION_NOT_FOUND", detail="reconciliation not found")


def list_revised_delivery_lineage(*, project_id: str, repo_root) -> tuple[RevisedDeliveryRecord, ...]:
    """Return the revised-delivery lineage for a project (deterministic, read-only)."""
    out: list[RevisedDeliveryRecord] = []
    for event in read_reconciliation_events(audit_log_path=reconciliation_audit_path(Path(repo_root))):
        if event.event_type == EVT_REVISED_DELIVERY_CREATED:
            rec = event.record
            if rec.get("project_id") == project_id or rec.get("revision_id") == project_id:
                out.append(RevisedDeliveryRecord(**rec))
    out.sort(key=lambda r: r.revision_version_sequence)
    return tuple(out)


def list_supersession_lineage(*, repo_root) -> tuple[SupersessionRecord, ...]:
    """Return all append-only supersession evidence (deterministic, read-only)."""
    out = [
        SupersessionRecord(**event.record)
        for event in read_reconciliation_events(audit_log_path=reconciliation_audit_path(Path(repo_root)))
        if event.event_type == EVT_DELIVERY_SUPERSEDED
    ]
    out.sort(key=lambda s: s.superseding_version_sequence)
    return tuple(out)
