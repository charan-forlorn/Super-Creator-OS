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
    RenderError,
    RenderProfile,
    RenderRequest,
    ShotSpec,
)
from scos.render.generative_video_backend import GenerativeVideoBackend
from scos.render.video_use_backend import VideoUseBackend
from scos.premium_media.canonical_backend import PremiumRenderBackend

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
    clips: list[ShotSpec] = []
    for c in clips_in:
        duration = round(float(c["end"]) - float(c["start"]), 3)
        audio = c.get("audio_path")
        clips.append(
            ShotSpec(
                scene_id=c.get("scene_id", f"scene_{len(clips):02d}"),
                visual_path=_resolve(c["asset_path"]),
                audio_path=_resolve(audio) if audio else None,
                duration_s=duration,
                motion=c.get("motion", "static"),
                motion_strength=float(c.get("motion_strength", 0.08)),
                camera=c.get("camera", "locked"),
                action=c.get("action", ""),
                environment=c.get("environment", ""),
                lighting=c.get("lighting", ""),
                style=c.get("style", ""),
                prompt=c.get("prompt", ""),
                references=tuple(c.get("references") or ()),
                start_frame=_resolve(c["start_frame"]) if c.get("start_frame") else None,
                end_frame=_resolve(c["end_frame"]) if c.get("end_frame") else None,
                generation_backend=c.get("generation_backend", "deterministic"),
                continuity_group=c.get("continuity_group", ""),
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
    edit_timeline = input_data.get("edit_timeline", {})
    backend_mode = str(input_data.get("backend") or input_data.get("renderer") or "").lower()
    if backend is None:
        if backend_mode == "premium":
            backend = PremiumRenderBackend()
        else:
            request_probe = _request_from_timeline(run_id, edit_timeline)
            needs_generation = any(
                clip.generation_backend != "deterministic" for clip in request_probe.clips
            )
            backend = GenerativeVideoBackend() if needs_generation else VideoUseBackend()
    if backend_mode == "premium" and isinstance(backend, PremiumRenderBackend):
        premium = input_data.get("premium")
        if not isinstance(premium, dict):
            raise RenderError("premium backend selected but input_data['premium'] is missing")
        from scos.premium_media.models import PremiumRenderProfile
        profile = PremiumRenderProfile(**premium["profile"])
        request = RenderRequest(
            run_id=run_id,
            clips=[],
            output_path=_resolve(str(premium.get("output_path") or f"scos/work/video/{run_id}.mp4")),
            work_dir=_WORK_DIR / run_id,
            profile=RenderProfile(width=profile.width, height=profile.height, fps=profile.fps),
            metadata={"premium": premium},
        )
    else:
        request = _request_from_timeline(run_id, edit_timeline)
    if not request.clips and not (backend_mode == "premium" and isinstance(backend, PremiumRenderBackend)):
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
