"""Bridge: SCOS stills+audio timeline -> per-scene clips + a video-use EDL.

The vendored video-use engine cuts ranges from *video* sources and has no image
input path. Stage-1 assets are stills (.png) + voiceover (.wav) per scene, so this
module performs the one piece of glue the engine lacks: it renders each
(still, voiceover) pair into a short canvas-sized video clip, then writes a
video-use-compatible `edl.json` whose `sources`/`ranges` point at those clips.

It deliberately does NOT re-implement grade / loudnorm / concat / subtitle
compositing — those stay in the engine, invoked downstream. The EDL shape mirrors
the one produced by integrations/adapter/timeline_to_edl.py so the engine consumes
it unchanged.

All ffmpeg here uses plain `-i` file inputs (no path-inside-filtergraph), which
sidesteps the Windows drive-colon hazard that the engine patches separately.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from scos.render.base import CAMERA_MOTIONS, RenderClip, RenderProfile, RenderRequest, RenderError
from scos.render.hardware import EncoderPlan, choose_encoder
from scos.render.render_cache import RenderCache

log = logging.getLogger("scos.render.edl_bridge")


def _run_ffmpeg(cmd: list[str], what: str) -> None:
    """Run an ffmpeg command, raising RenderError with captured stderr on failure.

    Unlike the engine's `check=True` (which discards the message), we surface the
    tail of ffmpeg's stderr so failures are diagnosable at the SCOS boundary.
    """
    log.debug("ffmpeg: %s", " ".join(cmd))
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()[-600:]
        raise RenderError(f"{what}: ffmpeg exited {proc.returncode}\n{tail}")


def _validate_clip_inputs(clip: RenderClip) -> None:
    """Honest failure: a missing/empty visual (or a declared-but-missing audio)
    is an unrecoverable input error, not something to paper over."""
    v = clip.visual_path
    if not v.exists() or v.stat().st_size == 0:
        raise RenderError(f"scene {clip.scene_id}: visual asset missing/empty: {v}")
    a = clip.audio_path
    if a is not None and (not a.exists() or a.stat().st_size == 0):
        raise RenderError(f"scene {clip.scene_id}: audio asset declared but missing/empty: {a}")
    if clip.duration_s <= 0:
        raise RenderError(f"scene {clip.scene_id}: non-positive duration {clip.duration_s}")


def _motion_vf(clip: RenderClip, width: int, height: int, fps: int) -> str:
    """Build a deterministic Flow-inspired camera move for a still asset."""
    if clip.motion not in CAMERA_MOTIONS:
        raise RenderError(f"scene {clip.scene_id}: unsupported camera motion '{clip.motion}'")
    if not 0.0 <= clip.motion_strength <= 0.5:
        raise RenderError(f"scene {clip.scene_id}: motion_strength must be within [0, 0.5]")
    if clip.motion == "static":
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )

    frames = max(1, round(clip.duration_s * fps))
    progress = f"on/{max(frames - 1, 1)}"
    strength_value = float(clip.motion_strength)
    strength = f"{strength_value:.6f}"
    if clip.motion == "push_in":
        zoom = f"1+{strength}*{progress}"
        x = "(iw-iw/zoom)/2"
        y = "(ih-ih/zoom)/2"
    elif clip.motion == "pull_out":
        zoom = f"1+{strength}*(1-{progress})"
        x = "(iw-iw/zoom)/2"
        y = "(ih-ih/zoom)/2"
    elif clip.motion == "drift_left":
        zoom = f"1+{strength_value * 0.5:.6f}"
        x = f"(iw-iw/zoom)*(1-{progress})"
        y = "(ih-ih/zoom)/2"
    elif clip.motion == "drift_right":
        zoom = f"1+{strength_value * 0.5:.6f}"
        x = f"(iw-iw/zoom)*{progress}"
        y = "(ih-ih/zoom)/2"
    elif clip.motion == "drift_up":
        zoom = f"1+{strength_value * 0.5:.6f}"
        x = "(iw-iw/zoom)/2"
        y = f"(ih-ih/zoom)*(1-{progress})"
    else:  # drift_down
        zoom = f"1+{strength_value * 0.5:.6f}"
        x = "(iw-iw/zoom)/2"
        y = f"(ih-ih/zoom)*{progress}"

    # Fill the vertical canvas with a softened copy, then center the source
    # as a foreground plate. The zoompan operates on the finished shot.
    return (
        f"split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},gblur=sigma=12,eq=brightness=-0.06:saturation=0.90[bg];"
        f"[fgsrc]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps},setsar=1"
    )


def build_scene_clip(
    clip: RenderClip,
    profile: RenderProfile,
    out_path: Path,
    encoder: EncoderPlan | None = None,
) -> None:
    """Render one (still [+ voiceover]) into a canvas-sized clip of exact duration.

    The still is letterboxed (scale+pad) to the profile canvas. Audio is the scene
    voiceover when present, otherwise a synthesized silent stereo track so the
    downstream engine always has an audio stream to fade/normalize.
    """
    _validate_clip_inputs(clip)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    w, h = profile.width, profile.height
    vf = _motion_vf(clip, w, h, profile.fps)
    dur = f"{clip.duration_s:.3f}"

    cmd = ["ffmpeg", "-y", "-hide_banner", "-nostats", "-loglevel", "error",
           "-framerate", "1", "-loop", "1", "-i", str(clip.visual_path)]
    if clip.audio_path is not None:
        cmd += ["-i", str(clip.audio_path)]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]

    encoder = encoder or choose_encoder()
    cmd += [
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", dur,                       # -t (not -shortest) — image loops forever
        "-vf", vf,
        "-r", str(profile.fps),
        *("-c:v", encoder.ffmpeg_encoder),
        *encoder.args,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out_path),
    ]
    log.info("scene %s -> %s (%.3fs)", clip.scene_id, out_path.name, clip.duration_s)
    _run_ffmpeg(cmd, f"scene clip {clip.scene_id}")
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RenderError(f"scene {clip.scene_id}: clip not produced: {out_path}")


def write_edl(
    clip_specs: list[tuple[str, Path, float]],
    profile: RenderProfile,
    edl_path: Path,
) -> Path:
    """Write a video-use-compatible EDL pointing at the prepared scene clips.

    `clip_specs` = [(source_id, clip_path, duration_s)]. Each clip becomes a full
    [0, duration] range so the engine concatenates them in order.
    """
    sources: dict[str, str] = {}
    ranges: list[dict] = []
    total = 0.0
    for source_id, clip_path, dur in clip_specs:
        sources[source_id] = str(clip_path.resolve())
        ranges.append({
            "source": source_id,
            "start": 0.0,
            "end": round(dur, 3),
            "beat": source_id,
            "reason": "scos stills+audio scene clip",
        })
        total += dur

    edl = {
        "version": 1,
        "_generated_by": "scos/render/edl_bridge.py",
        "sources": sources,
        "ranges": ranges,
        "grade": profile.grade,
        "overlays": [],
        "subtitles": None,
        "total_duration_s": round(total, 3),
    }
    edl_path.parent.mkdir(parents=True, exist_ok=True)
    edl_path.write_text(json.dumps(edl, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("EDL -> %s (%d ranges, %.3fs total)", edl_path.name, len(ranges), total)
    return edl_path


def prepare_render_inputs(
    request: RenderRequest,
    *,
    cache: RenderCache | None = None,
    encoder: EncoderPlan | None = None,
) -> Path:
    """Build every scene clip and the EDL. Returns the EDL path for the engine.

    Raises RenderError if there are no clips or any scene fails to build.
    """
    if not request.clips:
        raise RenderError("render request has no clips")

    clips_dir = request.work_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    cache = cache
    encoder = encoder or choose_encoder()

    specs: list[tuple[str, Path, float]] = []
    for i, clip in enumerate(request.clips):
        source_id = f"seg_{i:02d}"
        clip_path = clips_dir / f"{source_id}.mp4"
        if cache is not None:
            fingerprint = cache.clip_fingerprint(
                clip, request.profile, encoder.signature
            )
            cached = cache.lookup_scene(fingerprint)
            if cached is not None:
                cache.materialize(cached, clip_path)
            else:
                build_scene_clip(clip, request.profile, clip_path, encoder)
                cache.store(
                    kind="scene",
                    key=fingerprint,
                    source=clip_path,
                    fingerprint=fingerprint,
                    metadata={
                        "scene_id": clip.scene_id,
                        "encoder": encoder.signature,
                        "profile": request.profile.resolution,
                    },
                )
        else:
            build_scene_clip(clip, request.profile, clip_path, encoder)
        specs.append((source_id, clip_path, clip.duration_s))

    edl_path = request.work_dir / "edl.json"
    return write_edl(specs, request.profile, edl_path)
