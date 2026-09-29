from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from scos.render.base import RenderClip, RenderProfile, RenderRequest
from scos.render.platform_variants import render_platform_variants


def _media(path: Path, color: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", f"color=c={color}:s=640x360", "-frames:v", "1", str(path)],
        check=True,
    )


def test_real_platform_variants_cover_all_supported_formats() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _media(root / "scene.png", "blue")
        request = RenderRequest(
            run_id="variant",
            clips=[RenderClip("scene", root / "scene.png", None, 0.8)],
            output_path=root / "base.mp4",
            work_dir=root / "work",
            profile=RenderProfile(),
        )
        results = render_platform_variants(
            request,
            format_ids=("vertical_9_16", "square_1_1", "landscape_16_9"),
            output_dir=root / "out",
            cache_root=root / "cache",
        )
        assert [item.format_id for item in results] == [
            "vertical_9_16",
            "square_1_1",
            "landscape_16_9",
        ]
        assert all(item.result.success for item in results)
        assert [item.result.width for item in results] == [1080, 1080, 1920]
        assert [item.result.height for item in results] == [1920, 1080, 1080]
        assert all(item.output_path.is_file() for item in results)
