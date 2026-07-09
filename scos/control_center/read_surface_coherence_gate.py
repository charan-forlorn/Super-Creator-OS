"""Stage 7.2 read surface contract and coherence gate.

The gate sits on top of the Stage 7.1 public read-surface facade and converts
contract or coherence problems into deterministic checks, issues, blockers,
and warnings. It reads local evidence only and does not create files or
mutate Stage 6 stores.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

try:
    from .read_surface_coherence_models import (
        ReadSurfaceCoherenceError,
        ReadSurfaceCoherenceIssue,
        ReadSurfaceCoherenceReport,
        ReadSurfaceContractCheck,
    )
    from .read_surface_facade import (
        query_control_center_read_surface,
        validate_read_surface_is_read_only,
    )
    from .read_surface_models import (
        ALLOWED_READ_SURFACE_QUERY_TYPES,
        ReadSurfaceError,
        ReadSurfaceResult,
    )
    from .read_surface_validation import (
        validate_checked_at,
        validate_no_url_path,
        validate_repo_root_local,
    )
except ImportError:  # direct-module execution
    from read_surface_coherence_models import (
        ReadSurfaceCoherenceError,
        ReadSurfaceCoherenceIssue,
        ReadSurfaceCoherenceReport,
        ReadSurfaceContractCheck,
    )
    from read_surface_facade import (
        query_control_center_read_surface,
        validate_read_surface_is_read_only,
    )
    from read_surface_models import (
        ALLOWED_READ_SURFACE_QUERY_TYPES,
        ReadSurfaceError,
        ReadSurfaceResult,
    )
    from read_surface_validation import (
        validate_checked_at,
        validate_no_url_path,
        validate_repo_root_local,
    )

_REQUIRED_STAGE7_1_CONTRACT_FILES = (
    "docs/specification/CONTROL_CENTER_READ_SURFACE_CONTRACT.md",
    "docs/specification/STAGE7_READ_ONLY_QUERY_BOUNDARY.md",
    "docs/certification/Stage-7.1-plan.md",
)

_REQUIRED_STAGE6_SOURCE_FILES = (
    "scos/control_center/backend_health.py",
    "scos/control_center/drift_detection.py",
    "scos/control_center/sqlite_state_schema.py",
    "scos/control_center/host_metrics.py",
    "docs/roadmap/STAGE7_HANDOFF.md",
    "docs/specification/STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md",
)

_OPTIONAL_STAGE6_RUNTIME_ARTIFACTS = (
    "scos/work/control_center/state/control_center.sqlite3",
    "scos/work/control_center/events/command_events.jsonl",
    "scos/work/control_center/queue/approved_commands.jsonl",
)

_PUBLIC_STAGE7_1_EXPORTS = (
    "ALLOWED_READ_SURFACE_QUERY_TYPES",
    "READ_SURFACE_SCHEMA_VERSION",
    "ReadSurfaceError",
    "ReadSurfaceQuery",
    "ReadSurfaceRecord",
    "ReadSurfaceReference",
    "ReadSurfaceResult",
    "ReadSurfaceSnapshot",
    "build_read_surface_snapshot",
    "create_read_surface_query",
    "query_control_center_read_surface",
    "validate_read_surface_is_read_only",
)


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _check(
    *,
    check_name: str,
    status: str,
    severity: str,
    summary: str,
    source_stage: str,
    references: tuple[str, ...] = (),
    metadata: tuple[tuple[str, str], ...] = (),
) -> ReadSurfaceContractCheck:
    return ReadSurfaceContractCheck(
        check_id=_stable_id("rscc-", check_name, status, severity, summary, references, metadata),
        check_name=check_name,
        status=status,
        severity=severity,
        summary=summary,
        source_stage=source_stage,
        references=references,
        metadata=metadata,
    )


def _issue(
    *,
    issue_type: str,
    severity: str,
    message: str,
    source_reference: str,
    read_surface_reference: str,
    blocker: bool,
) -> ReadSurfaceCoherenceIssue:
    return ReadSurfaceCoherenceIssue(
        issue_id=_stable_id(
            "rsci-",
            issue_type,
            severity,
            message,
            source_reference,
            read_surface_reference,
            blocker,
        ),
        issue_type=issue_type,
        severity=severity,
        message=message,
        source_reference=source_reference,
        read_surface_reference=read_surface_reference,
        blocker=blocker,
    )


def _resolve_inside(root: Path, rel_path: str) -> Path:
    path_error = validate_no_url_path(rel_path, field_name="artifact_path")
    if path_error:
        raise ValueError(path_error)
    resolved = (root / rel_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(f"artifact_path must resolve inside repo_root: {rel_path}") from None
    return resolved


def _validate_inputs(repo_root: Any, checked_at: str) -> tuple[Path | None, ReadSurfaceCoherenceError | None]:
    errors = tuple(
        error
        for error in (validate_repo_root_local(repo_root), validate_checked_at(checked_at))
        if error
    )
    if errors:
        return None, ReadSurfaceCoherenceError.of(
            "INVALID_COHERENCE_INPUT",
            errors[0],
            checked_at=str(checked_at),
            blockers=errors,
        )
    return Path(repo_root).resolve(), None


def _artifact_hashes(root: Path) -> tuple[tuple[str, str], ...]:
    hashes: list[tuple[str, str]] = []
    for rel_path in sorted(_OPTIONAL_STAGE6_RUNTIME_ARTIFACTS):
        try:
            path = _resolve_inside(root, rel_path)
        except ValueError:
            continue
        if path.is_file():
            hashes.append((rel_path, hashlib.sha256(path.read_bytes()).hexdigest()))
    return tuple(hashes)


def _score(blockers: tuple[str, ...], warnings: tuple[str, ...]) -> int:
    if blockers:
        return max(0, 79 - (len(blockers) * 5))
    return max(80, 100 - (len(warnings) * 2))


def validate_read_surface_contract_alignment(
    *,
    repo_root,
    checked_at: str,
) -> tuple[ReadSurfaceContractCheck, ...] | ReadSurfaceCoherenceError:
    root, error = _validate_inputs(repo_root, checked_at)
    if error is not None:
        return error
    assert root is not None

    checks: list[ReadSurfaceContractCheck] = []
    for rel_path in _REQUIRED_STAGE7_1_CONTRACT_FILES:
        path = _resolve_inside(root, rel_path)
        exists = path.is_file()
        checks.append(
            _check(
                check_name=f"stage7_1_contract_file:{rel_path}",
                status="success" if exists else "failure",
                severity="info" if exists else "error",
                summary="Stage 7.1 contract artifact is present" if exists else "Stage 7.1 contract artifact is missing",
                source_stage="Stage 7.1",
                references=(str(path),),
            )
        )

    import scos.control_center as control_center

    missing_exports = tuple(
        name for name in _PUBLIC_STAGE7_1_EXPORTS if not hasattr(control_center, name)
    )
    checks.append(
        _check(
            check_name="stage7_1_public_exports",
            status="success" if not missing_exports else "failure",
            severity="info" if not missing_exports else "error",
            summary="Stage 7.1 public exports are intact" if not missing_exports else "Stage 7.1 public exports are missing",
            source_stage="Stage 7.1",
            references=("scos/control_center/__init__.py",),
            metadata=(("missing_exports", ",".join(missing_exports)),),
        )
    )
    checks.append(
        _check(
            check_name="stage7_1_query_type_contract",
            status="success" if "FULL_LOCAL_READ_SURFACE" in ALLOWED_READ_SURFACE_QUERY_TYPES else "failure",
            severity="info" if "FULL_LOCAL_READ_SURFACE" in ALLOWED_READ_SURFACE_QUERY_TYPES else "error",
            summary="Required read surface query type is available",
            source_stage="Stage 7.1",
            references=("scos/control_center/read_surface_models.py",),
            metadata=(("query_type_count", str(len(ALLOWED_READ_SURFACE_QUERY_TYPES))),),
        )
    )
    return tuple(checks)


def compare_read_surface_to_stage6_artifacts(
    *,
    repo_root,
    checked_at: str,
    query_type: str = "FULL_LOCAL_READ_SURFACE",
) -> tuple[ReadSurfaceCoherenceIssue, ...] | ReadSurfaceCoherenceError:
    root, error = _validate_inputs(repo_root, checked_at)
    if error is not None:
        return error
    assert root is not None

    result = query_control_center_read_surface(
        repo_root=root,
        query_type=query_type,
        checked_at=checked_at,
    )
    if isinstance(result, ReadSurfaceError):
        return ReadSurfaceCoherenceError.of(
            "READ_SURFACE_QUERY_FAILED",
            result.message,
            checked_at=checked_at,
            blockers=result.blockers,
        )
    if not isinstance(result, ReadSurfaceResult) or result.snapshot is None:
        return ReadSurfaceCoherenceError.of(
            "MALFORMED_READ_SURFACE_RESULT",
            "read surface did not return a result with a snapshot",
            checked_at=checked_at,
        )

    issues: list[ReadSurfaceCoherenceIssue] = []
    record_references = {
        reference.path
        for record in result.snapshot.records
        for reference in record.references
    }

    for rel_path in _REQUIRED_STAGE6_SOURCE_FILES:
        path = _resolve_inside(root, rel_path)
        present = path.is_file()
        if not present:
            issues.append(
                _issue(
                    issue_type="missing_required_stage6_source",
                    severity="error",
                    message=f"required Stage 6 source artifact is missing: {rel_path}",
                    source_reference=str(path),
                    read_surface_reference="snapshot.blockers",
                    blocker=True,
                )
            )
        elif str(path) not in record_references:
            issues.append(
                _issue(
                    issue_type="required_source_not_referenced",
                    severity="warning",
                    message=f"required Stage 6 source is not referenced by read surface: {rel_path}",
                    source_reference=str(path),
                    read_surface_reference="snapshot.records",
                    blocker=False,
                )
            )

    for rel_path in _OPTIONAL_STAGE6_RUNTIME_ARTIFACTS:
        path = _resolve_inside(root, rel_path)
        if not path.exists():
            issues.append(
                _issue(
                    issue_type="missing_optional_stage6_artifact",
                    severity="warning",
                    message=f"optional Stage 6 runtime artifact is missing: {rel_path}",
                    source_reference=str(path),
                    read_surface_reference="snapshot.warnings",
                    blocker=False,
                )
            )

    for blocker in result.blockers:
        issues.append(
            _issue(
                issue_type="read_surface_blocker",
                severity="error",
                message=blocker,
                source_reference="Stage 7.1 read surface",
                read_surface_reference="ReadSurfaceResult.blockers",
                blocker=True,
            )
        )
    for warning in result.warnings:
        issues.append(
            _issue(
                issue_type="read_surface_warning",
                severity="warning",
                message=warning,
                source_reference="Stage 7.1 read surface",
                read_surface_reference="ReadSurfaceResult.warnings",
                blocker=False,
            )
        )

    if result.accepted != (not result.blockers):
        issues.append(
            _issue(
                issue_type="malformed_read_surface_acceptance",
                severity="error",
                message="read surface accepted flag does not match blockers",
                source_reference="Stage 7.1 read surface",
                read_surface_reference="ReadSurfaceResult.accepted",
                blocker=True,
            )
        )
    if result.go_no_go == "GO" and result.blockers:
        issues.append(
            _issue(
                issue_type="malformed_read_surface_go_no_go",
                severity="error",
                message="read surface returned GO with blockers",
                source_reference="Stage 7.1 read surface",
                read_surface_reference="ReadSurfaceResult.go_no_go",
                blocker=True,
            )
        )
    return tuple(issues)


def validate_read_surface_non_mutation_contract(
    *,
    repo_root,
    checked_at: str,
) -> tuple[ReadSurfaceContractCheck, ...] | ReadSurfaceCoherenceError:
    root, error = _validate_inputs(repo_root, checked_at)
    if error is not None:
        return error
    assert root is not None

    before = _artifact_hashes(root)
    boundary = validate_read_surface_is_read_only(repo_root=root, checked_at=checked_at)
    result = query_control_center_read_surface(
        repo_root=root,
        query_type="FULL_LOCAL_READ_SURFACE",
        checked_at=checked_at,
    )
    after = _artifact_hashes(root)
    hash_stable = before == after
    boundary_ok = bool(boundary.get("ok", False))
    result_ok = isinstance(result, (ReadSurfaceResult, ReadSurfaceError))
    return (
        _check(
            check_name="read_only_boundary",
            status="success" if boundary_ok else "failure",
            severity="info" if boundary_ok else "error",
            summary="Stage 7.1 read-only boundary reports no write path" if boundary_ok else "Stage 7.1 read-only boundary reported blockers",
            source_stage="Stage 7.1",
            references=("validate_read_surface_is_read_only",),
            metadata=(
                ("write_operations_allowed", str(boundary.get("write_operations_allowed"))),
                ("output_path_allowed", str(boundary.get("output_path_allowed"))),
            ),
        ),
        _check(
            check_name="artifact_hash_stability",
            status="success" if hash_stable else "failure",
            severity="info" if hash_stable else "critical",
            summary="Known Stage 6 runtime artifact hashes are stable across coherence query" if hash_stable else "Known Stage 6 runtime artifact hash changed during coherence query",
            source_stage="Stage 7.2",
            references=tuple(path for path, _hash in before),
            metadata=(("artifact_count", str(len(before))),),
        ),
        _check(
            check_name="read_surface_query_result_shape",
            status="success" if result_ok else "failure",
            severity="info" if result_ok else "error",
            summary="Read surface query returned a known envelope",
            source_stage="Stage 7.1",
            references=("query_control_center_read_surface",),
        ),
    )


def run_read_surface_coherence_gate(
    *,
    repo_root,
    checked_at: str,
    query_type: str = "FULL_LOCAL_READ_SURFACE",
    require_stage7_1_contract: bool = True,
    require_stage6_sources: bool = True,
) -> ReadSurfaceCoherenceReport | ReadSurfaceCoherenceError:
    root, error = _validate_inputs(repo_root, checked_at)
    if error is not None:
        return error
    assert root is not None

    checks: list[ReadSurfaceContractCheck] = []
    issues: list[ReadSurfaceCoherenceIssue] = []
    blockers: list[str] = []
    warnings: list[str] = []

    if require_stage7_1_contract:
        contract_checks = validate_read_surface_contract_alignment(
            repo_root=root,
            checked_at=checked_at,
        )
        if isinstance(contract_checks, ReadSurfaceCoherenceError):
            return contract_checks
        checks.extend(contract_checks)

    non_mutation_checks = validate_read_surface_non_mutation_contract(
        repo_root=root,
        checked_at=checked_at,
    )
    if isinstance(non_mutation_checks, ReadSurfaceCoherenceError):
        return non_mutation_checks
    checks.extend(non_mutation_checks)

    if require_stage6_sources:
        coherence_issues = compare_read_surface_to_stage6_artifacts(
            repo_root=root,
            checked_at=checked_at,
            query_type=query_type,
        )
        if isinstance(coherence_issues, ReadSurfaceCoherenceError):
            return coherence_issues
        issues.extend(coherence_issues)

    for check in checks:
        if check.status == "failure" and check.severity in ("error", "critical"):
            blockers.append(check.summary)
        elif check.status == "warning" or check.severity == "warning":
            warnings.append(check.summary)
    for issue in issues:
        if issue.blocker:
            blockers.append(issue.message)
        else:
            warnings.append(issue.message)

    final_blockers = tuple(sorted(set(blockers)))
    final_warnings = tuple(sorted(set(warnings)))
    accepted = not final_blockers
    report_id = _stable_id(
        "rscg-",
        checked_at,
        query_type,
        len(checks),
        len(issues),
        len(final_blockers),
        len(final_warnings),
    )
    return ReadSurfaceCoherenceReport(
        report_id=report_id,
        checked_at=checked_at,
        accepted=accepted,
        go_no_go="GO" if accepted else "NO_GO",
        readiness_score=_score(final_blockers, final_warnings),
        contract_checks=tuple(checks),
        coherence_issues=tuple(issues),
        blockers=final_blockers,
        warnings=final_warnings,
    )


__all__ = sorted(
    (
        "compare_read_surface_to_stage6_artifacts",
        "run_read_surface_coherence_gate",
        "validate_read_surface_contract_alignment",
        "validate_read_surface_non_mutation_contract",
    )
)
