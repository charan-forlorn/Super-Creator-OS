"""SCOS <-> HVS Stage 6 delivery audit (JSONL, append-only).

Local, deterministic, append-only audit store for Stage 6 delivery-package
and manual-delivery events. The log is strictly append-only: this module
never deletes, truncates, or rewrites existing lines. Each event is one
JSON object per (UTF-8, LF) line, keyed by a content-derived event id so
replaying the same lifecycle always yields the same id.

This is a SEPARATE append-only store from the Stage 5 SQLite hash-chain
ledger. Stage 6 does not extend that ledger's decision/subject_type taxonomies
(avoiding changes to Stage 5 production code); instead it keeps its own
append-only delivery audit following the same local-first discipline as
``event_log`` / ``command_queue``.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid, no
network, no subprocess.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from .hvs_local_delivery_models import (
        ALLOWED_DELIVERY_EVENT_TYPES,
        DeliveryAuditEvent,
        _require_allowed,
        stable_delivery_event_id,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from hvs_local_delivery_models import (
        ALLOWED_DELIVERY_EVENT_TYPES,
        DeliveryAuditEvent,
        _require_allowed,
        stable_delivery_event_id,
    )

DELIVERY_AUDIT_SCHEMA_VERSION = "scos-hvs.delivery-audit-event.v1/1.0.0"


def _ensure_local_path(path: Any) -> Path:
    if isinstance(path, Path):
        return path
    if isinstance(path, str):
        text = path.strip()
        lowered = text.lower()
        if lowered.startswith(("http://", "https://")) or ":" in text.split("/", 1)[0]:
            raise ValueError("URL_PATH_REJECTED: audit path must be local")
        return Path(text)
    raise ValueError("INVALID_PATH: audit path must be a str or pathlib.Path")


def _jsonl_line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def append_delivery_event(
    *,
    audit_log_path: Any,
    event_type: str,
    package_id: str,
    approval_request_id: str,
    packet_id: str | None,
    artifact_sha256: str,
    resulting_state: str,
    operator_id: str | None,
    recorded_at: str,
    detail: str = "",
) -> DeliveryAuditEvent:
    """Append one delivery audit event; return the persisted ``DeliveryAuditEvent``.

    The event id is content-derived and timestamp-independent, so identical
    inputs produce the same id (the append is idempotent at the id level; the
    log still preserves every append as a separate line).
    """
    _require_allowed("event_type", event_type, ALLOWED_DELIVERY_EVENT_TYPES)
    _ensure_local_path(audit_log_path)

    event_id = stable_delivery_event_id(
        event_type=event_type,
        package_id=package_id,
        approval_request_id=approval_request_id,
        packet_id=packet_id,
        artifact_sha256=artifact_sha256,
        operator_id=operator_id,
        resulting_state=resulting_state,
    )
    event = DeliveryAuditEvent(
        schema_version=DELIVERY_AUDIT_SCHEMA_VERSION,
        event_id=event_id,
        event_type=event_type,
        package_id=package_id,
        approval_request_id=approval_request_id,
        packet_id=packet_id,
        artifact_sha256=artifact_sha256,
        resulting_state=resulting_state,
        operator_id=operator_id,
        recorded_at=recorded_at,
        automation_allowed=False,
        detail=detail,
    )
    target = _ensure_local_path(audit_log_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(_jsonl_line(event.to_dict()) + "\n")
    return event


def read_delivery_events(*, audit_log_path: Any) -> tuple[DeliveryAuditEvent, ...]:
    """Read every delivery audit event in append order (blank lines skipped)."""
    target = _ensure_local_path(audit_log_path)
    if not target.is_file():
        return ()
    events: list[DeliveryAuditEvent] = []
    text = target.read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError("INVALID_DELIVERY_AUDIT_LINE: not valid JSON")
        if not isinstance(payload, dict):
            raise ValueError("INVALID_DELIVERY_AUDIT_LINE: not a JSON object")
        events.append(
            DeliveryAuditEvent(
                schema_version=payload.get("schema_version", ""),
                event_id=payload.get("event_id", ""),
                event_type=payload.get("event_type", ""),
                package_id=payload.get("package_id", ""),
                approval_request_id=payload.get("approval_request_id", ""),
                packet_id=payload.get("packet_id"),
                artifact_sha256=payload.get("artifact_sha256", ""),
                resulting_state=payload.get("resulting_state", ""),
                operator_id=payload.get("operator_id"),
                recorded_at=payload.get("recorded_at", ""),
                automation_allowed=bool(payload.get("automation_allowed", False)),
                detail=payload.get("detail", ""),
            )
        )
    return tuple(events)


def compute_line_hash(audit_log_path: Any) -> str:
    """SHA-256 of the entire append-only log (tamper-evidence helper)."""
    target = _ensure_local_path(audit_log_path)
    h = hashlib.sha256()
    if target.is_file():
        h.update(target.read_bytes())
    return h.hexdigest()
