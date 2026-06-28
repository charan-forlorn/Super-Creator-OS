"""Render stage entrypoint for the Stage-1 pipeline.

Replaces the former no-op stub with a real renderer. The orchestrator calls
`render(input_data)` exactly as before (unchanged contract), so Module 1 needs no
edit. Behind that function sits the stable `RenderBackend` interface
(`scos/render/base.py`); the default backend (`VideoUseBackend`) drives the
vendored video-use engine over a subprocess boundary.

Honest failure: any unrecoverable problem (missing assets, engine failure, bad
output) raises `RenderError`, which the orchestrator's error boundary records as
`render: failed` — no fabricated success path.
"""

from __future__ import annotations

import logging
from pathlib import Path

from scos.render.base import (
    RenderBackend,
    RenderClip,
    RenderError,
    RenderProfile,
    RenderRequest,
)
from scos.render.video_use_backend import VideoUseBackend

log = logging.getLogger("scos.render.ffmpeg_engine")

# Repo root: scos/render/ffmpeg_engine.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_DIR = _REPO_ROOT / "scos" / "work" / "video"
_WORK_DIR = _REPO_ROOT / "scos" / "work"


def _resolve(path_str: str) -> Path:
    """Resolve an asset path; relative paths are anchored at the repo root."""
    p = Path(path_str)
    return p if p.is_absolute() else (_REPO_ROOT / p)


def _request_from_timeline(run_id: str, edit_timeline: dict) -> RenderRequest:
    """Map the orchestrator's edit_timeline (stills+audio) into a RenderRequest."""
    clips_in = edit_timeline.get("clips") or []
    clips: list[RenderClip] = []
    for c in clips_in:
        duration = round(float(c["end"]) - float(c["start"]), 3)
        audio = c.get("audio_path")
        clips.append(
            RenderClip(
                scene_id=c.get("scene_id", f"scene_{len(clips):02d}"),
                visual_path=_resolve(c["asset_path"]),
                audio_path=_resolve(audio) if audio else None,
                duration_s=duration,
            )
        )
    return RenderRequest(
        run_id=run_id,
        clips=clips,
        output_path=_OUTPUT_DIR / f"{run_id}.mp4",
        work_dir=_WORK_DIR / run_id,
        profile=RenderProfile(),
    )


def render(input_data: dict, backend: RenderBackend | None = None) -> dict:
    """Render the pipeline's edit_timeline to a real .mp4.

    Args:
        input_data: {"run_id": str, "edit_timeline": {clips, total_duration}}.
        backend: optional RenderBackend (dependency injection for tests). Defaults
            to the production VideoUseBackend.

    Returns a dict with the produced video path and render metadata.
    Raises RenderError on any unrecoverable failure.
    """
    run_id = input_data["run_id"]
    edit_timeline = input_data["edit_timeline"]
    backend = backend or VideoUseBackend()

    request = _request_from_timeline(run_id, edit_timeline)
    if not request.clips:
        raise RenderError(f"run {run_id}: edit_timeline has no clips to render")

    result = backend.render(request)

    return {
        "video_path": str(result.video_path),
        "render_success": result.success,
        "duration_s": result.duration_s,
        "resolution": f"{result.width}x{result.height}",
        "fps": result.fps,
        "info": result.info,
    }
