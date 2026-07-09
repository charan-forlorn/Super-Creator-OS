"""Stage 8.2 manual file snapshot refresh transport tests."""

from __future__ import annotations

import atexit
import hashlib
import json
import shutil
from pathlib import Path

from scos.control_center.file_snapshot_refresh_transport import (
    build_file_snapshot_transport_payload,
    refresh_file_snapshot_transport,
    validate_file_snapshot_transport_boundary,
)
from scos.control_center.file_snapshot_transport_models import (
    FileSnapshotTransportError,
    FileSnapshotTransportResult,
)

_NOW = "2026-07-10T06:00:00Z"
_SCRATCH_ROOT = Path("work") / "stage8_2_file_snapshot_tests"


def _scratch(name: str) -> Path:
    root = _SCRATCH_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    atexit.register(lambda target=root: shutil.rmtree(target, ignore_errors=True))
    return root


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_build_payload_does_not_write_any_file() -> None:
    target = _scratch("build_no_write") / "snapshot.json"

    result = build_file_snapshot_transport_payload(repo_root=Path("."), checked_at=_NOW)

    assert isinstance(result, FileSnapshotTransportResult)
    assert target.exists() is False
    assert result.output_path is None
    assert result.manifest is not None
    assert result.payload is not None


def test_refresh_writes_exactly_one_snapshot_json_file() -> None:
    output_dir = _scratch("refresh_once")
    output_path = output_dir / "snapshot.json"

    result = refresh_file_snapshot_transport(repo_root=Path("."), output_path=output_path, checked_at=_NOW)

    assert isinstance(result, FileSnapshotTransportResult)
    assert result.accepted is True
    assert output_path.exists()
    files = [path for path in output_dir.rglob("*") if path.is_file()]
    assert files == [output_path]
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["transport_mode"] == "FILE_SNAPSHOT_REFRESH"
    assert payload["manifest"]["snapshot_id"] == result.snapshot_id
    assert payload["payload"]["snapshot_id"] == result.snapshot_id


def test_refresh_fails_when_output_exists_and_overwrite_false() -> None:
    output_path = _scratch("overwrite_false") / "snapshot.json"
    first = refresh_file_snapshot_transport(repo_root=Path("."), output_path=output_path, checked_at=_NOW)
    second = refresh_file_snapshot_transport(repo_root=Path("."), output_path=output_path, checked_at=_NOW)

    assert isinstance(first, FileSnapshotTransportResult)
    assert isinstance(second, FileSnapshotTransportError)
    assert second.error_code == "FILE_SNAPSHOT_OUTPUT_EXISTS"


def test_refresh_succeeds_when_output_exists_and_overwrite_true() -> None:
    output_path = _scratch("overwrite_true") / "snapshot.json"
    first = refresh_file_snapshot_transport(repo_root=Path("."), output_path=output_path, checked_at=_NOW)
    first_sha = _sha(output_path)
    second = refresh_file_snapshot_transport(
        repo_root=Path("."),
        output_path=output_path,
        checked_at=_NOW,
        overwrite=True,
    )

    assert isinstance(first, FileSnapshotTransportResult)
    assert isinstance(second, FileSnapshotTransportResult)
    assert _sha(output_path) == first_sha
    assert second.snapshot_id == first.snapshot_id


def test_snapshot_json_is_stable_across_identical_inputs() -> None:
    first_path = _scratch("stable_a") / "snapshot.json"
    second_path = _scratch("stable_b") / "snapshot.json"

    first = refresh_file_snapshot_transport(repo_root=Path("."), output_path=first_path, checked_at=_NOW)
    second = refresh_file_snapshot_transport(repo_root=Path("."), output_path=second_path, checked_at=_NOW)

    assert isinstance(first, FileSnapshotTransportResult)
    assert isinstance(second, FileSnapshotTransportResult)
    assert first.manifest is not None
    assert second.manifest is not None
    assert first.manifest.payload_sha256 == second.manifest.payload_sha256
    assert first.snapshot_id != second.snapshot_id


