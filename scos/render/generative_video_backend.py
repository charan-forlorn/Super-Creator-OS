"""Mixed deterministic/generative renderer with deterministic finishing."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from scos.render.base import RenderError, RenderRequest, RenderResult, ShotSpec
from scos.render.edl_bridge import build_scene_clip, write_edl
from scos.render.generative.registry import GenerativeBackendRegistry, build_registry
from scos.render.generative.wan_vace_backend import WanVaceBackend
from scos.render.render_cache import RenderCache
from scos.render.video_use_backend import VideoUseBackend, _probe as probe_output

SILENT_AUDIO = "anullsrc=channel_layout=stereo:sample_rate=48000"


def _stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _scene_key(cache: RenderCache, shot: ShotSpec, profile, encoder: str, provider_id: str, provider_sig: str) -> str:
    payload = {
        "schema": 2,
        "kind": "generative-scene",
        "provider": provider_id,
        "provider_signature": provider_sig,
        "scene_id": shot.scene_id,
        "duration_s": round(shot.duration_s, 6),
        "visual_sha256": cache.source_digest(shot.visual_path),
        "audio_sha256": cache.source_digest(shot.audio_path) if shot.audio_path else "SILENCE",
        "action": shot.action,
        "environment": shot.environment,
        "lighting": shot.lighting,
        "style": shot.style,
        "prompt": shot.prompt,
        "references": list(shot.references),
        "continuity_group": shot.continuity_group,
        "profile": profile.__dict__,
        "encoder": encoder,
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _attach_audio(video_path: Path, audio_path: Path | None, output_path: Path, duration_s: float) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_suffix(f".audio.{os.getpid()}.mp4")
    inputs = ["-i", str(video_path)]
    if audio_path:
        inputs += ["-i", str(audio_path)]
        audio_map = "1:a:0"
    else:
        inputs += ["-f", "lavfi", "-i", SILENT_AUDIO]
        audio_map = "1:a:0"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats", "-loglevel", "error",
        *inputs,
        "-map", "0:v:0", "-map", audio_map,
        "-t", f"{duration_s:.3f}",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", str(temp),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode != 0:
        raise RenderError(f"audio binding failed: {proc.stderr.strip()[-700:]}")
    os.replace(temp, output_path)


class GenerativeVideoBackend(VideoUseBackend):
    """Route non-deterministic shots through a provider, then use SCOS finishing."""

    def __init__(self, *, registry: GenerativeBackendRegistry | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.registry = registry or build_registry([WanVaceBackend()])

    def render(self, request: RenderRequest) -> RenderResult:
        if not request.clips:
            raise RenderError("render request has no clips")
        if all(clip.generation_backend == "deterministic" for clip in request.clips):
            return super().render(request)

        prepared: list[tuple[str, Path, float]] = []
        scene_keys: list[str] = []
        providers: list[str] = []
        work = request.work_dir / "prepared_clips"
        work.mkdir(parents=True, exist_ok=True)

        for index, shot in enumerate(request.clips):
            seg_id = f"seg_{index:02d}"
            clip_path = work / f"{seg_id}.mp4"

            if shot.generation_backend == "deterministic":
                key = self._cache.clip_fingerprint(shot, request.profile, self._encoder.signature)
                scene_keys.append(key)
                cached = self._cache.lookup_scene(key)
                if cached is None:
                    build_scene_clip(shot, request.profile, clip_path, self._encoder)
                    self._cache.store(
                        kind="scene",
                        key=key,
                        source=clip_path,
                        fingerprint=key,
                        metadata={"scene_id": shot.scene_id, "kind": "deterministic"},
                    )
                else:
                    self._cache.materialize(cached, clip_path)
            else:
                provider = self.registry.get(shot.generation_backend)
                provider_sig = getattr(provider, "model_signature", provider.backend_id)
                key = _scene_key(
                    self._cache,
                    shot,
                    request.profile,
                    self._encoder.signature,
                    provider.backend_id,
                    str(provider_sig),
                )
                scene_keys.append(key)
                providers.append(provider.backend_id)
                cached = self._cache.lookup_scene(key)
                if cached is None:
                    generated = provider.generate(shot, request.profile, work / f"{seg_id}.generated.mp4")
                    _attach_audio(generated.video_path, shot.audio_path, clip_path, shot.duration_s)
                    self._cache.store(
                        kind="scene",
                        key=key,
                        source=clip_path,
                        fingerprint=key,
                        metadata={
                            "scene_id": shot.scene_id,
                            "provider": provider.backend_id,
                            "generated_task_id": generated.task_id,
                            "generated_info": generated.info,
                        },
                    )
                else:
                    self._cache.materialize(cached, clip_path)

            prepared.append((seg_id, clip_path, shot.duration_s))

        backend_signature = self._backend_signature() + "|generative|" + "|".join(sorted(set(providers)))
        final_fingerprint = self._cache.request_fingerprint(
            request,
            scene_keys,
            backend_signature,
            self._encoder.signature,
        )
        cached_final = self._cache.lookup_final(final_fingerprint)
        if cached_final is not None:
            self._cache.materialize(cached_final, request.output_path)
            meta = probe_output(request.output_path)
            return RenderResult(
                success=True,
                video_path=request.output_path,
                duration_s=round(meta["duration_s"], 3),
                width=meta["width"],
                height=meta["height"],
                fps=meta["fps"],
                info=f"generative final cache hit {final_fingerprint[:12]}",
            )

        edl_path = write_edl(prepared, request.profile, request.work_dir / "edl.json")
        self._invoke_engine(
            edl_path,
            request.output_path,
            no_loudnorm=all(shot.audio_path is None for shot in request.clips),
        )
        meta = probe_output(request.output_path)
        normalized = False
        if meta["width"] != request.profile.width or meta["height"] != request.profile.height:
            original = request.output_path.with_suffix(".engine.mp4")
            os.replace(request.output_path, original)
            self._normalize_output_geometry(
                original,
                request.output_path,
                request.profile.width,
                request.profile.height,
            )
            original.unlink(missing_ok=True)
            meta = probe_output(request.output_path)
            normalized = True

        if meta["width"] != request.profile.width or meta["height"] != request.profile.height:
            raise RenderError(
                f"generative final geometry {meta['width']}x{meta['height']} "
                f"!= {request.profile.resolution}"
            )

        self._cache.store(
            kind="final",
            key=final_fingerprint,
            source=request.output_path,
            fingerprint=final_fingerprint,
            metadata={
                "providers": sorted(set(providers)),
                "scene_count": len(request.clips),
                "normalized": normalized,
                "encoder": self._encoder.signature,
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
                f"generative render {len(request.clips)} scene(s); "
                f"providers={','.join(sorted(set(providers)))}; "
                f"normalized={normalized}"
            ),
        )


__all__ = ["GenerativeVideoBackend"]
