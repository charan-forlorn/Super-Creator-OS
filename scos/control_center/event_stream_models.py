"""SCOS Stage 6.4 local event stream & UI state sync data models.

Immutable dataclasses describing a deterministic, local-only event stream
projection (``EventStreamRecord`` / ``EventStreamSnapshot``) and a UI state
sync summary (``UIStateSyncSnapshot``) derived from the Stage 6.3 durable
SQLite WAL state store. This module defines shapes only -- it never opens a
database connection, a socket, a clock, or a network endpoint.

Reuses the Stage 5.5 ``FrozenMap`` immutable string mapping (which already
rejects secret-bearing metadata keys and URL values at construction time)
for the event payload field, satisfying the "reject URL paths / non-local
references" and "freeze mutable payload structures" builder requirements.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no server, no WebSocket, no SSE, no polling, no timers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

try:
    from .operator_packet_review_models import FrozenMap
except ImportError:  # direct-module execution (tests insert the package dir)
    from operator_packet_review_models import FrozenMap

EVENT_STREAM_SCHEMA_VERSION = 1
UI_STATE_SYNC_SCHEMA_VERSION = 1

ALLOWED_EVENT_TYPES = (
    "COMMAND_CREATED",
    "COMMAND_APPROVED",
    "COMMAND_REJECTED",
    "COMMAND_COMPLETED",
    "COMMAND_BLOCKED",
    "SESSION_CREATED",
    "SESSION_UPDATED",
    "RESULT_READY",
    "APPROVAL_REQUIRED",
    "STATE_SNAPSHOT_CREATED",
    "BACKEND_HEALTH_CHANGED",
    "DURABLE_STATE_CHANGED",
    "UI_SYNC_READY",
)

ALLOWED_EVENT_STATUSES = (
    "queued",
    "working",
    "ready",
    "blocked",
    "approved",
    "rejected",
    "completed",
    "failed",
    "stale",
    "unknown",
)


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(
            f"{field_name} must be one of {list(allowed)}, got {value!r}"
        )


def _require_nonempty(field_name: str, value: str) -> None:
    if not str(value).strip():
        raise ValueError(f"{field_name} must not be empty")


def _frozen_map(value: Any = None) -> FrozenMap:
    if isinstance(value, FrozenMap):
        return value
    return FrozenMap.of(value)


def _str_tuple(field_name: str, value: Any) -> tuple[str, ...]:
    items = tuple(value or ())
    for item in items:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} entries must be str, got {item!r}")
    return items


def _int_mapping(field_name: str, value: Any) -> Mapping[str, int]:
    items = dict(value or {})
    normalized: dict[str, int] = {}
    for key, count in items.items():
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be str, got {key!r}")
        normalized[key] = int(count)
    return dict(sorted(normalized.items()))


@dataclass(frozen=True)
class EventStreamRecord:
    """One deterministic, local-only projected event."""

    event_id: str
    sequence: int
    event_type: str
    source: str
    entity_type: str
    entity_id: str
    status: str
    occurred_at: str
    payload: FrozenMap
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", str(self.event_id))
        object.__setattr__(self, "sequence", int(self.sequence))
        object.__setattr__(self, "event_type", str(self.event_type))
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "entity_type", str(self.entity_type))
        object.__setattr__(self, "entity_id", str(self.entity_id))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "occurred_at", str(self.occurred_at))
        object.__setattr__(self, "payload", _frozen_map(self.payload))
        object.__setattr__(
            self, "evidence_refs", _str_tuple("evidence_refs", self.evidence_refs)
        )
        _require_nonempty("event_id", self.event_id)
        _require_nonempty("source", self.source)
        _require_nonempty("entity_type", self.entity_type)
        _require_nonempty("entity_id", self.entity_id)
        _require_nonempty("occurred_at", self.occurred_at)
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        _require_allowed("event_type", self.event_type, ALLOWED_EVENT_TYPES)
        _require_allowed("status", self.status, ALLOWED_EVENT_STATUSES)
        for ref in self.evidence_refs:
            if "://" in ref or ref.startswith("//"):
                raise ValueError(
                    f"evidence_refs must not contain URL references (found {ref!r})"
                )

    @staticmethod
    def of(
        event_id: str,
        sequence: int,
        event_type: str,
        source: str,
        entity_type: str,
        entity_id: str,
        status: str,
        occurred_at: str,
        *,
        payload: Any = None,
        evidence_refs: Any = (),
    ) -> "EventStreamRecord":
        return EventStreamRecord(
            event_id=event_id,
            sequence=sequence,
            event_type=event_type,
            source=source,
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            occurred_at=occurred_at,
            payload=_frozen_map(payload),
            evidence_refs=_str_tuple("evidence_refs", evidence_refs),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "source": self.source,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "status": self.status,
            "occurred_at": self.occurred_at,
            "payload": self.payload.to_dict(),
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class EventStreamSnapshot:
    """A deterministic, cursor-based batch of local event stream records."""

    schema_version: int
    snapshot_id: str
    generated_at: str
    cursor: str
    event_count: int
    events: tuple[EventStreamRecord, ...]
    status_counts: Mapping[str, int]
    source_counts: Mapping[str, int]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "snapshot_id", str(self.snapshot_id))
        object.__setattr__(self, "generated_at", str(self.generated_at))
        object.__setattr__(self, "cursor", str(self.cursor))
        object.__setattr__(self, "event_count", int(self.event_count))
        events = tuple(self.events or ())
        for event in events:
            if not isinstance(event, EventStreamRecord):
                raise ValueError("events entries must be EventStreamRecord instances")
        object.__setattr__(self, "events", events)
        object.__setattr__(
            self, "status_counts", _int_mapping("status_counts", self.status_counts)
        )
        object.__setattr__(
            self, "source_counts", _int_mapping("source_counts", self.source_counts)
        )
        object.__setattr__(self, "warnings", _str_tuple("warnings", self.warnings))
        _require_nonempty("snapshot_id", self.snapshot_id)
        _require_nonempty("generated_at", self.generated_at)
        _require_nonempty("cursor", self.cursor)
        if self.event_count != len(self.events):
            raise ValueError(
                "event_count must equal len(events) "
                f"({self.event_count} != {len(self.events)})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "generated_at": self.generated_at,
            "cursor": self.cursor,
            "event_count": self.event_count,
            "events": [event.to_dict() for event in self.events],
            "status_counts": dict(self.status_counts),
            "source_counts": dict(self.source_counts),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class UIStateSyncSnapshot:
    """A deterministic UI state sync summary derived from local state only."""

    schema_version: int
    sync_id: str
    generated_at: str
    state_source: str
    sync_status: str
    active_stage: str
    active_task: str
    backend_status: str
    durable_state_status: str
    latest_event_id: str
    latest_event_sequence: int
    pending_operator_actions: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "sync_id", str(self.sync_id))
        object.__setattr__(self, "generated_at", str(self.generated_at))
        object.__setattr__(self, "state_source", str(self.state_source))
        object.__setattr__(self, "sync_status", str(self.sync_status))
        object.__setattr__(self, "active_stage", str(self.active_stage))
        object.__setattr__(self, "active_task", str(self.active_task))
        object.__setattr__(self, "backend_status", str(self.backend_status))
        object.__setattr__(
            self, "durable_state_status", str(self.durable_state_status)
        )
        object.__setattr__(self, "latest_event_id", str(self.latest_event_id))
        object.__setattr__(
            self, "latest_event_sequence", int(self.latest_event_sequence)
        )
        object.__setattr__(
            self,
            "pending_operator_actions",
            _str_tuple("pending_operator_actions", self.pending_operator_actions),
        )
        object.__setattr__(self, "blockers", _str_tuple("blockers", self.blockers))
        object.__setattr__(self, "warnings", _str_tuple("warnings", self.warnings))
        _require_nonempty("sync_id", self.sync_id)
        _require_nonempty("generated_at", self.generated_at)
        _require_nonempty("state_source", self.state_source)
        _require_allowed("sync_status", self.sync_status, ALLOWED_EVENT_STATUSES)
        _require_allowed("backend_status", self.backend_status, ALLOWED_EVENT_STATUSES)
        _require_allowed(
            "durable_state_status", self.durable_state_status, ALLOWED_EVENT_STATUSES
        )
        if self.latest_event_sequence < 0:
            raise ValueError("latest_event_sequence must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sync_id": self.sync_id,
            "generated_at": self.generated_at,
            "state_source": self.state_source,
            "sync_status": self.sync_status,
            "active_stage": self.active_stage,
            "active_task": self.active_task,
            "backend_status": self.backend_status,
            "durable_state_status": self.durable_state_status,
            "latest_event_id": self.latest_event_id,
            "latest_event_sequence": self.latest_event_sequence,
            "pending_operator_actions": list(self.pending_operator_actions),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }
