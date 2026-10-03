from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scos.render.hardware import EncoderPlan
from scos.render.source_edit import render_source_edits


def _probe_with_audio():
    return SimpleNamespace(has_audio=True, fps=30.0)


def _nvenc_plan():
    return EncoderPlan(
        backend_id="nvenc",
        ffmpeg_encoder="h264_nvenc",
        args=("-preset", "p4"),
        hardware=True,
        accelerator="nvidia",
        reason="test",
    )


def _cpu_plan():
    return EncoderPlan(
        backend_id="libx264",        ffmpeg_encoder="libx264",
        args=("-preset", "fast", "-crf", "20"),
        hardware=False,
        accelerator="cpu",
        reason="test",
    )


def test_nvenc_profile_requires_runtime_hardware_policy():
    with (
        patch("scos.render.source_edit.probe_source", return_value=_probe_with_audio()),
        patch("scos.render.source_edit.resolve_ffmpeg", return_value="ffmpeg"),
        patch("scos.render.source_edit.choose_encoder", return_value=_cpu_plan()),
        patch("scos.render.source_edit.subprocess.run") as run,
    ):
        try:
            render_source_edits(
                Path("input.mp4"),
                [(0.0, 1.0)],
                Path("output.mp4"),
                profile="nvenc_p3_hq",
            )
        except RuntimeError as exc:
            assert "encoder policy rejected" in str(exc)
        else:
            raise AssertionError("NVENC profile bypassed runtime hardware policy")
        run.assert_not_called()

def test_nvenc_profile_is_allowed_when_runtime_policy_selects_nvenc():
    fake = SimpleNamespace(returncode=0, stdout="", stderr="")
    with (
        patch("scos.render.source_edit.probe_source", return_value=_probe_with_audio()),
        patch("scos.render.source_edit.resolve_ffmpeg", return_value="ffmpeg"),
        patch("scos.render.source_edit.choose_encoder", return_value=_nvenc_plan()),
        patch("scos.render.source_edit.subprocess.run", return_value=fake) as run,
    ):
        result = render_source_edits(
            Path("input.mp4"),
            [(0.0, 1.0)],
            Path("output.mp4"),
            profile="nvenc_p3_hq",
        )

    assert result["profile"] == "nvenc_p3_hq"
    assert run.called
    command = run.call_args.args[0]
    assert command[0] == "ffmpeg"
    assert "h264_nvenc" in command
