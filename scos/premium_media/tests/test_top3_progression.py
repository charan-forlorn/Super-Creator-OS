
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scos.premium_media import (
    GeneratedClipRef,
    JsonlTelemetrySink,
    ProviderEvaluationCandidate,
    ProductionGraph,
    CreativeBrief,
    evaluate_provider_candidates,
    assess_live_readiness,
    stage_generated_clips,
    visual_identity_check,
)
from scos.premium_media.live_execution import require_explicit_live_authority, LiveExecutionAuthorityError
from scos.premium_media.video_generation import GenerationArtifact, GenerationPlan, GenerationTask, ProviderDecision, ShotGenerationSpec


def _write_mp4(path: Path, *, color: str = "red", duration: float = 1.0) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=64x64:r=12",
            "-t", str(duration), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(path),
        ],
        check=True,
        timeout=60,
    )


def _plan(provider: str = "fake") -> GenerationPlan:
    shot = ShotGenerationSpec(
        shot_id="shot-01",
        purpose="hero",
        mode="text_to_video",
        start_s=0,
        end_s=4,
        prompt="premium product reveal",
        aspect_ratio="9:16",
    )
    decision = ProviderDecision("shot-01", provider, "model", (), 1.0, ("test",))
    return GenerationPlan("r11", "objective", (shot,), (decision,))


def test_generated_clip_ref_is_fingerprintable():
    graph = ProductionGraph(
        brief=CreativeBrief("p", "objective", "short_form"),
        generated_clips=(GeneratedClipRef("shot-01", "generated-clips/shot-01.mp4", "a" * 64),),
    )
    restored = __import__("scos.premium_media.creative_graph", fromlist=["graph_from_props"]).graph_from_props(graph.to_remotion_props())
    assert restored.generated_clips[0].sha256 == "a" * 64
    assert restored.fingerprint() == graph.fingerprint()


def test_stage_generated_clips_hash_seals(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"sealed")
    sha = hashlib.sha256(clip.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "SCOS_GENERATED_CLIP_MANIFEST_R1",
        "project_id": "p",
        "objective": "o",
        "plan_fingerprint": "f",
        "shots": [{
            "shot_id": "shot-01",
            "provider_id": "fake",
            "model_id": "m",
            "task_id": "t",
            "artifact": {"uri": str(clip), "sha256": sha, "media_type": "video/mp4"},
        }],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    staged = stage_generated_clips(manifest_path, tmp_path / "public")
    assert staged[0]["src"].startswith("generated-clips/shot-01-")
    staged_file = tmp_path / "public" / staged[0]["src"]
    assert hashlib.sha256(staged_file.read_bytes()).hexdigest() == sha


def test_visual_identity_same_clip_passes(tmp_path):
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    _write_mp4(a, color="red")
    _write_mp4(b, color="red")
    report = visual_identity_check(a, b)
    assert report.passed
    assert report.score is not None


def test_visual_identity_different_clip_fails_at_strict_threshold(tmp_path):
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    _write_mp4(a, color="red")
    _write_mp4(b, color="blue")
    report = visual_identity_check(a, b, threshold=0.999)
    assert not report.passed


def test_provider_ab_evaluation_is_qc_gated():
    evaluation = evaluate_provider_candidates((
        ProviderEvaluationCandidate("shot-01", "slow", "m", 0.96, latency_s=120, cost_units=80, qc_passed=True),
        ProviderEvaluationCandidate("bad", "bad", "m", 1.0, latency_s=1, cost_units=1, qc_passed=False),
        ProviderEvaluationCandidate("shot-01", "fast", "m2", 0.90, latency_s=20, cost_units=5, qc_passed=True),
    ))
    assert evaluation.selected_provider_id in {"slow", "fast"}
    assert all(candidate.qc_passed for candidate in evaluation.candidates)


def test_telemetry_sink_appends_observed_event(tmp_path):
    sink = JsonlTelemetrySink(tmp_path / "telemetry.jsonl")
    from scos.premium_media.telemetry import GenerationTelemetryEvent
    sink.append(GenerationTelemetryEvent("R1", 1.0, "t", "s", "p", "m", 0, "succeeded", latency_s=4.5))
    payload = json.loads((tmp_path / "telemetry.jsonl").read_text(encoding="utf-8"))
    assert payload["latency_s"] == 4.5
    assert payload["cost_units"] is None


def test_live_readiness_is_fail_closed_without_credentials(monkeypatch):
    for name in ("GEMINI_API_KEY", "LAS_API_KEY", "RUNWAYML_API_SECRET"):
        monkeypatch.delenv(name, raising=False)
    from scos.premium_media.video_generation_runtime import ProviderAdapterRegistry, GoogleVeoAdapter, SeedanceAdapter, RunwayGen45Adapter
    readiness = assess_live_readiness(
        _plan("google_veo"),
        ProviderAdapterRegistry((GoogleVeoAdapter(), SeedanceAdapter(), RunwayGen45Adapter())),
    )
    assert not readiness.ready
    assert all("credential_not_configured" in r.blocked_reasons for r in readiness.providers if not r.configured)


def test_live_authority_gate_is_explicit():
    with pytest.raises(LiveExecutionAuthorityError):
        require_explicit_live_authority(authorized=False)

