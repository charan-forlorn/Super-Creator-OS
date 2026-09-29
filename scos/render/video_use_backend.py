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

import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from scos.media_binaries import resolve_ffmpeg

from scos.render.hardware import EncoderPlan, choose_encoder
from scos.render.render_cache import RenderCache

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
_FFMPEG = resolve_ffmpeg()


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

    def __init__(
        self,
        vu_path: Path = _VU,
        repo_root: Path = _REPO_ROOT,
        *,
        cache_root: Path | None = None,
        cache_enabled: bool = True,
        encoder: EncoderPlan | None = None,
    ) -> None:
        self._vu = vu_path
        self._repo_root = repo_root
        self._encoder = encoder or choose_encoder()
        self._cache = (
            RenderCache(cache_root or (repo_root / "scos" / "work" / ".render-cache"))
            if cache_enabled
            else None
        )

    @property
    def cache(self) -> RenderCache | None:
        return self._cache

    @property
    def encoder(self) -> EncoderPlan:
        return self._encoder

    def _backend_signature(self) -> str:
        files = [self._vu]
        helpers = self._repo_root / "integrations" / "video-use" / "engine"
        files.extend(sorted(helpers.rglob("*.py")))
        digest = hashlib.sha256()
        for path in files:
            if not path.is_file():
                continue
            digest.update(str(path.relative_to(self._repo_root)).replace("\\", "/").encode())
            digest.update(b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
            digest.update(b"\0")
        return digest.hexdigest()

    def _normalize_output_geometry(self, input_path: Path, output_path: Path, width: int, height: int) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(f".normalize.{output_path.suffix.lstrip('.')}")
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )
        cmd = [
            _FFMPEG, "-y", "-hide_banner", "-nostats", "-loglevel", "error",
            "-i", str(input_path),
            "-vf", vf,
            "-c:v", self._encoder.ffmpeg_encoder,
            *self._encoder.args,
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(temporary),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise RenderError(
                f"final geometry normalization failed: {proc.stderr.strip()[-600:]}"
            )
        os.replace(temporary, output_path)

    def _invoke_engine(
        self,
        edl_path: Path,
        output_path: Path,
        *,
        no_loudnorm: bool = False,
    ) -> str:
        """Run `vu.py render <edl> -o <out>`. Returns combined engine output.

        Raises RenderError on a missing shim or a non-zero exit, surfacing the
        engine's stderr tail (the engine itself swallows it internally).
        """
        if not self._vu.exists():
            raise RenderError(f"video-use launcher not found: {self._vu}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(self._vu), "render", str(edl_path), "-o", str(output_path)]
        if no_loudnorm:
            cmd.append("--no-loudnorm")
        cmd += [
            "--video-encoder",
            self._encoder.ffmpeg_encoder,
            "--video-encoder-args-json",
            json.dumps(list(self._encoder.args)),
        ]
        log.info("engine: %s", " ".join(cmd))
        proc = subprocess.run(cmd, cwd=str(self._repo_root), capture_output=True, text=True)
        combined = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            raise RenderError(
                f"video-use render failed (exit {proc.returncode}):\n{combined.strip()[-800:]}"
            )
        return combined

    def render(self, request: RenderRequest) -> RenderResult:
        log.info(
            "render run_id=%s clips=%d -> %s encoder=%s",
            request.run_id,
            len(request.clips),
            request.output_path,
            self._encoder.signature,
        )

        unsupported_generators = sorted(
            {
                clip.generation_backend
                for clip in request.clips
                if clip.generation_backend != "deterministic"
            }
        )
        if unsupported_generators:
            raise RenderError(
                "generative backend(s) requested but not registered on this renderer: "
                + ", ".join(unsupported_generators)
            )

        # Exact final-request fingerprint is content/profile/backend bound.
        scene_fingerprints = (
            self._cache.scene_fingerprints(request, self._encoder.signature)
            if self._cache is not None
            else []
        )
        backend_signature = self._backend_signature()
        final_fingerprint = (
            self._cache.request_fingerprint(
                request,
                scene_fingerprints,
                backend_signature,
                self._encoder.signature,
            )
            if self._cache is not None
            else ""
        )

        if self._cache is not None:
            cached_final = self._cache.lookup_final(final_fingerprint)
            if cached_final is not None:
                self._cache.materialize(cached_final, request.output_path)
                meta = _probe(request.output_path)
                p = request.profile
                expected_duration = sum(clip.duration_s for clip in request.clips)
                if (
                    meta["width"] == p.width
                    and meta["height"] == p.height
                    and abs(meta["duration_s"] - expected_duration) < 0.5
                ):
                    return RenderResult(
                        success=True,
                        video_path=request.output_path,
                        duration_s=round(meta["duration_s"], 3),
                        width=meta["width"],
                        height=meta["height"],
                        fps=meta["fps"],
                        info=(
                            f"cache hit {final_fingerprint[:12]} -> "
                            f"{request.output_path.name}; encoder={self._encoder.signature}"
                        ),
                    )
                self._cache.invalidate(kind="final", key=final_fingerprint)

        # 1-2. Bridge stills+audio -> clips + EDL.
        edl_path = prepare_render_inputs(
            request,
            cache=self._cache,
            encoder=self._encoder,
        )

        # 3. Engine (black box). Silent-only timelines skip loudnorm:
        # there is no program audio to normalize, so the extra analysis pass is wasted.
        self._invoke_engine(
            edl_path,
            request.output_path,
            no_loudnorm=all(clip.audio_path is None for clip in request.clips),
        )

        # 4. Validate the real output. The vendored engine is portrait/landscape
        # oriented; normalize unsupported final geometry at the SCOS boundary.
        meta = _probe(request.output_path)
        p = request.profile
        normalized = False
        if meta["width"] != p.width or meta["height"] != p.height:
            original = request.output_path.with_suffix(".engine.mp4")
            os.replace(request.output_path, original)
            self._normalize_output_geometry(original, request.output_path, p.width, p.height)
            try:
                original.unlink()
            except FileNotFoundError:
                pass
            meta = _probe(request.output_path)
            normalized = True
        if meta["width"] != p.width or meta["height"] != p.height:
            raise RenderError(
                f"output geometry {meta['width']}x{meta['height']} != "
                f"expected {p.resolution}"
            )

        log.info("render ok: %s (%.2fs, %sx%s@%s)", request.output_path,
                 meta["duration_s"], meta["width"], meta["height"], meta["fps"])
        if self._cache is not None:
            self._cache.store(
                kind="final",
                key=final_fingerprint,
                source=request.output_path,
                fingerprint=final_fingerprint,
                metadata={
                    "backend_signature": backend_signature,
                    "encoder": self._encoder.signature,
                    "profile": request.profile.resolution,
                    "scene_count": len(request.clips),
                },
            )

        return RenderResult(
            success=True,
            video_path=request.output_path,
            duration_s=round(meta["duration_s"], 3),
            width=meta["width"],
            height=meta["height"],
            fps=meta["fps"],
            info=(
                f"rendered {len(request.clips)} scene(s) -> "
                f"{request.output_path.name}; normalized={normalized}; "
                f"encoder={self._encoder.signature}; "
                f"cache={final_fingerprint[:12]}"
            ),
        )
