"""Stage 6.4 tests: projecting Stage 6.3 durable events into event snapshots."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scos.control_center.event_stream_snapshot import (
    build_event_stream_snapshot_from_durable_events,
    project_durable_event,
)
from scos.control_center.state_models import DurableEventRecord


def _durable_event(
    event_id: str,
    sequence: int,
    *,
    event_type: str = "command_created",
    status: str = "queued",
) -> DurableEventRecord:
    return DurableEventRecord.of(
        event_id=event_id,
        event_type=event_type,
        source="control_center",
        subject_type="command",
        subject_id=f"cmd_{sequence}",
        created_at="2026-07-07T00:00:00Z",
        sequence=sequence,
        metadata={"status": status},
    )


def test_project_durable_event_maps_known_type_and_status():
    durable = _durable_event("evt_1", 1)
    projected = project_durable_event(durable)
    assert projected is not None
    assert projected.event_type == "COMMAND_CREATED"
    assert projected.status == "queued"
    assert projected.entity_type == "command"
    assert projected.entity_id == "cmd_1"


def test_project_durable_event_skips_unmappable_type():
    durable = _durable_event("evt_1", 1, event_type="totally_unknown_thing")
    assert project_durable_event(durable) is None


def test_project_durable_event_maps_status_aliases():
    durable = _durable_event("evt_1", 1, status="in_progress")
    projected = project_durable_event(durable)
    assert projected is not None
    assert projected.status == "working"


def test_build_snapshot_from_durable_events_skips_and_warns():
    events = [
        _durable_event("evt_1", 1),
        _durable_event("evt_2", 2, event_type="unmappable"),
    ]
    snapshot = build_event_stream_snapshot_from_durable_events(
        events, generated_at="2026-07-07T00:00:00Z"
    )
    assert snapshot.event_count == 1
    assert any(w.startswith("skipped_unsupported_event:evt_2") for w in snapshot.warnings)


def test_build_snapshot_from_durable_events_deterministic_ordering():
    events = [
        _durable_event("evt_b", 2),
        _durable_event("evt_a", 1),
    ]
    snapshot = build_event_stream_snapshot_from_durable_events(
        events, generated_at="2026-07-07T00:00:00Z"
    )
    assert [e.event_id for e in snapshot.events] == ["evt_a", "evt_b"]


def test_build_snapshot_from_durable_events_no_mutation_of_source(monkeypatch):
    events = [_durable_event("evt_1", 1)]
    before = events[0].to_dict()
    build_event_stream_snapshot_from_durable_events(events, generated_at="t1")
    assert events[0].to_dict() == before
