"""Stage 7.3 operator health/activity facade tests."""

from __future__ import annotations

from pathlib import Path

from scos.control_center.operator_health_activity_facade import (
    query_operator_health_activity_read_models,
    validate_operator_read_models_are_read_only,
)
from scos.control_center.operator_read_models import OperatorReadModelError, OperatorReadModelResult
from scos.control_center.tests.test_operator_health_activity import _NOW, _fixture


def test_query_operator_health_activity_read_models_returns_result(tmp_path: Path) -> None:
    _fixture(tmp_path)

    result = query_operator_health_activity_read_models(
        repo_root=tmp_path,
        checked_at=_NOW,
        activity_limit=5,
    )

    assert isinstance(result, OperatorReadModelResult)
    assert result.accepted is True
    assert result.go_no_go == "GO"
    assert result.snapshot is not None
    assert len(result.snapshot.recent_activity) <= 5


def test_query_operator_health_activity_read_models_returns_error_for_bad_path() -> None:
    result = query_operator_health_activity_read_models(
        repo_root="https://example.test/repo",
        checked_at=_NOW,
    )

    assert isinstance(result, OperatorReadModelError)
    assert result.error_code == "INVALID_OPERATOR_READ_MODEL_INPUT"


def test_validate_operator_read_models_are_read_only(tmp_path: Path) -> None:
    _fixture(tmp_path)

    result = validate_operator_read_models_are_read_only(
        repo_root=tmp_path,
        checked_at=_NOW,
    )

    assert result["ok"] is True
    assert result["write_operations_allowed"] is False
    assert result["output_path_allowed"] is False
    assert result["hash_stability_checked"] is True


def test_stage7_3_source_uses_no_forbidden_runtime_tokens() -> None:
    source_paths = (
        Path("scos/control_center/operator_read_models.py"),
        Path("scos/control_center/operator_health_activity.py"),
        Path("scos/control_center/operator_health_activity_facade.py"),
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
