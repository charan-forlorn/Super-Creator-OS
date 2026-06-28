"""Module 3 — Real Asset Builder.

Deterministic, local-first generation of per-scene visual + audio assets from a
Module-1 ScenePlan. Writes real files to `scos/work/assets/<run_id>/` and a
manifest to `scos/work/assets_manifest.json` with repo-relative paths.

Same ScenePlan in -> same run_id, same byte-identical files out.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from scos.assets.audio_gen import generate_sine_wav
from scos.assets.image_gen import generate_gradient_png
from scos.assets.models import Asset, AssetBuildResult, AssetConfig

log = logging.getLogger("scos.assets.asset_builder")

# Repo root: scos/assets/asset_builder.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSETS_DIR = _REPO_ROOT / "scos" / "work" / "assets"
_MANIFEST_PATH = _REPO_ROOT / "scos" / "work" / "assets_manifest.json"


def _derive_run_id(scene_plan: dict) -> str:
    """Stable run_id from canonicalized scene-plan content."""
    canon = {
        "scenes": [
            {
                "scene_id": s.get("scene_id"),
                "topic": s.get("topic"),
                "start": s.get("start"),
                "end": s.get("end"),
            }
            for s in scene_plan.get("scenes", [])
        ],
        "total_duration": scene_plan.get("total_duration"),
    }
    blob = json.dumps(canon, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


class AssetBuilder:
    """Generates a deterministic asset bundle for a ScenePlan."""

    def __init__(self, config: AssetConfig | None = None) -> None:
        self.cfg = config or AssetConfig()

    def run(self, scene_plan: dict, run_id: str | None = None) -> dict:
        scenes = scene_plan.get("scenes") or []
        if not scenes:
            raise ValueError("scene_plan has no scenes")

        run_id = run_id or _derive_run_id(scene_plan)
        out_dir = _ASSETS_DIR / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        assets: list[Asset] = []
        total = 0.0
        for scene in scenes:
            scene_id = scene["scene_id"]
            duration = round(float(scene["end"]) - float(scene["start"]), 3)
            if duration <= 0:
                raise ValueError(f"scene {scene_id}: non-positive duration {duration}")

            image_path = out_dir / f"{scene_id}.png"
            audio_path = out_dir / f"{scene_id}.wav"
            image_seed = scene.get("topic") or scene_id
            generate_gradient_png(image_path, self.cfg, image_seed)
            generate_sine_wav(audio_path, self.cfg, duration, scene_id)

            log.info("scene %s -> %s + %s (%.3fs)", scene_id,
                     image_path.name, audio_path.name, duration)
            assets.append(Asset(scene_id, image_path, audio_path, duration))
            total += duration

        result = AssetBuildResult(run_id=run_id, assets=assets,
                                  manifest_path=_MANIFEST_PATH, total_duration=round(total, 3))
        self._write_manifest(result)

        return {
            "run_id": run_id,
            "assets": [a.to_dict(relative_to=_REPO_ROOT) for a in assets],
            "manifest_path": str(_MANIFEST_PATH.relative_to(_REPO_ROOT).as_posix()),
            "total_duration": result.total_duration,
        }

    def _write_manifest(self, result: AssetBuildResult) -> None:
        manifest = {
            "run_id": result.run_id,
            "total_duration": result.total_duration,
            "assets": [a.to_dict(relative_to=_REPO_ROOT) for a in result.assets],
        }
        result.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        result.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("manifest -> %s (%d assets)", result.manifest_path, len(result.assets))
