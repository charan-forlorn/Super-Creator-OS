"""Public facade for Stage 7.1 Control Center read-surface queries."""

from __future__ import annotations

try:
    from .read_surface_models import ReadSurfaceError, ReadSurfaceResult
    from .read_surface_query import create_read_surface_query
    from .read_surface_snapshot import build_read_surface_snapshot
    from .read_surface_validation import validate_checked_at, validate_read_only_boundary
except ImportError:  # direct-module execution
    from read_surface_models import ReadSurfaceError, ReadSurfaceResult
    from read_surface_query import create_read_surface_query
    from read_surface_snapshot import build_read_surface_snapshot
    from read_surface_validation import validate_checked_at, validate_read_only_boundary


def _score(blockers: tuple[str, ...], warnings: tuple[str, ...]) -> int:
    if blockers:
        return max(0, 79 - (len(blockers) * 5))
    return max(80, 100 - (len(warnings) * 2))


def query_control_center_read_surface(
    *,
    repo_root,
    query_type: str,
    checked_at: str,
    include_state: bool = True,
    include_events: bool = True,
    include_approvals: bool = True,
    include_audit: bool = True,
    include_health: bool = True,
    include_drift: bool = True,
    limit: int = 50,
) -> ReadSurfaceResult | ReadSurfaceError:
    checked_error = validate_checked_at(checked_at)
    if checked_error:
        return ReadSurfaceError.of(
            "INVALID_CHECKED_AT",
            checked_error,
            checked_at=str(checked_at),
        )

    query = create_read_surface_query(
        query_type=query_type,
        requested_at=checked_at,
        include_state=include_state,
        include_events=include_events,
        include_approvals=include_approvals,
        include_audit=include_audit,
        include_health=include_health,
        include_drift=include_drift,
        limit=limit,
    )
    if isinstance(query, ReadSurfaceError):
        return query

    snapshot = build_read_surface_snapshot(
        repo_root=repo_root,
        query=query,
        checked_at=checked_at,
    )
    if isinstance(snapshot, ReadSurfaceError):
        return snapshot

    blockers = snapshot.blockers
    warnings = snapshot.warnings
    accepted = not blockers
    return ReadSurfaceResult(
        accepted=accepted,
        go_no_go="GO" if accepted else "NO_GO",
        readiness_score=_score(blockers, warnings),
        snapshot=snapshot,
        blockers=blockers,
        warnings=warnings,
        checked_at=checked_at,
    )


__all__ = sorted(
    (
        "query_control_center_read_surface",
        "validate_read_surface_is_read_only",
    )
)


def validate_read_surface_is_read_only(*, repo_root, checked_at: str) -> dict:
    checked_error = validate_checked_at(checked_at)
    if checked_error:
        return {
            "ok": False,
            "checked_at": str(checked_at),
            "blockers": (checked_error,),
            "warnings": (),
            "write_operations_allowed": False,
            "output_path_allowed": False,
        }
    result = validate_read_only_boundary(repo_root=repo_root)
    return {
        "ok": bool(result["ok"]),
        "checked_at": checked_at,
        "blockers": tuple(result["blockers"]),
        "warnings": tuple(result["warnings"]),
        "write_operations_allowed": False,
        "output_path_allowed": False,
    }