def test_payload_sha256_changes_when_payload_changes() -> None:
    first = build_file_snapshot_transport_payload(repo_root=Path("."), checked_at=_NOW)
    second = build_file_snapshot_transport_payload(
        repo_root=Path("."),
        checked_at=_NOW,
        include_approval_commands=False,
    )

    assert isinstance(first, FileSnapshotTransportResult)
    assert isinstance(second, FileSnapshotTransportResult)
    assert first.manifest is not None
    assert second.manifest is not None
    assert first.manifest.payload_sha256 != second.manifest.payload_sha256


def test_missing_optional_source_creates_warning_not_crash() -> None:
    result = build_file_snapshot_transport_payload(
        repo_root=Path("."),
        checked_at=_NOW,
        include_operator_health=False,
    )

    assert isinstance(result, FileSnapshotTransportResult)
    assert any("optional operator health" in warning for warning in result.warnings)
    assert result.go_no_go == "GO"


def test_missing_required_source_creates_blocker() -> None:
    result = build_file_snapshot_transport_payload(
        repo_root=Path("."),
        checked_at=_NOW,
        include_read_surface=False,
    )

    assert isinstance(result, FileSnapshotTransportResult)
    assert result.go_no_go == "NO_GO"
    assert any("required read surface" in blocker for blocker in result.blockers)


def test_invalid_checked_at_and_output_path_return_errors() -> None:
    checked = build_file_snapshot_transport_payload(repo_root=Path("."), checked_at="")
    outside = refresh_file_snapshot_transport(
        repo_root=Path("."),
        output_path=Path("..") / "stage8_2_snapshot.json",
        checked_at=_NOW,
    )

    assert isinstance(checked, FileSnapshotTransportError)
    assert isinstance(outside, FileSnapshotTransportError)


def test_source_artifacts_sqlite_and_jsonl_are_not_mutated() -> None:
    watched = tuple(
        path
        for path in (
            Path("scos/work/control_center/state/control_center.sqlite3"),
            Path("scos/work/control_center/events/command_events.jsonl"),
            Path("scos/work/control_center/queue/approved_commands.jsonl"),
        )
        if path.exists()
    )
    before = {path: _sha(path) for path in watched}

    result = build_file_snapshot_transport_payload(repo_root=Path("."), checked_at=_NOW)

    assert isinstance(result, FileSnapshotTransportResult)
    assert {path: _sha(path) for path in watched} == before


def test_validate_file_snapshot_transport_boundary_is_deterministic() -> None:
    first = validate_file_snapshot_transport_boundary(repo_root=Path("."), checked_at=_NOW)
    second = validate_file_snapshot_transport_boundary(repo_root=Path("."), checked_at=_NOW)

    assert first == second
    assert first["manual_refresh_only"] is True
    assert first["implicit_writes"] is False
    assert first["background_process"] is False
    assert first["file_watcher"] is False
    assert first["polling"] is False
    assert first["network"] is False
    assert first["command_execution"] is False


def test_no_forbidden_runtime_source_markers_and_no_frontend_route_files() -> None:
    source_paths = (
        Path("scos/control_center/file_snapshot_transport_models.py"),
        Path("scos/control_center/file_snapshot_transport_validation.py"),
        Path("scos/control_center/file_snapshot_refresh_transport.py"),
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)
    forbidden = (
        "Web" + "Socket",
        "Event" + "Source",
        "set" + "Interval",
        "set" + "Timeout",
        "fet" + "ch",
        "XML" + "HttpRequest",
        "axi" + "os",
        "sub" + "process",
        "os." + "system",
        "shell" + "=True",
        "requ" + "ests",
        "http." + "server",
        "socket" + "server",
    )
    for token in forbidden:
        assert token not in combined
    assert not list(Path("apps/control-center").rglob("route.ts"))
