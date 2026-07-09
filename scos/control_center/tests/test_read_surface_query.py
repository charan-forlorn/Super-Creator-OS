"""Stage 7.1 read surface query creation tests."""

from __future__ import annotations

from scos.control_center.read_surface_models import ReadSurfaceError, ReadSurfaceQuery
from scos.control_center.read_surface_query import create_read_surface_query

_NOW = "2026-07-09T00:00:00Z"


def test_create_query_success_and_deterministic_id() -> None:
    first = create_read_surface_query(
        query_type="FULL_LOCAL_READ_SURFACE",
        requested_at=_NOW,
        limit=25,
    )
    second = create_read_surface_query(
        query_type="FULL_LOCAL_READ_SURFACE",
        requested_at=_NOW,
        limit=25,
    )

    assert isinstance(first, ReadSurfaceQuery)
    assert isinstance(second, ReadSurfaceQuery)
    assert first.query_id == second.query_id
    assert first.query_id.startswith("rsq-")
    assert first.limit == 25


def test_query_id_changes_with_stable_inputs() -> None:
    full = create_read_surface_query(
        query_type="FULL_LOCAL_READ_SURFACE",
        requested_at=_NOW,
    )
    state = create_read_surface_query(
        query_type="STATE_SUMMARY",
        requested_at=_NOW,
    )

    assert isinstance(full, ReadSurfaceQuery)
    assert isinstance(state, ReadSurfaceQuery)
    assert full.query_id != state.query_id


def test_create_query_rejects_invalid_inputs() -> None:
    bad_type = create_read_surface_query(query_type="BAD", requested_at=_NOW)
    bad_time = create_read_surface_query(
        query_type="FULL_LOCAL_READ_SURFACE",
        requested_at="",
    )
    bad_limit = create_read_surface_query(
        query_type="FULL_LOCAL_READ_SURFACE",
        requested_at=_NOW,
        limit=0,
    )

    assert isinstance(bad_type, ReadSurfaceError)
    assert isinstance(bad_time, ReadSurfaceError)
    assert isinstance(bad_limit, ReadSurfaceError)
    assert bad_type.error_code == "INVALID_QUERY"
