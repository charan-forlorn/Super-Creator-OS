"""Maps each scene to a deterministic (dummy) media asset path."""

from __future__ import annotations

import hashlib


class AssetBuilder:
    def run(self, input_data: dict) -> dict:
        run_id = input_data["run_id"]
        scenes = input_data["scene_plan"]["scenes"]

        assets = []
        for scene in scenes:
            digest = hashlib.sha256(f"{run_id}:{scene['scene_id']}".encode()).hexdigest()[:8]
            assets.append(
                {
                    "scene_id": scene["scene_id"],
                    "asset_path": f"scos/work/frames/{run_id}_{digest}.png",
                    "audio_path": f"scos/work/audio/{run_id}_{digest}.wav",
                }
            )

        return {"assets": assets}
