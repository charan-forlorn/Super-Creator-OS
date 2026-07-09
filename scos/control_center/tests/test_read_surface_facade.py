"""Stage 7.1 read surface facade tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from scos.control_center.read_surface_facade import (
    query_control_center_read_surface,
    validate_read_surface_is_read_only,
)
from scos.control_center.read_surface_models import ReadSurfaceError, ReadSurfaceResult
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


def _fixture(root: Path) -> None:
    for rel_path in _REQUIRED_FILES:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# required source\n", encoding="utf-8")
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
        connection.commit()
    finally:
        connection.close()


def test_facade_returns_result_for_full_read_surface(tmp_path: Path) -> None:
    _fixture(tmp_path)

    result = query_control_center_read_surface(
        repo_root=tmp_path,
        query_type="FULL_LOCAL_READ_SURFACE",
        checked_at=_NOW,
    )

    assert isinstance(result, ReadSurfaceResult)
    assert result.accepted is True
    assert result.go_no_go == "GO"
    assert result.snapshot is not None
    assert result.readiness_score <= 100


def test_facade_returns_error_for_invalid_query() -> None:
    result = query_control_center_read_surface(
        repo_root="https://example.test/repo",
        query_type="BAD",
        checked_at=_NOW,
    )

    assert isinstance(result, ReadSurfaceError)
    assert result.error_code in {"INVALID_QUERY", "INVALID_SNAPSHOT_INPUT"}


def test_read_only_validation_facade(tmp_path: Path) -> None:
    outcome = validate_read_surface_is_read_only(
        repo_root=tmp_path,
        checked_at=_NOW,
    )

    assert outcome["ok"] is True
    assert outcome["checked_at"] == _NOW
    assert outcome["write_operations_allowed"] is False
    assert outcome["output_path_allowed"] is False


def test_read_surface_source_uses_no_forbidden_runtime_tokens() -> None:
    source_paths = (
        Path("scos/control_center/read_surface_models.py"),
        Path("scos/control_center/read_surface_query.py"),
        Path("scos/control_center/read_surface_snapshot.py"),
        Path("scos/control_center/read_surface_facade.py"),
        Path("scos/control_center/read_surface_validation.py"),
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
        "browser automation",
        "GUI automation",
    )
    for token in forbidden:
        assert token not in combined
