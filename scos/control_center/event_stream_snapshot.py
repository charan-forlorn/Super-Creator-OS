"""SCOS Stage 6.4 event stream snapshot projection from Stage 6.3 durable state.

Connects the Stage 6.3 durable SQLite WAL state store to the Stage 6.4
event stream builder:

    SQLiteStateStore -> StateRepository/list_events() -> DurableEventRecord
        -> project_durable_event() -> EventStreamRecord
        -> build_event_stream_snapshot() -> EventStreamSnapshot

This module only reads already-durable local records and projects their
shape; it never mutates Stage 6.3 tables, opens a socket, reads a clock, or
starts a live transport of any kind.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no server, no WebSocket, no SSE, no polling.
"""

from __future__ import annotations

from typing import Iterable

try:
    from .event_stream_builder import build_event_stream_snapshot
    from .event_stream_models import (
        ALLOWED_EVENT_STATUSES,
        ALLOWED_EVENT_TYPES,
        EventStreamRecord,
        EventStreamSnapshot,
    )
    from .state_models import DurableEventRecord
except ImportError:  # direct-module execution (tests insert the package dir)
    from event_stream_builder import build_event_stream_snapshot
    from event_stream_models import (
        ALLOWED_EVENT_STATUSES,
        ALLOWED_EVENT_TYPES,
        EventStreamRecord,
        EventStreamSnapshot,
    )
    from state_models import DurableEventRecord

_STATUS_ALIASES = {
    "in_progress": "working",
    "success": "completed",
    "error": "failed",
    "pending": "queued",
}


def _normalize_event_type(raw: str) -> str | None:
    candidate = str(raw).strip().upper()
    return candidate if candidate in ALLOWED_EVENT_TYPES else None


def _normalize_status(raw: str) -> str | None:
    candidate = str(raw).strip().lower()
    candidate = _STATUS_ALIASES.get(candidate, candidate)
    return candidate if candidate in ALLOWED_EVENT_STATUSES else None


def project_durable_event(record: DurableEventRecord) -> EventStreamRecord | None:
    """Project one Stage 6.3 ``DurableEventRecord`` into an ``EventStreamRecord``.

    Returns ``None`` if the raw record's event_type/status cannot be mapped
    onto the Stage 6.4 supported vocabulary -- the caller is expected to
    surface a warning for skipped records rather than fail the whole batch,
    since Stage 6.3 durable events were written under a looser vocabulary.
    """
    if not isinstance(record, DurableEventRecord):
        raise ValueError("record must be a DurableEventRecord")

    event_type = _normalize_event_type(record.event_type)
    status_source = record.metadata.to_dict().get("status", "unknown")
    status = _normalize_status(status_source)
    if event_type is None or status is None:
        return None

    return EventStreamRecord.of(
        event_id=record.event_id,
        sequence=record.sequence,
        event_type=event_type,
        source=record.source,
        entity_type=record.subject_type,
        entity_id=record.subject_id,
        status=status,
        occurred_at=record.created_at,
        payload=record.metadata.to_dict(),
        evidence_refs=(),
    )


def build_event_stream_snapshot_from_durable_events(
    durable_events: Iterable[DurableEventRecord],
    *,
    generated_at: str,
    cursor: str | None = None,
) -> EventStreamSnapshot:
    """Project a batch of Stage 6.3 durable events into a Stage 6.4 snapshot.

    Records whose event_type/status cannot be mapped onto the supported
    Stage 6.4 vocabulary are skipped (not raised) and reflected in the
    resulting snapshot's ``warnings`` tuple, since Stage 6.3 does not itself
    constrain event_type/status to the Stage 6.4 vocabulary.
    """
    projected: list[EventStreamRecord] = []
    skipped: list[str] = []
    for record in durable_events:
        projected_record = project_durable_event(record)
        if projected_record is None:
            skipped.append(record.event_id if isinstance(record, DurableEventRecord) else "unknown")
            continue
        projected.append(projected_record)

    snapshot = build_event_stream_snapshot(
        projected, generated_at=generated_at, cursor=cursor
    )

    if skipped:
        extra_warnings = tuple(
            f"skipped_unsupported_event:{event_id}" for event_id in skipped
        )
        snapshot = EventStreamSnapshot(
            schema_version=snapshot.schema_version,
            snapshot_id=snapshot.snapshot_id,
            generated_at=snapshot.generated_at,
            cursor=snapshot.cursor,
            event_count=snapshot.event_count,
            events=snapshot.events,
            status_counts=snapshot.status_counts,
            source_counts=snapshot.source_counts,
            warnings=snapshot.warnings + extra_warnings,
        )

    return snapshot
