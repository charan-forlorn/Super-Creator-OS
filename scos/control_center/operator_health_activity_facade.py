"""Public facade for Stage 7.3 operator health/activity read models."""

from __future__ import annotations

try:
    from .operator_health_activity import build_operator_health_activity_snapshot
    from .operator_read_models import OperatorReadModelError, OperatorReadModelResult, OperatorReadModelSnapshot
    from .read_surface_coherence_gate import validate_read_surface_non_mutation_contract
    from .read_surface_coherence_models import ReadSurfaceCoherenceError
    from .read_surface_facade import validate_read_surface_is_read_only
    from .read_surface_validation import validate_checked_at
except ImportError:  # direct-module execution
    from operator_health_activity import build_operator_health_activity_snapshot
    from operator_read_models import OperatorReadModelError, OperatorReadModelResult, OperatorReadModelSnapshot
    from read_surface_coherence_gate import validate_read_surface_non_mutation_contract
    from read_surface_coherence_models import ReadSurfaceCoherenceError
    from read_surface_facade import validate_read_surface_is_read_only
    from read_surface_validation import validate_checked_at


def query_operator_health_activity_read_models(
    *,
    repo_root,
    checked_at: str,
    activity_limit: int = 25,
) -> OperatorReadModelResult | OperatorReadModelError:
    snapshot = build_operator_health_activity_snapshot(
        repo_root=repo_root,
        checked_at=checked_at,
        activity_limit=activity_limit,
    )
    if isinstance(snapshot, OperatorReadModelError):
        return snapshot
    if not isinstance(snapshot, OperatorReadModelSnapshot):
        return OperatorReadModelError.of(
            "MALFORMED_OPERATOR_SNAPSHOT",
            "operator read model builder returned an unknown result",
            checked_at=str(checked_at),
        )
    accepted = not snapshot.blockers
    return OperatorReadModelResult(
        accepted=accepted,
        go_no_go="GO" if accepted else "NO_GO",
        readiness_score=snapshot.readiness_score,
        snapshot=snapshot,
        blockers=snapshot.blockers,
        warnings=snapshot.warnings,
        checked_at=checked_at,
    )


def validate_operator_read_models_are_read_only(
    *,
    repo_root,
    checked_at: str,
) -> dict:
    checked_error = validate_checked_at(checked_at)
    if checked_error:
        return {
            "ok": False,
            "checked_at": str(checked_at),
            "blockers": (checked_error,),
            "warnings": (),
            "write_operations_allowed": False,
            "output_path_allowed": False,
            "hash_stability_checked": False,
        }
    boundary = validate_read_surface_is_read_only(repo_root=repo_root, checked_at=checked_at)
    mutation = validate_read_surface_non_mutation_contract(repo_root=repo_root, checked_at=checked_at)
    blockers = list(boundary.get("blockers", ()))
    warnings = list(boundary.get("warnings", ()))
    hash_stability_checked = False
    if isinstance(mutation, ReadSurfaceCoherenceError):
        blockers.extend(mutation.blockers)
    else:
        hash_stability_checked = True
        for check in mutation:
            if check.status == "failure" and check.severity in {"error", "critical"}:
                blockers.append(check.summary)
            elif check.status == "warning" or check.severity == "warning":
                warnings.append(check.summary)
    return {
        "ok": not blockers and bool(boundary.get("ok", False)),
        "checked_at": checked_at,
        "blockers": tuple(sorted(set(str(item) for item in blockers))),
        "warnings": tuple(sorted(set(str(item) for item in warnings))),
        "write_operations_allowed": False,
        "output_path_allowed": False,
        "hash_stability_checked": hash_stability_checked,
    }


__all__ = sorted(
    (
        "query_operator_health_activity_read_models",
        "validate_operator_read_models_are_read_only",
    )
)
