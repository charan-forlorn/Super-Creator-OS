import json
from pathlib import Path

import pytest

from integrations.haios_bridge.bridge import run_bridge

CONTRACT = "HAIOS_SCOS_CREATIVE_JOB_V1"


def _request(root: Path, mode: str = "dry_run") -> dict:
    return {
        "schema_version": 1,
        "contract": CONTRACT,
        "goal_id": "g1",
        "job_id": "j1",
        "project_id": "p1",
        "capability": "creative_execution",
        "goal_text": "make a short video",
        "acceptance_criteria": ["result_recorded"],
        "requested_at": "2026-09-08T00:00:00Z",
        "workspace": str(root),
        "input_artifacts": [],
        "execution_mode": mode,
    }


def test_dry_run_validates_without_pipeline_call(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "integrations.haios_bridge.bridge._run_pipeline",
        lambda _: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    result = run_bridge(_request(tmp_path), dry_run=True)
    assert result["status"] == "BLOCKED"
    assert result["provenance"]["execution"] == "dry_run"


def test_local_mode_returns_success_envelope(tmp_path: Path, monkeypatch):
    def fake(prompt: str) -> dict:
        out = tmp_path / "final.mp4"
        out.write_bytes(b"video-bytes")
        return {
            "status": "success",
            "video_path": str(out),
            "qa_report": {"status": "PASS"},
            "execution_trace": [{"stage": "qa", "status": "success"}],
        }

    monkeypatch.setattr("integrations.haios_bridge.bridge._run_pipeline", fake)
    result = run_bridge(_request(tmp_path, mode="local"), dry_run=False)
    assert result["status"] == "SUCCEEDED"
    assert result["artifacts"][0]["sha256"]
    assert result["qa"]["status"] == "PASS"


def test_invalid_contract_blocks(tmp_path: Path):
    req = _request(tmp_path)
    req["contract"] = "BAD"
    result = run_bridge(req, dry_run=True)
    assert result["status"] == "BLOCKED"
    assert result["provenance"]["reason"] == "REQUEST_REJECTED"


def test_outside_artifact_is_rejected(tmp_path: Path, monkeypatch):
    outside = tmp_path.parent / "outside.mp4"
    outside.write_bytes(b"x")

    def fake(_: str) -> dict:
        return {"status": "success", "video_path": str(outside), "qa_report": {"status": "PASS"}, "execution_trace": []}

    monkeypatch.setattr("integrations.haios_bridge.bridge._run_pipeline", fake)
    result = run_bridge(_request(tmp_path, mode="local"), dry_run=False)
    assert result["status"] == "BLOCKED"
    assert "OUT_OF_BOUNDS" in result["provenance"]["reason"]
