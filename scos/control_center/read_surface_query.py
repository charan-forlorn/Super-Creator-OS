"""Stage 7.1 query creation for the local Control Center read surface."""

from __future__ import annotations

import hashlib

try:
    from .read_surface_models import ReadSurfaceError, ReadSurfaceQuery
    from .read_surface_validation import (
        validate_limit,
        validate_query_type,
        validate_requested_at,
    )
except ImportError:  # direct-module execution
    from read_surface_models import ReadSurfaceError, ReadSurfaceQuery
    from read_surface_validation import (
        validate_limit,
        validate_query_type,
        validate_requested_at,
    )


def _stable_query_id(
    *,
    query_type: str,
    requested_at: str,
    include_state: bool,
    include_events: bool,
    include_approvals: bool,
    include_audit: bool,
    include_health: bool,
    include_drift: bool,
    limit: int,
) -> str:
    payload = "|".join(
        (
            "read_surface_query",
            query_type,
            requested_at,
            str(bool(include_state)),
            str(bool(include_events)),
            str(bool(include_approvals)),
            str(bool(include_audit)),
            str(bool(include_health)),
            str(bool(include_drift)),
            str(int(limit)),
        )
    )
    return "rsq-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def create_read_surface_query(
    *,
    query_type: str,
    requested_at: str,
    include_state: bool = True,
    include_events: bool = True,
    include_approvals: bool = True,
    include_audit: bool = True,
    include_health: bool = True,
    include_drift: bool = True,
    limit: int = 50,
) -> ReadSurfaceQuery | ReadSurfaceError:
    blockers = tuple(
        error
        for error in (
            validate_query_type(query_type),
            validate_requested_at(requested_at),
            validate_limit(limit),
        )
        if error
    )
    if blockers:
        return ReadSurfaceError.of(
            "INVALID_QUERY",
            blockers[0],
            checked_at=str(requested_at),
            blockers=blockers,
        )

    normalized_limit = int(limit)
    return ReadSurfaceQuery(
        query_id=_stable_query_id(
            query_type=query_type,
            requested_at=requested_at,
            include_state=include_state,
            include_events=include_events,
            include_approvals=include_approvals,
            include_audit=include_audit,
            include_health=include_health,
            include_drift=include_drift,
            limit=normalized_limit,
        ),
        query_type=query_type,
        requested_at=requested_at,
        include_state=include_state,
        include_events=include_events,
        include_approvals=include_approvals,
        include_audit=include_audit,
        include_health=include_health,
        include_drift=include_drift,
        limit=normalized_limit,
    )


__all__ = sorted(("create_read_surface_query",))
