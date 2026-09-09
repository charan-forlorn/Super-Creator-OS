from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
import telemetry_export as TE  # noqa: E402


def test_json_export_normalizes_and_imports(tmp_path: Path):
    source = tmp_path / "youtube.json"
    source.write_text(json.dumps([{
        "loopRunId": "run-yt-1", "projectName": "p1", "platform": "youtube_shorts",
        "timestamp": "2026-09-10T01:00:00Z", "views": 1200,
        "averageViewPercentage": 48, "likes": 40, "comments": 3,
        "shares": 7, "subscribersGained": 2,
    }]), encoding="utf-8")
    store = tmp_path / "telemetry.json"

    result = TE.import_export(source, telemetry_path=store)

    assert result["ok"] is True
    rows = json.loads(store.read_text(encoding="utf-8"))
    assert rows[0]["loop_run_id"] == "run-yt-1"
    assert rows[0]["avg_watch_pct"] == 48.0
    assert rows[0]["followers_gained"] == 2.0
    assert rows[0]["source"] == "manual"


def test_csv_export_and_predicted_field_rejected(tmp_path: Path):
    source = tmp_path / "analytics.csv"
    source.write_text(
        "loop_run_id,project_name,platform,collected_at,views,retention_score\n"
        "run-1,p1,tiktok,2026-09-10T02:00:00Z,100,90\n", encoding="utf-8"
    )
    store = tmp_path / "telemetry.json"

    result = TE.import_export(source, telemetry_path=store)

    assert result["ok"] is False
    assert result["failed_row"] == 0
    assert not store.exists() or json.loads(store.read_text(encoding="utf-8")) == []


def test_empty_export_is_valid_noop(tmp_path: Path):
    source = tmp_path / "empty.json"
    source.write_text("[]", encoding="utf-8")
    result = TE.import_export(source, telemetry_path=tmp_path / "telemetry.json")
    assert result == {"ok": True, "rows_seen": 0, "rows_imported": 0, "results": []}
