"""test_renderer.py — Module 2 (Real FFmpeg Renderer) test suite.

UNIT (no ffmpeg): request mapping, EDL construction, honest-failure validation.
INTEGRATION (real ffmpeg, synthetic lavfi fixtures): stills+audio -> real .mp4,
ffprobe asserts 1080x1920 + duration, determinism across two runs, and the
missing-asset failure path.

No shipped media: fixtures are generated at runtime with ffmpeg lavfi sources, so
the real render path runs in CI (no skip).

Run: python scos/render/tests/test_renderer.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from scos.render.base import (  # noqa: E402
    RenderBackend, RenderClip, RenderError, RenderProfile, RenderRequest, RenderResult,
)
from scos.render import edl_bridge, ffmpeg_engine  # noqa: E402
from scos.render.video_use_backend import VideoUseBackend  # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def make_still(path: Path, size: str = "1280x720", color: str = "blue") -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"color=c={color}:s={size}",
                    "-frames:v", "1", str(path)], check=True)


def make_voice(path: Path, dur: float = 2.0, freq: int = 440) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur}",
                    "-ac", "2", "-ar", "48000", str(path)], check=True)


def ffprobe_geom(path: Path) -> tuple[int, int, float]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-show_entries", "format=duration",
         "-of", "json", str(path)], capture_output=True, text=True).stdout
    j = json.loads(out)
    st = j["streams"][0]
    return st["width"], st["height"], float(j["format"]["duration"])


# --------------------------------------------------------------------------- #
# unit
# --------------------------------------------------------------------------- #
class _FakeBackend(RenderBackend):
    """Captures the RenderRequest without touching ffmpeg."""
    def __init__(self):
        self.request: RenderRequest | None = None

    def render(self, request: RenderRequest) -> RenderResult:
        self.request = request
        return RenderResult(success=True, video_path=request.output_path,
                            duration_s=3.5, width=1080, height=1920, fps=30, info="fake")


def test_request_mapping():
    print("\n[1] edit_timeline -> RenderRequest mapping")
    fake = _FakeBackend()
    timeline = {"clips": [
        {"scene_id": "scene_00", "start": 0.0, "end": 2.0,
         "asset_path": "a.png", "audio_path": "a.wav"},
        {"scene_id": "scene_01", "start": 2.0, "end": 3.5,
         "asset_path": "b.png", "audio_path": None},
    ], "total_duration": 3.5}
    out = ffmpeg_engine.render({"run_id": "testrun", "edit_timeline": timeline}, backend=fake)
    req = fake.request
    check("two clips mapped", len(req.clips) == 2)
    check("duration derived from end-start", abs(req.clips[0].duration_s - 2.0) < 1e-6
          and abs(req.clips[1].duration_s - 1.5) < 1e-6)
    check("None audio stays None", req.clips[1].audio_path is None)
    check("output path uses run_id", req.output_path.name == "testrun.mp4")
    check("result dict carries video_path", out["video_path"].endswith("testrun.mp4"))


def test_write_edl():
    print("\n[2] write_edl produces a video-use-compatible EDL")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        c0, c1 = td / "seg_00.mp4", td / "seg_01.mp4"
        c0.write_bytes(b"x"); c1.write_bytes(b"x")
        edl_path = edl_bridge.write_edl(
            [("seg_00", c0, 2.0), ("seg_01", c1, 1.5)], RenderProfile(), td / "edl.json")
        edl = json.loads(edl_path.read_text())
        check("sources map both segments", set(edl["sources"]) == {"seg_00", "seg_01"})
        check("ranges are full [0,dur]",
              edl["ranges"][0]["start"] == 0.0 and edl["ranges"][0]["end"] == 2.0)
        check("total_duration_s summed", abs(edl["total_duration_s"] - 3.5) < 1e-6)
        check("grade + overlays present for engine", edl["grade"] == "none" and edl["overlays"] == [])


def test_honest_failure_validation():
    print("\n[3] honest failure on missing/empty inputs (no ffmpeg)")
    bad = RenderClip(scene_id="s", visual_path=Path("does_not_exist.png"),
                     audio_path=None, duration_s=2.0)
    try:
        edl_bridge._validate_clip_inputs(bad); raised = False
    except RenderError:
        raised = True
    check("missing visual -> RenderError", raised)

    try:
        ffmpeg_engine.render({"run_id": "r", "edit_timeline": {"clips": []}},
                             backend=_FakeBackend()); raised = False
    except RenderError:
        raised = True
    check("empty clips -> RenderError", raised)


# --------------------------------------------------------------------------- #
# integration (real render)
# --------------------------------------------------------------------------- #
def test_integration_render():
    print("\n[4] integration — synthetic stills+audio -> real 1080x1920 mp4")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        still0, still1 = td / "s0.png", td / "s1.png"
        voice0 = td / "v0.wav"
        make_still(still0, "1280x720", "blue")
        make_still(still1, "640x640", "red")
        make_voice(voice0, dur=2.0)

        clips = [
            RenderClip("scene_00", still0, voice0, 2.0),      # with voiceover
            RenderClip("scene_01", still1, None, 1.5),        # silent (anullsrc)
        ]
        out = td / "out.mp4"
        req = RenderRequest(run_id="itest", clips=clips, output_path=out,
                            work_dir=td / "work", profile=RenderProfile())
        res = VideoUseBackend().render(req)
        check("render reports success", res.success is True)
        check("output exists & non-empty", out.exists() and out.stat().st_size > 0)
        if out.exists() and out.stat().st_size > 0:
            w, h, dur = ffprobe_geom(out)
            check("output is exactly 1080x1920", (w, h) == (1080, 1920))
            check("duration approx sum of scenes (3.5s)", abs(dur - 3.5) < 0.4)

        # determinism: a second run yields identical geometry + ~equal duration
        out2 = td / "out2.mp4"
        req2 = RenderRequest(run_id="itest2", clips=clips, output_path=out2,
                             work_dir=td / "work2", profile=RenderProfile())
        VideoUseBackend().render(req2)
        if out.exists() and out2.exists():
            g1, g2 = ffprobe_geom(out), ffprobe_geom(out2)
            check("deterministic geometry across runs", g1[:2] == g2[:2])
            check("deterministic duration across runs", abs(g1[2] - g2[2]) < 0.05)


def test_integration_missing_asset():
    print("\n[5] integration — missing asset raises RenderError (honest fail)")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        clips = [RenderClip("scene_00", td / "nope.png", None, 2.0)]
        req = RenderRequest(run_id="failtest", clips=clips, output_path=td / "out.mp4",
                            work_dir=td / "work", profile=RenderProfile())
        try:
            VideoUseBackend().render(req); raised = False
        except RenderError:
            raised = True
        check("missing visual -> RenderError (no output)", raised)


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60)
    print(" MODULE 2 — REAL FFMPEG RENDERER — TEST SUITE")
    print("=" * 60)
    test_request_mapping()
    test_write_edl()
    test_honest_failure_validation()
    test_integration_render()
    test_integration_missing_asset()
    print("\n" + "=" * 60)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
