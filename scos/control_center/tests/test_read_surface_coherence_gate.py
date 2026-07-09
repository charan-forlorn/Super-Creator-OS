"""Stage 7.2 read surface coherence gate tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from scos.control_center.approval_audit_models import (
    GENESIS_PREV_HASH,
    ApprovalDecision,
    AuditEntry,
)
from scos.control_center.read_surface_coherence_gate import (
    compare_read_surface_to_stage6_artifacts,
    run_read_surface_coherence_gate,
    validate_read_surface_contract_alignment,
    validate_read_surface_non_mutation_contract,
)
from scos.control_center.read_surface_coherence_models import (
    ReadSurfaceCoherenceError,
    ReadSurfaceCoherenceIssue,
    ReadSurfaceCoherenceReport,
    ReadSurfaceContractCheck,
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


def _fixture(root: Path, *, include_runtime: bool = True) -> tuple[Path, ...]:
    _write_required_sources(root)
    if not include_runtime:
        return ()
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


def test_contract_alignment_checks_stage7_1_exports_and_docs(tmp_path: Path) -> None:
    _fixture(tmp_path, include_runtime=False)

    checks = validate_read_surface_contract_alignment(
        repo_root=tmp_path,
        checked_at=_NOW,
    )

    assert isinstance(checks, tuple)
    assert all(isinstance(check, ReadSurfaceContractCheck) for check in checks)
    assert all(check.status == "success" for check in checks)


def test_coherence_gate_passes_with_complete_fixture_without_mutation(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    before = _hashes(paths)

    report = run_read_surface_coherence_gate(
        repo_root=tmp_path,
        checked_at=_NOW,
    )

    assert isinstance(report, ReadSurfaceCoherenceReport)
    assert report.accepted is True
    assert report.go_no_go == "GO"
    assert report.blockers == ()
    assert _hashes(paths) == before


def test_missing_optional_artifacts_are_warnings(tmp_path: Path) -> None:
    _fixture(tmp_path, include_runtime=False)

    issues = compare_read_surface_to_stage6_artifacts(
        repo_root=tmp_path,
        checked_at=_NOW,
    )
    report = run_read_surface_coherence_gate(
        repo_root=tmp_path,
        checked_at=_NOW,
    )

    assert isinstance(issues, tuple)
    assert any(
        isinstance(issue, ReadSurfaceCoherenceIssue)
        and issue.issue_type == "missing_optional_stage6_artifact"
        and not issue.blocker
        for issue in issues
    )
    assert isinstance(report, ReadSurfaceCoherenceReport)
    assert report.accepted is True
    assert report.warnings


def test_missing_required_stage6_source_is_blocker(tmp_path: Path) -> None:
    _fixture(tmp_path)
    (tmp_path / "docs/roadmap/STAGE7_HANDOFF.md").unlink()

    report = run_read_surface_coherence_gate(
        repo_root=tmp_path,
        checked_at=_NOW,
    )

    assert isinstance(report, ReadSurfaceCoherenceReport)
    assert report.accepted is False
    assert report.go_no_go == "NO_GO"
    assert any("required Stage 6 source artifact is missing" in blocker for blocker in report.blockers)


def test_non_mutation_contract_returns_checks(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    before = _hashes(paths)

    checks = validate_read_surface_non_mutation_contract(
        repo_root=tmp_path,
        checked_at=_NOW,
    )

    assert isinstance(checks, tuple)
    assert all(check.status == "success" for check in checks)
    assert _hashes(paths) == before


def test_gate_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    _fixture(tmp_path)

    first = run_read_surface_coherence_gate(repo_root=tmp_path, checked_at=_NOW)
    second = run_read_surface_coherence_gate(repo_root=tmp_path, checked_at=_NOW)

    assert isinstance(first, ReadSurfaceCoherenceReport)
    assert isinstance(second, ReadSurfaceCoherenceReport)
    assert first.to_dict() == second.to_dict()


def test_invalid_inputs_return_error(tmp_path: Path) -> None:
    result = run_read_surface_coherence_gate(
        repo_root=tmp_path / "missing",
        checked_at=_NOW,
    )

    assert isinstance(result, ReadSurfaceCoherenceError)
    assert result.error_code == "INVALID_COHERENCE_INPUT"


def test_stage7_2_source_uses_no_forbidden_runtime_tokens() -> None:
    source_paths = (
        Path("scos/control_center/read_surface_coherence_models.py"),
        Path("scos/control_center/read_surface_coherence_gate.py"),
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)
    forbidden = (
        "http." + "server",
        "fast" + "api",
        "flask",
        "django",
        "requests",
        "urllib." + "request",
        "sub" + "process",
        "shell=True",
        "time." + "time",
        "datetime." + "now",
        "uuid",
        "random",
        "Web" + "Socket",
        "Event" + "Source",
        "set" + "Interval",
        "set" + "Timeout",
        "fetch(",
        "XML" + "HttpRequest",
        "axios",
        "clipboard",
        "route." + "ts",
        "middleware." + "ts",
        '"use ' + 'server"',
    )
    for token in forbidden:
        assert token not in combined
