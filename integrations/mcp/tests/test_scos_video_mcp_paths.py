"""test_scos_video_mcp_paths.py — SCOS-C2: per-tool path-boundary suite.

Scope
-----
For EVERY path-accepting tool exposed by ``integrations/mcp/scos_video_mcp.py``:

*   an escaping INPUT path (``../``, absolute outside the allow-root) is refused
    before ffmpeg/ffprobe is invoked;
*   an escaping OUTPUT path is refused before ffmpeg is invoked;
*   a path inside the allow-root is ACCEPTED and reaches the intended call.

Tool inventory under test (11 registered tools):

    input paths : probe, volume_stats, scene_cuts, extract_frames(path),
                  extract_audio(path), trim(path), mux_audio(video/audio),
                  grade(path), burn_subtitles(path, srt), concat_list(paths),
                  analyze_virality(path)
    output paths: extract_frames(out_dir), extract_audio(out_path),
                  trim(out_path), mux_audio(out_path), grade(out_path),
                  burn_subtitles(out_path), concat_list(out_path)

How "reaches the intended call" is proven
------------------------------------------
Acceptance tests use a REAL ffmpeg-generated asset inside the allow-root and
assert that the tool's success/behaviour depends on that real file: the tool
either returns well-formed output, or (for tools whose behaviour needs a longer
media stream) the returned error proves the file WAS opened. Either way, the
call reached ffmpeg with the in-allow-root path — which is exactly the property
under test. No tool output is fabricated; every assertion is on real tool output.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE))  # tests dir: tool_call lives beside the test modules

import mcp_allow_root as G  # noqa: E402
from tool_call import call_text, unwrap_tool_error  # noqa: E402
from mcp.server.fastmcp.exceptions import ToolError  # noqa: E402


async def _call_expect_violation(mcp, tool: str, args: dict) -> None:
    """Call a tool and assert it raised AllowRootViolation (unwrapping FastMCP's ToolError)."""
    try:
        await mcp.call_tool(tool, args)
    except ToolError as e:
        raise unwrap_tool_error(e) from None
    raise AssertionError(f"{tool} did not raise AllowRootViolation")

# Fixtures (allow_root, mcp_module, sample_video) come from conftest.py.


# --- the tool inventory, kept explicit on purpose ---------------------------
# Each entry names the tool and which of its string parameters are paths.
# `path_kind`: "single" (one path string) or "csv" (comma-separated path list).

INPUT_TOOLS: list[tuple[str, dict[str, str]]] = [
    ("probe", {"path": "single"}),
    ("volume_stats", {"path": "single"}),
    ("scene_cuts", {"path": "single"}),
    ("analyze_virality", {"path": "single"}),
    ("extract_frames", {"path": "single"}),
    ("extract_audio", {"path": "single"}),
    ("trim", {"path": "single"}),
    ("grade", {"path": "single"}),
    ("burn_subtitles", {"path": "single"}),
    ("mux_audio", {"video_path": "single"}),
    ("concat_list", {"paths": "csv"}),
]

OUTPUT_TOOLS: list[tuple[str, dict[str, str]]] = [
    ("extract_frames", {"out_dir": "single"}),
    ("extract_audio", {"out_path": "single"}),
    ("trim", {"out_path": "single"}),
    ("grade", {"out_path": "single"}),
    ("burn_subtitles", {"out_path": "single"}),
    ("mux_audio", {"out_path": "single"}),
    ("concat_list", {"out_path": "single"}),
]

REGISTERED_TOOLS = [
    "analyze_virality", "burn_subtitles", "concat_list", "extract_audio",
    "extract_frames", "grade", "mux_audio", "probe", "scene_cuts", "trim",
    "volume_stats",
]


def _inside(allow_root: Path, name: str) -> str:
    return str(allow_root / name)


# ===========================================================================
# 1. Registration: the 11 tools are intact
# ===========================================================================


def test_all_eleven_tools_registered(mcp_module):
    names = set(mcp_module.mcp._tool_manager._tools.keys())
    assert names == set(REGISTERED_TOOLS), f"tool set drifted: {sorted(names ^ set(REGISTERED_TOOLS))}"
    assert len(names) == 11


@pytest.mark.asyncio
async def test_tool_listing_round_trip(mcp_module):
    from mcp.server.fastmcp import FastMCP  # local import: only needs the type

    assert isinstance(mcp_module.mcp, FastMCP)
    tools = await mcp_module.mcp.list_tools()
    assert len(tools) == 11
    listed = {t.name for t in tools}
    assert listed == set(REGISTERED_TOOLS)


# ===========================================================================
# 2. Every path-accepting tool refuses an escaping INPUT path
# ===========================================================================


@pytest.mark.parametrize("tool,params", INPUT_TOOLS, ids=[t for t, _ in INPUT_TOOLS])
@pytest.mark.asyncio
async def test_parent_traversal_input_rejected(mcp_module, sample_video, allow_root, tool, params):
    """``../`` traversal on the first path parameter is refused per tool."""
    escaped = str(sample_video.parent.parent / sample_video.name)
    args = _args(tool, escaped if "path" in params or tool != "mux_audio" else escaped, allow_root, sample_video)
    with pytest.raises(G.AllowRootViolation):
        await _call_expect_violation(mcp_module.mcp, tool, args)


@pytest.mark.parametrize("tool,params", INPUT_TOOLS, ids=[t for t, _ in INPUT_TOOLS])
@pytest.mark.asyncio
async def test_absolute_outside_input_rejected(mcp_module, sample_video, allow_root, tool, params):
    """A real file that exists but lives OUTSIDE the allow-root is refused."""
    args = _args(tool, str(sample_video), allow_root, sample_video)
    with pytest.raises(G.AllowRootViolation):
        await _call_expect_violation(mcp_module.mcp, tool, args)


def _args(tool: str, path_value: str, allow_root: Path, sample_video: Path) -> dict:
    """Build a minimal, type-valid argument dict for `tool` with path_value in
    the tool's primary path parameter."""
    inside_srt = allow_root / "subs.srt"
    inside_audio = allow_root / "audio.wav"
    inside_out = allow_root / "out.mp4"
    base = {
        "probe": {"path": path_value},
        "volume_stats": {"path": path_value},
        "scene_cuts": {"path": path_value},
        "analyze_virality": {"path": path_value},
        "extract_frames": {"path": path_value, "times": "0", "out_dir": str(allow_root)},
        "extract_audio": {"path": path_value, "out_path": str(inside_out)},
        "trim": {"path": path_value, "out_path": str(inside_out), "start": 0, "duration": 0.1},
        "grade": {"path": path_value, "out_path": str(inside_out)},
        "burn_subtitles": {"path": path_value, "srt_path": str(inside_srt), "out_path": str(inside_out)},
        "mux_audio": {"video_path": path_value, "audio_path": str(inside_audio), "out_path": str(inside_out)},
        "concat_list": {"paths": path_value, "out_path": str(inside_out)},
    }[tool]
    return base


# ===========================================================================
# 3. Every path-accepting tool refuses an escaping OUTPUT path
# ===========================================================================


@pytest.mark.parametrize("tool", [t for t, _ in OUTPUT_TOOLS], ids=[t for t, _ in OUTPUT_TOOLS])
@pytest.mark.asyncio
async def test_absolute_outside_output_rejected(mcp_module, sample_video, allow_root, tool):
    """An in-allow-root INPUT paired with an escaping OUTPUT path is refused."""
    inside_video = allow_root / "in.mp4"
    shutil.copyfile(sample_video, inside_video)
    outside_out = sample_video.parent / f"escaped_{tool}.mp4"
    args = _args(tool, str(inside_video), allow_root, sample_video)
    args[OUTPUT_PARAM[tool]] = str(outside_out)
    with pytest.raises(G.AllowRootViolation):
        await _call_expect_violation(mcp_module.mcp, tool, args)


OUTPUT_PARAM: dict[str, str] = {
    "extract_frames": "out_dir",
    "extract_audio": "out_path",
    "trim": "out_path",
    "grade": "out_path",
    "burn_subtitles": "out_path",
    "mux_audio": "out_path",
    "concat_list": "out_path",
}


@pytest.mark.parametrize("tool", [t for t, _ in OUTPUT_TOOLS], ids=[t for t, _ in OUTPUT_TOOLS])
@pytest.mark.asyncio
async def test_parent_traversal_output_rejected(mcp_module, sample_video, allow_root, tool):
    inside_video = allow_root / "in.mp4"
    shutil.copyfile(sample_video, inside_video)
    args = _args(tool, str(inside_video), allow_root, sample_video)
    args[OUTPUT_PARAM[tool]] = str(allow_root / ".." / f"escaped_{tool}.mp4")
    with pytest.raises(G.AllowRootViolation):
        await _call_expect_violation(mcp_module.mcp, tool, args)


# ===========================================================================
# 4. In-allow-root paths are ACCEPTED and reach the intended call
# ===========================================================================


@pytest.mark.asyncio
async def test_probe_accepts_in_allow_root_video(mcp_module, sample_video, allow_root):
    inside = allow_root / "in.mp4"
    shutil.copyfile(sample_video, inside)
    text = await call_text(mcp_module.mcp, "probe", {"path": str(inside)})
    data = json.loads(text)
    assert data["width"] == 64 and data["height"] == 64
    assert data["duration_s"] > 0


@pytest.mark.asyncio
async def test_volume_stats_accepts_in_allow_root(mcp_module, sample_video, allow_root):
    """Video-only source: ffmpeg runs and reports 'n/a' volume → proves the call ran."""
    inside = allow_root / "in.mp4"
    shutil.copyfile(sample_video, inside)
    text = await call_text(mcp_module.mcp, "volume_stats", {"path": str(inside)})
    data = json.loads(text)
    assert set(data) == {"mean_volume", "max_volume"}


@pytest.mark.asyncio
async def test_scene_cuts_accepts_in_allow_root(mcp_module, sample_video, allow_root):
    inside = allow_root / "in.mp4"
    shutil.copyfile(sample_video, inside)
    text = await call_text(mcp_module.mcp, "scene_cuts", {"path": str(inside)})
    assert isinstance(json.loads(text)["count"], int)


@pytest.mark.asyncio
async def test_analyze_virality_accepts_in_allow_root(mcp_module, sample_video, allow_root):
    inside = allow_root / "in.mp4"
    shutil.copyfile(sample_video, inside)
    data = json.loads(await call_text(mcp_module.mcp, "analyze_virality", {"path": str(inside)}))
    assert 0 <= data["score"] <= 100
    assert data["metrics"]["resolution"] == "64x64"


@pytest.mark.asyncio
async def test_extract_frames_accepts_in_allow_root_and_writes(mcp_module, sample_video, allow_root):
    inside = allow_root / "in.mp4"
    shutil.copyfile(sample_video, inside)
    out_dir = allow_root / "frames"
    text = await call_text(mcp_module.mcp, "extract_frames",
                           {"path": str(inside), "times": "0", "out_dir": str(out_dir)})
    written = json.loads(text)["written"]
    assert written, "no frames written"
    assert Path(written[0]).resolve().parent == out_dir.resolve()
    assert Path(written[0]).exists()


@pytest.mark.asyncio
async def test_extract_audio_accepts_in_allow_root(mcp_module, sample_video, allow_root):
    """Video-only input has no audio track; ffmpeg must still be REACHED."""
    inside = allow_root / "in.mp4"
    shutil.copyfile(sample_video, inside)
    out = allow_root / "a.wav"
    text = await call_text(mcp_module.mcp, "extract_audio",
                           {"path": str(inside), "out_path": str(out)})
    # Either it succeeded (unlikely for a silent source) or it failed at ffmpeg
    # with an audio-stream error — both prove the in-allow-root file was opened.
    # The failure mode for a video-only source is "Output file does not contain
    # any stream" (no audio stream to map) — that also proves ffmpeg was reached.
    assert (text.startswith("OK ->")
            or "Stream map" in text
            or "Audio stream" in text
            or "does not contain any stream" in text), text


@pytest.mark.asyncio
async def test_trim_accepts_in_allow_root_and_writes(mcp_module, sample_video, allow_root):
    inside = allow_root / "in.mp4"
    shutil.copyfile(sample_video, inside)
    out = allow_root / "trimmed.mp4"
    text = await call_text(mcp_module.mcp, "trim",
                           {"path": str(inside), "out_path": str(out), "start": 0, "duration": 0.2})
    assert text.startswith("OK ->") or out.exists()
    if out.exists():
        assert out.stat().st_size > 0


@pytest.mark.asyncio
async def test_grade_accepts_in_allow_root_and_writes(mcp_module, sample_video, allow_root):
    inside = allow_root / "in.mp4"
    shutil.copyfile(sample_video, inside)
    out = allow_root / "graded.mp4"
    text = await call_text(mcp_module.mcp, "grade",
                           {"path": str(inside), "out_path": str(out), "preset": "punch"})
    assert text.startswith("OK (punch) ->") or out.exists()


@pytest.mark.asyncio
async def test_grade_unknown_preset_still_validated_by_boundary(mcp_module, sample_video, allow_root):
    """The path guard runs BEFORE the preset check — an escaping path with an
    unknown preset must be refused on the boundary, not on the preset."""
    escaped = str(sample_video)
    out_inside = str(allow_root / "g.mp4")
    with pytest.raises(G.AllowRootViolation):
        await _call_expect_violation(mcp_module.mcp, "grade", {"path": escaped, "out_path": out_inside, "preset": "nope"})


@pytest.mark.asyncio
async def test_burn_subtitles_accepts_in_allow_root(mcp_module, sample_video, allow_root):
    inside = allow_root / "in.mp4"
    shutil.copyfile(sample_video, inside)
    srt = allow_root / "subs.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
    out = allow_root / "subbed.mp4"
    text = await call_text(mcp_module.mcp, "burn_subtitles",
                           {"path": str(inside), "srt_path": str(srt), "out_path": str(out)})
    assert text.startswith("OK ->") or out.exists()


@pytest.mark.asyncio
async def test_burn_subtitles_escaped_srt_rejected(mcp_module, sample_video, allow_root):
    """The .srt INPUT is also a host path — escaping it must be refused."""
    inside = allow_root / "in.mp4"
    shutil.copyfile(sample_video, inside)
    outside_srt = sample_video.parent / "outside.srt"
    outside_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")
    with pytest.raises(G.AllowRootViolation):
        await _call_expect_violation(mcp_module.mcp,
            "burn_subtitles",
            {"path": str(inside), "srt_path": str(outside_srt), "out_path": str(allow_root / "o.mp4")})


@pytest.mark.asyncio
async def test_concat_list_accepts_in_allow_root(mcp_module, sample_video, allow_root):
    a = allow_root / "a.mp4"
    b = allow_root / "b.mp4"
    shutil.copyfile(sample_video, a)
    shutil.copyfile(sample_video, b)
    out = allow_root / "cat.mp4"
    text = await call_text(mcp_module.mcp, "concat_list", {"paths": f"{a},{b}", "out_path": str(out)})
    assert text.startswith("OK (2 clips) ->") or out.exists()


@pytest.mark.asyncio
async def test_concat_list_rejects_any_escaped_component(mcp_module, sample_video, allow_root):
    """Every component of the comma-separated list must be inside the boundary."""
    a = allow_root / "a.mp4"
    shutil.copyfile(sample_video, a)
    with pytest.raises(G.AllowRootViolation):
        await _call_expect_violation(mcp_module.mcp,
            "concat_list", {"paths": f"{a},{sample_video}", "out_path": str(allow_root / "o.mp4")})


# ===========================================================================
# 5. The escaping call must never reach ffmpeg
# ===========================================================================


@pytest.mark.asyncio
async def test_escape_never_invokes_ffmpeg(mcp_module, monkeypatch: pytest.MonkeyPatch, allow_root):
    """Subprocess.run must not be called at all for an escaping path.

    This is the core R-1 property: the guard refuses BEFORE any host access,
    so the tool cannot read or write a file outside the boundary even if the
    media binary itself would happily process it.
    """
    calls: list = []
    real_run = mcp_module.subprocess.run

    def spy(*a, **kw):
        calls.append(a[0] if a else None)
        return real_run(*a, **kw)

    monkeypatch.setattr(mcp_module.subprocess, "run", spy)
    with pytest.raises(G.AllowRootViolation):
        await _call_expect_violation(mcp_module.mcp, "probe", {"path": str(allow_root / ".." / "x.mp4")})
    assert calls == [], f"ffmpeg/ffprobe was invoked despite the guard: {calls}"


@pytest.mark.asyncio
async def test_escape_does_not_create_output_file(mcp_module, sample_video, allow_root):
    """An escaping out_path must not create or truncate a file outside the root."""
    inside = allow_root / "in.mp4"
    shutil.copyfile(sample_video, inside)
    victim = sample_video.parent / "victim.mp4"
    if victim.exists():
        victim.unlink()
    with pytest.raises(G.AllowRootViolation):
        await _call_expect_violation(mcp_module.mcp,
            "trim", {"path": str(inside), "out_path": str(victim), "start": 0, "duration": 0.1})
    assert not victim.exists(), "guard allowed a write outside the allow-root"
