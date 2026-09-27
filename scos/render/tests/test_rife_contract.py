from scos.render.rife_interpolator import resolve_rife_exe,resolve_model
from scos.render.smooth_plus import _segments
import pytest
from types import SimpleNamespace

def test_segments_split_at_scene_cuts():
    assert _segments([(10.0,30.0)],[20.0])==[(10.0,20.0),(20.0,30.0)]

def test_rife_paths_are_callable():
    assert callable(resolve_rife_exe)
    assert callable(resolve_model)


def test_rife_target_fps_defaults_to_60():
    import inspect
    import scos.render.rife_interpolator as mod
    param = inspect.signature(mod.interpolate_segment_to_video).parameters["target_fps"]
    assert param.default == 60.0


def test_rife_rejects_input_fps_mismatch(monkeypatch, tmp_path):
    import scos.render.rife_interpolator as mod

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    monkeypatch.setattr(
        mod,
        "probe_source",
        lambda _: type("Probe", (), {"fps": 25.0, "cfr": True})(),
    )
    with pytest.raises(ValueError, match="does not match probed source FPS"):
        mod.interpolate_segment_to_video(
            source, 0.0, 1.0, tmp_path / "out.mp4", input_fps=30.0
        )

def test_render_strategy_without_rife_preserves_source_cadence(monkeypatch, tmp_path):
    import scos.render.smooth_plus as mod

    source = tmp_path / "source.mp4"
    output = tmp_path / "out.mp4"
    source.write_bytes(b"x")
    seen = {}

    monkeypatch.setattr(
        mod,
        "probe_source",
        lambda _: SimpleNamespace(fps=25.0, cfr=True),
    )

    def fake_compose(source_path, parts, output_path, *, target_fps):
        seen["target_fps"] = target_fps
        return {"target_fps": target_fps, "timeline_parts": [p.to_dict() for p in parts]}

    monkeypatch.setattr(mod, "_compose_timeline", fake_compose)

    result = mod._render_strategy(
        source, [(0.0, 1.0)], [], output, [], input_fps=25.0
    )
    assert result["target_fps"] == 25.0
    assert seen["target_fps"] == 25.0
