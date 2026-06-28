"""Converts a script brief into an ordered list of timeline scenes."""

from __future__ import annotations


class ScenePlanner:
    def run(self, input_data: dict) -> dict:
        script = input_data["script"]
        duration_target = script["duration_target"]
        points = script["main_points"]

        scene_count = max(1, len(points))
        scene_duration = round(duration_target / scene_count, 2)

        scenes = []
        cursor = 0.0
        for i, point in enumerate(points):
            scenes.append(
                {
                    "scene_id": f"scene_{i:02d}",
                    "topic": point,
                    "start": cursor,
                    "end": round(cursor + scene_duration, 2),
                }
            )
            cursor = round(cursor + scene_duration, 2)

        return {"scenes": scenes, "total_duration": cursor}
