"""Stage 7.1 read surface snapshot tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from scos.control_center.read_surface_models import ReadSurfaceError, ReadSurfaceSnapshot
from scos.control_center.read_surface_query import create_read_surface_query
from scos.control_center.read_surface_snapshot import build_read_surface_snapshot
from scos.control_center.approval_audit_models import (
    GENESIS_PREV_HASH,
    ApprovalDecision,
    AuditEntry,
)
from scos.control_center.sqlite_state_schema import (
    DEFAULT_STATE_DB_RELATIVE_PATH,
    get_index_statements,
    get_pragmas,
    get_schema_statements,
)

_NOW = "2026-07-09T00:00:00Z"
_REQUIRED_FILES = (
    "scos/control_center/backend_health.py",
    "scos/control_center/drift_detection.py",
    "scos/control_center/sqlite_state_schema.py",
    "scos/control_center/host_metrics.py",
    "docs/roadmap/STAGE7_HANDOFF.md",
    "docs/specification/STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md",
)


def _stable_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_required_sources(root: Path) -> None:
    for rel_path in _REQUIRED_FILES:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# required source\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(_stable_json(payload) + "\n")


def _init_db(root: Path) -> Path:
    db = root / DEFAULT_STATE_DB_RELATIVE_PATH
    db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db))
    try:
        for pragma in get_pragmas():
            connection.execute(pragma)
        for statement in get_schema_statements():
            connection.execute(statement)
        for statement in get_index_statements():
            connection.execute(statement)
        connection.execute(
            "INSERT INTO state_schema (schema_name, schema_version, applied_at, metadata_json) "
            "VALUES (?, ?, ?, ?)",
            ("control_center_state", 2, _NOW, "{}"),
        )
        connection.execute(
            "INSERT INTO commands (command_id, command_type, status, request_id, session_id, "
            "payload_json, created_at, updated_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("cmd-1", "RUN_SMOKE_CHECK", "queued", None, None, "{}", _NOW, None, "{}"),
        )
        connection.execute(
            "INSERT INTO events (event_id, event_type, source, subject_type, subject_id, "
            "payload_json, created_at, sequence, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("evt-1", "COMMAND_QUEUED", "runner", "command", "cmd-1", "{}", _NOW, 1, "{}"),
        )
        connection.execute(
            "INSERT INTO results (result_id, result_type, subject_type, subject_id, verdict, "
            "payload_json, created_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("res-1", "command_result", "command", "cmd-1", "ok", "{}", _NOW, "{}"),
        )
        decision = ApprovalDecision.of(
            subject_type="command",
            subject_id="cmd-1",
            decision="approved",
            decided_by="operator",
            decided_at=_NOW,
        )
        entry = AuditEntry.of(
            sequence=1,
            prev_hash=GENESIS_PREV_HASH,
            decision=decision,
        )
        connection.execute(
            "INSERT INTO audit_ledger (entry_id, sequence, prev_hash, entry_hash, decision_id, "
            "subject_type, subject_id, decision, decided_by, decided_at, reason, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.entry_id,
                entry.sequence,
                entry.prev_hash,
                entry.entry_hash,
                entry.decision_id,
                entry.subject_type,
                entry.subject_id,
                entry.decision,
                entry.decided_by,
                entry.decided_at,
                entry.reason,
                entry.metadata_json,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return db


def _fixture(root: Path) -> tuple[Path, Path, Path]:
    _write_required_sources(root)
    db = _init_db(root)
    event_log = root / "scos/work/control_center/events/command_events.jsonl"
    queue = root / "scos/work/control_center/queue/approved_commands.jsonl"
    _append_jsonl(
        event_log,
        {
            "event_id": "evt-jsonl-1",
            "command_id": "cmd-1",
            "event_type": "COMMAND_COMPLETED",
            "created_at": _NOW,
            "status": "success",
            "message": "completed",
            "metadata": [],
        },
    )
    _append_jsonl(
        queue,
        {
            "command_id": "cmd-1",
            "command_type": "RUN_SMOKE_CHECK",
            "approved_by": "operator",
            "approved_at": _NOW,
            "args": [],
            "metadata": [],
        },
    )
    return db, event_log, queue


def _hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def test_snapshot_reads_stage6_artifacts_without_mutation(tmp_path: Path) -> None:
    db, event_log, queue = _fixture(tmp_path)
    before = _hashes((db, event_log, queue))
    query = create_read_surface_query(
        query_type="FULL_LOCAL_READ_SURFACE",
        requested_at=_NOW,
        limit=10,
    )

    snapshot = build_read_surface_snapshot(
        repo_root=tmp_path,
        query=query,
        checked_at=_NOW,
    )

    assert isinstance(snapshot, ReadSurfaceSnapshot)
    assert snapshot.blockers == ()
    assert snapshot.readiness.to_dict()["go_no_go"] == "GO"
    assert any(record.record_type == "state_summary" for record in snapshot.records)
    assert any(record.record_type == "event_summary" for record in snapshot.records)
    assert any(record.record_type == "approval_summary" for record in snapshot.records)
    assert any(record.record_type == "audit_summary" for record in snapshot.records)
    assert _hashes((db, event_log, queue)) == before


def test_snapshot_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    _fixture(tmp_path)
    query = create_read_surface_query(
        query_type="FULL_LOCAL_READ_SURFACE",
        requested_at=_NOW,
    )

    first = build_read_surface_snapshot(repo_root=tmp_path, query=query, checked_at=_NOW)
    second = build_read_surface_snapshot(repo_root=tmp_path, query=query, checked_at=_NOW)

    assert isinstance(first, ReadSurfaceSnapshot)
    assert isinstance(second, ReadSurfaceSnapshot)
    assert first.to_dict() == second.to_dict()


def test_missing_optional_runtime_artifacts_are_warnings(tmp_path: Path) -> None:
    _write_required_sources(tmp_path)
    query = create_read_surface_query(
        query_type="FULL_LOCAL_READ_SURFACE",
        requested_at=_NOW,
    )

    snapshot = build_read_surface_snapshot(repo_root=tmp_path, query=query, checked_at=_NOW)

    assert isinstance(snapshot, ReadSurfaceSnapshot)
    assert snapshot.blockers == ()
    assert any("missing optional runtime artifact" in warning for warning in snapshot.warnings)


def test_missing_required_source_is_blocker(tmp_path: Path) -> None:
    _fixture(tmp_path)
    (tmp_path / "docs/roadmap/STAGE7_HANDOFF.md").unlink()
    query = create_read_surface_query(
        query_type="FULL_LOCAL_READ_SURFACE",
        requested_at=_NOW,
    )

    snapshot = build_read_surface_snapshot(repo_root=tmp_path, query=query, checked_at=_NOW)

    assert isinstance(snapshot, ReadSurfaceSnapshot)
    assert any("missing_required_source" in blocker for blocker in snapshot.blockers)
    assert snapshot.readiness.to_dict()["go_no_go"] == "NO_GO"


def test_snapshot_rejects_bad_inputs(tmp_path: Path) -> None:
    query = create_read_surface_query(
        query_type="FULL_LOCAL_READ_SURFACE",
        requested_at=_NOW,
    )

    missing_root = build_read_surface_snapshot(
        repo_root=tmp_path / "missing",
        query=query,
        checked_at=_NOW,
    )
    bad_query = build_read_surface_snapshot(
        repo_root=tmp_path,
        query="not-query",  # type: ignore[arg-type]
        checked_at=_NOW,
    )

    assert isinstance(missing_root, ReadSurfaceError)
    assert isinstance(bad_query, ReadSurfaceError)
