"""Canonical SCOS RenderBackend bridge for Premium Media.

Premium Media owns richer creative data, but orchestration enters through the
existing scos.render.base.RenderBackend contract. This adapter is the boundary.
"""
from __future__ import annotations

from pathlib import Path

from scos.render.base import RenderBackend, RenderError, RenderRequest, RenderResult

from .brand import BrandKitError, brand_profile_to_props, repository_root, resolve_brand_profile
from .models import AudioRole, AudioStem, PremiumRenderProfile, SubtitleCue
from .pipeline import finalize_video
from .render_router import RenderJob, RenderRouter, RenderRouterError
from .safe_zone import LayoutBox, validate_layout
from .qc import probe_media


class PremiumRenderBackend(RenderBackend):
    def render(self, request: RenderRequest) -> RenderResult:
        cfg = request.metadata.get("premium")
        if not isinstance(cfg, dict):
            raise RenderError("request.metadata['premium'] is required for PremiumRenderBackend")
        try:
            profile = PremiumRenderProfile(**cfg["profile"])
            project_dir = Path(cfg["project_dir"])
            entrypoint = str(cfg.get("entrypoint", "src/index.jsx"))
            composition_id = str(cfg["composition_id"])
            props = dict(cfg["props"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RenderError(f"invalid premium render metadata: {exc}") from exc

        meta = props.get("production_graph", {})
        brand_id = meta.get("brand_kit_id") if isinstance(meta, dict) else None
        try:
            brand = resolve_brand_profile(repository_root(project_dir), brand_id)
        except BrandKitError as exc:
            raise RenderError(f"brand kit resolution failed: {exc}") from exc
        if brand is not None:
            props["brand"] = brand_profile_to_props(brand)
        if request.profile.width != profile.width or request.profile.height != profile.height:
            raise RenderError("canonical RenderProfile geometry does not match premium delivery profile")
        props.setdefault("width", profile.width)
        props.setdefault("height", profile.height)
        props.setdefault("fps", profile.fps)
        left = profile.width * 0.065
        right = profile.width * 0.935
        safe_errors = validate_layout(
            width=profile.width,
            height=profile.height,
            boxes=(
                LayoutBox("primary_content", left, profile.height * 0.094, right, profile.height * 0.859),
                LayoutBox("caption_region", profile.width * 0.072, profile.height * 0.755, profile.width * 0.928, profile.height * 0.912),
                LayoutBox("header_region", left, profile.height * 0.061, right, profile.height * 0.156),
                LayoutBox("footer_region", profile.width * 0.072, profile.height * 0.917, profile.width * 0.928, profile.height * 0.946),
            ),
        )
        if safe_errors:
            raise RenderError("safe-zone preflight failed: " + "; ".join(safe_errors))

        base_output = request.output_path.with_name(request.output_path.stem + ".render.mp4")
        job = RenderJob(
            project_dir=project_dir,
            entrypoint=entrypoint,
            composition_id=composition_id,
            props=props,
            output_path=base_output,
            profile=profile,
        )
        try:
            rendered = RenderRouter().render_remotion(job)
        except RenderRouterError as exc:
            raise RenderError(str(exc)) from exc

        stems = [
            AudioStem(
                asset_id=str(s["asset_id"]),
                role=AudioRole(str(s["role"])),
                start_s=float(s.get("start_s", 0.0)),
                gain_db=float(s.get("gain_db", 0.0)),
            )
            for s in cfg.get("audio_stems", [])
        ]
        cues = [
            SubtitleCue(
                start_s=float(c["start_s"]), end_s=float(c["end_s"]),
                text=str(c["text"]), language=str(c.get("language", "und")),
            )
            for c in cfg.get("subtitles", [])
        ]
        try:
            report = finalize_video(
                rendered, request.output_path, profile,
                audio_stems=stems, subtitles=cues,
                production_metadata={
                    "brand_kit_id": brand.brand_kit_id if brand is not None else None,
                    "brand_fingerprint": brand.fingerprint() if brand is not None else None,
                    "render_geometry": {"width": profile.width, "height": profile.height, "fps": profile.fps},
                },
            )
        except Exception as exc:
            raise RenderError(str(exc)) from exc
        probe = report.probe or probe_media(request.output_path)
        return RenderResult(
            success=True, video_path=request.output_path,
            duration_s=probe.duration_s, width=probe.width, height=probe.height,
            fps=round(probe.fps), info=f"premium:{profile.name}",
        )
