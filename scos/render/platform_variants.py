"""Local platform-variant rendering using the canonical SCOS renderer.

This is a render planner/executor only. It does not publish or contact external
platforms. Each variant remains content/profile/cache bound and inherits the
existing GPU-aware renderer and content-addressed cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scos.control_center.platform_delivery_plan import PLATFORM_FORMATS
from scos.render.base import RenderRequest, RenderResult, RenderProfile
from scos.render.video_use_backend import VideoUseBackend


@dataclass(frozen=True)
class PlatformVariantRender:
    format_id: str
    output_path: Path
    result: RenderResult

    def to_dict(self) -> dict:
        return {
            "format_id": self.format_id,
            "output_path": str(self.output_path),
            "success": self.result.success,
            "duration_s": self.result.duration_s,
            "resolution": f"{self.result.width}x{self.result.height}",
            "fps": self.result.fps,
            "info": self.result.info,
        }


def render_platform_variants(
    request: RenderRequest,
    *,
    format_ids: tuple[str, ...],
    output_dir: Path | None = None,
    cache_root: Path | None = None,
) -> tuple[PlatformVariantRender, ...]:
    output_root = Path(output_dir or request.output_path.parent / "platform")
    backend = VideoUseBackend(cache_root=cache_root)
    results: list[PlatformVariantRender] = []

    for format_id in dict.fromkeys(format_ids):
        spec = PLATFORM_FORMATS.get(format_id)
        if spec is None:
            raise ValueError(f"unsupported platform format: {format_id!r}")
        profile = RenderProfile(
            width=spec["width"],
            height=spec["height"],
            fps=spec["fps"],
            intermediate_crf=request.profile.intermediate_crf,
            grade=request.profile.grade,
        )
        variant_request = RenderRequest(
            run_id=f"{request.run_id}-{format_id}",
            clips=request.clips,
            output_path=output_root / f"{request.run_id}.{format_id}.mp4",
            work_dir=request.work_dir / format_id,
            profile=profile,
        )
        result = backend.render(variant_request)
        results.append(
            PlatformVariantRender(
                format_id=format_id,
                output_path=variant_request.output_path,
                result=result,
            )
        )
    return tuple(results)


__all__ = ["PlatformVariantRender", "render_platform_variants"]
