"""Builds a timestamp-based edit timeline from scenes + assets."""

from __future__ import annotations


class EditComposer:
    def run(self, input_data: dict) -> dict:
        scenes = input_data["scene_plan"]["scenes"]
        assets = {a["scene_id"]: a for a in input_data["asset_bundle"]["assets"]}

        clips = []
        for scene in scenes:
            asset = assets[scene["scene_id"]]
            clips.append(
                {
                    "scene_id": scene["scene_id"],
                    "start": scene["start"],
                    "end": scene["end"],
                    "asset_path": asset["asset_path"],
                    "audio_path": asset["audio_path"],
                }
            )

        return {"clips": clips, "total_duration": input_data["scene_plan"]["total_duration"]}
