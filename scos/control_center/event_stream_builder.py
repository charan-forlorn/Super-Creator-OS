"""SCOS Stage 6.4 deterministic event stream snapshot builder.

Builds an ``EventStreamSnapshot`` from explicit, caller-supplied local event
records (e.g. Stage 6.3 ``DurableEventRecord`` rows read back from the
SQLite WAL state store). Deterministic ordering, duplicate rejection,
unsupported-event-type rejection, and sha256-based snapshot IDs only.

Never opens a database connection, a socket, a clock, or a network endpoint.
No WebSocket, no SSE, no polling loop, no timer, no background thread.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no server.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

try:
    from .event_stream_models import (
        ALLOWED_EVENT_STATUSES,
        ALLOWED_EVENT_TYPES,
        EVENT_STREAM_SCHEMA_VERSION,
        EventStreamRecord,
        EventStreamSnapshot,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from event_stream_models import (
        ALLOWED_EVENT_STATUSES,
        ALLOWED_EVENT_TYPES,
        EVENT_STREAM_SCHEMA_VERSION,
        EventStreamRecord,
        EventStreamSnapshot,
    )


class EventStreamBuilderError(ValueError):
    """Raised when the supplied local event records cannot be projected."""


def _sha256_snapshot_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"evt-snap-{digest[:32]}"


def _sort_key(record: EventStreamRecord) -> tuple[int, str]:
    return (record.sequence, record.event_id)


def build_event_stream_snapshot(
    records: Iterable[EventStreamRecord],
    *,
    generated_at: str,
    cursor: str | None = None,
) -> EventStreamSnapshot:
    """Project explicit local ``EventStreamRecord`` rows into a snapshot.

    - Deterministic ordering by (sequence, event_id).
    - Rejects duplicate (sequence, event_id) pairs.
    - Rejects unsupported event types / statuses (delegated to the model's
      own validation, which is exercised again here defensively).
    - Never reads a clock or generates a random ID; ``generated_at`` and
      ``cursor`` must be supplied by the caller.
    """
    if not str(generated_at).strip():
        raise EventStreamBuilderError("generated_at must not be empty")

    all_records: list[EventStreamRecord] = []
    for record in records:
        if not isinstance(record, EventStreamRecord):
            raise EventStreamBuilderError(
                "records entries must be EventStreamRecord instances"
            )
        if record.event_type not in ALLOWED_EVENT_TYPES:
            raise EventStreamBuilderError(
                f"unsupported event_type {record.event_type!r}"
            )
        if record.status not in ALLOWED_EVENT_STATUSES:
            raise EventStreamBuilderError(f"unsupported status {record.status!r}")
        all_records.append(record)

    seen_pairs: set[tuple[int, str]] = set()
    for record in all_records:
        pair = (record.sequence, record.event_id)
        if pair in seen_pairs:
            raise EventStreamBuilderError(
                "duplicate (sequence, event_id) pair: "
                f"sequence={record.sequence} event_id={record.event_id!r}"
            )
        seen_pairs.add(pair)

    ordered = tuple(sorted(all_records, key=_sort_key))

    status_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for record in ordered:
        status_counts[record.status] = status_counts.get(record.status, 0) + 1
        source_counts[record.source] = source_counts.get(record.source, 0) + 1

    warnings: tuple[str, ...] = ()
    if not ordered:
        warnings = ("no_local_events_available",)

    resolved_cursor = cursor
    if resolved_cursor is None:
        resolved_cursor = ordered[-1].event_id if ordered else "cursor-empty"

    snapshot_id_parts = [generated_at, resolved_cursor] + [
        f"{record.sequence}:{record.event_id}" for record in ordered
    ]
    snapshot_id = _sha256_snapshot_id(*snapshot_id_parts)

    return EventStreamSnapshot(
        schema_version=EVENT_STREAM_SCHEMA_VERSION,
        snapshot_id=snapshot_id,
        generated_at=generated_at,
        cursor=resolved_cursor,
        event_count=len(ordered),
        events=ordered,
        status_counts=status_counts,
        source_counts=source_counts,
        warnings=warnings,
    )
