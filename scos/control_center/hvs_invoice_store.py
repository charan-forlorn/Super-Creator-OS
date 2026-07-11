"""SCOS <-> HVS Stage 8A append-only invoice audit store."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .hvs_invoice_models import (
    ALLOWED_INVOICE_EVENT_TYPES,
    INVOICE_AUDIT_SCHEMA_VERSION,
    PaymentStatusEvent,
    stable_invoice_event_id,
)
from .hvs_local_delivery_models import _require_allowed
from .hvs_local_delivery_service import _runtime_root

INVOICE_AUDIT_FILENAME = "hvs_invoice_audit.jsonl"


def invoice_audit_path(repo_root: Path) -> Path:
    return _runtime_root(Path(repo_root)) / INVOICE_AUDIT_FILENAME


def _ensure_local_path(path: Any) -> Path:
    target = path if isinstance(path, Path) else Path(str(path))
    text = str(target)
    lowered = text.lower()
    if lowered.startswith(("http://", "https://")) or "\x00" in text:
        raise ValueError("audit path must be a safe local path")
    return target


def append_invoice_event(
    *,
    audit_log_path: Any,
    event_type: str,
    invoice_preparation_id: str | None,
    commercial_scope_id: str | None,
    delivery_closure_id: str | None,
    resulting_status: str,
    operator_id: str | None,
    recorded_at: str,
    record: dict[str, Any] | None = None,
    detail: str | None = None,
    decision: str | None = None,
    reference: str | None = None,
) -> PaymentStatusEvent:
    _require_allowed("event_type", event_type, ALLOWED_INVOICE_EVENT_TYPES)
    event = PaymentStatusEvent(
        schema_version=INVOICE_AUDIT_SCHEMA_VERSION,
        event_id=stable_invoice_event_id(
            event_type=event_type,
            invoice_preparation_id=invoice_preparation_id,
            commercial_scope_id=commercial_scope_id,
            resulting_status=resulting_status,
            operator_id=operator_id,
            decision=decision,
            reference=reference,
        ),
        event_type=event_type,
        invoice_preparation_id=invoice_preparation_id,
        commercial_scope_id=commercial_scope_id,
        delivery_closure_id=delivery_closure_id,
        resulting_status=resulting_status,
        operator_id=operator_id,
        recorded_at=recorded_at,
        automation_allowed=False,
        record=record,
        detail=detail,
    )
    target = _ensure_local_path(audit_log_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
    return event


def read_invoice_events(*, audit_log_path: Any) -> tuple[PaymentStatusEvent, ...]:
    target = _ensure_local_path(audit_log_path)
    if not target.is_file():
        return ()
    events: list[PaymentStatusEvent] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        events.append(PaymentStatusEvent(**payload))
    return tuple(events)


def compute_line_hash(audit_log_path: Any) -> str:
    target = _ensure_local_path(audit_log_path)
    h = hashlib.sha256()
    if target.is_file():
        h.update(target.read_bytes())
    return h.hexdigest()
