"""Post-render QA checks for timeline integrity and real asset presence."""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_asset(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else _REPO_ROOT / candidate


class QAAgent:
    def run(self, input_data: dict) -> dict:
        edit_timeline = input_data["edit_timeline"]
        clips = edit_timeline["clips"]

        missing_assets = [
            c["asset_path"]
            for c in clips
            if not _resolve_asset(c["asset_path"]).is_file()
            or _resolve_asset(c["asset_path"]).stat().st_size <= 0
        ]
        sync_ok = all(c["start"] < c["end"] for c in clips)
        duration_ok = edit_timeline["total_duration"] > 0
        passed = sync_ok and duration_ok and not missing_assets

        return {
            "sync": sync_ok,
            "duration": duration_ok,
            "missing_assets": missing_assets,
            "passed": passed,
            "status": "PASS" if passed else "FAIL",
        }
