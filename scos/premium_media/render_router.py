"""Premium renderer routing.
Remotion is the preferred motion/UI/typography engine; FFmpeg handles finishing;
legacy VideoUse remains available for existing EDL pipelines.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import PremiumRenderProfile, RenderBackendKind
from .qc import QCError, validate_render
from .render_cache import (
    RenderCache,
    RenderCacheError,
    cache_key,
    fingerprint_value,
    source_tree_fingerprint,
)


class RenderRouterError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderJob:
    project_dir: Path
    entrypoint: str
    composition_id: str
    props: dict
    output_path: Path
    profile: PremiumRenderProfile


class RemotionBackend:
    def __init__(self, *, node_exe: str = "node") -> None:
        self.node_exe = node_exe

    def render(self, job: RenderJob) -> Path:
        project = job.project_dir.resolve()
        if not (project / "node_modules").exists():
            raise RenderRouterError(f"Remotion dependencies missing: {project}")
        props_path = job.output_path.with_suffix(".props.json").resolve()
        props_path.parent.mkdir(parents=True, exist_ok=True)
        props_path.write_text(
            json.dumps(job.props, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        npx = shutil.which("npx")
        if not npx:
            raise RenderRouterError("npx not found")
        output = job.output_path.resolve()
        codec_map = {
            "libx264": "h264",
            "h264_nvenc": "h264",
            "libx265": "h265",
            "hevc_nvenc": "h265",
            "libaom-av1": "av1",
            "av1_nvenc": "av1",
        }
        remotion_codec = codec_map.get(job.profile.video_codec, "h264")
        command = [
            npx,
            "--yes",
            "remotion",
            "render",
            job.entrypoint,
            job.composition_id,
            str(output),
            f"--props={props_path.as_posix()}",
            f"--codec={remotion_codec}",
            f"--crf={job.profile.video_crf}",
            "--pixel-format",
            job.profile.pix_fmt,
            "--overwrite",
        ]
        proc = subprocess.run(command, cwd=str(project), capture_output=True, text=True)
        if proc.returncode != 0:
            raise RenderRouterError(
                "Remotion render failed:\n" + ((proc.stdout + "\n" + proc.stderr).strip()[-3000:])
            )
        if not output.exists() or output.stat().st_size <= 0:
            raise RenderRouterError("Remotion reported success but output is missing or empty")
        return output


def _cache_relevant_props(props: dict) -> dict:
    """Remove provenance-only graph identity that must not invalidate pixel reuse."""
    payload = json.loads(json.dumps(props, ensure_ascii=False))
    graph = payload.get("production_graph")
    if isinstance(graph, dict):
        graph.pop("loop_run_id", None)
        graph.pop("fingerprint", None)
    return payload


class RenderRouter:
    """Select and execute the canonical renderer with content-addressed reuse."""

    def __init__(
        self,
        *,
        cache: RenderCache | None = None,
        cache_enabled: bool = True,
    ) -> None:
        self.cache = cache
        self.cache_enabled = cache_enabled

    def select(self, *, single_screen: bool = True, requires_vfx: bool = False,
               legacy_edl: bool = False) -> RenderBackendKind:
        if legacy_edl:
            return RenderBackendKind.VIDEO_USE
        if single_screen or requires_vfx:
            return RenderBackendKind.REMOTION
        return RenderBackendKind.FFMPEG

    def render_remotion(self, job: RenderJob) -> Path:
        output = job.output_path.resolve()
        cache = self.cache or RenderCache.for_project(job.project_dir)
        cache_payload = {
            "schema": "SCOS_REMOTION_STAGE_R1",
            "composition_id": job.composition_id,
            "profile": job.profile.__dict__,
            "source_tree_fingerprint": source_tree_fingerprint(job.project_dir),
            "props": fingerprint_value(_cache_relevant_props(job.props), base_dir=job.project_dir),
        }
        key = cache_key(cache_payload)

        if self.cache_enabled:
            hit = cache.lookup("remotion", key)
            if hit is not None:
                cache.materialize(hit, output)
                report = validate_render(
                    output,
                    job.profile,
                    expected_duration_s=job.props.get("duration_s"),
                    require_audio=False,
                )
                if not report.passed:
                    raise RenderRouterError("cached render failed current QC: " + "; ".join(report.errors))
                return output

        rendered = RemotionBackend().render(job)
        report = validate_render(
            rendered,
            job.profile,
            expected_duration_s=job.props.get("duration_s"),
            require_audio=False,
        )
        if not report.passed:
            raise QCError("; ".join(report.errors))
        if self.cache_enabled:
            try:
                cache.store(
                    "remotion",
                    key,
                    rendered,
                    metadata={
                        "composition_id": job.composition_id,
                        "profile": job.profile.__dict__,
                        "source_tree_fingerprint": cache_payload["source_tree_fingerprint"],
                    },
                )
            except RenderCacheError as exc:
                # Cache is derived state; keep a verified render usable when cache I/O fails.
                print(f"[premium-cache] remotion stage not cached: {exc}")
        return rendered


def write_render_job(job: RenderJob, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "project_dir": str(job.project_dir),
                "entrypoint": job.entrypoint,
                "composition_id": job.composition_id,
                "props": job.props,
                "output_path": str(job.output_path),
                "profile": job.profile.__dict__,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return target
