"""Read and register immutable delivery-version lineage without Stage 8B actions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hvs_delivery_closure_models import CLOSURE_ACCEPTED
from .hvs_delivery_closure_service import get_closure
from .hvs_delivery_lineage_models import (
    ALLOWED_REGISTRATION_BASES, BASIS_EXISTING_EXTERNAL_VERSION_RECORD,
    BASIS_IMPORTED_CERTIFIED_LINEAGE, BASIS_OPERATOR_HISTORICAL_RECONCILIATION,
    BASIS_ORIGINAL_DELIVERY_CONFIRMED, BASIS_SUCCESSOR_OF_REGISTERED_DELIVERY,
    DELIVERY_LINEAGE_EVENT_SCHEMA_VERSION, DELIVERY_LINEAGE_SCHEMA_VERSION,
    ERR_ARTIFACT_SHA_MISMATCH, ERR_CONFLICT, ERR_DELIVERY_VERSION_UNKNOWN,
    ERR_INELIGIBLE_CLOSURE, ERR_LEGACY_CONFIRMATION_REQUIRED, ERR_MISSING_OPERATOR_ID,
    ERR_NOT_FOUND, ERR_PARENT_INVALID, ERR_PARENT_REQUIRED, EVT_LINEAGE_CONFLICT_DETECTED,
    EVT_LINEAGE_REGISTERED, EVT_LINEAGE_REGISTRATION_REJECTED,
    EVT_LINEAGE_REGISTRATION_REQUESTED, LINEAGE_REGISTERED, LINEAGE_UNKNOWN,
    SUPERSESSION_NOT_YET_SUPERSEDED, DeliveryLineageEvent, DeliveryLineageRecord,
    DeliveryLineageRegistrationRequest, DeliveryVersion, SuccessorVersionPlan,
    stable_artifact_id, stable_lineage_event_id, stable_lineage_id,
)
from .hvs_delivery_lineage_store import append_lineage_event, lineage_audit_path, read_lineage_events
from .hvs_local_delivery_service import load_manual_delivery_record


@dataclass(frozen=True)
class DeliveryLineageServiceResult:
    ok: bool
    delivery_record_id: str | None = None
    delivery_closure_id: str | None = None
    artifact_sha256: str | None = None
    lineage_status: str = LINEAGE_UNKNOWN
    registered_version: DeliveryVersion | None = None
    lineage: DeliveryLineageRecord | None = None
    lineages: tuple[DeliveryLineageRecord, ...] = ()
    successor_plan: SuccessorVersionPlan | None = None
    successor_planning_eligible: bool = False
    blocking_reason: str | None = ERR_DELIVERY_VERSION_UNKNOWN
    error_code: str | None = None
    error_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": DELIVERY_LINEAGE_SCHEMA_VERSION,
            "delivery_record_id": self.delivery_record_id,
            "delivery_closure_id": self.delivery_closure_id,
            "artifact_sha256": self.artifact_sha256,
            "lineage_status": self.lineage_status,
            "registered_version": self.registered_version.to_dict() if self.registered_version else None,
            "lineage": self.lineage.to_dict() if self.lineage else None,
            "lineages": [record.to_dict() for record in self.lineages],
            "successor_plan": self.successor_plan.to_dict() if self.successor_plan else None,
            "successor_planning_eligible": self.successor_planning_eligible,
            "blocking_reason": self.blocking_reason,
            "automation_allowed": False,
            "persistence_performed": False,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }


def _deny(*, code: str, detail: str, delivery_record_id: str | None = None, closure: Any = None) -> DeliveryLineageServiceResult:
    return DeliveryLineageServiceResult(
        ok=False,
        delivery_record_id=delivery_record_id,
        delivery_closure_id=getattr(closure, "closure_id", None),
        artifact_sha256=getattr(closure, "artifact_sha256", None),
        lineage_status=LINEAGE_UNKNOWN,
        blocking_reason=code,
        error_code=code,
        error_detail=detail,
    )


def _records(repo_root: Path) -> tuple[DeliveryLineageRecord, ...]:
    latest: dict[str, DeliveryLineageRecord] = {}
    for event in read_lineage_events(audit_log_path=lineage_audit_path(repo_root)):
        if event.event_type != EVT_LINEAGE_REGISTERED or not event.record:
            continue
        record = DeliveryLineageRecord(**event.record)
        prior = latest.get(record.lineage_id)
        if prior is not None and prior != record:
            raise ValueError("conflicting immutable lineage record")
        latest[record.lineage_id] = record
    return tuple(latest[key] for key in sorted(latest))


def _closure_for_delivery(*, delivery_record_id: str, repo_root: Path):
    for path in (repo_root / "scos" / "work" / "hvs_delivery_packages").glob("*/delivery_closure_*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("malformed delivery closure record") from exc
        if payload.get("delivery_record_id") != delivery_record_id:
            continue
        result = get_closure(closure_id=payload.get("closure_id", ""), repo_root=repo_root)
        if not result.ok or result.closure is None:
            raise LookupError(result.error_detail or "delivery closure cannot be verified")
        return result.closure
    return None


def _content_hash(record: DeliveryLineageRecord) -> str:
    identity = record.to_dict().copy()
    identity.pop("registered_at")
    identity.pop("deterministic_content_hash")
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def _find_for_delivery(records: tuple[DeliveryLineageRecord, ...], delivery_record_id: str) -> DeliveryLineageRecord | None:
    found = [record for record in records if record.delivery_record_id == delivery_record_id]
    if len(found) > 1:
        raise ValueError("conflicting registered lineage for delivery record")
    return found[0] if found else None


def inspect_delivery_lineage(*, delivery_record_id: str, repo_root) -> DeliveryLineageServiceResult:
    repo = Path(repo_root)
    try:
        closure = _closure_for_delivery(delivery_record_id=delivery_record_id, repo_root=repo)
    except (LookupError, ValueError) as exc:
        return _deny(code=ERR_NOT_FOUND, detail=str(exc), delivery_record_id=delivery_record_id)
    if closure is None:
        return _deny(code=ERR_NOT_FOUND, detail="completed delivery closure not found", delivery_record_id=delivery_record_id)
    try:
        record = _find_for_delivery(_records(repo), delivery_record_id)
    except ValueError as exc:
        return _deny(code=ERR_CONFLICT, detail=str(exc), delivery_record_id=delivery_record_id, closure=closure)
    if record is None:
        return DeliveryLineageServiceResult(
            ok=True, delivery_record_id=delivery_record_id, delivery_closure_id=closure.closure_id,
            artifact_sha256=closure.artifact_sha256, lineage_status=LINEAGE_UNKNOWN,
            successor_planning_eligible=False, blocking_reason=ERR_DELIVERY_VERSION_UNKNOWN,
        )
    return DeliveryLineageServiceResult(
        ok=True, delivery_record_id=delivery_record_id, delivery_closure_id=closure.closure_id,
        artifact_sha256=closure.artifact_sha256, lineage_status=record.lineage_status,
        registered_version=DeliveryVersion(record.delivery_version_sequence), lineage=record,
        successor_planning_eligible=record.lineage_status == LINEAGE_REGISTERED,
        blocking_reason=None,
    )


def _append_event(*, repo_root: Path, event_type: str, delivery_record_id: str | None, lineage_id: str | None, status: str, operator_id: str | None, recorded_at: str, detail: str | None, record: DeliveryLineageRecord | None = None) -> None:
    event = DeliveryLineageEvent(
        schema_version=DELIVERY_LINEAGE_EVENT_SCHEMA_VERSION,
        event_id=stable_lineage_event_id(event_type=event_type, lineage_id=lineage_id, delivery_record_id=delivery_record_id, detail=detail),
        event_type=event_type, delivery_record_id=delivery_record_id, lineage_id=lineage_id,
        resulting_status=status, operator_id=operator_id, recorded_at=recorded_at,
        automation_allowed=False, detail=detail, record=record.to_dict() if record else None,
    )
    append_lineage_event(audit_log_path=lineage_audit_path(repo_root), event=event)


def _validate_basis(request: DeliveryLineageRegistrationRequest) -> str | None:
    if request.registration_basis not in ALLOWED_REGISTRATION_BASES:
        return "registration basis is not allowed"
    if request.registration_basis == BASIS_EXISTING_EXTERNAL_VERSION_RECORD and not str(request.evidence_reference or "").strip():
        return "EXISTING_EXTERNAL_VERSION_RECORD requires evidence_reference"
    if request.registration_basis == BASIS_OPERATOR_HISTORICAL_RECONCILIATION and not str(request.registration_reason or "").strip():
        return "OPERATOR_HISTORICAL_RECONCILIATION requires registration_reason"
    if request.registration_basis == BASIS_IMPORTED_CERTIFIED_LINEAGE and not str(request.parent_lineage_id or "").strip():
        return "IMPORTED_CERTIFIED_LINEAGE requires parent_lineage_id"
    if request.registration_basis == BASIS_IMPORTED_CERTIFIED_LINEAGE and not str(request.evidence_reference or "").strip():
        return "IMPORTED_CERTIFIED_LINEAGE requires evidence_reference"
    return None


def register_delivery_lineage(*, request: DeliveryLineageRegistrationRequest, repo_root, recorded_at: str) -> DeliveryLineageServiceResult:
    repo = Path(repo_root)
    if not str(request.operator_id or "").strip():
        return _deny(code=ERR_MISSING_OPERATOR_ID, detail="operator_id is required", delivery_record_id=request.delivery_record_id)
    if not request.confirm_legacy_version:
        return _deny(code=ERR_LEGACY_CONFIRMATION_REQUIRED, detail="explicit legacy version confirmation is required", delivery_record_id=request.delivery_record_id)
    basis_error = _validate_basis(request)
    if basis_error:
        return _deny(code="INVALID_REGISTRATION_BASIS", detail=basis_error, delivery_record_id=request.delivery_record_id)
    try:
        closure = _closure_for_delivery(delivery_record_id=request.delivery_record_id, repo_root=repo)
    except (LookupError, ValueError) as exc:
        return _deny(code=ERR_NOT_FOUND, detail=str(exc), delivery_record_id=request.delivery_record_id)
    if closure is None:
        return _deny(code=ERR_NOT_FOUND, detail="completed delivery closure not found", delivery_record_id=request.delivery_record_id)
    if closure.closure_status != CLOSURE_ACCEPTED or not closure.accepted_by_customer:
        return _deny(code=ERR_INELIGIBLE_CLOSURE, detail="lineage registration requires an accepted delivery closure", delivery_record_id=request.delivery_record_id, closure=closure)
    try:
        records = _records(repo)
    except ValueError as exc:
        return _deny(code=ERR_CONFLICT, detail=str(exc), delivery_record_id=request.delivery_record_id, closure=closure)
    current = _find_for_delivery(records, request.delivery_record_id)
    artifact_id = stable_artifact_id(artifact_sha256=closure.artifact_sha256)
    delivery_record = load_manual_delivery_record(package_id=closure.package_id, repo_root=repo)
    if delivery_record is None:
        return _deny(code=ERR_NOT_FOUND, detail="manual delivery record not found", delivery_record_id=request.delivery_record_id, closure=closure)
    parent = None
    if request.parent_lineage_id:
        parent = next((record for record in records if record.lineage_id == request.parent_lineage_id), None)
        if parent is None or parent.lineage_status != LINEAGE_REGISTERED:
            return _deny(code=ERR_PARENT_INVALID, detail="parent lineage is not registered", delivery_record_id=request.delivery_record_id, closure=closure)
        if parent.project_id != closure.project_id or parent.delivery_version_sequence >= request.delivery_version.sequence:
            return _deny(code=ERR_PARENT_INVALID, detail="parent lineage project or version is invalid", delivery_record_id=request.delivery_record_id, closure=closure)
        if (request.delivery_version.sequence != parent.delivery_version_sequence + 1
                and request.registration_basis != BASIS_IMPORTED_CERTIFIED_LINEAGE):
            return _deny(code=ERR_PARENT_INVALID, detail="successor version must immediately follow its parent", delivery_record_id=request.delivery_record_id, closure=closure)
        if parent.artifact_sha256 == closure.artifact_sha256:
            return _deny(code=ERR_CONFLICT, detail="successor must bind a distinct artifact SHA-256", delivery_record_id=request.delivery_record_id, closure=closure)
    elif request.delivery_version.sequence > 1:
        return _deny(code=ERR_PARENT_REQUIRED, detail="non-original delivery versions require a registered parent lineage", delivery_record_id=request.delivery_record_id, closure=closure)
    if request.registration_basis == BASIS_ORIGINAL_DELIVERY_CONFIRMED and request.delivery_version.sequence != 1:
        return _deny(code="INVALID_REGISTRATION_BASIS", detail="ORIGINAL_DELIVERY_CONFIRMED requires version 1", delivery_record_id=request.delivery_record_id, closure=closure)
    if request.registration_basis == BASIS_SUCCESSOR_OF_REGISTERED_DELIVERY and parent is None:
        return _deny(code=ERR_PARENT_REQUIRED, detail="SUCCESSOR_OF_REGISTERED_DELIVERY requires parent_lineage_id", delivery_record_id=request.delivery_record_id, closure=closure)
    lineage_id = stable_lineage_id(
        project_id=closure.project_id,
        delivery_record_id=closure.delivery_record_id,
        delivery_closure_id=closure.closure_id, artifact_id=artifact_id,
        artifact_sha256=closure.artifact_sha256, delivery_version_sequence=request.delivery_version.sequence,
        parent_lineage_id=request.parent_lineage_id,
    )
    candidate = DeliveryLineageRecord(
        schema_version=DELIVERY_LINEAGE_SCHEMA_VERSION, lineage_id=lineage_id,
        project_id=closure.project_id, recipient_label=delivery_record.recipient_label,
        delivery_record_id=closure.delivery_record_id,
        delivery_closure_id=closure.closure_id, artifact_id=artifact_id,
        artifact_sha256=closure.artifact_sha256.lower(),
        delivery_version_sequence=request.delivery_version.sequence,
        delivery_version_display=request.delivery_version.display,
        parent_lineage_id=parent.lineage_id if parent else None,
        parent_artifact_id=parent.artifact_id if parent else None,
        parent_artifact_sha256=parent.artifact_sha256 if parent else None,
        parent_delivery_version_sequence=parent.delivery_version_sequence if parent else None,
        lineage_status=LINEAGE_REGISTERED, supersession_status=SUPERSESSION_NOT_YET_SUPERSEDED,
        registered_by_operator_id=request.operator_id.strip(), registration_basis=request.registration_basis,
        evidence_reference=request.evidence_reference.strip() if request.evidence_reference else None,
        registration_reason=request.registration_reason.strip() if request.registration_reason else None,
        deterministic_content_hash="", registered_at=recorded_at,
    )
    candidate = DeliveryLineageRecord(**(candidate.to_dict() | {"deterministic_content_hash": _content_hash(candidate)}))
    if current is not None:
        if current.lineage_id == candidate.lineage_id and current.deterministic_content_hash == candidate.deterministic_content_hash:
            return DeliveryLineageServiceResult(ok=True, delivery_record_id=current.delivery_record_id, delivery_closure_id=current.delivery_closure_id, artifact_sha256=current.artifact_sha256, lineage_status=current.lineage_status, registered_version=DeliveryVersion(current.delivery_version_sequence), lineage=current, successor_planning_eligible=True, blocking_reason=None)
        _append_event(repo_root=repo, event_type=EVT_LINEAGE_CONFLICT_DETECTED, delivery_record_id=request.delivery_record_id, lineage_id=current.lineage_id, status="CONFLICT", operator_id=request.operator_id, recorded_at=recorded_at, detail="delivery record already has immutable lineage")
        return _deny(code=ERR_CONFLICT, detail="delivery record already has conflicting lineage", delivery_record_id=request.delivery_record_id, closure=closure)
    for seen in records:
        if seen.project_id == closure.project_id and seen.delivery_version_sequence == candidate.delivery_version_sequence:
            return _deny(code=ERR_CONFLICT, detail="delivery version is already registered for another artifact", delivery_record_id=request.delivery_record_id, closure=closure)
        if seen.project_id == closure.project_id and seen.artifact_sha256 == candidate.artifact_sha256:
            return _deny(code=ERR_CONFLICT, detail="artifact SHA-256 is already registered at another version", delivery_record_id=request.delivery_record_id, closure=closure)
    _append_event(repo_root=repo, event_type=EVT_LINEAGE_REGISTRATION_REQUESTED, delivery_record_id=candidate.delivery_record_id, lineage_id=candidate.lineage_id, status="REQUESTED", operator_id=request.operator_id, recorded_at=recorded_at, detail="explicit operator lineage registration")
    _append_event(repo_root=repo, event_type=EVT_LINEAGE_REGISTERED, delivery_record_id=candidate.delivery_record_id, lineage_id=candidate.lineage_id, status=LINEAGE_REGISTERED, operator_id=request.operator_id, recorded_at=recorded_at, detail="immutable lineage registered", record=candidate)
    return DeliveryLineageServiceResult(ok=True, delivery_record_id=candidate.delivery_record_id, delivery_closure_id=candidate.delivery_closure_id, artifact_sha256=candidate.artifact_sha256, lineage_status=candidate.lineage_status, registered_version=DeliveryVersion(candidate.delivery_version_sequence), lineage=candidate, successor_planning_eligible=True, blocking_reason=None)


def derive_successor_version(*, lineage_record: DeliveryLineageRecord) -> DeliveryLineageServiceResult:
    if lineage_record.lineage_status != LINEAGE_REGISTERED:
        return _deny(code=ERR_DELIVERY_VERSION_UNKNOWN, detail="source delivery lineage is not registered", delivery_record_id=lineage_record.delivery_record_id)
    source = DeliveryVersion(lineage_record.delivery_version_sequence)
    plan = SuccessorVersionPlan(source_lineage_id=lineage_record.lineage_id, source_version=source, planned_successor_version=DeliveryVersion(source.sequence + 1), source_artifact_sha256=lineage_record.artifact_sha256, supersession_status=SUPERSESSION_NOT_YET_SUPERSEDED, persistence_performed=False, rerender_started=False, automation_allowed=False)
    return DeliveryLineageServiceResult(ok=True, delivery_record_id=lineage_record.delivery_record_id, delivery_closure_id=lineage_record.delivery_closure_id, artifact_sha256=lineage_record.artifact_sha256, lineage_status=lineage_record.lineage_status, registered_version=source, lineage=lineage_record, successor_plan=plan, successor_planning_eligible=True, blocking_reason=None)


def plan_successor_version(*, delivery_record_id: str, repo_root) -> DeliveryLineageServiceResult:
    inspected = inspect_delivery_lineage(delivery_record_id=delivery_record_id, repo_root=repo_root)
    if not inspected.ok or inspected.lineage is None:
        return _deny(code=ERR_DELIVERY_VERSION_UNKNOWN, detail="delivery version lineage is unknown", delivery_record_id=delivery_record_id)
    return derive_successor_version(lineage_record=inspected.lineage)


def verify_lineage_integrity(*, lineage_id: str, repo_root) -> DeliveryLineageServiceResult:
    """Revalidate a registered lineage against its immutable Stage 7 source."""
    repo = Path(repo_root)
    try:
        record = next((item for item in _records(repo) if item.lineage_id == lineage_id), None)
    except ValueError as exc:
        return _deny(code=ERR_CONFLICT, detail=str(exc))
    if record is None:
        return _deny(code=ERR_NOT_FOUND, detail="lineage record not found")
    try:
        closure = _closure_for_delivery(delivery_record_id=record.delivery_record_id, repo_root=repo)
    except (LookupError, ValueError) as exc:
        return _deny(code=ERR_ARTIFACT_SHA_MISMATCH, detail=str(exc), delivery_record_id=record.delivery_record_id)
    if closure is None or closure.closure_id != record.delivery_closure_id:
        return _deny(code=ERR_NOT_FOUND, detail="delivery closure no longer matches lineage", delivery_record_id=record.delivery_record_id)
    if closure.closure_status != CLOSURE_ACCEPTED:
        return _deny(code=ERR_INELIGIBLE_CLOSURE, detail="delivery closure is no longer accepted", delivery_record_id=record.delivery_record_id, closure=closure)
    if closure.artifact_sha256.lower() != record.artifact_sha256.lower():
        return _deny(code=ERR_ARTIFACT_SHA_MISMATCH, detail="delivery artifact SHA-256 no longer matches lineage", delivery_record_id=record.delivery_record_id, closure=closure)
    return DeliveryLineageServiceResult(
        ok=True, delivery_record_id=record.delivery_record_id,
        delivery_closure_id=record.delivery_closure_id, artifact_sha256=record.artifact_sha256,
        lineage_status=record.lineage_status, registered_version=DeliveryVersion(record.delivery_version_sequence),
        lineage=record, successor_planning_eligible=record.lineage_status == LINEAGE_REGISTERED,
        blocking_reason=None,
    )


def list_project_delivery_lineage(*, project_id: str, repo_root) -> DeliveryLineageServiceResult:
    records = tuple(record for record in _records(Path(repo_root)) if record.project_id == project_id)
    return DeliveryLineageServiceResult(ok=True, lineages=records, lineage_status=LINEAGE_REGISTERED if records else LINEAGE_UNKNOWN, successor_planning_eligible=False, blocking_reason=None if records else ERR_DELIVERY_VERSION_UNKNOWN)


def inspect_lineage_events(*, repo_root) -> tuple[DeliveryLineageEvent, ...]:
    return read_lineage_events(audit_log_path=lineage_audit_path(Path(repo_root)))
