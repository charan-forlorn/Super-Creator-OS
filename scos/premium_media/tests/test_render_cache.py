import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scos.premium_media.hardware import (
    HardwareCapabilities,
    encoder_args,
    resolve_finish_profile,
)
from scos.premium_media.models import PremiumRenderProfile
from scos.premium_media.pipeline import _final_cache_key
from scos.premium_media.render_cache import (
    RenderCache,
    RenderCacheError,
    cache_key,
    fingerprint_value,
)
from scos.premium_media.render_router import (
    RenderJob,
    RenderRouter,
    RemotionBackend,
    _cache_relevant_props,
)


def test_render_cache_round_trip_and_tamper_detection(tmp_path: Path):
    source = tmp_path / "render.mp4"
    source.write_bytes(b"video-bytes")
    cache = RenderCache(tmp_path / "cache")
    key = cache_key({"graph": "g1", "profile": "p1"})
    hit = cache.store("remotion", key, source, metadata={"profile": "p1"})
    assert hit.artifact_sha256
    restored = tmp_path / "restored.mp4"
    cache.materialize(hit, restored)
    assert restored.read_bytes() == b"video-bytes"

    hit.artifact_path.write_bytes(b"tampered")
    assert cache.lookup("remotion", key) is None


def test_render_cache_rejects_unsafe_components(tmp_path: Path):
    cache = RenderCache(tmp_path / "cache")
    with pytest.raises(RenderCacheError):
        cache.lookup("../escape", "a")


def test_fingerprint_value_tracks_local_file_bytes(tmp_path: Path):
    asset = tmp_path / "asset.wav"
    asset.write_bytes(b"one")
    first = fingerprint_value(str(asset), base_dir=tmp_path)
    asset.write_bytes(b"two")
    second = fingerprint_value(str(asset), base_dir=tmp_path)
    assert first["sha256"] != second["sha256"]



def test_gpu_policy_is_explicit_and_fail_closed():
    profile = PremiumRenderProfile(
        name="ad", platform="ad", render_acceleration="auto", video_crf=18
    )
    caps = HardwareCapabilities(
        ffmpeg_path="ffmpeg",
        encoders=("h264_nvenc",),
        gpu_name="Test GPU",
        gpu_memory_mb=8192,
    )
    resolved = resolve_finish_profile(profile, capabilities=caps)
    assert resolved.video_codec == "h264_nvenc"
    assert resolved.video_preset == "p5"
    assert "-cq:v" in encoder_args(resolved)

    no_gpu = HardwareCapabilities(ffmpeg_path="ffmpeg", encoders=())
    with pytest.raises(RuntimeError):
        resolve_finish_profile(
            PremiumRenderProfile(
                name="gpu", platform="test", render_acceleration="gpu"
            ),
            capabilities=no_gpu,
        )


def test_final_cache_key_changes_with_audio_bytes(tmp_path: Path):
    video = tmp_path / "video.mp4"
    audio = tmp_path / "music.wav"
    video.write_bytes(b"video")
    audio.write_bytes(b"music-a")
    profile = PremiumRenderProfile(name="test", platform="test")
    from scos.premium_media.models import AudioRole, AudioStem

    stem = AudioStem(str(audio), AudioRole.MUSIC)
    first = _final_cache_key(
        video, profile, audio_stems=(stem,), subtitles=(), subtitle_style=None,
        production_metadata={"graph_fingerprint": "g1"},
    )
    audio.write_bytes(b"music-b")
    second = _final_cache_key(
        video, profile, audio_stems=(stem,), subtitles=(), subtitle_style=None,
        production_metadata={"graph_fingerprint": "g1"},
    )
    assert first != second


def test_remotion_router_reuses_cached_stage(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    (project / "node_modules").mkdir(parents=True)
    (project / "src").mkdir()
    (project / "src" / "index.jsx").write_text("export default null;", encoding="utf-8")
    (project / "package.json").write_text("{}", encoding="utf-8")
    (project / "package-lock.json").write_text("{}", encoding="utf-8")

    calls = {"render": 0}
    def fake_render(self, job):
        calls["render"] += 1
        job.output_path.parent.mkdir(parents=True, exist_ok=True)
        job.output_path.write_bytes(b"rendered")
        return job.output_path

    monkeypatch.setattr(RemotionBackend, "render", fake_render)
    monkeypatch.setattr(
        "scos.premium_media.render_router.validate_render",
        lambda *args, **kwargs: SimpleNamespace(passed=True, errors=[]),
    )
    job1 = RenderJob(
        project_dir=project,
        entrypoint="src/index.jsx",
        composition_id="Test",
        props={"duration_s": 1, "states": []},
        output_path=tmp_path / "one.mp4",
        profile=PremiumRenderProfile(name="test", platform="test"),
    )
    router = RenderRouter(cache=RenderCache(tmp_path / "render-cache"))
    assert router.render_remotion(job1).read_bytes() == b"rendered"
    job2 = RenderJob(
        project_dir=project,
        entrypoint="src/index.jsx",
        composition_id="Test",
        props={"duration_s": 1, "states": []},
        output_path=tmp_path / "two.mp4",
        profile=job1.profile,
    )
    assert router.render_remotion(job2).read_bytes() == b"rendered"
    assert calls["render"] == 1


def test_cache_key_is_order_stable():
    assert cache_key({"b": 2, "a": 1}) == cache_key({"a": 1, "b": 2})


def test_cache_identity_excludes_learning_only_graph_identity():
    props = {
        "duration_s": 1,
        "states": [{"start": 0, "end": 1, "headline": "Same"}],
        "production_graph": {
            "fingerprint": "volatile",
            "loop_run_id": "run-123",
            "project_id": "p1",
        },
    }
    normalized = _cache_relevant_props(props)
    assert normalized["production_graph"] == {"project_id": "p1"}
