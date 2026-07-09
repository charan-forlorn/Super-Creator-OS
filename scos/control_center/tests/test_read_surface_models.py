"""Stage 7.1 read surface model tests."""

from __future__ import annotations

import dataclasses

import pytest

from scos.control_center.read_surface_models import (
    FrozenMap,
    ReadSurfaceError,
    ReadSurfaceQuery,
    ReadSurfaceRecord,
    ReadSurfaceReference,
    ReadSurfaceResult,
    ReadSurfaceSnapshot,
)


def test_reference_and_query_to_dict_are_stable() -> None:
    ref = ReadSurfaceReference(
        reference_id="ref-1",
        reference_type="state_db",
        path="scos/work/control_center/state/control_center.sqlite3",
        exists=True,
        readable=True,
        source_stage="Stage 6.3",
    )
    query = ReadSurfaceQuery(
        query_id="rsq-1",
        query_type="FULL_LOCAL_READ_SURFACE",
        requested_at="2026-07-09T00:00:00Z",
        include_state=True,
        include_events=True,
        include_approvals=True,
        include_audit=True,
        include_health=True,
        include_drift=True,
        limit=50,
    )

    assert list(ref.to_dict()) == [
        "reference_id",
        "reference_type",
        "path",
        "exists",
        "readable",
        "source_stage",
    ]
    assert list(query.to_dict()) == [
        "query_id",
        "query_type",
        "requested_at",
        "include_state",
        "include_events",
        "include_approvals",
        "include_audit",
        "include_health",
        "include_drift",
        "limit",
    ]


def test_record_snapshot_and_result_are_immutable() -> None:
    ref = ReadSurfaceReference("ref-1", "stage6_source", "p", True, True, "Stage 6")
    record = ReadSurfaceRecord(
        record_id="record-1",
        record_type="state_summary",
        source_stage="Stage 6.3",
        summary="summary",
        status="readable",
        references=(ref,),
        metadata=(("b", "2"), ("a", "1")),
    )
    snapshot = ReadSurfaceSnapshot(
        snapshot_id="snap-1",
        checked_at="2026-07-09T00:00:00Z",
        query_id="rsq-1",
        records=(record,),
        readiness=FrozenMap.from_mapping({"z": "last", "a": "first"}),
        blockers=(),
        warnings=("warn-b", "warn-a"),
    )
    result = ReadSurfaceResult(
        accepted=True,
        go_no_go="GO",
        readiness_score=98,
        snapshot=snapshot,
        blockers=(),
        warnings=snapshot.warnings,
        checked_at=snapshot.checked_at,
    )

    assert record.metadata == (("a", "1"), ("b", "2"))
    assert snapshot.warnings == ("warn-a", "warn-b")
    assert list(snapshot.readiness.to_dict()) == ["a", "z"]
    assert result.to_dict()["snapshot"]["records"][0]["metadata"] == [["a", "1"], ["b", "2"]]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.readiness_score = 1  # type: ignore[misc]


def test_error_to_dict_is_deterministic() -> None:
    error = ReadSurfaceError.of(
        "INVALID_QUERY",
        "bad query",
        checked_at="2026-07-09T00:00:00Z",
        blockers=("b2", "b1"),
    )

    assert error.blockers == ("b1", "b2")
    assert list(error.to_dict()) == ["error_code", "message", "checked_at", "blockers"]


def test_record_rejects_invalid_reference_type() -> None:
    with pytest.raises(ValueError):
        ReadSurfaceRecord(
            record_id="record-1",
            record_type="bad",
            source_stage="Stage 7.1",
            summary="summary",
            status="blocked",
            references=("not-a-reference",),  # type: ignore[arg-type]
            metadata=(),
        )
