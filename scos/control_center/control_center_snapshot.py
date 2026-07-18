"""Cohort 9A truthful read-only Control Center snapshot projection.

This module is the single authoritative projection boundary for the
Control Center observability bridge. It is LOCAL-ONLY and READ-ONLY:

* It composes existing certified read facades
  (``backend_health``, ``read_surface_facade``, ``operator_health_activity_facade``,
  ``command_queue``).
* It NEVER imports or invokes HVS (``hvs_adapter``, ``hvs_project_initialization_*``).
* It NEVER calls mutation-capable functions (``operator_approval.approve_command``,
  ``command_api``, ``local_backend``).
* It NEVER writes files, never opens a socket, never reads the system clock
  (``checked_at`` is supplied by the caller/route boundary).
* It projects only UI-safe fields; absolute filesystem paths, raw command argv,
  metadata payloads, authorization/lease tokens, secrets, and raw exception
  text are never serialized.

Entry point::

    python -m scos.control_center.control_center_snapshot --checked-at <ISO> [--repo-root <path>]

Prints a stable JSON ``ControlCenterSnapshot`` to stdout and exits 0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .backend_health import (
        DEFAULT_COMMAND_QUEUE_RELATIVE_PATH,
        run_backend_health_check,
    )
    from .command_queue import read_command_queue
    from .operator_health_activity import OperatorReadModelSnapshot  # type: ignore
    from .operator_health_activity_facade import (
        query_operator_health_activity_read_models,
    )
    from .operator_read_models import OperatorReadModelResult  # type: ignore
    from .read_surface_facade import query_control_center_read_surface
    from .read_surface_models import (  # type: ignore
        ReadSurfaceError,
        ReadSurfaceResult,
        ReadSurfaceSnapshot,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from backend_health import (  # type: ignore
        DEFAULT_COMMAND_QUEUE_RELATIVE_PATH,
        run_backend_health_check,
    )
    from command_queue import read_command_queue  # type: ignore
    from operator_health_activity import OperatorReadModelSnapshot  # type: ignore
    from operator_health_activity_facade import (  # type: ignore
        query_operator_health_activity_read_models,
    )
    from operator_read_models import OperatorReadModelResult  # type: ignore
    from read_surface_facade import query_control_center_read_surface  # type: ignore
    from read_surface_models import (  # type: ignore
        ReadSurfaceError,
        ReadSurfaceResult,
        ReadSurfaceSnapshot,
    )

CONTROL_CENTER_SNAPSHOT_SCHEMA_VERSION = 1
SOURCE_MODE = "LIVE_LOCAL_READ_ONLY"

# Stable, UI-safe reason codes. Never raw exception text.
RC_OK = "READ_OK"
RC_EMPTY = "READ_SOURCE_EMPTY"
RC_MISSING = "READ_SOURCE_MISSING"
RC_UNREADABLE = "READ_SOURCE_UNREADABLE"
RC_FAILED = "READ_FAILED"
RC_ERROR = "UNEXPECTED_ERROR"

# Section status vocabulary (distinct from valid-empty vs unavailable).
STATUS_AVAILABLE_WITH_DATA = "AVAILABLE_WITH_DATA"
STATUS_AVAILABLE_EMPTY = "AVAILABLE_EMPTY"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_DEGRADED = "DEGRADED"
STATUS_ERROR = "ERROR"


def _section(
    *,
    available: bool,
    status: str,
    data: Any,
    reason_code: str | None,
    observed_at: str,
) -> dict[str, Any]:
    return {
        "available": bool(available),
        "status": status,
        "data": data,
        "reason_code": reason_code,
        "observed_at": observed_at,
    }


def _safe_iso(value: str | None) -> str:
    if value:
        return str(value)
    return datetime.now(timezone.utc).isoformat()


def _build_health_section(repo_root: Path, checked_at: str) -> dict[str, Any]:
    report = run_backend_health_check(repo_root=repo_root, checked_at=checked_at)
    data = {
        "health_status": report.health_status,
        "artifact_count": report.artifact_count,
        "event_count": report.event_count,
        "command_record_count": report.command_record_count,
        "audit_record_count": report.audit_record_count,
        "warning_count": report.warning_count,
        "blocker_count": report.blocker_count,
        "source_coverage": [[key, value] for key, value in report.source_coverage],
    }
    if report.blocker_count:
        status = STATUS_DEGRADED
        reason_code = RC_UNREADABLE
    elif report.warning_count:
        status = STATUS_AVAILABLE_WITH_DATA
        reason_code = RC_OK
    else:
        status = STATUS_AVAILABLE_WITH_DATA
        reason_code = RC_OK
    return _section(
        available=True,
        status=status,
        data=data,
        reason_code=reason_code if status == STATUS_DEGRADED else None,
        observed_at=checked_at,
    )


def _build_queue_section(repo_root: Path, checked_at: str) -> dict[str, Any]:
    queue_path = repo_root / DEFAULT_COMMAND_QUEUE_RELATIVE_PATH
    commands = read_command_queue(queue_path=queue_path)
    # Redacted projection: command_id, command_type, approved_at only.
    # Raw argv (args) and metadata payloads are intentionally excluded.
    items = [
        {
            "command_id": cmd.command_id,
            "command_type": cmd.command_type,
            "approved_at": cmd.approved_at,
        }
        for cmd in commands
    ]
    if items:
        return _section(
            available=True,
            status=STATUS_AVAILABLE_WITH_DATA,
            data={"count": len(items), "items": items},
            reason_code=None,
            observed_at=checked_at,
        )
    return _section(
        available=True,
        status=STATUS_AVAILABLE_EMPTY,
        data={"count": 0, "items": []},
        reason_code=RC_EMPTY,
        observed_at=checked_at,
    )


def _read_surface_metadata(repo_root: Path, checked_at: str) -> dict[str, dict[str, Any]]:
    result = query_control_center_read_surface(
        repo_root=repo_root,
        query_type="FULL_LOCAL_READ_SURFACE",
        checked_at=checked_at,
    )
    # The facade returns a ReadSurfaceResult whose `.snapshot` holds the
    # ReadSurfaceSnapshot (or None). The earlier code checked for
    # ReadSurfaceSnapshot directly, which was always False, so records stayed
    # empty and Approvals/Evidence were falsely reported UNAVAILABLE.
    snapshot = None
    if isinstance(result, ReadSurfaceResult):
        snapshot = result.snapshot
    records = []
    if isinstance(snapshot, ReadSurfaceSnapshot) and snapshot.records:
        records = list(snapshot.records)
    by_type: dict[str, dict[str, Any]] = {}
    for record in records:
        meta = record.metadata
        if isinstance(meta, (list, tuple)):
            by_type[record.record_type] = {str(k): str(v) for k, v in meta}
        elif isinstance(meta, dict):
            by_type[record.record_type] = {str(k): str(v) for k, v in meta.items()}
    return by_type


def _build_read_surface_sections(
    repo_root: Path, checked_at: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    meta = _read_surface_metadata(repo_root, checked_at)

    approval_count = meta.get("approval_summary", {}).get("approval_count")
    audit_count = meta.get("audit_summary", {}).get("audit_record_count")
    event_count = meta.get("event_summary", {}).get("record_count")
    state = meta.get("state_summary", {})

    # Approvals section (authoritative read model exists).
    if approval_count is not None:
        approval_count_int = int(approval_count)
        # A real zero count is a valid empty state, not unavailable.
        approval_status = (
            STATUS_AVAILABLE_EMPTY if approval_count_int == 0 else STATUS_AVAILABLE_WITH_DATA
        )
        approval_data = {
            "approval_count": approval_count_int,
            "audit_record_count": int(audit_count) if audit_count is not None else 0,
        }
        approval_reason = None if approval_count_int else RC_EMPTY
    else:
        approval_status = STATUS_UNAVAILABLE
        approval_data = None
        approval_reason = RC_MISSING

    # Evidence section: the event/audit trail is the authoritative evidence read model.
    if event_count is not None or audit_count is not None:
        event_count_int = int(event_count) if event_count is not None else 0
        audit_count_int = int(audit_count) if audit_count is not None else 0
        # A real zero count is a valid empty state, not unavailable.
        evidence_status = (
            STATUS_AVAILABLE_EMPTY
            if event_count_int == 0 and audit_count_int == 0
            else STATUS_AVAILABLE_WITH_DATA
        )
        evidence_data = {
            "event_record_count": event_count_int,
            "audit_record_count": audit_count_int,
        }
        evidence_reason = (
            None
            if (event_count_int or audit_count_int)
            else RC_EMPTY
        )
    else:
        evidence_status = STATUS_UNAVAILABLE
        evidence_data = None
        evidence_reason = RC_MISSING

    # Project section: no dedicated project read model. Truthfully report the
    # underlying state tables that do exist, with an explicit "no dedicated model" note.
    project_data = {
        "state_tables_present": sorted(
            [key for key in state.keys() if key not in ("wal_enabled",)]
        ),
        "has_dedicated_project_model": False,
    }
    project_status = STATUS_AVAILABLE_WITH_DATA
    project_reason = RC_OK

    approval_section = _section(
        available=approval_status != STATUS_UNAVAILABLE,
        status=approval_status,
        data=approval_data,
        reason_code=approval_reason,
        observed_at=checked_at,
    )
    evidence_section = _section(
        available=evidence_status != STATUS_UNAVAILABLE,
        status=evidence_status,
        data=evidence_data,
        reason_code=evidence_reason,
        observed_at=checked_at,
    )
    project_section = _section(
        available=True,
        status=project_status,
        data=project_data,
        reason_code=project_reason,
        observed_at=checked_at,
    )
    return approval_section, evidence_section, project_section


def _build_activity_section(repo_root: Path, checked_at: str) -> dict[str, Any]:
    result = query_operator_health_activity_read_models(
        repo_root=repo_root, checked_at=checked_at
    )
    if not isinstance(result, OperatorReadModelResult) or result.snapshot is None:
        return _section(
            available=False,
            status=STATUS_UNAVAILABLE,
            data=None,
            reason_code=RC_MISSING,
            observed_at=checked_at,
        )
    snapshot = result.snapshot
    items = [
        {
            "activity_id": rec.activity_id,
            "activity_type": rec.activity_type,
            "status": rec.status,
            "summary": rec.summary,
            "occurred_at": rec.occurred_at,
        }
        for rec in snapshot.recent_activity
    ]
    if items:
        return _section(
            available=True,
            status=STATUS_AVAILABLE_WITH_DATA,
            data={"count": len(items), "items": items},
            reason_code=None,
            observed_at=checked_at,
        )
    return _section(
        available=True,
        status=STATUS_AVAILABLE_EMPTY,
        data={"count": 0, "items": []},
        reason_code=RC_EMPTY,
        observed_at=checked_at,
    )


def _degradation_reasons(*sections: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for section in sections:
        status = section.get("status")
        if status in (STATUS_UNAVAILABLE, STATUS_DEGRADED, STATUS_ERROR):
            reason = section.get("reason_code") or status
            reasons.append(f"{reason}")
    # de-duplicate while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            ordered.append(reason)
    return ordered


def build_control_center_snapshot(
    *,
    repo_root: str,
    checked_at: str,
) -> dict[str, Any]:
    """Build a redacted, UI-safe Control Center snapshot.

    Each subsystem is read in its own guarded call so that one subsystem
    failure degrades only its own section and never corrupts the others.
    """
    root = Path(repo_root).resolve()
    observed_at = _safe_iso(checked_at)

    # Each builder is isolated; failures become UNAVAILABLE sections.
    try:
        health = _build_health_section(root, observed_at)
    except Exception:
        health = _section(
            available=False,
            status=STATUS_UNAVAILABLE,
            data=None,
            reason_code=RC_FAILED,
            observed_at=observed_at,
        )

    try:
        queue = _build_queue_section(root, observed_at)
    except Exception:
        queue = _section(
            available=False,
            status=STATUS_UNAVAILABLE,
            data=None,
            reason_code=RC_FAILED,
            observed_at=observed_at,
        )

    try:
        approvals, evidence, projects = _build_read_surface_sections(root, observed_at)
    except Exception:
        approvals = _section(
            available=False,
            status=STATUS_UNAVAILABLE,
            data=None,
            reason_code=RC_FAILED,
            observed_at=observed_at,
        )
        evidence = _section(
            available=False,
            status=STATUS_UNAVAILABLE,
            data=None,
            reason_code=RC_FAILED,
            observed_at=observed_at,
        )
        projects = _section(
            available=False,
            status=STATUS_UNAVAILABLE,
            data=None,
            reason_code=RC_FAILED,
            observed_at=observed_at,
        )

    try:
        activity = _build_activity_section(root, observed_at)
    except Exception:
        activity = _section(
            available=False,
            status=STATUS_UNAVAILABLE,
            data=None,
            reason_code=RC_FAILED,
            observed_at=observed_at,
        )

    degradation = _degradation_reasons(health, queue, approvals, evidence, projects, activity)

    snapshot_id = hashlib.sha256(
        "|".join(
            [
                str(CONTROL_CENTER_SNAPSHOT_SCHEMA_VERSION),
                observed_at,
                health.get("status", ""),
                queue.get("status", ""),
                approvals.get("status", ""),
                evidence.get("status", ""),
                projects.get("status", ""),
                activity.get("status", ""),
            ]
        ).encode("utf-8")
    ).hexdigest()[:16]

    return {
        "schema_version": CONTROL_CENTER_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": f"ccs-{snapshot_id}",
        "generated_at": observed_at,
        "source_mode": SOURCE_MODE,
        "health": health,
        "queue_summary": queue,
        "approval_summary": approvals,
        "project_summary": projects,
        "evidence_summary": evidence,
        "recent_activity": activity,
        "degradation_reasons": degradation,
    }


def _unavailable_envelope(reason_code: str, checked_at: str) -> dict[str, Any]:
    observed_at = _safe_iso(checked_at)
    section = _section(
        available=False,
        status=STATUS_UNAVAILABLE,
        data=None,
        reason_code=reason_code,
        observed_at=observed_at,
    )
    return {
        "schema_version": CONTROL_CENTER_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": f"ccs-failed-{reason_code.lower()}",
        "generated_at": observed_at,
        "source_mode": SOURCE_MODE,
        "generation_error": reason_code,
        "health": section,
        "queue_summary": section,
        "approval_summary": section,
        "project_summary": section,
        "evidence_summary": section,
        "recent_activity": section,
        "degradation_reasons": [reason_code],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scos.control_center.control_center_snapshot",
        description="Cohort 9A truthful read-only Control Center snapshot (local-only).",
    )
    parser.add_argument("--checked-at", required=True, help="ISO-8601 observation timestamp.")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root (local path). Defaults to current directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        snapshot = build_control_center_snapshot(
            repo_root=args.repo_root, checked_at=args.checked_at
        )
        print(json.dumps(snapshot, sort_keys=True, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:  # pragma: no cover - defensive final boundary
        envelope = _unavailable_envelope(RC_ERROR, args.checked_at)
        envelope["detail"] = type(exc).__name__
        print(json.dumps(envelope, sort_keys=True, indent=2, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
