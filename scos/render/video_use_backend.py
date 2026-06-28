"""VideoUseBackend — the concrete RenderBackend for Stage 1.

Pipeline:
  1. Bridge the stills+audio request into per-scene clips + an EDL (edl_bridge).
  2. Invoke the vendored video-use engine through its PUBLIC CLI shim
     (`integrations/video-use/vu.py render <edl> -o <out>`) as a subprocess —
     a black box. No engine symbols are imported; the engine is never modified.
  3. Validate the produced file with ffprobe (exists, non-empty, geometry,
     duration), converting any silent engine failure into an explicit RenderError.

This is the ONLY place in SCOS that touches integrations/video-use, and it does so
exclusively over a process boundary.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from scos.render.base import (
    RenderBackend,
    RenderError,
    RenderRequest,
    RenderResult,
)
from scos.render.edl_bridge import prepare_render_inputs

log = logging.getLogger("scos.render.video_use_backend")

# Repo root: scos/render/video_use_backend.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_VU = _REPO_ROOT / "integrations" / "video-use" / "vu.py"


def _probe(path: Path) -> dict:
    """Return {width, height, fps, duration_s} for a rendered file, or raise."""
    if not path.exists() or path.stat().st_size == 0:
        raise RenderError(f"render output missing or empty: {path}")
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-show_entries", "format=duration",
        "-of", "json", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RenderError(f"ffprobe failed on output {path}: {proc.stderr.strip()[-300:]}")
    data = json.loads(proc.stdout)
    st = (data.get("streams") or [{}])[0]
    fr = st.get("r_frame_rate", "0/1")
    try:
        num, den = (fr.split("/") + ["1"])[:2]
        fps = round(float(num) / float(den)) if float(den) else None
    except (ValueError, ZeroDivisionError):
        fps = None
    return {
        "width": st.get("width"),
        "height": st.get("height"),
        "fps": fps,
        "duration_s": float(data.get("format", {}).get("duration", 0.0) or 0.0),
    }


class VideoUseBackend(RenderBackend):
    """Renders SCOS timelines via the vendored video-use engine CLI."""

    def __init__(self, vu_path: Path = _VU, repo_root: Path = _REPO_ROOT) -> None:
        self._vu = vu_path
        self._repo_root = repo_root

    def _invoke_engine(self, edl_path: Path, output_path: Path) -> str:
        """Run `vu.py render <edl> -o <out>`. Returns combined engine output.

        Raises RenderError on a missing shim or a non-zero exit, surfacing the
        engine's stderr tail (the engine itself swallows it internally).
        """
        if not self._vu.exists():
            raise RenderError(f"video-use launcher not found: {self._vu}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(self._vu), "render", str(edl_path), "-o", str(output_path)]
        log.info("engine: %s", " ".join(cmd))
        proc = subprocess.run(cmd, cwd=str(self._repo_root), capture_output=True, text=True)
        combined = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            raise RenderError(
                f"video-use render failed (exit {proc.returncode}):\n{combined.strip()[-800:]}"
            )
        return combined

    def render(self, request: RenderRequest) -> RenderResult:
        log.info("render run_id=%s clips=%d -> %s",
                 request.run_id, len(request.clips), request.output_path)

        # 1-2. Bridge stills+audio -> clips + EDL.
        edl_path = prepare_render_inputs(request)

        # 3. Engine (black box).
        self._invoke_engine(edl_path, request.output_path)

        # 4. Validate the real output.
        meta = _probe(request.output_path)
        p = request.profile
        if meta["width"] != p.width or meta["height"] != p.height:
            raise RenderError(
                f"output geometry {meta['width']}x{meta['height']} != "
                f"expected {p.resolution}"
            )

        log.info("render ok: %s (%.2fs, %sx%s@%s)", request.output_path,
                 meta["duration_s"], meta["width"], meta["height"], meta["fps"])
        return RenderResult(
            success=True,
            video_path=request.output_path,
            duration_s=round(meta["duration_s"], 3),
            width=meta["width"],
            height=meta["height"],
            fps=meta["fps"],
            info=f"rendered {len(request.clips)} scene(s) -> {request.output_path.name}",
        )
