"""Stage 8.2 file snapshot transport validation tests."""

from __future__ import annotations

from pathlib import Path

from scos.control_center.file_snapshot_transport_validation import (
    validate_checked_at,
    validate_local_repo_root,
    validate_no_forbidden_transport_behavior,
    validate_no_url_path,
    validate_path_contained,
    validate_payload_is_json_object,
    validate_snapshot_output_path,
)


def test_checked_at_is_required_and_caller_supplied() -> None:
    ok, errors = validate_checked_at("")

    assert ok is False
    assert any("checked_at" in error for error in errors)


def test_url_paths_are_rejected() -> None:
    for value in ("http://example.test", "https://example.test", "ws://local", "wss://local", "ftp://x", "file://x"):
        ok, errors = validate_no_url_path(value)
        assert ok is False
        assert errors


def test_output_path_traversal_and_outside_repo_are_rejected() -> None:
    ok, errors = validate_snapshot_output_path(repo_root=Path("."), output_path=Path("..") / "outside.json")

    assert ok is False
    assert any("inside repo_root" in error for error in errors)


def test_output_path_inside_repo_is_allowed() -> None:
    ok, errors = validate_snapshot_output_path(
        repo_root=Path("."),
        output_path=Path("work") / "stage8_2_validation" / "snapshot.json",
    )

    assert ok is True
    assert errors == ()


def test_path_containment_uses_resolved_paths() -> None:
    assert validate_path_contained(parent=Path("."), child=Path("docs")) is True
    assert validate_path_contained(parent=Path("."), child=Path("..")) is False


def test_local_repo_root_validation_rejects_remote_or_missing_path() -> None:
    remote_ok, remote_errors = validate_local_repo_root("https://example.test/repo")
    missing_ok, missing_errors = validate_local_repo_root("missing-stage8-2-repo")

    assert remote_ok is False
    assert remote_errors
    assert missing_ok is False
    assert missing_errors


def test_payload_must_be_json_object() -> None:
    ok, errors = validate_payload_is_json_object([])  # type: ignore[arg-type]

    assert ok is False
    assert errors == ("payload must be a JSON object",)


def test_forbidden_behavior_scan_catches_runtime_tokens() -> None:
    ok, errors = validate_no_forbidden_transport_behavior("value = 'WebSocket'; other = 'subprocess'")

    assert ok is False
    assert any("WebSocket" in error for error in errors)
    assert any("subprocess" in error for error in errors)


def test_clean_source_passes_forbidden_behavior_scan() -> None:
    ok, errors = validate_no_forbidden_transport_behavior("VALUE = 'manual file snapshot only'")

    assert ok is True
    assert errors == ()
