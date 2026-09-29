"""Stage 8.2 manual file snapshot refresh transport tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
from pathlib import Path
from typing import Iterator

import pytest

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
_REPOSITORY_STAGE8_2_PATH = Path("work") / "stage8_2_file_snapshot_tests"
_ISOLATED_REPO_SEED_FILES = (
    "docs/roadmap/STAGE7_HANDOFF.md",
    "docs/roadmap/STAGE8_EXECUTION_PLAN.md",
    "docs/roadmap/STAGE8_HANDOFF.md",
    "docs/roadmap/STAGE8_HANDOFF_REVIEW.md",
    "docs/specification/ADAPTER_ACTIVATION_PREFLIGHT_GATE_CONTRACT.md",
    "docs/specification/READ_SURFACE_TRANSPORT_DECISION_CONTRACT.md",
    "docs/specification/STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md",
    "docs/specification/STAGE7_FINAL_CLOSURE_GATE_CONTRACT.md",
    "docs/specification/STAGE8_ACCEPTANCE_CRITERIA.md",
    "docs/specification/STAGE8_SCOPE_BOUNDARY.md",
    "docs/certification/Stage-4-final-commercial-release.md",
    "docs/certification/Stage-5-final-ai-command-center-certification.md",
    "docs/certification/Stage-6-final-integration-release.md",
    "docs/certification/Stage-7-final-closure.md",
    "docs/certification/Stage-7.8-plan.md",
    "docs/certification/Stage-8.0-plan.md",
    "scos/control_center/backend_health.py",
    "scos/control_center/drift_detection.py",
    "scos/control_center/file_snapshot_refresh_transport.py",
    "scos/control_center/file_snapshot_transport_models.py",
    "scos/control_center/file_snapshot_transport_validation.py",
    "scos/control_center/host_metrics.py",
    "scos/control_center/sqlite_state_schema.py",
    "scos/control_center/transport_activation_decision_gate.py",
    "scos/control_center/transport_activation_decision_models.py",
)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _is_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    attrs = getattr(metadata, "st_file_attributes", 0)
    return path.is_symlink() or bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _repository_path_state(path: Path = _REPOSITORY_STAGE8_2_PATH) -> dict[str, object]:
    absolute = Path.cwd() / path
    try:
        root_metadata = absolute.lstat()
    except FileNotFoundError:
        return {
            "exists": False,
            "reparse_point": False,
            "file_count": 0,
            "directory_count": 0,
            "total_bytes": 0,
            "sha256": None,
        }

    hasher = hashlib.sha256()
    file_count = 0
    directory_count = 1 if stat.S_ISDIR(root_metadata.st_mode) else 0
    total_bytes = 0
    root_reparse = _is_reparse_point(absolute)
    hasher.update(f".|mode={stat.S_IFMT(root_metadata.st_mode)}|reparse={root_reparse}\n".encode("utf-8"))

    if root_reparse or not absolute.is_dir():
        if stat.S_ISREG(root_metadata.st_mode):
            file_count = 1
            data = absolute.read_bytes()
            total_bytes = len(data)
            hasher.update(hashlib.sha256(data).hexdigest().encode("ascii"))
        return {
            "exists": True,
            "reparse_point": root_reparse,
            "file_count": file_count,
            "directory_count": directory_count,
            "total_bytes": total_bytes,
            "sha256": hasher.hexdigest(),
        }

    pending = [absolute]
    while pending:
        current = pending.pop()
        for child in sorted(current.iterdir(), key=lambda item: item.relative_to(absolute).as_posix()):
            relative = child.relative_to(absolute).as_posix()
            try:
                metadata = child.lstat()
            except OSError as exc:
                hasher.update(f"{relative}|unreadable|{type(exc).__name__}\n".encode("utf-8"))
                continue
            child_reparse = _is_reparse_point(child)
            mode = stat.S_IFMT(metadata.st_mode)
            hasher.update(f"{relative}|mode={mode}|reparse={child_reparse}|size={metadata.st_size}\n".encode("utf-8"))
            if child.is_dir() and not child_reparse:
                directory_count += 1
                pending.append(child)
            elif child.is_file() and not child_reparse:
                file_count += 1
                data = child.read_bytes()
                total_bytes += len(data)
                hasher.update(hashlib.sha256(data).hexdigest().encode("ascii"))

    return {
        "exists": True,
        "reparse_point": root_reparse,
        "file_count": file_count,
        "directory_count": directory_count,
        "total_bytes": total_bytes,
        "sha256": hasher.hexdigest(),
    }


def _copy_seed_file(repo_root: Path, isolated_root: Path, relative_path: str) -> None:
    source = repo_root / relative_path
    target = isolated_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


@pytest.fixture(autouse=True)
def _preserve_repository_stage8_2_path() -> None:
    before = _repository_path_state()
    yield
    assert _repository_path_state() == before


@pytest.fixture
def isolated_repo_root(tmp_path: Path) -> Iterator[Path]:
    root = (tmp_path / "isolated_repo").resolve(strict=False)
    repo_root = Path.cwd().resolve()
    assert root.is_absolute()
    assert not _is_relative_to(root, repo_root)
    root.mkdir()
    for relative_path in _ISOLATED_REPO_SEED_FILES:
        _copy_seed_file(repo_root, root, relative_path)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def _scratch(root: Path, name: str) -> Path:
    child = root / name
    child.mkdir()
    return child


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_build_payload_does_not_write_any_file(isolated_repo_root: Path) -> None:
    target = _scratch(isolated_repo_root, "build_no_write") / "snapshot.json"

    result = build_file_snapshot_transport_payload(repo_root=isolated_repo_root, checked_at=_NOW)

    assert isinstance(result, FileSnapshotTransportResult)
    assert target.exists() is False
    assert result.output_path is None
    assert result.manifest is not None
    assert result.payload is not None


def test_refresh_writes_exactly_one_snapshot_json_file(isolated_repo_root: Path) -> None:
    output_dir = _scratch(isolated_repo_root, "refresh_once")
    output_path = output_dir / "snapshot.json"

    result = refresh_file_snapshot_transport(repo_root=isolated_repo_root, output_path=output_path, checked_at=_NOW)

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


def test_refresh_fails_when_output_exists_and_overwrite_false(isolated_repo_root: Path) -> None:
    output_path = _scratch(isolated_repo_root, "overwrite_false") / "snapshot.json"
    first = refresh_file_snapshot_transport(repo_root=isolated_repo_root, output_path=output_path, checked_at=_NOW)
    second = refresh_file_snapshot_transport(repo_root=isolated_repo_root, output_path=output_path, checked_at=_NOW)

    assert isinstance(first, FileSnapshotTransportResult)
    assert isinstance(second, FileSnapshotTransportError)
    assert second.error_code == "FILE_SNAPSHOT_OUTPUT_EXISTS"


def test_refresh_succeeds_when_output_exists_and_overwrite_true(isolated_repo_root: Path) -> None:
    output_path = _scratch(isolated_repo_root, "overwrite_true") / "snapshot.json"
    first = refresh_file_snapshot_transport(repo_root=isolated_repo_root, output_path=output_path, checked_at=_NOW)
    first_sha = _sha(output_path)
    second = refresh_file_snapshot_transport(
        repo_root=isolated_repo_root,
        output_path=output_path,
        checked_at=_NOW,
        overwrite=True,
    )

    assert isinstance(first, FileSnapshotTransportResult)
    assert isinstance(second, FileSnapshotTransportResult)
    assert _sha(output_path) == first_sha
    assert second.snapshot_id == first.snapshot_id


def test_snapshot_json_is_stable_across_identical_inputs(isolated_repo_root: Path) -> None:
    first_path = _scratch(isolated_repo_root, "stable_a") / "snapshot.json"
    second_path = _scratch(isolated_repo_root, "stable_b") / "snapshot.json"

    first = refresh_file_snapshot_transport(repo_root=isolated_repo_root, output_path=first_path, checked_at=_NOW)
    second = refresh_file_snapshot_transport(repo_root=isolated_repo_root, output_path=second_path, checked_at=_NOW)

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


def test_invalid_checked_at_and_output_path_return_errors(isolated_repo_root: Path) -> None:
    checked = build_file_snapshot_transport_payload(repo_root=isolated_repo_root, checked_at="")
    outside = refresh_file_snapshot_transport(
        repo_root=isolated_repo_root,
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



def test_no_forbidden_runtime_source_markers_and_legacy_frontend_retired() -> None:
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
    assert not Path("apps/control-center").exists()
    research = Path("docs/architecture/FLOOT_CONTROL_CENTER_RESEARCH_20260919.md").read_text(encoding="utf-8")
    assert "Floot Mission Control" in research
    assert "Skills" in research
    assert "Evidence" in research
    truth_gate = Path("scripts/control_center_truth_gate.py").read_text(encoding="utf-8")
    for token in ("child_process", "shell=True", "os.system"):
        assert token not in truth_gate
