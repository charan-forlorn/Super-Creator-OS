"""Stage 7.3 operator health/activity builder tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scos.control_center.approval_audit_models import GENESIS_PREV_HASH, ApprovalDecision, AuditEntry
from scos.control_center.operator_health_activity import (
    build_operator_health_activity_snapshot,
    evaluate_operator_readiness,
)
from scos.control_center.operator_read_models import (
    HEALTH_SIGNAL_TYPES,
    OperatorFreshnessStatus,
    OperatorHealthSignal,
    OperatorReadModelError,
    OperatorReadModelSnapshot,
)
from scos.control_center.sqlite_state_schema import (
    DEFAULT_STATE_DB_RELATIVE_PATH,
    get_index_statements,
    get_pragmas,
    get_schema_statements,
)

_NOW = "2026-07-09T00:00:00Z"
_REQUIRED_STAGE6 = (
    "scos/control_center/backend_health.py",
    "scos/control_center/drift_detection.py",
    "scos/control_center/sqlite_state_schema.py",
    "scos/control_center/host_metrics.py",
    "docs/roadmap/STAGE7_HANDOFF.md",
    "docs/specification/STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md",
)
_REQUIRED_STAGE7_1 = (
    "docs/specification/CONTROL_CENTER_READ_SURFACE_CONTRACT.md",
    "docs/specification/STAGE7_READ_ONLY_QUERY_BOUNDARY.md",
    "docs/certification/Stage-7.1-plan.md",
)


def _stable_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_required_sources(root: Path) -> None:
    for rel_path in _REQUIRED_STAGE6 + _REQUIRED_STAGE7_1:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# required source\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(_stable_json(payload) + "\n")


def _init_db(root: Path) -> None:
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
        entry = AuditEntry.of(sequence=1, prev_hash=GENESIS_PREV_HASH, decision=decision)
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


def _fixture(root: Path, *, include_runtime: bool = True) -> None:
    _write_required_sources(root)
    if not include_runtime:
        return
    _init_db(root)
    _append_jsonl(
        root / "scos/work/control_center/events/command_events.jsonl",
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
        root / "scos/work/control_center/queue/approved_commands.jsonl",
        {
            "command_id": "cmd-1",
            "command_type": "RUN_SMOKE_CHECK",
            "approved_by": "operator",
            "approved_at": _NOW,
            "args": [],
            "metadata": [],
        },
    )


def test_snapshot_contains_required_health_signals_and_activity(tmp_path: Path) -> None:
    _fixture(tmp_path)

    snapshot = build_operator_health_activity_snapshot(
        repo_root=tmp_path,
        checked_at=_NOW,
        activity_limit=25,
    )

    assert isinstance(snapshot, OperatorReadModelSnapshot)
    assert {signal.signal_type for signal in snapshot.health_signals} == set(HEALTH_SIGNAL_TYPES)
    assert {signal.status for signal in snapshot.health_signals} <= {
        "HEALTHY",
        "DEGRADED",
        "STALE",
        "MISSING",
        "BLOCKED",
        "UNKNOWN",
    }
    assert any(activity.activity_type == "EVENT_ACTIVITY" for activity in snapshot.recent_activity)
    assert snapshot.go_no_go == "GO"


def test_snapshot_is_deterministic_and_activity_limit_is_applied(tmp_path: Path) -> None:
    _fixture(tmp_path)

    first = build_operator_health_activity_snapshot(repo_root=tmp_path, checked_at=_NOW, activity_limit=3)
    second = build_operator_health_activity_snapshot(repo_root=tmp_path, checked_at=_NOW, activity_limit=3)

    assert isinstance(first, OperatorReadModelSnapshot)
    assert isinstance(second, OperatorReadModelSnapshot)
    assert first.to_dict() == second.to_dict()
    assert len(first.recent_activity) == 3


def test_missing_optional_evidence_is_not_marked_healthy(tmp_path: Path) -> None:
    _fixture(tmp_path, include_runtime=False)

    snapshot = build_operator_health_activity_snapshot(repo_root=tmp_path, checked_at=_NOW)

    assert isinstance(snapshot, OperatorReadModelSnapshot)
    by_type = {signal.signal_type: signal for signal in snapshot.health_signals}
    assert by_type["STATE_STORE_HEALTH"].status == "MISSING"
    assert by_type["EVENT_STREAM_HEALTH"].status == "MISSING"
    assert by_type["APPROVAL_HEALTH"].status == "MISSING"
    assert by_type["AUDIT_HEALTH"].status == "MISSING"
    assert by_type["HOST_METRICS"].status == "MISSING"
    assert all(signal.status != "HEALTHY" for signal in by_type.values() if signal.freshness.freshness_level == "MISSING")


def test_missing_required_evidence_blocks_snapshot(tmp_path: Path) -> None:
    _fixture(tmp_path)
    (tmp_path / "docs/roadmap/STAGE7_HANDOFF.md").unlink()

    snapshot = build_operator_health_activity_snapshot(repo_root=tmp_path, checked_at=_NOW)

    assert isinstance(snapshot, OperatorReadModelSnapshot)
    assert snapshot.go_no_go == "NO_GO"
    assert snapshot.blockers
    assert any(signal.status == "BLOCKED" for signal in snapshot.health_signals)


def test_invalid_inputs_return_operator_error(tmp_path: Path) -> None:
    result = build_operator_health_activity_snapshot(
        repo_root=tmp_path / "missing",
        checked_at=_NOW,
    )

    assert isinstance(result, OperatorReadModelError)
    assert result.error_code == "INVALID_OPERATOR_READ_MODEL_INPUT"


def test_evaluate_operator_readiness_never_treats_unknown_as_go() -> None:
    freshness = OperatorHealthSignal(
        signal_id="signal-1",
        signal_type="BACKEND_HEALTH",
        status="UNKNOWN",
        severity="warning",
        summary="unknown",
        source_stage="Stage 7.3",
        freshness=OperatorFreshnessStatus(_NOW, "source-1", "BACKEND_HEALTH", True, False, False, "UNKNOWN", ()),
        metadata=(),
    )

    readiness = evaluate_operator_readiness(
        health_signals=(freshness,),
        recent_activity=(),
        checked_at=_NOW,
    )

    assert readiness["go_no_go"] == "GO"
    assert readiness["warnings"] == ("BACKEND_HEALTH: unknown",)
