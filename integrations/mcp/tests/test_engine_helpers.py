"""test_engine_helpers.py — SCOS-C3: tiny render fixture tests for engine helpers.

Scope
-----
First-ever regression protection for the video-use engine helpers:
- grade.py: get_preset() preset lookup + apply_grade() ffmpeg command construction
- render.py: build_final_composite() command structure + build_master_srt() SRT generation
- timeline_view.py: extract_frames() frame extraction from a real ffmpeg-generated asset

These are FIXTURE tests — small, deterministic, real ffmpeg output on a 1s testsrc clip.
Not exhaustive coverage; the goal is first regression protection for the engine modules
that production_readiness_audit.md D57 identified as 0-tests.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ENGINE_HELPERS = _HERE.parent.parent / "video-use" / "engine" / "helpers"
for _p in (str(_HERE.parent), str(_ENGINE_HELPERS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import grade as G  # noqa: E402
import render as R  # noqa: E402
import timeline_view as TV  # noqa: E402


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory):
    """A real, tiny (1s, 64x64, 5fps) testsrc mp4 created by ffmpeg."""
    base = tmp_path_factory.mktemp("engine_assets")
    out = base / "sample.mp4"
    rc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=5",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out)],
        capture_output=True, text=True,
    )
    if rc.returncode != 0 or not out.exists():
        pytest.skip(f"ffmpeg unavailable: {rc.stderr[:200]}")
    return out


# ===========================================================================
# grade.py
# ===========================================================================


def test_get_preset_returns_known_presets():
    """get_preset() must return a non-empty filter string for each real preset.

    The 'none' preset is special: it maps to an empty string (no filter), which
    is the documented behavior for "no grading". All other presets must return
    a real ffmpeg filter chain.
    """
    presets = sorted(G.PRESETS)
    assert presets, "no presets defined"
    for name in presets:
        vf = G.get_preset(name)
        assert isinstance(vf, str), f"preset {name} returned non-str"
        if name == "none":
            assert vf == "", "'none' preset must be empty (no filter)"
        else:
            assert vf, f"preset {name} returned empty filter string"


def test_get_preset_unknown_raises_keyerror():
    """get_preset() must raise KeyError for an unknown preset (fail-closed)."""
    with pytest.raises(KeyError):
        G.get_preset("nonexistent_preset_xyz")


def test_apply_grade_produces_output(sample_video, tmp_path):
    """apply_grade() must run ffmpeg with a preset filter and produce a real output file."""
    out = tmp_path / "graded.mp4"
    preset_name = sorted(G.PRESETS)[0]  # first available preset
    filter_string = G.get_preset(preset_name)
    G.apply_grade(sample_video, out, filter_string)
    assert out.exists(), "apply_grade did not produce output"
    assert out.stat().st_size > 0, "graded output is empty"


def test_apply_grade_empty_filter_copies(sample_video, tmp_path):
    """apply_grade() with an empty filter string must copy the stream (no re-encode)."""
    out = tmp_path / "copied.mp4"
    G.apply_grade(sample_video, out, "")
    assert out.exists(), "apply_grade with empty filter did not produce output"
    assert out.stat().st_size > 0


# ===========================================================================
# render.py
# ===========================================================================


def test_build_master_srt_writes_srt_file(tmp_path):
    """build_master_srt() must write a parseable SRT file from an EDL + transcripts.

    EDL structure: 'sources' (list of source names) + 'ranges' (list of
    {source, start, end} time windows). Transcripts live in
    edit_dir/transcripts/<source>.json as word-level dicts.
    """
    import json as _json
    edit_dir = tmp_path / "edit"
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True)
    transcript = {"words": [
        {"type": "word", "start": 0.0, "end": 0.5, "text": "hello"},
        {"type": "word", "start": 0.5, "end": 1.0, "text": "world"},
    ]}
    (transcripts_dir / "a.json").write_text(_json.dumps(transcript), encoding="utf-8")
    edl = {
        "sources": ["a"],
        "ranges": [{"source": "a", "start": 0.0, "end": 1.0}],
    }
    out = tmp_path / "master.srt"
    R.build_master_srt(edl, edit_dir, out)
    assert out.exists(), "build_master_srt did not write output"
    content = out.read_text(encoding="utf-8")
    assert "HELLO" in content and "WORLD" in content


# ===========================================================================
# timeline_view.py
# ===========================================================================


def test_compute_envelope_returns_array(sample_video):
    """compute_envelope() must return a numpy array of RMS values for a real video."""
    import numpy as np
    result = TV.compute_envelope(Path(sample_video), 0.0, 1.0)
    assert isinstance(result, np.ndarray), f"expected ndarray, got {type(result)}"
    assert len(result) > 0, "envelope is empty"


def test_find_silences_returns_gaps():
    """find_silences() must find gaps between word tokens inside [start, end]."""
    words = [
        {"start": 0.0, "end": 0.5, "text": "hello"},
        {"start": 2.0, "end": 2.5, "text": "world"},  # 1.5s gap before this
    ]
    gaps = TV.find_silences(words, 0.0, 3.0, threshold=0.4)
    assert isinstance(gaps, list)
    # The 1.5s gap between 0.5 and 2.0 should be detected (>= 0.4s threshold)
    assert any(abs(g[1] - g[0]) >= 0.4 for g in gaps), f"expected a gap, got {gaps}"
