"""Read-only deterministic drift detection for Stage 6.9 observability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DRIFT_DETECTION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DriftFinding:
    finding_id: str
    drift_type: str
    severity: str
    source: str
    subject_type: str
    subject_id: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "drift_type": self.drift_type,
            "severity": self.severity,
            "source": self.source,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "detail": self.detail,
        }


def _stable_finding_id(drift_type: str, source: str, subject_type: str, subject_id: str) -> str:
    import hashlib

    payload = "|".join((drift_type, source, subject_type, subject_id))
    return "drift-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _finding(
    *,
    drift_type: str,
    severity: str,
    source: str,
    subject_type: str,
    subject_id: str,
    detail: str,
) -> DriftFinding:
    return DriftFinding(
        finding_id=_stable_finding_id(drift_type, source, subject_type, subject_id),
        drift_type=drift_type,
        severity=severity,
        source=source,
        subject_type=subject_type,
        subject_id=subject_id,
        detail=detail,
    )


def detect_backend_drift(
    *,
    state_commands: tuple[dict[str, Any], ...] = (),
    state_sessions: tuple[dict[str, Any], ...] = (),
    state_events: tuple[dict[str, Any], ...] = (),
    state_results: tuple[dict[str, Any], ...] = (),
    queue_commands: tuple[dict[str, Any], ...] = (),
    event_log_records: tuple[dict[str, Any], ...] = (),
    audit_decisions: tuple[dict[str, Any], ...] = (),
    audit_chain_ok: bool | None = None,
    malformed_sources: tuple[str, ...] = (),
) -> tuple[DriftFinding, ...]:
    """Compare local artifacts and return deterministic drift findings."""
    findings: list[DriftFinding] = []
    command_ids = {
        str(record.get("command_id"))
        for record in state_commands
        if record.get("command_id") is not None
    }
    command_ids.update(
        str(record.get("command_id"))
        for record in queue_commands
        if record.get("command_id") is not None
    )
    command_event_ids = {
        str(record.get("command_id"))
        for record in event_log_records
        if record.get("command_id") is not None
    }
    command_event_ids.update(
        str(record.get("subject_id"))
        for record in state_events
        if str(record.get("subject_type")) == "command" and record.get("subject_id") is not None
    )
    result_subject_ids = {
        str(record.get("subject_id"))
        for record in state_results
        if str(record.get("subject_type")) == "command" and record.get("subject_id") is not None
    }

    for record in queue_commands:
        command_id = str(record.get("command_id", ""))
        if command_id and command_id not in command_event_ids and command_id not in result_subject_ids:
            findings.append(_finding(
                drift_type="queued_command_missing_result_or_event",
                severity="warning",
                source="command_queue",
                subject_type="command",
                subject_id=command_id,
                detail="command exists in queue but no matching event or result evidence was found",
            ))

    known_session_ids = {
        str(record.get("session_id"))
        for record in state_sessions
        if record.get("session_id") is not None
    }
    for record in event_log_records:
        command_id = str(record.get("command_id", ""))
        if command_id and command_id not in command_ids:
            findings.append(_finding(
                drift_type="event_references_unknown_command",
                severity="warning",
                source="event_log",
                subject_type="command",
                subject_id=command_id,
                detail="event log references a command missing from queue and state command records",
            ))
    for record in state_events:
        subject_type = str(record.get("subject_type", ""))
        subject_id = str(record.get("subject_id", ""))
        if subject_type == "command" and subject_id and subject_id not in command_ids:
            findings.append(_finding(
                drift_type="event_references_unknown_command",
                severity="warning",
                source="sqlite_events",
                subject_type="command",
                subject_id=subject_id,
                detail="SQLite event references a command missing from queue and state command records",
            ))
        if subject_type == "session" and subject_id and subject_id not in known_session_ids:
            findings.append(_finding(
                drift_type="event_references_unknown_session",
                severity="warning",
                source="sqlite_events",
                subject_type="session",
                subject_id=subject_id,
                detail="SQLite event references an unknown session",
            ))

    for record in audit_decisions:
        subject_type = str(record.get("subject_type", ""))
        subject_id = str(record.get("subject_id", ""))
        if subject_type == "command" and subject_id and subject_id not in command_ids:
            findings.append(_finding(
                drift_type="approval_missing_command_evidence",
                severity="warning",
                source="audit_ledger",
                subject_type="command",
                subject_id=subject_id,
                detail="approval decision exists without matching command evidence",
            ))

    if audit_chain_ok is False:
        findings.append(_finding(
            drift_type="audit_chain_verification_failed",
            severity="blocker",
            source="audit_ledger",
            subject_type="audit_ledger",
            subject_id="audit_ledger",
            detail="audit ledger hash chain verification failed",
        ))

    for source in sorted(malformed_sources):
        findings.append(_finding(
            drift_type="malformed_source_records",
            severity="blocker",
            source=source,
            subject_type="artifact",
            subject_id=source,
            detail="artifact contains malformed records and cannot be trusted",
        ))

    return tuple(sorted(findings, key=lambda item: item.finding_id))
