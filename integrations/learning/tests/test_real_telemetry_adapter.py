from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent
sys.path.insert(0, str(_PKG))

import telemetry as TEL
from observation_binding import ObservationBindingError, load_render_binding
from youtube_analytics_adapter import YouTubeAnalyticsAdapter, YouTubeQuery, YouTubeAnalyticsError, capture_binding


def _provenance(tmp_path: Path, *, loop_run_id: str = "loop-1") -> tuple[Path, str, str]:
    artifact = tmp_path / "master.mp4"
    artifact.write_bytes(b"stable-artifact-bytes")
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    graph = hashlib.sha256(b"graph").hexdigest()
    prov = tmp_path / "master.provenance.json"
    prov.write_text(json.dumps({
        "schema_version": "SCOS_PREMIUM_MEDIA_R1",
        "output": str(artifact),
        "output_sha256": sha,
        "extra": {"project_name": "Telemetry Demo"},
        "learning_handoff": {
            "schema_version": "SCOS_LEARNING_HANDOFF_R1",
            "loop_run_id": loop_run_id,
            "graph_fingerprint": graph,
            "artifact_sha256": sha,
        },
    }), encoding="utf-8")
    return prov, sha, graph


def _payload():
    return {
        "columnHeaders": [
            {"name": "views"}, {"name": "engagedViews"},
            {"name": "averageViewDuration"}, {"name": "averageViewPercentage"},
            {"name": "likes"}, {"name": "comments"}, {"name": "shares"},
            {"name": "subscribersGained"},
        ],
        "rows": [[1200, 1100, 15.5, 52.25, 70, 8, 12, 4]],
    }


def test_binding_verifies_current_artifact_bytes(tmp_path):
    prov, sha, graph = _provenance(tmp_path)
    binding = load_render_binding(prov, platform_content_id="yt-123")
    assert binding.artifact_sha256 == sha
    assert binding.graph_fingerprint == graph
    assert binding.loop_run_id == "loop-1"


def test_binding_rejects_tampered_artifact(tmp_path):
    prov, _, _ = _provenance(tmp_path)
    artifact = tmp_path / "master.mp4"
    artifact.write_bytes(b"tampered")
    with pytest.raises(ObservationBindingError, match="ARTIFACT_SHA_BYTES_MISMATCH"):
        load_render_binding(prov, platform_content_id="yt-123")


def test_youtube_adapter_normalizes_official_metrics(tmp_path):
    prov, sha, graph = _provenance(tmp_path)
    binding = load_render_binding(prov, platform_content_id="yt-123")
    query = YouTubeQuery("2026-09-18", "2026-09-19", "yt-123")
    adapter = YouTubeAnalyticsAdapter("token", query, http_get=lambda *_: json.dumps(_payload()).encode())
    raw = adapter.fetch("loop-1", "youtube_shorts")
    assert raw["views"] == 1200
    assert raw["avg_watch_time_s"] == 15.5
    assert raw["avg_watch_pct"] == 52.25
    assert raw["followers_gained"] == 4
    evidence = raw["observation_evidence"]
    assert evidence["platform_content_id"] == "yt-123"
    assert len(evidence["query_sha256"]) == 64
    assert len(evidence["response_sha256"]) == 64


def test_api_capture_persists_only_with_complete_binding(tmp_path):
    prov, sha, graph = _provenance(tmp_path)
    binding = load_render_binding(prov, platform_content_id="yt-123")
    adapter = YouTubeAnalyticsAdapter(
        "token",
        YouTubeQuery("2026-09-18", "2026-09-19", "yt-123"),
        http_get=lambda *_: json.dumps(_payload()).encode(),
    )
    telemetry = tmp_path / "telemetry.json"
    result = capture_binding(adapter, binding, telemetry_path=telemetry)
    assert result["ok"] is True
    rows = json.loads(telemetry.read_text(encoding="utf-8"))
    assert len(rows) == 1
    assert rows[0]["source"] == "api"
    assert rows[0]["loop_run_id"] == "loop-1"
    assert rows[0]["observation_evidence"]["artifact_sha256"] == sha
    assert rows[0]["observation_evidence"]["graph_fingerprint"] == graph


def test_api_validator_rejects_missing_evidence(tmp_path):
    row = {
        "loop_run_id": "loop-1", "project_name": "Project",
        "platform": "youtube_shorts", "collected_at": "2026-09-19T00:00:00Z",
        "source": "api", "views": 10,
    }
    ok, info = TEL.append_telemetry(row, path=tmp_path / "telemetry.json")
    assert ok is False
    assert "observation_evidence" in info
    assert not (tmp_path / "telemetry.json").exists()


def test_telemetry_rejects_cross_artifact_evidence_conflict(tmp_path):
    path = tmp_path / "telemetry.json"
    base = {
        "loop_run_id": "loop-1", "project_name": "Project",
        "platform": "youtube_shorts", "collected_at": "2026-09-19T00:00:00Z",
        "source": "api", "views": 10,
        "observation_evidence": {
            "provider": "youtube_analytics", "platform_content_id": "yt-1",
            "graph_fingerprint": "a" * 64, "artifact_sha256": "b" * 64,
            "query_sha256": "c" * 64, "response_sha256": "d" * 64,
        },
    }
    ok, _ = TEL.append_telemetry(base, path=path)
    assert ok is True
    conflict = dict(base)
    conflict["collected_at"] = "2026-09-19T01:00:00Z"
    conflict["observation_evidence"] = dict(base["observation_evidence"])
    conflict["observation_evidence"]["artifact_sha256"] = "e" * 64
    ok, info = TEL.append_telemetry(conflict, path=path)
    assert ok is False
    assert "artifact_sha256" in info


def test_adapter_requires_oauth_token():
    with pytest.raises(YouTubeAnalyticsError, match="ACCESS_TOKEN_REQUIRED"):
        YouTubeAnalyticsAdapter("", YouTubeQuery("2026-09-18", "2026-09-19", "yt-123"))
