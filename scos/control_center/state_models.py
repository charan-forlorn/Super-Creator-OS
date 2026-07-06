"""SCOS Stage 6.3 durable Control Center state models.

Immutable dataclasses describing the first durable local state records for
the Control Center: commands, sessions, events, approvals, and results. These
records are persisted by ``sqlite_state_store`` (SQLite + WAL) and read back
by ``state_repository``/``state_snapshot``. This module defines shapes only —
it never opens a database connection, a socket, or a clock.

Reuses the Stage 5.5 ``FrozenMap`` immutable string mapping (which already
rejects secret-bearing metadata keys and URL values at construction time)
rather than redefining one.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no server.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .operator_packet_review_models import FrozenMap
except ImportError:  # direct-module execution (tests insert the package dir)
    from operator_packet_review_models import FrozenMap

CONTROL_CENTER_STATE_SCHEMA_VERSION = 1

ALLOWED_COMMAND_STATUSES = (
    "draft",
    "validated",
    "approval_required",
    "approved",
    "rejected",
    "dry_run_enqueued",
    "completed",
    "failed",
    "blocked",
)

ALLOWED_SESSION_STATUSES = (
    "planned",
    "queued",
    "working",
    "waiting_for_operator",
    "result_ready",
    "reviewing",
    "completed",
    "blocked",
    "failed",
)

ALLOWED_APPROVAL_DECISIONS = (
    "pending",
    "approved",
    "rejected",
    "needs_review",
    "blocked",
)

ALLOWED_RESULT_VERDICTS = (
    "pass",
    "fail",
    "blocked",
    "needs_fix",
    "warning",
    "info",
)

ALLOWED_STATE_ERROR_KINDS = (
    "not_found",
    "duplicate_id",
    "invalid_status",
    "invalid_decision",
    "invalid_verdict",
    "invalid_payload",
    "invalid_path",
    "schema_mismatch",
    "storage_unavailable",
)


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(
            f"{field_name} must be one of {list(allowed)}, got {value!r}"
        )


def _require_nonempty(field_name: str, value: str) -> None:
    if not str(value).strip():
        raise ValueError(f"{field_name} must not be empty")


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _frozen_map(value: Any = None) -> FrozenMap:
    if isinstance(value, FrozenMap):
        return value
    return FrozenMap.of(value)


@dataclass(frozen=True)
class StateRecordRef:
    """A lightweight reference to any durable state record."""

    record_id: str
    record_type: str
    created_at: str
    updated_at: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", str(self.record_id))
        object.__setattr__(self, "record_type", str(self.record_type))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "updated_at", _optional_str(self.updated_at))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_nonempty("record_id", self.record_id)
        _require_nonempty("record_type", self.record_type)
        _require_nonempty("created_at", self.created_at)

    @staticmethod
    def of(
        record_id: str,
        record_type: str,
        created_at: str,
        *,
        updated_at: str | None = None,
        metadata: Any = None,
    ) -> "StateRecordRef":
        return StateRecordRef(
            record_id=record_id,
            record_type=record_type,
            created_at=created_at,
            updated_at=updated_at,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "StateRecordRef":
        return StateRecordRef(
            record_id=data["record_id"],
            record_type=data["record_type"],
            created_at=data["created_at"],
            updated_at=data.get("updated_at"),
            metadata=_frozen_map(data.get("metadata")),
        )


@dataclass(frozen=True)
class DurableCommandRecord:
    """A durable snapshot of one Control Center command's lifecycle state."""

    command_id: str
    command_type: str
    status: str
    request_id: str | None
    session_id: str | None
    payload_json: str
    created_at: str
    updated_at: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", str(self.command_id))
        object.__setattr__(self, "command_type", str(self.command_type))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "request_id", _optional_str(self.request_id))
        object.__setattr__(self, "session_id", _optional_str(self.session_id))
        object.__setattr__(self, "payload_json", str(self.payload_json))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "updated_at", _optional_str(self.updated_at))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_nonempty("command_id", self.command_id)
        _require_nonempty("command_type", self.command_type)
        _require_nonempty("created_at", self.created_at)
        _require_allowed("status", self.status, ALLOWED_COMMAND_STATUSES)

    @staticmethod
    def of(
        command_id: str,
        command_type: str,
        status: str,
        created_at: str,
        *,
        request_id: str | None = None,
        session_id: str | None = None,
        payload_json: str = "{}",
        updated_at: str | None = None,
        metadata: Any = None,
    ) -> "DurableCommandRecord":
        return DurableCommandRecord(
            command_id=command_id,
            command_type=command_type,
            status=status,
            request_id=request_id,
            session_id=session_id,
            payload_json=payload_json,
            created_at=created_at,
            updated_at=updated_at,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type,
            "status": self.status,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "payload_json": self.payload_json,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "DurableCommandRecord":
        return DurableCommandRecord(
            command_id=data["command_id"],
            command_type=data["command_type"],
            status=data["status"],
            request_id=data.get("request_id"),
            session_id=data.get("session_id"),
            payload_json=data.get("payload_json", "{}"),
            created_at=data["created_at"],
            updated_at=data.get("updated_at"),
            metadata=_frozen_map(data.get("metadata")),
        )


@dataclass(frozen=True)
class DurableSessionRecord:
    """A durable snapshot of one AI work session's lifecycle state."""

    session_id: str
    task_id: str | None
    agent_id: str | None
    runtime_id: str | None
    status: str
    created_at: str
    updated_at: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "task_id", _optional_str(self.task_id))
        object.__setattr__(self, "agent_id", _optional_str(self.agent_id))
        object.__setattr__(self, "runtime_id", _optional_str(self.runtime_id))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "updated_at", _optional_str(self.updated_at))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_nonempty("session_id", self.session_id)
        _require_nonempty("created_at", self.created_at)
        _require_allowed("status", self.status, ALLOWED_SESSION_STATUSES)

    @staticmethod
    def of(
        session_id: str,
        status: str,
        created_at: str,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        runtime_id: str | None = None,
        updated_at: str | None = None,
        metadata: Any = None,
    ) -> "DurableSessionRecord":
        return DurableSessionRecord(
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            runtime_id=runtime_id,
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "runtime_id": self.runtime_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "DurableSessionRecord":
        return DurableSessionRecord(
            session_id=data["session_id"],
            task_id=data.get("task_id"),
            agent_id=data.get("agent_id"),
            runtime_id=data.get("runtime_id"),
            status=data["status"],
            created_at=data["created_at"],
            updated_at=data.get("updated_at"),
            metadata=_frozen_map(data.get("metadata")),
        )


@dataclass(frozen=True)
class DurableEventRecord:
    """An append-only durable Control Center event."""

    event_id: str
    event_type: str
    source: str
    subject_type: str
    subject_id: str
    payload_json: str
    created_at: str
    sequence: int
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", str(self.event_id))
        object.__setattr__(self, "event_type", str(self.event_type))
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "subject_type", str(self.subject_type))
        object.__setattr__(self, "subject_id", str(self.subject_id))
        object.__setattr__(self, "payload_json", str(self.payload_json))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "sequence", int(self.sequence))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_nonempty("event_id", self.event_id)
        _require_nonempty("event_type", self.event_type)
        _require_nonempty("source", self.source)
        _require_nonempty("subject_type", self.subject_type)
        _require_nonempty("subject_id", self.subject_id)
        _require_nonempty("created_at", self.created_at)
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")

    @staticmethod
    def of(
        event_id: str,
        event_type: str,
        source: str,
        subject_type: str,
        subject_id: str,
        created_at: str,
        sequence: int,
        *,
        payload_json: str = "{}",
        metadata: Any = None,
    ) -> "DurableEventRecord":
        return DurableEventRecord(
            event_id=event_id,
            event_type=event_type,
            source=source,
            subject_type=subject_type,
            subject_id=subject_id,
            payload_json=payload_json,
            created_at=created_at,
            sequence=sequence,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "payload_json": self.payload_json,
            "created_at": self.created_at,
            "sequence": self.sequence,
            "metadata": self.metadata.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "DurableEventRecord":
        return DurableEventRecord(
            event_id=data["event_id"],
            event_type=data["event_type"],
            source=data["source"],
            subject_type=data["subject_type"],
            subject_id=data["subject_id"],
            payload_json=data.get("payload_json", "{}"),
            created_at=data["created_at"],
            sequence=int(data["sequence"]),
            metadata=_frozen_map(data.get("metadata")),
        )


@dataclass(frozen=True)
class DurableApprovalRecord:
    """A durable operator approval decision for some subject."""

    approval_id: str
    approval_type: str
    subject_type: str
    subject_id: str
    decision: str
    decided_by: str
    decided_at: str
    reason: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "approval_id", str(self.approval_id))
        object.__setattr__(self, "approval_type", str(self.approval_type))
        object.__setattr__(self, "subject_type", str(self.subject_type))
        object.__setattr__(self, "subject_id", str(self.subject_id))
        object.__setattr__(self, "decision", str(self.decision))
        object.__setattr__(self, "decided_by", str(self.decided_by))
        object.__setattr__(self, "decided_at", str(self.decided_at))
        object.__setattr__(self, "reason", _optional_str(self.reason))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_nonempty("approval_id", self.approval_id)
        _require_nonempty("subject_type", self.subject_type)
        _require_nonempty("subject_id", self.subject_id)
        _require_nonempty("decided_by", self.decided_by)
        _require_nonempty("decided_at", self.decided_at)
        _require_allowed("decision", self.decision, ALLOWED_APPROVAL_DECISIONS)

    @staticmethod
    def of(
        approval_id: str,
        approval_type: str,
        subject_type: str,
        subject_id: str,
        decision: str,
        decided_by: str,
        decided_at: str,
        *,
        reason: str | None = None,
        metadata: Any = None,
    ) -> "DurableApprovalRecord":
        return DurableApprovalRecord(
            approval_id=approval_id,
            approval_type=approval_type,
            subject_type=subject_type,
            subject_id=subject_id,
            decision=decision,
            decided_by=decided_by,
            decided_at=decided_at,
            reason=reason,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "approval_type": self.approval_type,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "decision": self.decision,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "reason": self.reason,
            "metadata": self.metadata.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "DurableApprovalRecord":
        return DurableApprovalRecord(
            approval_id=data["approval_id"],
            approval_type=data["approval_type"],
            subject_type=data["subject_type"],
            subject_id=data["subject_id"],
            decision=data["decision"],
            decided_by=data["decided_by"],
            decided_at=data["decided_at"],
            reason=data.get("reason"),
            metadata=_frozen_map(data.get("metadata")),
        )


@dataclass(frozen=True)
class DurableResultRecord:
    """A durable agent/verification result record for some subject."""

    result_id: str
    result_type: str
    subject_type: str
    subject_id: str
    verdict: str
    payload_json: str
    created_at: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "result_id", str(self.result_id))
        object.__setattr__(self, "result_type", str(self.result_type))
        object.__setattr__(self, "subject_type", str(self.subject_type))
        object.__setattr__(self, "subject_id", str(self.subject_id))
        object.__setattr__(self, "verdict", str(self.verdict))
        object.__setattr__(self, "payload_json", str(self.payload_json))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_nonempty("result_id", self.result_id)
        _require_nonempty("subject_type", self.subject_type)
        _require_nonempty("subject_id", self.subject_id)
        _require_nonempty("created_at", self.created_at)
        _require_allowed("verdict", self.verdict, ALLOWED_RESULT_VERDICTS)

    @staticmethod
    def of(
        result_id: str,
        result_type: str,
        subject_type: str,
        subject_id: str,
        verdict: str,
        created_at: str,
        *,
        payload_json: str = "{}",
        metadata: Any = None,
    ) -> "DurableResultRecord":
        return DurableResultRecord(
            result_id=result_id,
            result_type=result_type,
            subject_type=subject_type,
            subject_id=subject_id,
            verdict=verdict,
            payload_json=payload_json,
            created_at=created_at,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "result_type": self.result_type,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "verdict": self.verdict,
            "payload_json": self.payload_json,
            "created_at": self.created_at,
            "metadata": self.metadata.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "DurableResultRecord":
        return DurableResultRecord(
            result_id=data["result_id"],
            result_type=data["result_type"],
            subject_type=data["subject_type"],
            subject_id=data["subject_id"],
            verdict=data["verdict"],
            payload_json=data.get("payload_json", "{}"),
            created_at=data["created_at"],
            metadata=_frozen_map(data.get("metadata")),
        )


@dataclass(frozen=True)
class DurableStateError:
    """A deterministic durable-state failure, never a raw exception."""

    ok: bool
    error_kind: str
    error_detail: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_allowed("error_kind", self.error_kind, ALLOWED_STATE_ERROR_KINDS)

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        *,
        metadata: Any = None,
    ) -> "DurableStateError":
        return DurableStateError(
            ok=False,
            error_kind=error_kind,
            error_detail=error_detail,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "metadata": self.metadata.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "DurableStateError":
        return DurableStateError(
            ok=bool(data.get("ok", False)),
            error_kind=data["error_kind"],
            error_detail=data["error_detail"],
            metadata=_frozen_map(data.get("metadata")),
        )
