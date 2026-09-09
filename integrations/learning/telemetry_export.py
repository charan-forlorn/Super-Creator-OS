"""Import platform analytics exports into the observed-only telemetry moat.

Supported inputs: CSV or JSON array/object-of-rows. Export values are treated as
observed data and routed through telemetry_capture.capture; no prediction-derived
field is accepted and no production data is synthesized.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable

import telemetry_capture as TC

FIELD_ALIASES = {
    "loop_run_id": ("loop_run_id", "loopRunId", "run_id"),
    "project_name": ("project_name", "projectName"),
    "platform": ("platform", "source_platform"),
    "collected_at": ("collected_at", "collectedAt", "date", "timestamp"),
    "views": ("views", "view_count", "video_views"),
    "reach": ("reach", "accounts_reached"),
    "avg_watch_pct": ("avg_watch_pct", "averageViewPercentage", "average_view_percentage"),
    "avg_watch_time_s": ("avg_watch_time_s", "averageViewDuration", "average_view_duration"),
    "completion_rate": ("completion_rate", "completionRate"),
    "rewatch_rate_pct": ("rewatch_rate_pct", "rewatch_rate", "rewatchRate"),
    "ctr_pct": ("ctr_pct", "ctr"),
    "likes": ("likes", "like_count"),
    "comments": ("comments", "comment_count"),
    "shares": ("shares", "share_count"),
    "saves": ("saves", "save_count"),
    "followers_gained": ("followers_gained", "subscribersGained", "followersGained"),
}


def _first(row: dict, names: Iterable[str]):
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def normalize_export_row(row: dict, *, source: str = "manual") -> dict:
    out = {"source": source}
    consumed = set()
    for canonical, aliases in FIELD_ALIASES.items():
        value = _first(row, aliases)
        if value is not None:
            out[canonical] = value
            consumed.update(aliases)
    # Preserve unknown fields so downstream observed-only validation can reject
    # forbidden predicted metrics instead of silently dropping them.
    for key, value in row.items():
        if key not in consumed and value not in (None, ""):
            out[key] = value
    for key in ("views", "reach", "avg_watch_pct", "avg_watch_time_s", "completion_rate",
                "rewatch_rate_pct", "ctr_pct", "likes", "comments", "shares", "saves",
                "followers_gained"):
        if key in out:
            out[key] = float(out[key])
    return out


def _load_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        return data["rows"]
    raise ValueError("export JSON must be an array or an object containing 'rows'")


def import_export(path: str | Path, *, telemetry_path=None, db_path=None,
                  source: str = "manual") -> dict:
    """Normalize and capture all rows; stop safely on first rejected row."""
    if source not in {"manual", "api"}:
        raise ValueError("source must be manual or api")
    rows = _load_rows(Path(path))
    results = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            return {"ok": False, "failed_row": index, "errors": ["row is not an object"],
                    "imported": results}
        normalized = normalize_export_row(raw, source=source)
        result = TC.capture(normalized, telemetry_path=telemetry_path, db_path=db_path)
        results.append(result)
        if not result.get("ok"):
            return {"ok": False, "failed_row": index, "imported": results}
    return {"ok": True, "rows_seen": len(rows), "rows_imported": len(results), "results": results}
