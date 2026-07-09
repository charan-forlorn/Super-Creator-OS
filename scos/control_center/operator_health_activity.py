"""Stage 7.3 operator health/activity read-model builder."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

try:
    from .operator_read_models import (
        OperatorActivityRecord,
        OperatorFreshnessStatus,
        OperatorHealthSignal,
        OperatorReadModelError,
        OperatorReadModelSnapshot,
    )
    from .read_surface_coherence_gate import run_read_surface_coherence_gate
    from .read_surface_coherence_models import ReadSurfaceCoherenceError, ReadSurfaceCoherenceReport
    from .read_surface_facade import query_control_center_read_surface
    from .read_surface_models import ReadSurfaceError, ReadSurfaceRecord, ReadSurfaceResult
    from .read_surface_validation import validate_checked_at, validate_limit, validate_repo_root_local
except ImportError:  # direct-module execution
    from operator_read_models import (
        OperatorActivityRecord,
        OperatorFreshnessStatus,
        OperatorHealthSignal,
        OperatorReadModelError,
        OperatorReadModelSnapshot,
    )
    from read_surface_coherence_gate import run_read_surface_coherence_gate
    from read_surface_coherence_models import ReadSurfaceCoherenceError, ReadSurfaceCoherenceReport
    from read_surface_facade import query_control_center_read_surface
    from read_surface_models import ReadSurfaceError, ReadSurfaceRecord, ReadSurfaceResult
    from read_surface_validation import validate_checked_at, validate_limit, validate_repo_root_local

_HEALTH_SIGNAL_ORDER = (
    "BACKEND_HEALTH",
    "STATE_STORE_HEALTH",
    "EVENT_STREAM_HEALTH",
    "APPROVAL_HEALTH",
    "AUDIT_HEALTH",
    "SECURITY_BASELINE",
    "DRIFT_STATUS",
    "HOST_METRICS",
)

_RECORD_SIGNAL_MAP = {
    "health_summary": "BACKEND_HEALTH",
    "state_summary": "STATE_STORE_HEALTH",
    "event_summary": "EVENT_STREAM_HEALTH",
    "approval_summary": "APPROVAL_HEALTH",
    "audit_summary": "AUDIT_HEALTH",
    "drift_summary": "DRIFT_STATUS",
    "command_queue_summary": "HOST_METRICS",
}

_RECORD_ACTIVITY_MAP = {
    "command_queue_summary": "COMMAND_ACTIVITY",
    "approval_summary": "APPROVAL_ACTIVITY",
    "audit_summary": "AUDIT_ACTIVITY",
    "event_summary": "EVENT_ACTIVITY",
    "state_summary": "STATE_ACTIVITY",
    "state_commands": "STATE_ACTIVITY",
    "state_sessions": "STATE_ACTIVITY",
    "state_events": "EVENT_ACTIVITY",
    "state_approvals": "APPROVAL_ACTIVITY",
    "state_results": "STATE_ACTIVITY",
    "stage6_source": "SECURITY_ACTIVITY",
    "drift_summary": "DRIFT_ACTIVITY",
}


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _normalize_status(status: str) -> str:
    value = str(status).strip().lower()
    if value in {"healthy", "success", "readable", "ok", "go"}:
        return "HEALTHY"
    if value in {"degraded", "warning"}:
        return "DEGRADED"
    if value in {"stale"}:
        return "STALE"
    if value in {"missing"}:
        return "MISSING"
    if value in {"blocked", "blocker", "failure", "error", "critical", "no_go"}:
        return "BLOCKED"
    return "UNKNOWN"


def _severity_for(status: str) -> str:
    if status == "BLOCKED":
        return "error"
    if status in {"DEGRADED", "STALE", "MISSING", "UNKNOWN"}:
        return "warning"
    return "info"


def _freshness_level(*, status: str, present: bool, readable: bool, warnings: tuple[str, ...]) -> str:
    if not present:
        return "MISSING"
    if status == "STALE":
        return "STALE"
    if not readable or status == "UNKNOWN":
        return "UNKNOWN"
    if warnings:
        return "STALE"
    return "FRESH"


def _record_by_signal(records: tuple[ReadSurfaceRecord, ...]) -> dict[str, ReadSurfaceRecord]:
    mapped: dict[str, ReadSurfaceRecord] = {}
    for record in sorted(records, key=lambda item: item.record_id):
        signal_type = _RECORD_SIGNAL_MAP.get(record.record_type)
        if signal_type and signal_type not in mapped:
            mapped[signal_type] = record
    return mapped


def _record_references(record: ReadSurfaceRecord | None) -> tuple[str, ...]:
    if record is None:
        return ()
    return tuple(reference.path for reference in record.references)


def _freshness_for_record(
    *,
    checked_at: str,
    signal_type: str,
    status: str,
    record: ReadSurfaceRecord | None,
    warnings: tuple[str, ...],
) -> OperatorFreshnessStatus:
    references = tuple(record.references if record else ())
    present = any(reference.exists for reference in references) if references else record is not None
    readable = any(reference.readable for reference in references) if references else record is not None
    return OperatorFreshnessStatus(
        checked_at=checked_at,
        source_id=record.record_id if record else _stable_id("missing-", signal_type, checked_at),
        source_type=signal_type,
        is_present=present,
        is_readable=readable,
        is_stale=bool(warnings) or status == "STALE",
        freshness_level=_freshness_level(
            status=status,
            present=present,
            readable=readable,
            warnings=warnings,
        ),
        warnings=warnings,
    )


def _signal_from_record(
    *,
    checked_at: str,
    signal_type: str,
    record: ReadSurfaceRecord | None,
    warnings: tuple[str, ...] = (),
    blockers: tuple[str, ...] = (),
) -> OperatorHealthSignal:
    status = "MISSING" if record is None else _normalize_status(record.status)
    if blockers:
        status = "BLOCKED"
    elif warnings and status == "HEALTHY":
        status = "DEGRADED"
    source_stage = record.source_stage if record else "Stage 7.3"
    summary = record.summary if record else f"{signal_type} evidence is missing"
    metadata = tuple(record.metadata if record else ()) + (
        ("blocker_count", str(len(blockers))),
        ("warning_count", str(len(warnings))),
    )
    return OperatorHealthSignal(
        signal_id=_stable_id("ohs-", signal_type, status, summary, metadata),
        signal_type=signal_type,
        status=status,
        severity=_severity_for(status),
        summary=summary,
        source_stage=source_stage,
        freshness=_freshness_for_record(
            checked_at=checked_at,
            signal_type=signal_type,
            status=status,
            record=record,
            warnings=warnings,
        ),
        metadata=metadata,
    )


def _security_signal(
    *,
    checked_at: str,
    report: ReadSurfaceCoherenceReport,
) -> OperatorHealthSignal:
    status = "HEALTHY"
    if report.blockers:
        status = "BLOCKED"
    elif report.warnings:
        status = "DEGRADED"
    metadata = (
        ("coherence_issue_count", str(len(report.coherence_issues))),
        ("contract_check_count", str(len(report.contract_checks))),
        ("readiness_score", str(report.readiness_score)),
    )
    freshness = OperatorFreshnessStatus(
        checked_at=checked_at,
        source_id=report.report_id,
        source_type="SECURITY_BASELINE",
        is_present=True,
        is_readable=True,
        is_stale=bool(report.warnings),
        freshness_level="STALE" if report.warnings else "FRESH",
        warnings=report.warnings,
    )
    return OperatorHealthSignal(
        signal_id=_stable_id("ohs-", "SECURITY_BASELINE", status, report.report_id, metadata),
        signal_type="SECURITY_BASELINE",
        status=status,
        severity=_severity_for(status),
        summary="Stage 7.2 read surface coherence and non-mutation baseline",
        source_stage="Stage 7.2",
        freshness=freshness,
        metadata=metadata,
    )


def _activity_from_record(*, record: ReadSurfaceRecord, checked_at: str) -> OperatorActivityRecord | None:
    activity_type = _RECORD_ACTIVITY_MAP.get(record.record_type)
    if activity_type is None:
        return None
    references = _record_references(record)
    metadata = record.metadata + (("read_surface_record_id", record.record_id),)
    return OperatorActivityRecord(
        activity_id=_stable_id("oar-", activity_type, record.record_id, checked_at, metadata),
        activity_type=activity_type,
        status=_normalize_status(record.status),
        summary=record.summary,
        source_stage=record.source_stage,
        occurred_at=checked_at,
        references=references,
        metadata=metadata,
    )


def _activity_from_coherence_issue(*, issue: Any, checked_at: str) -> OperatorActivityRecord:
    status = "BLOCKED" if bool(issue.blocker) else "DEGRADED"
    activity_type = "SECURITY_ACTIVITY"
    if "drift" in str(issue.issue_type):
        activity_type = "DRIFT_ACTIVITY"
    return OperatorActivityRecord(
        activity_id=_stable_id("oar-", activity_type, issue.issue_id, checked_at),
        activity_type=activity_type,
        status=status,
        summary=str(issue.message),
        source_stage="Stage 7.2",
        occurred_at=checked_at,
        references=(str(issue.source_reference), str(issue.read_surface_reference)),
        metadata=(("issue_id", str(issue.issue_id)), ("issue_type", str(issue.issue_type))),
    )


def _build_health_signals(
    *,
    records: tuple[ReadSurfaceRecord, ...],
    report: ReadSurfaceCoherenceReport,
    checked_at: str,
) -> tuple[OperatorHealthSignal, ...]:
    by_signal = _record_by_signal(records)
    signals: list[OperatorHealthSignal] = []
    warning_text = tuple(report.warnings)
    blocker_text = tuple(report.blockers)
    for signal_type in _HEALTH_SIGNAL_ORDER:
        if signal_type == "SECURITY_BASELINE":
            signals.append(_security_signal(checked_at=checked_at, report=report))
            continue
        related_warnings = tuple(
            warning for warning in warning_text if signal_type.lower().split("_", 1)[0] in warning.lower()
        )
        related_blockers = tuple(
            blocker for blocker in blocker_text if signal_type.lower().split("_", 1)[0] in blocker.lower()
        )
        signals.append(
            _signal_from_record(
                checked_at=checked_at,
                signal_type=signal_type,
                record=by_signal.get(signal_type),
                warnings=related_warnings,
                blockers=related_blockers,
            )
        )
    return tuple(signals)


def _build_activity(
    *,
    records: tuple[ReadSurfaceRecord, ...],
    report: ReadSurfaceCoherenceReport,
    checked_at: str,
    activity_limit: int,
) -> tuple[OperatorActivityRecord, ...]:
    activity: list[OperatorActivityRecord] = []
    for record in records:
        item = _activity_from_record(record=record, checked_at=checked_at)
        if item is not None:
            activity.append(item)
    for issue in report.coherence_issues:
        activity.append(_activity_from_coherence_issue(issue=issue, checked_at=checked_at))
    ordered = tuple(sorted(activity, key=lambda item: (item.occurred_at, item.activity_id), reverse=True))
    return ordered[: int(activity_limit)]


def evaluate_operator_readiness(
    *,
    health_signals,
    recent_activity,
    checked_at: str,
) -> dict:
    checked_error = validate_checked_at(checked_at)
    blockers: list[str] = []
    warnings: list[str] = []
    if checked_error:
        blockers.append(checked_error)
    for signal in tuple(health_signals or ()):
        status = str(getattr(signal, "status", "UNKNOWN"))
        signal_type = str(getattr(signal, "signal_type", "UNKNOWN"))
        if status == "BLOCKED":
            blockers.append(f"{signal_type}: blocked")
        elif status in {"DEGRADED", "STALE", "MISSING", "UNKNOWN"}:
            warnings.append(f"{signal_type}: {status.lower()}")
    for activity in tuple(recent_activity or ()):
        if str(getattr(activity, "status", "")) == "BLOCKED":
            warnings.append(f"activity:{getattr(activity, 'activity_id', 'unknown')}: blocked")
    final_blockers = tuple(sorted(set(blockers)))
    final_warnings = tuple(sorted(set(warnings)))
    if final_blockers:
        score = max(0, 79 - (len(final_blockers) * 5) - (len(final_warnings) * 2))
    else:
        score = max(80, 100 - (len(final_warnings) * 2))
    return {
        "accepted": not final_blockers,
        "go_no_go": "NO_GO" if final_blockers else "GO",
        "readiness_score": score,
        "blockers": final_blockers,
        "warnings": final_warnings,
        "checked_at": str(checked_at),
    }


def _validate_inputs(repo_root: Any, checked_at: str, activity_limit: int) -> tuple[Path | None, OperatorReadModelError | None]:
    errors = tuple(
        error
        for error in (
            validate_repo_root_local(repo_root),
            validate_checked_at(checked_at),
            validate_limit(activity_limit),
        )
        if error
    )
    if errors:
        return None, OperatorReadModelError.of(
            "INVALID_OPERATOR_READ_MODEL_INPUT",
            errors[0],
            checked_at=str(checked_at),
            blockers=errors,
        )
    return Path(repo_root).resolve(), None


def build_operator_health_activity_snapshot(
    *,
    repo_root,
    checked_at: str,
    activity_limit: int = 25,
) -> OperatorReadModelSnapshot | OperatorReadModelError:
    root, error = _validate_inputs(repo_root, checked_at, activity_limit)
    if error is not None:
        return error
    assert root is not None

    read_result = query_control_center_read_surface(
        repo_root=root,
        query_type="FULL_LOCAL_READ_SURFACE",
        checked_at=checked_at,
        limit=activity_limit,
    )
    if isinstance(read_result, ReadSurfaceError):
        return OperatorReadModelError.of(
            "READ_SURFACE_QUERY_FAILED",
            read_result.message,
            checked_at=checked_at,
            blockers=read_result.blockers,
        )
    if not isinstance(read_result, ReadSurfaceResult) or read_result.snapshot is None:
        return OperatorReadModelError.of(
            "MALFORMED_READ_SURFACE_RESULT",
            "read surface did not return a snapshot",
            checked_at=checked_at,
        )

    coherence = run_read_surface_coherence_gate(repo_root=root, checked_at=checked_at)
    if isinstance(coherence, ReadSurfaceCoherenceError):
        return OperatorReadModelError.of(
            "COHERENCE_GATE_FAILED",
            coherence.message,
            checked_at=checked_at,
            blockers=coherence.blockers,
        )
    if not isinstance(coherence, ReadSurfaceCoherenceReport):
        return OperatorReadModelError.of(
            "MALFORMED_COHERENCE_RESULT",
            "coherence gate returned an unknown result",
            checked_at=checked_at,
        )

    records = read_result.snapshot.records
    health_signals = _build_health_signals(records=records, report=coherence, checked_at=checked_at)
    recent_activity = _build_activity(
        records=records,
        report=coherence,
        checked_at=checked_at,
        activity_limit=activity_limit,
    )
    readiness = evaluate_operator_readiness(
        health_signals=health_signals,
        recent_activity=recent_activity,
        checked_at=checked_at,
    )
    blockers = tuple(sorted(set(read_result.blockers) | set(coherence.blockers) | set(readiness["blockers"])))
    warnings = tuple(sorted(set(read_result.warnings) | set(coherence.warnings) | set(readiness["warnings"])))
    go_no_go = "NO_GO" if blockers else "GO"
    score = max(0, min(int(read_result.readiness_score), int(coherence.readiness_score), int(readiness["readiness_score"])))
    snapshot_id = _stable_id(
        "orms-",
        checked_at,
        read_result.snapshot.snapshot_id,
        coherence.report_id,
        len(health_signals),
        len(recent_activity),
        len(blockers),
        len(warnings),
    )
    return OperatorReadModelSnapshot(
        snapshot_id=snapshot_id,
        checked_at=checked_at,
        health_signals=health_signals,
        recent_activity=recent_activity,
        readiness_score=score,
        go_no_go=go_no_go,
        blockers=blockers,
        warnings=warnings,
    )


__all__ = sorted(
    (
        "build_operator_health_activity_snapshot",
        "evaluate_operator_readiness",
    )
)
