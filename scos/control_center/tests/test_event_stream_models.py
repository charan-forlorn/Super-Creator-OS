"""Stage 6.4 tests: event_stream_models immutability and validation."""

from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scos.control_center.event_stream_models import (
    ALLOWED_EVENT_STATUSES,
    ALLOWED_EVENT_TYPES,
    EVENT_STREAM_SCHEMA_VERSION,
    UI_STATE_SYNC_SCHEMA_VERSION,
    EventStreamRecord,
    EventStreamSnapshot,
    UIStateSyncSnapshot,
)


def _record(**overrides) -> EventStreamRecord:
    fields = dict(
        event_id="evt_1",
        sequence=1,
        event_type="COMMAND_CREATED",
        source="control_center",
        entity_type="command",
        entity_id="cmd_1",
        status="queued",
        occurred_at="2026-07-07T00:00:00Z",
        payload={"note": "ok"},
        evidence_refs=("local-ref-1",),
    )
    fields.update(overrides)
    return EventStreamRecord.of(**fields)


def test_event_record_immutable():
    record = _record()
    with pytest.raises(FrozenInstanceError):
        record.event_id = "changed"  # type: ignore[misc]


def test_event_record_rejects_unsupported_event_type():
    with pytest.raises(ValueError):
        _record(event_type="NOT_A_REAL_TYPE")


def test_event_record_rejects_unsupported_status():
    with pytest.raises(ValueError):
        _record(status="not_a_real_status")


def test_event_record_rejects_url_evidence_ref():
    with pytest.raises(ValueError):
        _record(evidence_refs=("https://example.com/evidence",))


def test_event_record_rejects_url_payload_value():
    with pytest.raises(ValueError):
        _record(payload={"link": "https://example.com"})


def test_event_record_payload_is_frozen_mapping():
    record = _record(payload={"b": "2", "a": "1"})
    assert record.payload.to_dict() == {"a": "1", "b": "2"}
    with pytest.raises(TypeError):
        record.payload["c"] = "3"  # type: ignore[index]


def test_all_event_types_and_statuses_constructible():
    for event_type in ALLOWED_EVENT_TYPES:
        for status in ALLOWED_EVENT_STATUSES:
            _record(event_type=event_type, status=status)


def test_event_stream_snapshot_immutable_and_consistent():
    events = (_record(event_id="evt_1", sequence=1), _record(event_id="evt_2", sequence=2))
    snapshot = EventStreamSnapshot(
        schema_version=EVENT_STREAM_SCHEMA_VERSION,
        snapshot_id="snap_1",
        generated_at="2026-07-07T00:00:00Z",
        cursor="evt_2",
        event_count=2,
        events=events,
        status_counts={"queued": 2},
        source_counts={"control_center": 2},
        warnings=(),
    )
    assert snapshot.event_count == 2
    with pytest.raises(FrozenInstanceError):
        snapshot.snapshot_id = "changed"  # type: ignore[misc]


def test_event_stream_snapshot_rejects_count_mismatch():
    with pytest.raises(ValueError):
        EventStreamSnapshot(
            schema_version=EVENT_STREAM_SCHEMA_VERSION,
            snapshot_id="snap_1",
            generated_at="2026-07-07T00:00:00Z",
            cursor="evt_1",
            event_count=5,
            events=(_record(),),
            status_counts={},
            source_counts={},
            warnings=(),
        )


def test_ui_state_sync_snapshot_immutable_and_valid():
    snapshot = UIStateSyncSnapshot(
        schema_version=UI_STATE_SYNC_SCHEMA_VERSION,
        sync_id="sync_1",
        generated_at="2026-07-07T00:00:00Z",
        state_source="scos.control_center.state_snapshot",
        sync_status="ready",
        active_stage="6.4",
        active_task="event_stream_foundation",
        backend_status="ready",
        durable_state_status="ready",
        latest_event_id="evt_2",
        latest_event_sequence=2,
        pending_operator_actions=(),
        blockers=(),
        warnings=(),
    )
    assert snapshot.sync_status == "ready"
    with pytest.raises(FrozenInstanceError):
        snapshot.sync_status = "blocked"  # type: ignore[misc]


def test_ui_state_sync_snapshot_rejects_bad_status():
    with pytest.raises(ValueError):
        UIStateSyncSnapshot(
            schema_version=UI_STATE_SYNC_SCHEMA_VERSION,
            sync_id="sync_1",
            generated_at="2026-07-07T00:00:00Z",
            state_source="scos.control_center.state_snapshot",
            sync_status="not_a_status",
            active_stage="6.4",
            active_task="event_stream_foundation",
            backend_status="ready",
            durable_state_status="ready",
            latest_event_id="",
            latest_event_sequence=0,
            pending_operator_actions=(),
            blockers=(),
            warnings=(),
        )
