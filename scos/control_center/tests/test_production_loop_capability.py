from __future__ import annotations

import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from scos.control_center.production_loop_capability import (
    OPEN_TELEMETRY,
    ProductionLoopRequest,
    SEALED_OPEN,
    execute_production_loop,
)


def _git_repo(root: Path) -> None:
    (root / "scos" / "work" / "run-1").mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    marker = root / "marker.txt"
    marker.write_text("baseline", encoding="utf-8")
    subprocess.run(["git", "add", "marker.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, capture_output=True)


def _request(root: Path, artifact: Path, **kwargs) -> ProductionLoopRequest:
    return ProductionLoopRequest(
        repo_root=root,
        task_id="task-1",
        run_id="run-1",
        artifact_path=artifact,
        **kwargs,
    )


def _fake_probe(path: Path) -> dict:
    return {
        "container_duration_s": "2.0",
        "size_bytes": path.stat().st_size,
        "video_codec": "h264",
        "audio_codec": "aac",
        "width": 1080,
        "height": 1920,
        "fps": "24/1",
        "video_streams": 1,
        "audio_streams": 1,
    }

def test_end_to_end_is_idempotent_and_truthful() -> None:
    with TemporaryDirectory() as td:
        root = Path(td)
        _git_repo(root)
        artifact = root / "scos" / "work" / "run-1" / "output.mp4"
        artifact.write_bytes(b"media-v1")
        request = _request(root, artifact)

        with mock.patch(
            "scos.control_center.production_loop_capability._ffprobe",
            side_effect=_fake_probe,
        ):
            first = execute_production_loop(request)
            second = execute_production_loop(request)

        assert first.status == SEALED_OPEN
        assert first.telemetry["status"] == OPEN_TELEMETRY
        assert first.evidence["bundle_id"] == second.evidence["bundle_id"]
        assert first.staging["action"] == "COPIED"
        assert second.staging["action"] == "REUSED"
        evidence = root / first.evidence["path"]
        saved = json.loads(evidence.read_text(encoding="utf-8"))
        assert saved["human_approval_inferred"] is False
        assert saved["external_dispatch"] is False


def test_changed_artifact_invalidates_previous_evidence() -> None:
    with TemporaryDirectory() as td:
        root = Path(td)
        _git_repo(root)
        artifact = root / "scos" / "work" / "run-1" / "output.mp4"
        artifact.write_bytes(b"media-v1")
        request = _request(root, artifact)

        with mock.patch(
            "scos.control_center.production_loop_capability._ffprobe",
            side_effect=_fake_probe,
        ):
            first = execute_production_loop(request)
            artifact.write_bytes(b"media-v2")
            second = execute_production_loop(request)

        assert first.evidence["bundle_id"] != second.evidence["bundle_id"]
        log = root / "evidence" / "production-loop" / "run-1" / "invalidation.jsonl"
        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        assert records[-1]["event"] == "STALE_EVIDENCE_INVALIDATED"
        assert records[-1]["previous_bundle_id"] == first.evidence["bundle_id"]
        assert records[-1]["new_bundle_id"] == second.evidence["bundle_id"]

def test_joined_telemetry_is_bound_to_existing_provenance() -> None:
    with TemporaryDirectory() as td:
        root = Path(td)
        _git_repo(root)
        artifact = root / "scos" / "work" / "run-1" / "output.mp4"
        artifact.write_bytes(b"media-v1")
        export = root / "analytics.csv"
        export.write_text(
            "loop_run_id,project_name,platform,collected_at,views,avg_watch_pct\n"
            "run-1,Demo,youtube_shorts,2026-09-19T00:00:00Z,100,50\n",
            encoding="utf-8",
        )
        db = root / "database.json"
        db.write_text(json.dumps([{"provenance": {"loop_run_id": "run-1"}}]), encoding="utf-8")

        request = _request(
            root,
            artifact,
            telemetry_export_path=export,
            telemetry_db_path=db,
            telemetry_path=root / "telemetry.json",
        )
        with mock.patch(
            "scos.control_center.production_loop_capability._ffprobe",
            side_effect=_fake_probe,
        ):
            result = execute_production_loop(request)

        assert result.telemetry["status"] == "OBSERVATIONS_JOINED"
        assert result.telemetry["learning_qualification"] is False
        assert result.status == "SEALED"


def test_missing_artifact_fails_closed() -> None:
    with TemporaryDirectory() as td:
        root = Path(td)
        _git_repo(root)
        request = _request(
            root,
            root / "scos" / "work" / "run-1" / "missing.mp4",
        )
        with mock.patch(
            "scos.control_center.production_loop_capability._git_truth",
            return_value={"head": "x", "branch": "main", "status_lines": [], "status_count": 0, "status_sha256": "x"},
        ):
            try:
                execute_production_loop(request)
                raised = False
            except FileNotFoundError:
                raised = True
        assert raised

def test_evidence_path_is_repo_bounded() -> None:
    with TemporaryDirectory() as td:
        root = Path(td)
        _git_repo(root)
        artifact = root / "scos" / "work" / "run-1" / "output.mp4"
        artifact.write_bytes(b"media")
        request = _request(
            root,
            artifact,
            evidence_path=root / "outside.json",
        )
        with mock.patch(
            "scos.control_center.production_loop_capability._ffprobe",
            side_effect=_fake_probe,
        ):
            result = execute_production_loop(request)
        assert result.evidence["path"] == "outside.json"
