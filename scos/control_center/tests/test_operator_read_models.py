"""Stage 7.3 operator read model tests."""

from __future__ import annotations

import dataclasses

import pytest

from scos.control_center.operator_read_models import (
    OperatorActivityRecord,
    OperatorFreshnessStatus,
    OperatorHealthSignal,
    OperatorReadModelError,
    OperatorReadModelResult,
    OperatorReadModelSnapshot,
)

_NOW = "2026-07-09T00:00:00Z"


def test_operator_models_are_immutable_and_serialize_stably() -> None:
    freshness = OperatorFreshnessStatus(
        checked_at=_NOW,
        source_id="source-1",
        source_type="BACKEND_HEALTH",
        is_present=True,
        is_readable=True,
        is_stale=False,
        freshness_level="FRESH",
        warnings=("b", "a"),
    )
    signal = OperatorHealthSignal(
        signal_id="signal-1",
        signal_type="BACKEND_HEALTH",
        status="HEALTHY",
        severity="info",
        summary="healthy",
        source_stage="Stage 6.9",
        freshness=freshness,
        metadata=(("z", "2"), ("a", "1")),
    )
    activity = OperatorActivityRecord(
        activity_id="activity-1",
        activity_type="EVENT_ACTIVITY",
        status="HEALTHY",
        summary="event",
        source_stage="Stage 6.4",
        occurred_at=_NOW,
        references=("b", "a"),
        metadata=(("z", "2"), ("a", "1")),
    )
    snapshot = OperatorReadModelSnapshot(
        snapshot_id="snapshot-1",
        checked_at=_NOW,
        health_signals=(signal,),
        recent_activity=(activity,),
        readiness_score=100,
        go_no_go="GO",
        blockers=(),
        warnings=("warn-b", "warn-a"),
    )
    result = OperatorReadModelResult(
        accepted=True,
        go_no_go="GO",
        readiness_score=100,
        snapshot=snapshot,
        blockers=(),
        warnings=snapshot.warnings,
        checked_at=_NOW,
    )

    assert freshness.warnings == ("a", "b")
    assert signal.metadata == (("a", "1"), ("z", "2"))
    assert activity.references == ("a", "b")
    assert snapshot.warnings == ("warn-a", "warn-b")
    assert list(result.to_dict()) == [
        "accepted",
        "go_no_go",
        "readiness_score",
        "snapshot",
        "blockers",
        "warnings",
        "checked_at",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        signal.status = "BLOCKED"  # type: ignore[misc]


def test_operator_models_reject_unknown_allowed_values() -> None:
    freshness = OperatorFreshnessStatus(_NOW, "source-1", "BACKEND_HEALTH", True, True, False, "FRESH", ())
    with pytest.raises(ValueError):
        OperatorHealthSignal(
            signal_id="signal-1",
            signal_type="NOT_REAL",
            status="HEALTHY",
            severity="info",
            summary="bad",
            source_stage="Stage 7.3",
            freshness=freshness,
            metadata=(),
        )
    with pytest.raises(ValueError):
        OperatorFreshnessStatus(_NOW, "source-1", "BACKEND_HEALTH", True, True, False, "RECENT", ())


def test_operator_error_to_dict_is_deterministic() -> None:
    error = OperatorReadModelError.of(
        "INVALID_OPERATOR_READ_MODEL_INPUT",
        "bad",
        checked_at=_NOW,
        blockers=("b", "a"),
    )

    assert error.blockers == ("a", "b")
    assert list(error.to_dict()) == ["error_code", "message", "checked_at", "blockers"]
