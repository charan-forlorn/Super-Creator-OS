from pathlib import Path

import pytest

from scos.control_center.hyperframes_driver import (
    APPROVED_HYPERFRAMES_VERSION,
    HyperFramesDriverError,
    _temporal_qa,
)


def test_temporal_qa_accepts_exact_cfr():
    result = _temporal_qa(
        {
            "r_frame_rate": "30/1",
            "nb_frames": 300,
            "duration": 10.0,
        }
    )
    assert result["status"] == "PASS"
    assert result["frame_count_delta"] == 0


def test_temporal_qa_rejects_wrong_fps():
    with pytest.raises(HyperFramesDriverError, match="TEMPORAL_FPS"):
        _temporal_qa(
            {
                "r_frame_rate": "24/1",
                "nb_frames": 240,
                "duration": 10.0,
            }
        )


def test_approved_version_is_pinned():
    assert APPROVED_HYPERFRAMES_VERSION == "0.7.45"


def test_driver_output_must_stay_inside_renders(tmp_path, monkeypatch):
    from scos.control_center import hyperframes_driver as driver

    project = tmp_path / "project"
    project.mkdir()
    (project / "index.html").write_text("<html></html>", encoding="utf-8")
    bad_output = tmp_path / "outside.mp4"

    monkeypatch.setattr(
        driver,
        "_resolved_launcher",
        lambda: driver.APPROVED_HYPERFRAMES_ROOT / "node_modules" / ".bin" / "hyperframes.cmd",
    )
    monkeypatch.setattr(
        driver,
        "_validate_launcher",
        lambda *args, **kwargs: ("0.7.45", "v24.20.0"),
    )
    with pytest.raises(HyperFramesDriverError, match="OUTPUT_OUTSIDE"):
        driver.render_hyperframes(
            run_id="test",
            project_root=project,
            output_path=bad_output,
        )

def test_launcher_override_outside_approved_root_is_rejected(tmp_path, monkeypatch):
    from scos.control_center import hyperframes_driver as driver

    launcher = tmp_path / "hyperframes.cmd"
    launcher.write_text("@echo off", encoding="utf-8")
    monkeypatch.setenv(driver.HYPERFRAMES_ENV, str(launcher))

    with pytest.raises(
        HyperFramesDriverError,
        match="LAUNCHER_OUTSIDE_APPROVED_ROOT",
    ):
        driver._resolved_launcher()
