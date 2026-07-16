"""Stage 6.9 backend health report tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from scos.control_center.approval_audit_store import append_decision
from scos.control_center.backend_health import DEGRADED, HEALTHY, UNAVAILABLE, UNKNOWN, run_backend_health_check
from scos.control_center.host_metrics import collect_jsonl_metric, collect_sqlite_metric
from scos.control_center.sqlite_state_schema import get_index_statements, get_pragmas, get_schema_statements

_CHECKED_AT = "2026-07-09T00:00:00Z"


def _stable_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(_stable_json(payload) + "\n")


def _init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
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
            ("control_center_state", 2, "2026-07-09T00:00:00Z", "{}"),
        )
        connection.execute(
            "INSERT INTO commands (command_id, command_type, status, request_id, session_id, "
            "payload_json, created_at, updated_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("cmd-1", "RUN_SMOKE_CHECK", "queued", None, None, "{}", "2026-07-09T00:01:00Z", None, "{}"),
        )
        connection.execute(
            "INSERT INTO events (event_id, event_type, source, subject_type, subject_id, "
            "payload_json, created_at, sequence, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("evt-1", "COMMAND_QUEUED", "runner", "command", "cmd-1", "{}", "2026-07-09T00:02:00Z", 1, "{}"),
        )
        connection.execute(
            "INSERT INTO results (result_id, result_type, subject_type, subject_id, verdict, "
            "payload_json, created_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("res-1", "command_result", "command", "cmd-1", "ok", "{}", "2026-07-09T00:03:00Z", "{}"),
        )
        connection.commit()
    finally:
        connection.close()


def _healthy_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    db = tmp_path / "state" / "control.sqlite3"
    event_log = tmp_path / "events" / "events.jsonl"
    queue = tmp_path / "queue" / "commands.jsonl"
    _init_db(db)
    append_decision(
        subject_type="command",
        subject_id="cmd-1",
        decision="approved",
        decided_by="operator",
        decided_at="2026-07-09T00:04:00Z",
        repo_root=tmp_path,
        db_path=db,
    )
    _append_jsonl(queue, {
        "command_id": "cmd-1",
        "command_type": "RUN_SMOKE_CHECK",
        "approved_by": "operator",
        "approved_at": "2026-07-09T00:04:00Z",
        "args": [],
        "metadata": [],
    })
    _append_jsonl(event_log, {
        "event_id": "evt-jsonl-1",
        "command_id": "cmd-1",
        "event_type": "COMMAND_COMPLETED",
        "created_at": "2026-07-09T00:05:00Z",
        "status": "success",
        "message": "completed",
        "metadata": [],
    })
    return db, event_log, queue


def _file_hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def test_backend_health_healthy_report_with_all_artifacts(tmp_path: Path) -> None:
    db, event_log, queue = _healthy_fixture(tmp_path)

    report = run_backend_health_check(
        repo_root=tmp_path,
        checked_at=_CHECKED_AT,
        state_db_path=db,
        event_log_path=event_log,
        command_queue_path=queue,
    )

    assert report.health_status == HEALTHY
    assert report.artifact_count == 4
    assert report.event_count == 2
    assert report.audit_record_count == 1
    assert report.command_record_count == 2
    assert report.drift_count == 0
    assert report.warning_count == 0
    assert report.blocker_count == 0
    assert dict(report.recent_activity_summary)["latest_event_command_id"] == "cmd-1"


def test_backend_health_degraded_when_optional_artifact_missing(tmp_path: Path) -> None:
    db, event_log, queue = _healthy_fixture(tmp_path)
    event_log.unlink()

    report = run_backend_health_check(
        repo_root=tmp_path,
        checked_at=_CHECKED_AT,
        state_db_path=db,
        event_log_path=event_log,
        command_queue_path=queue,
    )

    assert report.health_status == DEGRADED
    assert "event_log: missing artifact" in report.warnings
    assert report.blocker_count == 0


def test_backend_health_unavailable_when_required_sqlite_is_malformed(tmp_path: Path) -> None:
    db = tmp_path / "state" / "broken.sqlite3"
    db.parent.mkdir(parents=True)
    db.write_text("not sqlite", encoding="utf-8")

    report = run_backend_health_check(
        repo_root=tmp_path,
        checked_at=_CHECKED_AT,
        state_db_path=db,
    )

    assert report.health_status == UNAVAILABLE
    assert any("state_db" in blocker for blocker in report.blockers)


def test_backend_health_deterministic_for_same_inputs(tmp_path: Path) -> None:
    db, event_log, queue = _healthy_fixture(tmp_path)

    first = run_backend_health_check(
        repo_root=tmp_path,
        checked_at=_CHECKED_AT,
        state_db_path=db,
        event_log_path=event_log,
        command_queue_path=queue,
    )
    second = run_backend_health_check(
        repo_root=tmp_path,
        checked_at=_CHECKED_AT,
        state_db_path=db,
        event_log_path=event_log,
        command_queue_path=queue,
    )

    assert first.to_dict() == second.to_dict()


def test_backend_health_does_not_mutate_artifacts(tmp_path: Path) -> None:
    db, event_log, queue = _healthy_fixture(tmp_path)
    paths = (db, event_log, queue)
    before = _file_hashes(paths)

    run_backend_health_check(
        repo_root=tmp_path,
        checked_at=_CHECKED_AT,
        state_db_path=db,
        event_log_path=event_log,
        command_queue_path=queue,
    )

    assert _file_hashes(paths) == before


def test_jsonl_malformed_line_handling(tmp_path: Path) -> None:
    queue = tmp_path / "queue.jsonl"
    queue.write_text('{"command_id":"cmd-1"}\n{broken\n', encoding="utf-8")

    metric = collect_jsonl_metric(tmp_path, queue, "command_queue")

    assert metric.record_count == 1
    assert metric.malformed_line_count == 1


def test_sqlite_wal_readability_check(tmp_path: Path) -> None:
    db = tmp_path / "state.sqlite3"
    _init_db(db)

    metric = collect_sqlite_metric(
        tmp_path,
        db,
        "state_db",
        expected_tables=("commands", "events", "audit_ledger"),
    )

    assert metric.readable is True
    assert metric.wal_enabled is True
    assert dict(metric.table_counts)["commands"] == 1


def test_backend_health_rejects_unsafe_local_paths(tmp_path: Path) -> None:
    report = run_backend_health_check(
        repo_root=tmp_path,
        checked_at=_CHECKED_AT,
        state_db_path=tmp_path / "state.sqlite3",
        event_log_path=tmp_path.parent / "outside.jsonl",
    )

    assert report.health_status == UNAVAILABLE
    assert "event_log: unsafe local path" in report.blockers


def test_backend_health_unknown_when_evidence_is_malformed(tmp_path: Path) -> None:
    db, event_log, queue = _healthy_fixture(tmp_path)
    event_log.write_text('{"event_id":"evt-jsonl-1"}\n{broken\n', encoding="utf-8")

    report = run_backend_health_check(
        repo_root=tmp_path,
        checked_at=_CHECKED_AT,
        state_db_path=db,
        event_log_path=event_log,
        command_queue_path=queue,
    )

    assert report.health_status == UNKNOWN
    assert "event_log: malformed JSONL records found" in report.blockers


def test_backend_health_errors_are_categorized_without_secret_detail(tmp_path: Path) -> None:
    report = run_backend_health_check(
        repo_root=tmp_path,
        checked_at=_CHECKED_AT,
        state_db_path="https://user:cohort9g-password@example.invalid/state.sqlite3",
    )
    text = json.dumps(report.to_dict(), sort_keys=True)

    assert report.health_status == UNAVAILABLE
    assert "URL_PATH_REJECTED" in text
    assert "cohort9g-password" not in text


def test_backend_health_source_uses_no_clock_random_uuid_or_network_subprocess() -> None:
    source = Path("scos/control_center/backend_health.py").read_text(encoding="utf-8")
    host_source = Path("scos/control_center/host_metrics.py").read_text(encoding="utf-8")
    drift_source = Path("scos/control_center/drift_detection.py").read_text(encoding="utf-8")
    combined = source + host_source + drift_source
    forbidden = (
        "datetime." + "now",
        "time." + "time",
        "random.",
        "uuid",
        "import " + "subprocess",
        "import " + "socket",
        "requests",
        "urllib." + "request",
    )
    for token in forbidden:
        assert token not in combined
