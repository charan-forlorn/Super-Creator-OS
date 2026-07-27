"""SCOS Cohort 10I — durable, append-only paid-pilot operational audit.

Each relevant transition records bounded data. The log is strictly append-only:
this module never deletes, truncates, or rewrites existing lines. Event IDs are
content-derived so identical inputs produce the same id (idempotent at the id
level; the log preserves every append as a separate line).

Do NOT store: raw stderr, secrets, tokens, environment values, absolute local
paths, full subprocess command lines, unrelated user data.

Stdlib-only. Deterministic. No clock/random/uuid.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

DELIVERY_AUDIT_SCHEMA_VERSION = "scos-hvs.paid-pilot-audit.v1/1.0.0"

ALLOWED_EVENT_TYPES = (
    "RIGHTS_REVIEWED",
    "QA_APPLIED",
    "DELIVERY_APPROVED",
    "PACKAGE_CREATED",
    "BACKUP_FINALIZED",
    "HANDOFF_READY",
    "RESTART_RECONSTRUCTED",
    "RESTORE_VERIFIED",
    "RESTORE_REJECTED",
    "CORRUPTION_REJECTED",
    "DUPLICATE_REPLAY",
    "CONFLICT_REJECTED",
    "READINESS_COMPUTED",
)

# Browser-safe reason codes (never raw exception text).
RC_OK = "AUDIT_OK"
RC_CORRUPT = "AUDIT_CORRUPT"
RC_UNREADABLE = "AUDIT_UNREADABLE"


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


def _stable_event_id(
    event_type: str,
    delivery_id: str,
    actor: str,
    transition: str,
    result: str,
) -> str:
    """Content-derived event id (timestamp-independent)."""
    canon = "|".join([event_type, delivery_id, actor, transition, result])
    return "scos-hvs-pp-audit-" + hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class PaidPilotAuditEvent:
    schema_version: str
    event_id: str
    event_type: str
    delivery_id: str
    actor: str
    transition: str
    previous_state: str
    new_state: str
    result: str
    correlation_key: str
    recorded_at: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "delivery_id": self.delivery_id,
            "actor": self.actor,
            "transition": self.transition,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "result": self.result,
            "correlation_key": self.correlation_key,
            "recorded_at": self.recorded_at,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PaidPilotAuditEvent":
        return cls(
            schema_version=str(d.get("schema_version", DELIVERY_AUDIT_SCHEMA_VERSION)),
            event_id=str(d.get("event_id", "")),
            event_type=str(d.get("event_type", "")),
            delivery_id=str(d.get("delivery_id", "")),
            actor=str(d.get("actor", "")),
            transition=str(d.get("transition", "")),
            previous_state=str(d.get("previous_state", "")),
            new_state=str(d.get("new_state", "")),
            result=str(d.get("result", "")),
            correlation_key=str(d.get("correlation_key", "")),
            recorded_at=str(d.get("recorded_at", "")),
            detail=str(d.get("detail", "")),
        )


def append_audit_event(
    *,
    audit_log_path: Any,
    event_type: str,
    delivery_id: str,
    actor: str,
    transition: str,
    previous_state: str,
    new_state: str,
    result: str,
    correlation_key: str,
    recorded_at: str,
    detail: str = "",
) -> PaidPilotAuditEvent:
    """Append one audit event; return the persisted event."""
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"INVALID_EVENT_TYPE: {event_type}")
    target = _ensure_local_path(audit_log_path)
    event_id = _stable_event_id(event_type, delivery_id, actor, transition, result)
    event = PaidPilotAuditEvent(
        schema_version=DELIVERY_AUDIT_SCHEMA_VERSION,
        event_id=event_id,
        event_type=event_type,
        delivery_id=delivery_id,
        actor=actor,
        transition=transition,
        previous_state=previous_state,
        new_state=new_state,
        result=result,
        correlation_key=correlation_key,
        recorded_at=recorded_at,
        detail=detail,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(_jsonl_line(event.to_dict()) + "\n")
    return event


def read_audit_events(*, audit_log_path: Any) -> tuple[PaidPilotAuditEvent, ...]:
    """Read every audit event in append order (blank lines skipped)."""
    target = _ensure_local_path(audit_log_path)
    if not target.is_file():
        return ()
    events: list[PaidPilotAuditEvent] = []
    text = target.read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError("INVALID_AUDIT_LINE: not valid JSON")
        if not isinstance(payload, dict):
            raise ValueError("INVALID_AUDIT_LINE: not a JSON object")
        events.append(PaidPilotAuditEvent.from_dict(payload))
    return tuple(events)


def compute_audit_hash(*, audit_log_path: Any) -> str:
    """SHA-256 of the entire append-only log (tamper-evidence helper)."""
    target = _ensure_local_path(audit_log_path)
    h = hashlib.sha256()
    if target.is_file():
        h.update(target.read_bytes())
    return h.hexdigest()


def verify_audit_integrity(*, audit_log_path: Any) -> tuple[bool, str]:
    """Read-only verification: log is valid JSONL with no corrupt lines."""
    target = _ensure_local_path(audit_log_path)
    if not target.is_file():
        return (True, "EMPTY")
    try:
        events = read_audit_events(audit_log_path=target)
        return (True, f"OK ({len(events)} events)")
    except ValueError as exc:
        return (False, str(exc))
