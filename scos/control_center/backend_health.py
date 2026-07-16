"""Stage 6.9 local backend health report generation.

The health check is offline-safe and read-only. It reads existing local
artifacts directly and never initializes stores, appends logs, executes
commands, opens network surfaces, or reads the system clock.
"""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from pathlib import Path
from typing import Any

try:
    from .drift_detection import DriftFinding, detect_backend_drift
    from .host_metrics import (
        JsonlMetric,
        SQLiteMetric,
        collect_jsonl_metric,
        collect_sqlite_metric,
        resolve_local_artifact_path,
    )
    from .sqlite_state_schema import DEFAULT_STATE_DB_RELATIVE_PATH
except ImportError:  # direct-module execution (tests insert the package dir)
    from drift_detection import DriftFinding, detect_backend_drift
    from host_metrics import (
        JsonlMetric,
        SQLiteMetric,
        collect_jsonl_metric,
        collect_sqlite_metric,
        resolve_local_artifact_path,
    )
    from sqlite_state_schema import DEFAULT_STATE_DB_RELATIVE_PATH

BACKEND_HEALTH_SCHEMA_VERSION = 1
DEFAULT_EVENT_LOG_RELATIVE_PATH = "scos/work/control_center/events/command_events.jsonl"
DEFAULT_COMMAND_QUEUE_RELATIVE_PATH = "scos/work/control_center/queue/approved_commands.jsonl"
HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
UNAVAILABLE = "UNAVAILABLE"
UNKNOWN = "UNKNOWN"

_STATE_TABLES = (
    "state_schema", "commands", "sessions", "events", "approvals",
    "results", "audit_ledger",
)


@dataclass(frozen=True)
class BackendHealthCheck:
    check_id: str
    status: str
    severity: str
    message: str
    metadata: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
            "metadata": [[key, value] for key, value in self.metadata],
        }


