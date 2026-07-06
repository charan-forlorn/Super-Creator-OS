"""Stage 6.4 tests: event_stream_builder deterministic snapshot assembly."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scos.control_center.event_stream_builder import (
    EventStreamBuilderError,
    build_event_stream_snapshot,
)
from scos.control_center.event_stream_models import EventStreamRecord


def _record(event_id: str, sequence: int, **overrides) -> EventStreamRecord:
    fields = dict(
        event_id=event_id,
        sequence=sequence,
        event_type="COMMAND_CREATED",
        source="control_center",
        entity_type="command",
        entity_id=f"cmd_{sequence}",
        status="queued",
        occurred_at="2026-07-07T00:00:00Z",
        payload={},
        evidence_refs=(),
    )
    fields.update(overrides)
    return EventStreamRecord.of(**fields)


def test_snapshot_orders_by_sequence_then_event_id():
    records = [
        _record("evt_b", 1),
        _record("evt_a", 1),
        _record("evt_c", 0),
    ]
    snapshot = build_event_stream_snapshot(records, generated_at="2026-07-07T00:00:00Z")
    ordered_ids = [event.event_id for event in snapshot.events]
    assert ordered_ids == ["evt_c", "evt_a", "evt_b"]


def test_snapshot_is_deterministic_for_same_input():
    records = [_record("evt_1", 1), _record("evt_2", 2)]
    a = build_event_stream_snapshot(records, generated_at="t1", cursor="evt_2")
    b = build_event_stream_snapshot(list(reversed(records)), generated_at="t1", cursor="evt_2")
    assert a.snapshot_id == b.snapshot_id
    assert a.to_dict() == b.to_dict()


def test_snapshot_rejects_duplicate_sequence_event_id_pair():
    records = [_record("evt_1", 1), _record("evt_1", 1)]
    with pytest.raises(EventStreamBuilderError):
        build_event_stream_snapshot(records, generated_at="t1")


def test_snapshot_allows_same_event_id_different_sequence():
    records = [_record("evt_1", 1), _record("evt_1", 2)]
    snapshot = build_event_stream_snapshot(records, generated_at="t1")
    assert snapshot.event_count == 2


def test_snapshot_rejects_non_record_entries():
    with pytest.raises(EventStreamBuilderError):
        build_event_stream_snapshot([{"not": "a record"}], generated_at="t1")


def test_snapshot_requires_generated_at():
    with pytest.raises(EventStreamBuilderError):
        build_event_stream_snapshot([], generated_at="")


def test_snapshot_status_and_source_counts():
    records = [
        _record("evt_1", 1, status="queued", source="control_center"),
        _record("evt_2", 2, status="completed", source="control_center"),
        _record("evt_3", 3, status="completed", source="operator"),
    ]
    snapshot = build_event_stream_snapshot(records, generated_at="t1")
    assert snapshot.status_counts == {"queued": 1, "completed": 2}
    assert snapshot.source_counts == {"control_center": 2, "operator": 1}


def test_empty_snapshot_has_warning_and_default_cursor():
    snapshot = build_event_stream_snapshot([], generated_at="t1")
    assert snapshot.event_count == 0
    assert snapshot.cursor == "cursor-empty"
    assert "no_local_events_available" in snapshot.warnings


def test_snapshot_never_reads_clock_or_random(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("clock/random must never be used")

    monkeypatch.setattr("time.time", _boom)
    monkeypatch.setattr("random.random", _boom)
    records = [_record("evt_1", 1)]
    snapshot = build_event_stream_snapshot(records, generated_at="t1")
    assert snapshot.event_count == 1
