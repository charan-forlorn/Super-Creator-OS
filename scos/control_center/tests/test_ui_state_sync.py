"""Stage 6.4 tests: UI state sync snapshot builder."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scos.control_center.event_stream_builder import build_event_stream_snapshot
from scos.control_center.event_stream_models import EventStreamRecord
from scos.control_center.ui_state_sync import (
    UIStateSyncBuilderError,
    build_ui_state_sync_snapshot,
)

_READY_STATE = {
    "checked_at": "2026-07-07T00:00:00Z",
    "db_mode": "wal",
    "wal_enabled": True,
}

_NOT_READY_STATE = {
    "checked_at": "2026-07-07T00:00:00Z",
    "db_mode": None,
    "wal_enabled": False,
}


def _record(event_id: str, sequence: int) -> EventStreamRecord:
    return EventStreamRecord.of(
        event_id=event_id,
        sequence=sequence,
        event_type="UI_SYNC_READY",
        source="control_center",
        entity_type="ui",
        entity_id="panel_1",
        status="ready",
        occurred_at="2026-07-07T00:00:00Z",
    )


def test_build_ui_state_sync_snapshot_ready():
    event_snapshot = build_event_stream_snapshot(
        [_record("evt_1", 1)], generated_at="2026-07-07T00:00:00Z"
    )
    snapshot = build_ui_state_sync_snapshot(
        _READY_STATE,
        event_snapshot,
        generated_at="2026-07-07T00:01:00Z",
        active_stage="6.4",
        active_task="event_stream_foundation",
    )
    assert snapshot.sync_status == "ready"
    assert snapshot.backend_status == "ready"
    assert snapshot.durable_state_status == "ready"
    assert snapshot.latest_event_id == "evt_1"
    assert snapshot.latest_event_sequence == 1
    assert snapshot.blockers == ()


def test_build_ui_state_sync_snapshot_blocked_when_state_not_ready():
    event_snapshot = build_event_stream_snapshot([], generated_at="t1")
    snapshot = build_ui_state_sync_snapshot(
        _NOT_READY_STATE,
        event_snapshot,
        generated_at="t2",
        active_stage="6.4",
        active_task="event_stream_foundation",
    )
    assert snapshot.sync_status == "blocked"
    assert "durable_state_store_not_ready" in snapshot.blockers


def test_build_ui_state_sync_snapshot_stale_detection_no_clock():
    event_snapshot = build_event_stream_snapshot([], generated_at="t1")
    snapshot = build_ui_state_sync_snapshot(
        _READY_STATE,
        event_snapshot,
        generated_at="t2",
        active_stage="6.4",
        active_task="event_stream_foundation",
        stale_if_state_checked_before="2026-07-08T00:00:00Z",
    )
    assert snapshot.sync_status == "stale"
    assert "durable_state_snapshot_older_than_expected" in snapshot.warnings


def test_build_ui_state_sync_snapshot_propagates_warnings_from_events():
    event_snapshot = build_event_stream_snapshot([], generated_at="t1")
    snapshot = build_ui_state_sync_snapshot(
        _READY_STATE,
        event_snapshot,
        generated_at="t2",
        active_stage="6.4",
        active_task="event_stream_foundation",
    )
    assert "no_local_events_available" in snapshot.warnings


def test_build_ui_state_sync_snapshot_deterministic_id():
    event_snapshot = build_event_stream_snapshot(
        [_record("evt_1", 1)], generated_at="t1"
    )
    a = build_ui_state_sync_snapshot(
        _READY_STATE, event_snapshot, generated_at="t2",
        active_stage="6.4", active_task="task",
    )
    b = build_ui_state_sync_snapshot(
        _READY_STATE, event_snapshot, generated_at="t2",
        active_stage="6.4", active_task="task",
    )
    assert a.sync_id == b.sync_id


def test_build_ui_state_sync_snapshot_rejects_non_event_snapshot():
    with pytest.raises(UIStateSyncBuilderError):
        build_ui_state_sync_snapshot(
            _READY_STATE, {"not": "a snapshot"}, generated_at="t2",
            active_stage="6.4", active_task="task",
        )


def test_build_ui_state_sync_snapshot_requires_generated_at():
    event_snapshot = build_event_stream_snapshot([], generated_at="t1")
    with pytest.raises(UIStateSyncBuilderError):
        build_ui_state_sync_snapshot(
            _READY_STATE, event_snapshot, generated_at="",
            active_stage="6.4", active_task="task",
        )


def test_build_ui_state_sync_snapshot_never_reads_clock_or_random(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("clock/random must never be used")

    monkeypatch.setattr("time.time", _boom)
    monkeypatch.setattr("random.random", _boom)
    event_snapshot = build_event_stream_snapshot([], generated_at="t1")
    build_ui_state_sync_snapshot(
        _READY_STATE, event_snapshot, generated_at="t2",
        active_stage="6.4", active_task="task",
    )
