"""Simulates post-render QA checks: sync, duration, missing assets."""

from __future__ import annotations

import os


class QAAgent:
    def run(self, input_data: dict) -> dict:
        edit_timeline = input_data["edit_timeline"]
        clips = edit_timeline["clips"]

        missing_assets = [
            c["asset_path"] for c in clips if not os.path.exists(c["asset_path"])
        ]
        sync_ok = all(c["start"] < c["end"] for c in clips)
        duration_ok = edit_timeline["total_duration"] > 0

        return {
            "sync": sync_ok,
            "duration": duration_ok,
            "missing_assets": missing_assets,
            "passed": sync_ok and duration_ok,
        }
