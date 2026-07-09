"""Stage 7.1 deterministic read-only snapshot builder."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

try:
    from .backend_health import (
        DEFAULT_COMMAND_QUEUE_RELATIVE_PATH,
        DEFAULT_EVENT_LOG_RELATIVE_PATH,
        run_backend_health_check,
    )
    from .host_metrics import collect_jsonl_metric, collect_sqlite_metric
    from .read_surface_models import (
        FrozenMap,
        ReadSurfaceError,
        ReadSurfaceQuery,
        ReadSurfaceRecord,
        ReadSurfaceReference,
        ReadSurfaceSnapshot,
    )
    from .read_surface_validation import (
        resolve_repo_path,
        validate_checked_at,
        validate_read_only_boundary,
        validate_repo_root_local,
    )
    from .sqlite_state_schema import DEFAULT_STATE_DB_RELATIVE_PATH
except ImportError:  # direct-module execution
    from backend_health import (
        DEFAULT_COMMAND_QUEUE_RELATIVE_PATH,
        DEFAULT_EVENT_LOG_RELATIVE_PATH,
        run_backend_health_check,
    )
    from host_metrics import collect_jsonl_metric, collect_sqlite_metric
    from read_surface_models import (
        FrozenMap,
        ReadSurfaceError,
        ReadSurfaceQuery,
        ReadSurfaceRecord,
        ReadSurfaceReference,
        ReadSurfaceSnapshot,
    )
    from read_surface_validation import (
        resolve_repo_path,
        validate_checked_at,
        validate_read_only_boundary,
        validate_repo_root_local,
    )
    from sqlite_state_schema import DEFAULT_STATE_DB_RELATIVE_PATH

_STATE_TABLES = (
    "approvals",
    "audit_ledger",
    "commands",
    "events",
    "results",
    "sessions",
    "state_schema",
)

_REQUIRED_STAGE6_SOURCE_FILES = (
    "scos/control_center/backend_health.py",
    "scos/control_center/drift_detection.py",
    "scos/control_center/sqlite_state_schema.py",
    "scos/control_center/host_metrics.py",
    "docs/roadmap/STAGE7_HANDOFF.md",
    "docs/specification/STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md",
)


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _reference(
    *,
    repo_root: Path,
    reference_type: str,
    path: str,
    source_stage: str,
) -> ReadSurfaceReference:
    try:
        resolved = resolve_repo_path(repo_root, path, field_name=reference_type)
    except ValueError:
        return ReadSurfaceReference(
            reference_id=_stable_id("rsr-", reference_type, path, source_stage),
            reference_type=reference_type,
            path=str(path),
            exists=False,
            readable=False,
            source_stage=source_stage,
        )
    exists = resolved.exists()
    readable = False
    if exists:
        try:
            if resolved.is_file():
                with open(resolved, "rb") as handle:
                    handle.read(0)
            readable = True
        except OSError:
            readable = False
    return ReadSurfaceReference(
        reference_id=_stable_id("rsr-", reference_type, str(resolved), source_stage),
        reference_type=reference_type,
        path=str(resolved),
        exists=exists,
        readable=readable,
        source_stage=source_stage,
    )


def _record(
    *,
    record_type: str,
    source_stage: str,
    summary: str,
    status: str,
    references: tuple[ReadSurfaceReference, ...],
    metadata: tuple[tuple[str, str], ...] = (),
) -> ReadSurfaceRecord:
    return ReadSurfaceRecord(
        record_id=_stable_id("rsrec-", record_type, source_stage, summary, status, metadata),
        record_type=record_type,
        source_stage=source_stage,
        summary=summary,
        status=status,
        references=references,
        metadata=metadata,
    )


def _table_count(metric: Any, table: str) -> int:
    return dict(metric.table_counts).get(table, 0)


def _read_latest_rows(repo_root: Path, db_path: str, table: str, limit: int) -> tuple[dict[str, str], ...]:
    resolved = resolve_repo_path(repo_root, db_path, field_name="state_db")
    if not resolved.is_file():
        return ()
    uri = resolved.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if exists is None:
            return ()
        rows = connection.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        connection.close()
    selected = rows[-limit:]
    return tuple(
        {str(key): str(row[key]) for key in sorted(row.keys())}
        for row in selected
    )


def _source_contract_records(repo_root: Path) -> tuple[list[ReadSurfaceRecord], list[str]]:
    records: list[ReadSurfaceRecord] = []
    blockers: list[str] = []
    for rel_path in _REQUIRED_STAGE6_SOURCE_FILES:
        ref = _reference(
            repo_root=repo_root,
            reference_type="stage6_source",
            path=rel_path,
            source_stage="Stage 6",
        )
        if not ref.exists or not ref.readable:
            blockers.append(f"missing_required_source:{rel_path}")
        records.append(
            _record(
                record_type="stage6_source",
                source_stage="Stage 6",
                summary=f"required source {rel_path}",
                status="readable" if ref.exists and ref.readable else "blocked",
                references=(ref,),
            )
        )
    return records, blockers


def _state_records(repo_root: Path, limit: int) -> tuple[list[ReadSurfaceRecord], list[str]]:
    ref = _reference(
        repo_root=repo_root,
        reference_type="state_db",
        path=DEFAULT_STATE_DB_RELATIVE_PATH,
        source_stage="Stage 6.3",
    )
    metric = collect_sqlite_metric(
        repo_root,
        DEFAULT_STATE_DB_RELATIVE_PATH,
        "state_db",
        expected_tables=_STATE_TABLES,
    )
    status = "missing" if not ref.exists else ("readable" if metric.readable else "blocked")
    warnings = [] if ref.exists else ["state_db: missing optional runtime artifact"]
    metadata = (
        ("commands", str(_table_count(metric, "commands"))),
        ("sessions", str(_table_count(metric, "sessions"))),
        ("events", str(_table_count(metric, "events"))),
        ("approvals", str(_table_count(metric, "approvals"))),
        ("results", str(_table_count(metric, "results"))),
        ("wal_enabled", str(bool(getattr(metric, "wal_enabled", False)))),
    )
    records = [
        _record(
            record_type="state_summary",
            source_stage="Stage 6.3",
            summary="SQLite WAL state summary",
            status=status,
            references=(ref,),
            metadata=metadata,
        )
    ]
    if ref.exists and metric.readable:
        for table in ("commands", "sessions", "events", "approvals", "results"):
            rows = _read_latest_rows(repo_root, DEFAULT_STATE_DB_RELATIVE_PATH, table, limit)
            records.append(
                _record(
                    record_type=f"state_{table}",
                    source_stage="Stage 6.3",
                    summary=f"latest {len(rows)} {table} rows",
                    status="readable",
                    references=(ref,),
                    metadata=(("row_count", str(len(rows))),),
                )
            )
    return records, warnings


def _event_records(repo_root: Path) -> tuple[list[ReadSurfaceRecord], list[str], list[str]]:
    ref = _reference(
        repo_root=repo_root,
        reference_type="event_log",
        path=DEFAULT_EVENT_LOG_RELATIVE_PATH,
        source_stage="Stage 6.4",
    )
    metric = collect_jsonl_metric(repo_root, DEFAULT_EVENT_LOG_RELATIVE_PATH, "event_log")
    warnings: list[str] = []
    blockers: list[str] = []
    if not ref.exists:
        warnings.append("event_log: missing optional runtime artifact")
    if metric.malformed_line_count:
        blockers.append("event_log: malformed JSONL records found")
    record = _record(
        record_type="event_summary",
        source_stage="Stage 6.4",
        summary="local command event log summary",
        status="blocked" if blockers else ("readable" if ref.exists else "missing"),
        references=(ref,),
        metadata=(
            ("record_count", str(metric.record_count)),
            ("malformed_line_count", str(metric.malformed_line_count)),
        ),
    )
    return [record], warnings, blockers


def _approval_records(repo_root: Path, include_audit: bool) -> tuple[list[ReadSurfaceRecord], list[str]]:
    ref = _reference(
        repo_root=repo_root,
        reference_type="approval_audit",
        path=DEFAULT_STATE_DB_RELATIVE_PATH,
        source_stage="Stage 6.6",
    )
    metric = collect_sqlite_metric(
        repo_root,
        DEFAULT_STATE_DB_RELATIVE_PATH,
        "approval_audit",
        expected_tables=("approvals", "audit_ledger"),
    )
    warnings = [] if ref.exists else ["approval_audit: missing optional runtime artifact"]
    records = [
        _record(
            record_type="approval_summary",
            source_stage="Stage 6.6",
            summary="operator approval record summary",
            status="readable" if metric.readable else ("missing" if not ref.exists else "blocked"),
            references=(ref,),
            metadata=(("approval_count", str(_table_count(metric, "approvals"))),),
        )
    ]
    if include_audit:
        records.append(
            _record(
                record_type="audit_summary",
                source_stage="Stage 6.7",
                summary="approval audit ledger summary",
                status="readable" if metric.readable else ("missing" if not ref.exists else "blocked"),
                references=(ref,),
                metadata=(("audit_record_count", str(_table_count(metric, "audit_ledger"))),),
            )
        )
    return records, warnings


def _queue_record(repo_root: Path) -> tuple[ReadSurfaceRecord, list[str], list[str]]:
    ref = _reference(
        repo_root=repo_root,
        reference_type="command_queue",
        path=DEFAULT_COMMAND_QUEUE_RELATIVE_PATH,
        source_stage="Stage 6.2",
    )
    metric = collect_jsonl_metric(repo_root, DEFAULT_COMMAND_QUEUE_RELATIVE_PATH, "command_queue")
    warnings: list[str] = []
    blockers: list[str] = []
    if not ref.exists:
        warnings.append("command_queue: missing optional runtime artifact")
    if metric.malformed_line_count:
        blockers.append("command_queue: malformed JSONL records found")
    return (
        _record(
            record_type="command_queue_summary",
            source_stage="Stage 6.2",
            summary="approved command queue summary",
            status="blocked" if blockers else ("readable" if ref.exists else "missing"),
            references=(ref,),
            metadata=(
                ("record_count", str(metric.record_count)),
                ("malformed_line_count", str(metric.malformed_line_count)),
            ),
        ),
        warnings,
        blockers,
    )


def _health_records(repo_root: Path, checked_at: str, include_drift: bool) -> tuple[list[ReadSurfaceRecord], list[str], list[str]]:
    report = run_backend_health_check(repo_root=repo_root, checked_at=checked_at)
    ref = _reference(
        repo_root=repo_root,
        reference_type="backend_health_module",
        path="scos/control_center/backend_health.py",
        source_stage="Stage 6.9",
    )
    records = [
        _record(
            record_type="health_summary",
            source_stage="Stage 6.9",
            summary=f"backend health is {report.health_status}",
            status=report.health_status,
            references=(ref,),
            metadata=(
                ("artifact_count", str(report.artifact_count)),
                ("event_count", str(report.event_count)),
                ("command_record_count", str(report.command_record_count)),
                ("audit_record_count", str(report.audit_record_count)),
                ("warning_count", str(report.warning_count)),
                ("blocker_count", str(report.blocker_count)),
            ),
        )
    ]
    if include_drift:
        records.append(
            _record(
                record_type="drift_summary",
                source_stage="Stage 6.9",
                summary=f"{report.drift_count} drift finding(s)",
                status="blocked" if report.blocker_count else ("warning" if report.drift_count else "readable"),
                references=(ref,),
                metadata=(("drift_count", str(report.drift_count)),),
            )
        )
    return records, list(report.warnings), list(report.blockers)


def _score(blockers: tuple[str, ...], warnings: tuple[str, ...]) -> int:
    if blockers:
        return max(0, 79 - (len(blockers) * 5))
    return max(80, 100 - (len(warnings) * 2))


def build_read_surface_snapshot(
    *,
    repo_root,
    query: ReadSurfaceQuery,
    checked_at: str,
) -> ReadSurfaceSnapshot | ReadSurfaceError:
    if not isinstance(query, ReadSurfaceQuery):
        return ReadSurfaceError.of(
            "INVALID_QUERY_OBJECT",
            "query must be a ReadSurfaceQuery",
            checked_at=str(checked_at),
        )

    validation_errors = tuple(
        error
        for error in (validate_repo_root_local(repo_root), validate_checked_at(checked_at))
        if error
    )
    if validation_errors:
        return ReadSurfaceError.of(
            "INVALID_SNAPSHOT_INPUT",
            validation_errors[0],
            checked_at=str(checked_at),
            blockers=validation_errors,
        )

    root = Path(repo_root).resolve()
    records: list[ReadSurfaceRecord] = []
    warnings: list[str] = []
    blockers: list[str] = []

    source_records, source_blockers = _source_contract_records(root)
    records.extend(source_records)
    blockers.extend(source_blockers)

    queue, queue_warnings, queue_blockers = _queue_record(root)
    records.append(queue)
    warnings.extend(queue_warnings)
    blockers.extend(queue_blockers)

    if query.include_state:
        state_records, state_warnings = _state_records(root, query.limit)
        records.extend(state_records)
        warnings.extend(state_warnings)
    if query.include_events:
        event_records, event_warnings, event_blockers = _event_records(root)
        records.extend(event_records)
        warnings.extend(event_warnings)
        blockers.extend(event_blockers)
    if query.include_approvals or query.include_audit:
        approval_records, approval_warnings = _approval_records(root, query.include_audit)
        records.extend(approval_records)
        warnings.extend(approval_warnings)
    if query.include_health or query.include_drift:
        health_records, health_warnings, health_blockers = _health_records(
            root, checked_at, query.include_drift
        )
        records.extend(health_records)
        warnings.extend(health_warnings)
        blockers.extend(health_blockers)

    boundary = validate_read_only_boundary(repo_root=root)
    blockers.extend(str(item) for item in boundary["blockers"])
    warnings.extend(str(item) for item in boundary["warnings"])

    final_blockers = tuple(sorted(set(blockers)))
    final_warnings = tuple(sorted(set(warnings)))
    readiness_score = _score(final_blockers, final_warnings)
    readiness = FrozenMap.from_mapping(
        {
            "accepted": str(not final_blockers),
            "go_no_go": "NO_GO" if final_blockers else "GO",
            "readiness_score": str(readiness_score),
            "record_count": str(len(records)),
            "write_operations_allowed": "False",
            "output_path_allowed": "False",
        }
    )
    snapshot_id = _stable_id(
        "rss-",
        checked_at,
        query.query_id,
        len(records),
        len(final_blockers),
        len(final_warnings),
    )
    return ReadSurfaceSnapshot(
        snapshot_id=snapshot_id,
        checked_at=checked_at,
        query_id=query.query_id,
        records=tuple(records),
        readiness=readiness,
        blockers=final_blockers,
        warnings=final_warnings,
    )


__all__ = sorted(("build_read_surface_snapshot",))
