"""Stage 7.1 read surface validation tests."""

from __future__ import annotations

from pathlib import Path

from scos.control_center.read_surface_validation import (
    resolve_repo_path,
    validate_checked_at,
    validate_limit,
    validate_no_url_path,
    validate_query_type,
    validate_read_only_boundary,
    validate_repo_root_local,
    validate_requested_at,
)


def test_query_type_limit_and_timestamps() -> None:
    assert validate_query_type("FULL_LOCAL_READ_SURFACE") is None
    assert validate_query_type("BAD") is not None
    assert validate_limit(1) is None
    assert validate_limit(500) is None
    assert validate_limit(0) is not None
    assert validate_limit(501) is not None
    assert validate_requested_at("2026-07-09T00:00:00Z") is None
    assert validate_checked_at("2026-07-09T00:00:00Z") is None
    assert validate_requested_at("") is not None
    assert validate_checked_at("not a timestamp") is not None


def test_repo_root_and_url_validation(tmp_path: Path) -> None:
    assert validate_repo_root_local(tmp_path) is None
    assert validate_repo_root_local(tmp_path / "missing") is not None
    assert validate_no_url_path("https://example.test/repo", field_name="repo_root") is not None
    assert validate_no_url_path("ws://example.test/socket", field_name="repo_root") is not None


def test_resolve_repo_path_rejects_escape(tmp_path: Path) -> None:
    inside = resolve_repo_path(tmp_path, "docs/example.md", field_name="artifact")
    assert str(inside).startswith(str(tmp_path.resolve()))
    try:
        resolve_repo_path(tmp_path, tmp_path.parent / "outside.txt", field_name="artifact")
    except ValueError as exc:
        assert "inside repo_root" in str(exc)
    else:
        raise AssertionError("expected path escape rejection")


def test_read_only_boundary_reports_no_write_permissions(tmp_path: Path) -> None:
    result = validate_read_only_boundary(repo_root=tmp_path)

    assert result["ok"] is True
    assert result["write_operations_allowed"] is False
    assert result["output_path_allowed"] is False
