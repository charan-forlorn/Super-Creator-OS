from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scos.render.base import RenderClip, RenderProfile, RenderRequest
from scos.render.hardware import EncoderPlan, choose_encoder
from scos.render.render_cache import RenderCache
from scos.render.video_use_backend import VideoUseBackend


def _make_still(path: Path, color: str) -> None:
    import subprocess
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=640x360",
            "-frames:v", "1", str(path),
        ],
        check=True,
    )


def _make_voice(path: Path, duration: float = 0.8) -> None:
    import subprocess
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
            "-ac", "2", "-ar", "48000", str(path),
        ],
        check=True,
    )


def _request(root: Path, second_visual: Path) -> RenderRequest:
    return RenderRequest(
        run_id="cache-test",
        clips=[
            RenderClip("scene_00", root / "s0.png", root / "v0.wav", 0.8),
            RenderClip("scene_01", second_visual, None, 0.8),
        ],
        output_path=root / "out.mp4",
        work_dir=root / "work",
        profile=RenderProfile(),
    )


def test_hardware_mode_off_is_deterministic() -> None:
    plan = choose_encoder(mode="off")
    assert plan.hardware is False
    assert plan.ffmpeg_encoder == "libx264"
    assert "CPU" in plan.reason


def test_required_mode_fails_closed_when_no_hardware_exists(monkeypatch) -> None:
    import scos.render.hardware as hardware
    monkeypatch.setattr(hardware, "available_encoders", lambda *_: frozenset())
    with pytest.raises(RuntimeError, match="no supported hardware encoder"):
        hardware.choose_encoder(mode="required")


def test_content_addressed_scene_fingerprint_changes_on_source_bytes() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        visual = root / "s.png"
        visual.write_bytes(b"one")
        clip = RenderClip("s", visual, None, 1.0)
        cache = RenderCache(root / "cache")
        first = cache.clip_fingerprint(clip, RenderProfile(), "cpu")
        visual.write_bytes(b"two")
        second = cache.clip_fingerprint(clip, RenderProfile(), "cpu")
        assert first != second


def test_motion_change_invalidates_scene_fingerprint() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        visual = root / "s.png"
        visual.write_bytes(b"same")
        cache = RenderCache(root / "cache")
        static = RenderClip("s", visual, None, 1.0, motion="static")
        push = RenderClip("s", visual, None, 1.0, motion="push_in")
        first = cache.clip_fingerprint(static, RenderProfile(), "cpu")
        second = cache.clip_fingerprint(push, RenderProfile(), "cpu")
        assert first != second


def test_final_cache_hit_skips_engine_after_first_real_render() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _make_still(root / "s0.png", "blue")
        _make_still(root / "s1.png", "red")
        _make_voice(root / "v0.wav")
        request = _request(root, root / "s1.png")
        cache_root = root / "cache"

        first = VideoUseBackend(cache_root=cache_root).render(request)
        assert first.success
        assert first.info.startswith("rendered")

        backend = VideoUseBackend(cache_root=cache_root)
        def fail_engine(*_args, **_kwargs):
            raise AssertionError("engine must not run on final cache hit")
        backend._invoke_engine = fail_engine  # type: ignore[method-assign]
        second = backend.render(request)
        assert second.success
        assert second.info.startswith("cache hit")
        assert backend.cache is not None
        assert backend.cache.stats["hits"] >= 1


def test_single_scene_change_reuses_unchanged_scene_cache() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _make_still(root / "s0.png", "blue")
        _make_still(root / "s1.png", "red")
        _make_still(root / "s1_changed.png", "green")
        _make_voice(root / "v0.wav")
        cache_root = root / "cache"

        first_request = _request(root, root / "s1.png")
        first_backend = VideoUseBackend(cache_root=cache_root)
        first_backend.render(first_request)
        assert first_backend.cache is not None

        import scos.render.edl_bridge as edl
        original = edl.build_scene_clip
        built: list[str] = []

        def wrapped(clip, profile, out_path, encoder=None):
            built.append(clip.scene_id)
            return original(clip, profile, out_path, encoder)

        edl.build_scene_clip = wrapped
        try:
            second_backend = VideoUseBackend(cache_root=cache_root)
            second_backend.render(_request(root, root / "s1_changed.png"))
        finally:
            edl.build_scene_clip = original

        assert built == ["scene_01"]
        assert second_backend.cache is not None
        assert second_backend.cache.stats["hits"] >= 1
        assert second_backend.cache.stats["stores"] >= 1
