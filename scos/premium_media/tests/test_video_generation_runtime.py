from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from scos.premium_media.video_generation import (
    GenerationArtifact,
    GenerationPlan,
    GenerationTask,
    ProviderDecision,
    ReferenceAsset,
    ShotGenerationSpec,
)
from scos.premium_media.video_generation_runtime import (
    GoogleVeoAdapter,
    ProviderAdapterRegistry,
    ProviderContractError,
    ProviderPoll,
    ProviderSubmission,
    ReferencePackager,
    RunwayGen45Adapter,
    SeedanceAdapter,
    TaskJournal,
    VideoGenerationOrchestrator,
)


SHA = "a" * 64


def spec(duration: float = 5.0, *, mode: str = "text_to_video") -> ShotGenerationSpec:
    return ShotGenerationSpec(
        shot_id="shot-01",
        purpose="hero",
        mode=mode,
        start_s=0.0,
        end_s=duration,
        prompt="premium product reveal",
        aspect_ratio="9:16",
        required_capabilities=frozenset({"text_to_video"}),
    )


def decision(*providers: str) -> ProviderDecision:
    return ProviderDecision("shot-01", providers[0], "model", tuple(providers[1:]), 1.0, ("test",))


def plan_for(*providers: str) -> GenerationPlan:
    s = spec()
    return GenerationPlan("p", "test objective", (s,), (ProviderDecision("shot-01", providers[0], "model", tuple(providers[1:]), 1.0, ("test",)),))


def test_registry_negotiates_real_provider_constraints(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("LAS_API_KEY", "x")
    monkeypatch.setenv("RUNWAYML_API_SECRET", "x")
    registry = ProviderAdapterRegistry((GoogleVeoAdapter(), SeedanceAdapter(), RunwayGen45Adapter()))
    candidates = registry.resolve(spec(5), decision("google_veo", "bytedance_seedance", "runway"))
    assert candidates[1] == "bytedance_seedance"


def test_reference_packager_fail_closes_on_hash_mismatch(tmp_path):
    path = tmp_path / "ref.png"
    path.write_bytes(b"image-bytes")
    ref = ReferenceAsset("r1", "scene", str(path), "b" * 64)
    with pytest.raises(ProviderContractError, match="sha256 mismatch"):
        ReferencePackager().package("bytedance_seedance", ref)


def test_reference_packager_embeds_local_image(tmp_path):
    path = tmp_path / "ref.png"
    path.write_bytes(b"image-bytes")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    ref = ReferenceAsset("r1", "scene", str(path), sha)
    packed = ReferencePackager().package("bytedance_seedance", ref)
    assert packed.provider_uri.startswith("data:image/png;base64,")
    assert packed.sha256 == sha


class FakeAdapter:
    provider_id = "fake"
    model_id = "fake-1"

    def __init__(self):
        self.submissions = 0
        self.polls = 0

    def available(self):
        return True

    def validate_spec(self, spec):
        return ()

    def submit(self, spec, *, prompt, packed_references, idempotency_key):
        self.submissions += 1
        return ProviderSubmission(f"provider-{self.submissions}")

    def poll(self, provider_task_id):
        self.polls += 1
        if self.polls == 1:
            return ProviderPoll("running")
        return ProviderPoll("succeeded", artifact_uri="memory://artifact")

    def download(self, artifact_uri, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"artifact-bytes")
        return destination


class FakeFailureAdapter(FakeAdapter):
    provider_id = "fake-primary"

    def poll(self, provider_task_id):
        return ProviderPoll("failed", error_code="provider_error", error_message="synthetic failure")


class FakeFallbackAdapter(FakeAdapter):
    provider_id = "fake-fallback"


def test_orchestrator_journals_and_reconciles(tmp_path):
    adapter = FakeAdapter()
    registry = ProviderAdapterRegistry((adapter,))
    journal = TaskJournal(tmp_path / "journal")
    orch = VideoGenerationOrchestrator(adapters=registry, journal=journal)
    tasks = orch.submit_plan(plan_for("fake"), output_dir=tmp_path / "out")
    assert tasks[0].state == "submitted"
    again = orch.submit_plan(plan_for("fake"), output_dir=tmp_path / "out")
    assert again[0].task_id == tasks[0].task_id
    assert adapter.submissions == 1
    running = orch.reconcile(output_dir=tmp_path / "out")
    assert running[0].state == "running"
    done = orch.reconcile(output_dir=tmp_path / "out")
    assert done[0].state == "succeeded"
    assert done[0].artifact is not None
    assert (tmp_path / "out" / "evidence" / f"{done[0].task_id}.json").exists()


def test_orchestrator_fail_closed_on_provider_failure(tmp_path):
    primary = FakeFailureAdapter()
    registry = ProviderAdapterRegistry((primary,))
    journal = TaskJournal(tmp_path / "journal")
    orch = VideoGenerationOrchestrator(adapters=registry, journal=journal)
    orch.submit_plan(plan_for("fake-primary"), output_dir=tmp_path / "out")
    done = orch.reconcile(output_dir=tmp_path / "out")
    assert done[0].state == "failed"
    assert done[0].error_code == "provider_error"


def test_runway_refuses_unuploaded_local_reference(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNWAYML_API_SECRET", "x")
    path = tmp_path / "ref.png"
    path.write_bytes(b"image")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    ref = ReferenceAsset("r", "scene", str(path), sha)
    s = ShotGenerationSpec(
        shot_id="s", purpose="hero", mode="image_to_video", start_s=0, end_s=5,
        prompt="p", aspect_ratio="9:16", references=(ref,),
        required_capabilities=frozenset({"image_to_video"}),
    )
    packed = ReferencePackager().package("runway", ref)
    adapter = RunwayGen45Adapter(client=None)
    with pytest.raises(ProviderContractError, match="upload-enabled"):
        adapter.submit(s, prompt="p", packed_references=(packed,), idempotency_key="k")


from scos.premium_media.video_generation_runtime import write_generation_clip_manifest

def test_generation_clip_manifest_requires_sealed_success(tmp_path):
    plan = plan_for("fake")
    task = GenerationTask("t1", "shot-01", "fake", "model").transition(
        "submitted", provider_task_id="p1"
    ).transition(
        "running"
    )
    with pytest.raises(ProviderContractError, match="requires succeeded"):
        write_generation_clip_manifest(plan, (task,), tmp_path / "manifest.json")


def test_generation_clip_manifest_roundtrip_shape(tmp_path):
    plan = plan_for("fake")
    artifact = GenerationArtifact(str(tmp_path / "clip.mp4"), "c" * 64, "video/mp4", 1080, 1920, 5.0)
    task = GenerationTask("t1", "shot-01", "fake", "model").transition(
        "submitted", provider_task_id="p1"
    ).transition(
        "running"
    ).transition(
        "succeeded", artifact=artifact
    )
    out = write_generation_clip_manifest(plan, (task,), tmp_path / "manifest.json")
    data = __import__("json").loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == "SCOS_GENERATED_CLIP_MANIFEST_R1"
    assert data["shots"][0]["artifact"]["sha256"] == "c" * 64