@dataclass(frozen=True)
class BackendHealthReport:
    schema_version: int
    checked_at: str
    health_status: str
    source_coverage: tuple[tuple[str, str], ...]
    artifact_count: int
    event_count: int
    audit_record_count: int
    command_record_count: int
    drift_count: int
    warning_count: int
    blocker_count: int
    checks: tuple[BackendHealthCheck, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    recent_activity_summary: tuple[tuple[str, str], ...]
    drift_findings: tuple[DriftFinding, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "checked_at": self.checked_at,
            "health_status": self.health_status,
            "source_coverage": [[key, value] for key, value in self.source_coverage],
            "artifact_count": self.artifact_count,
            "event_count": self.event_count,
            "audit_record_count": self.audit_record_count,
            "command_record_count": self.command_record_count,
            "drift_count": self.drift_count,
            "warning_count": self.warning_count,
            "blocker_count": self.blocker_count,
            "checks": [check.to_dict() for check in self.checks],
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "recent_activity_summary": [[key, value] for key, value in self.recent_activity_summary],
            "drift_findings": [finding.to_dict() for finding in self.drift_findings],
        }


def _check(check_id: str, status: str, severity: str, message: str,
           metadata: tuple[tuple[str, str], ...] = ()) -> BackendHealthCheck:
    return BackendHealthCheck(check_id=check_id, status=status, severity=severity,
                              message=message, metadata=metadata)


def _table_count(metric: SQLiteMetric, table: str) -> int:
    return dict(metric.table_counts).get(table, 0)


def _read_table(repo_root: Path, db_path: Any, table: str) -> tuple[dict[str, Any], ...]:
    resolved = resolve_local_artifact_path(repo_root, db_path, "state_db_path")
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
        return tuple(dict(row) for row in rows)
    finally:
        connection.close()


def _verify_audit_chain(repo_root: Path, db_path: Any) -> bool | None:
    rows = _read_table(repo_root, db_path, "audit_ledger")
    if not rows:
        return True
    try:
        from .approval_audit_models import AuditEntry, GENESIS_PREV_HASH
    except ImportError:  # direct-module execution
        from approval_audit_models import AuditEntry, GENESIS_PREV_HASH

    expected_prev = GENESIS_PREV_HASH
    for row in sorted(rows, key=lambda item: (int(item.get("sequence", 0)), str(item.get("entry_id", "")))):
        entry = AuditEntry(
            entry_id=str(row.get("entry_id", "")),
            sequence=int(row.get("sequence", 0)),
            prev_hash=str(row.get("prev_hash", "")),
            entry_hash=str(row.get("entry_hash", "")),
            decision_id=str(row.get("decision_id", "")),
            subject_type=str(row.get("subject_type", "")),
            subject_id=str(row.get("subject_id", "")),
            decision=str(row.get("decision", "")),
            decided_by=str(row.get("decided_by", "")),
            decided_at=str(row.get("decided_at", "")),
            reason=row.get("reason"),
            metadata_json=str(row.get("metadata_json", "")),
        )
        if entry.prev_hash != expected_prev or entry.entry_hash != entry.recompute_entry_hash():
            return False
        expected_prev = entry.entry_hash
    return True


def _coverage(name: str, present: bool, readable: bool, malformed: bool = False) -> tuple[str, str]:
    if malformed:
        return (name, "malformed")
    if present and readable:
        return (name, "readable")
    if present:
        return (name, "unreadable")
    return (name, "missing")


def _last_value(records: tuple[dict[str, Any], ...], *keys: str) -> str:
    for record in reversed(records):
        for key in keys:
            value = record.get(key)
            if value is not None:
                return str(value)
    return ""


def run_backend_health_check(
    *,
    repo_root,
    checked_at: str,
    state_db_path=None,
    event_log_path=None,
    approval_audit_path=None,
    command_queue_path=None,
) -> BackendHealthReport:
    root = Path(repo_root)
    if not str(checked_at):
        raise ValueError("checked_at is required")
    state_path = state_db_path or DEFAULT_STATE_DB_RELATIVE_PATH
    audit_path = approval_audit_path or state_path
    event_path = event_log_path or DEFAULT_EVENT_LOG_RELATIVE_PATH
    queue_path = command_queue_path or DEFAULT_COMMAND_QUEUE_RELATIVE_PATH

    checks: list[BackendHealthCheck] = []
    warnings: list[str] = []
    blockers: list[str] = []

    state_metric = collect_sqlite_metric(
        root, state_path, "state_db", expected_tables=_STATE_TABLES,
    )
    audit_metric = (
        state_metric if audit_path == state_path else collect_sqlite_metric(
            root, audit_path, "approval_audit", expected_tables=("audit_ledger",),
        )
    )
    event_metric = collect_jsonl_metric(root, event_path, "event_log")
    queue_metric = collect_jsonl_metric(root, queue_path, "command_queue")

    metrics: tuple[SQLiteMetric | JsonlMetric, ...] = (
        state_metric, audit_metric, event_metric, queue_metric,
    )
    for name, metric in (
        ("state_db", state_metric),
        ("approval_audit", audit_metric),
        ("event_log", event_metric),
        ("command_queue", queue_metric),
    ):
        artifact = metric.artifact
        if artifact.error_kind in ("URL_PATH_REJECTED", "PATH_ESCAPE_REJECTED"):
            blockers.append(f"{name}: unsafe local path")
            checks.append(_check(name, "failure", "blocker", artifact.error_detail or "unsafe path"))
        elif not artifact.exists:
            warnings.append(f"{name}: missing artifact")
            checks.append(_check(name, "warning", "warning", "artifact is missing"))
        elif not artifact.readable:
            blockers.append(f"{name}: unreadable artifact")
            checks.append(_check(name, "failure", "blocker", "artifact is unreadable"))
        else:
            checks.append(_check(name, "success", "info", "artifact is readable"))

    if state_metric.artifact.exists and not state_metric.readable:
        blockers.append("state_db: SQLite database is malformed or unreadable")
    if audit_metric.artifact.exists and not audit_metric.readable:
        blockers.append("approval_audit: SQLite database is malformed or unreadable")

    malformed_sources: list[str] = []
    if event_metric.malformed_line_count:
        malformed_sources.append("event_log")
        blockers.append("event_log: malformed JSONL records found")
    if queue_metric.malformed_line_count:
        malformed_sources.append("command_queue")
        blockers.append("command_queue: malformed JSONL records found")

    state_commands = _read_table(root, state_path, "commands") if state_metric.readable else ()
    state_sessions = _read_table(root, state_path, "sessions") if state_metric.readable else ()
    state_events = _read_table(root, state_path, "events") if state_metric.readable else ()
    state_results = _read_table(root, state_path, "results") if state_metric.readable else ()
    audit_decisions = _read_table(root, audit_path, "audit_ledger") if audit_metric.readable else ()
    audit_chain_ok = _verify_audit_chain(root, audit_path) if audit_metric.readable else None
    if audit_chain_ok is False:
        blockers.append("approval_audit: audit chain verification failed")

    drift_findings = detect_backend_drift(
        state_commands=state_commands,
        state_sessions=state_sessions,
        state_events=state_events,
        state_results=state_results,
        queue_commands=queue_metric.records,
        event_log_records=event_metric.records,
        audit_decisions=audit_decisions,
        audit_chain_ok=audit_chain_ok,
        malformed_sources=tuple(malformed_sources),
    )
    for finding in drift_findings:
        message = f"{finding.drift_type}: {finding.subject_id}"
        if finding.severity == "blocker":
            blockers.append(message)
        else:
            warnings.append(message)
    checks.append(_check(
        "drift_detection",
        "success" if not drift_findings else "warning",
        "warning" if drift_findings else "info",
        f"{len(drift_findings)} drift finding(s)",
    ))

    source_coverage = (
        _coverage("state_db", state_metric.artifact.exists, state_metric.readable,
                  state_metric.artifact.exists and not state_metric.readable),
        _coverage("approval_audit", audit_metric.artifact.exists, audit_metric.readable,
                  audit_metric.artifact.exists and not audit_metric.readable),
        _coverage("event_log", event_metric.artifact.exists, event_metric.artifact.readable,
                  event_metric.malformed_line_count > 0),
        _coverage("command_queue", queue_metric.artifact.exists, queue_metric.artifact.readable,
                  queue_metric.malformed_line_count > 0),
    )
    event_count = _table_count(state_metric, "events") + event_metric.record_count
    audit_record_count = _table_count(audit_metric, "audit_ledger")
    command_record_count = _table_count(state_metric, "commands") + queue_metric.record_count
    artifact_count = sum(1 for metric in metrics if metric.artifact.exists)
    warning_count = len(warnings)
    blocker_count = len(blockers)
    if malformed_sources:
        health_status = UNKNOWN
    elif blocker_count:
        health_status = UNAVAILABLE
    elif warning_count:
        health_status = DEGRADED
    else:
        health_status = HEALTHY
    recent_activity_summary = (
        ("checked_at", checked_at),
        ("latest_event_at", _last_value(event_metric.records, "created_at")),
        ("latest_event_command_id", _last_value(event_metric.records, "command_id")),
        ("latest_queued_command_id", _last_value(queue_metric.records, "command_id")),
        ("latest_audit_subject_id", _last_value(audit_decisions, "subject_id")),
    )
    return BackendHealthReport(
        schema_version=BACKEND_HEALTH_SCHEMA_VERSION,
        checked_at=checked_at,
        health_status=health_status,
        source_coverage=source_coverage,
        artifact_count=artifact_count,
        event_count=event_count,
        audit_record_count=audit_record_count,
        command_record_count=command_record_count,
        drift_count=len(drift_findings),
        warning_count=warning_count,
        blocker_count=blocker_count,
        checks=tuple(checks),
        warnings=tuple(sorted(warnings)),
        blockers=tuple(sorted(blockers)),
        recent_activity_summary=recent_activity_summary,
        drift_findings=drift_findings,
    )
