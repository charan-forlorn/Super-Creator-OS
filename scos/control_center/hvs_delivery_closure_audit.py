"""SCOS <-> HVS Stage 7 append-only delivery closure audit."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hvs_local_delivery_models import _require_allowed, _sha256_hex16

CLOSURE_AUDIT_SCHEMA_VERSION = "scos-hvs.delivery-closure-audit-event.v1/1.0.0"

EVT_CUSTOMER_RECEIPT_ACKNOWLEDGED = "CUSTOMER_RECEIPT_ACKNOWLEDGED"
EVT_CUSTOMER_REVISION_REQUESTED = "CUSTOMER_REVISION_REQUESTED"
EVT_CUSTOMER_DELIVERY_REJECTED = "CUSTOMER_DELIVERY_REJECTED"
EVT_CUSTOMER_RECEIPT_UNCONFIRMED = "CUSTOMER_RECEIPT_UNCONFIRMED"
EVT_REVISION_REQUEST_OPENED = "REVISION_REQUEST_OPENED"
EVT_DELIVERY_ACCEPTED_AND_CLOSED = "DELIVERY_ACCEPTED_AND_CLOSED"
EVT_DELIVERY_REVISION_OPEN = "DELIVERY_REVISION_OPEN"
EVT_DELIVERY_REJECTED_AND_CLOSED = "DELIVERY_REJECTED_AND_CLOSED"
EVT_DELIVERY_CLOSED_WITHOUT_CONFIRMATION = "DELIVERY_CLOSED_WITHOUT_CONFIRMATION"
EVT_DELIVERY_CLOSURE_REJECTED = "DELIVERY_CLOSURE_REJECTED"
EVT_REVENUE_AUDIT_SUMMARY_CREATED = "REVENUE_AUDIT_SUMMARY_CREATED"
EVT_REVENUE_AUDIT_SUMMARY_BLOCKED = "REVENUE_AUDIT_SUMMARY_BLOCKED"
EVT_INTEGRITY_REVALIDATION_FAILED = "INTEGRITY_REVALIDATION_FAILED"
ALLOWED_CLOSURE_EVENT_TYPES = (
    EVT_CUSTOMER_RECEIPT_ACKNOWLEDGED,
    EVT_CUSTOMER_REVISION_REQUESTED,
    EVT_CUSTOMER_DELIVERY_REJECTED,
    EVT_CUSTOMER_RECEIPT_UNCONFIRMED,
    EVT_REVISION_REQUEST_OPENED,
    EVT_DELIVERY_ACCEPTED_AND_CLOSED,
    EVT_DELIVERY_REVISION_OPEN,
    EVT_DELIVERY_REJECTED_AND_CLOSED,
    EVT_DELIVERY_CLOSED_WITHOUT_CONFIRMATION,
    EVT_DELIVERY_CLOSURE_REJECTED,
    EVT_REVENUE_AUDIT_SUMMARY_CREATED,
    EVT_REVENUE_AUDIT_SUMMARY_BLOCKED,
    EVT_INTEGRITY_REVALIDATION_FAILED,
)


@dataclass(frozen=True)
class DeliveryClosureAuditEvent:
    schema_version: str
    event_id: str
    receipt_evidence_id: str | None
    closure_id: str | None
    revision_request_id: str | None
    summary_id: str | None
    package_id: str
    delivery_record_id: str
    project_id: str | None
    artifact_sha256: str
    event_type: str
    resulting_status: str
    operator_id: str
    recorded_at: str
    automation_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def stable_closure_event_id(
    *,
    event_type: str,
    package_id: str,
    delivery_record_id: str,
    artifact_sha256: str,
    resulting_status: str,
    receipt_evidence_id: str | None = None,
    closure_id: str | None = None,
    revision_request_id: str | None = None,
    summary_id: str | None = None,
    operator_id: str | None = None,
) -> str:
    canon = "|".join(
        [
            event_type,
            package_id,
            delivery_record_id,
            artifact_sha256,
            resulting_status,
            receipt_evidence_id or "",
            closure_id or "",
            revision_request_id or "",
            summary_id or "",
            operator_id or "",
        ]
    )
    return "clsevt-" + _sha256_hex16(canon)


def _ensure_local_path(path: Any) -> Path:
    target = path if isinstance(path, Path) else Path(str(path))
    text = str(target)
    lowered = text.lower()
    if lowered.startswith(("http://", "https://")) or "\x00" in text:
        raise ValueError("audit path must be a safe local path")
    return target


def append_closure_event(
    *,
    audit_log_path: Any,
    event_type: str,
    package_id: str,
    delivery_record_id: str,
    project_id: str | None,
    artifact_sha256: str,
    resulting_status: str,
    operator_id: str,
    recorded_at: str,
    receipt_evidence_id: str | None = None,
    closure_id: str | None = None,
    revision_request_id: str | None = None,
    summary_id: str | None = None,
) -> DeliveryClosureAuditEvent:
    _require_allowed("event_type", event_type, ALLOWED_CLOSURE_EVENT_TYPES)
    event = DeliveryClosureAuditEvent(
        schema_version=CLOSURE_AUDIT_SCHEMA_VERSION,
        event_id=stable_closure_event_id(
            event_type=event_type,
            package_id=package_id,
            delivery_record_id=delivery_record_id,
            artifact_sha256=artifact_sha256,
            resulting_status=resulting_status,
            receipt_evidence_id=receipt_evidence_id,
            closure_id=closure_id,
            revision_request_id=revision_request_id,
            summary_id=summary_id,
            operator_id=operator_id,
        ),
        receipt_evidence_id=receipt_evidence_id,
        closure_id=closure_id,
        revision_request_id=revision_request_id,
        summary_id=summary_id,
        package_id=package_id,
        delivery_record_id=delivery_record_id,
        project_id=project_id,
        artifact_sha256=artifact_sha256,
        event_type=event_type,
        resulting_status=resulting_status,
        operator_id=operator_id,
        recorded_at=recorded_at,
        automation_allowed=False,
    )
    target = _ensure_local_path(audit_log_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
    return event


def read_closure_events(*, audit_log_path: Any) -> tuple[DeliveryClosureAuditEvent, ...]:
    target = _ensure_local_path(audit_log_path)
    if not target.is_file():
        return ()
    events: list[DeliveryClosureAuditEvent] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        events.append(DeliveryClosureAuditEvent(**payload))
    return tuple(events)


def compute_line_hash(audit_log_path: Any) -> str:
    target = _ensure_local_path(audit_log_path)
    h = hashlib.sha256()
    if target.is_file():
        h.update(target.read_bytes())
    return h.hexdigest()
