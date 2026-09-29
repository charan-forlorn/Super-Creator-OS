from __future__ import annotations

import json
from pathlib import Path

from integrations.learning.telemetry_receipt import build_telemetry_receipt


CSV = (
    "loop_run_id,project_name,platform,collected_at,views,avg_watch_pct\n"
    "run-1,Demo,youtube_shorts,2026-09-19T00:00:00Z,100,50\n"
)


def test_joined_observation_receipt(tmp_path: Path) -> None:
    export = tmp_path / "analytics.csv"
    export.write_text(CSV, encoding="utf-8")
    db = tmp_path / "database.json"
    db.write_text(
        json.dumps([{
            "project_name": "Demo",
            "product_niche": "test",
            "hook_successful": "x",
            "editing_specs": "x",
            "retention_score": 70,
            "lesson_learned": "x",
            "created_at": "2026-09-19T00:00:00Z",
            "provenance": {"loop_run_id": "run-1"},
        }]),
        encoding="utf-8",
    )
    tel = tmp_path / "telemetry.json"
    receipt = tmp_path / "receipt.json"

    result = build_telemetry_receipt(
        export_path=export,
        db_path=db,
        telemetry_path=tel,
        receipt_path=receipt,
    )

    assert result["status"] == "OBSERVATIONS_JOINED"
    assert result["joined_loop_run_ids"] == ["run-1"]
    assert result["orphan_loop_run_ids"] == []
    assert result["learning_qualification"] is False
    assert receipt.is_file()


def test_orphan_observation_never_qualifies_learning(tmp_path: Path) -> None:
    export = tmp_path / "analytics.csv"
    export.write_text(CSV.replace("run-1", "unknown-run"), encoding="utf-8")
    db = tmp_path / "database.json"
    db.write_text("[]", encoding="utf-8")

    result = build_telemetry_receipt(
        export_path=export,
        db_path=db,
        telemetry_path=tmp_path / "telemetry.json",
        receipt_path=tmp_path / "receipt.json",
    )

    assert result["status"] == "ORPHAN_OBSERVATIONS"
    assert result["learning_qualification"] is False
    assert result["orphan_loop_run_ids"] == ["unknown-run"]


def test_historical_orphan_does_not_poison_new_joined_receipt(tmp_path: Path) -> None:
    export = tmp_path / "analytics.csv"
    export.write_text(CSV, encoding="utf-8")
    db = tmp_path / "database.json"
    db.write_text(
        json.dumps([{
            "project_name": "Demo",
            "product_niche": "test",
            "hook_successful": "x",
            "editing_specs": "x",
            "retention_score": 70,
            "lesson_learned": "x",
            "created_at": "2026-09-19T00:00:00Z",
            "provenance": {"loop_run_id": "run-1"},
        }]),
        encoding="utf-8",
    )
    tel = tmp_path / "telemetry.json"
    tel.write_text(json.dumps([{
        "loop_run_id": "old-orphan",
        "project_name": "Old",
        "platform": "youtube_shorts",
        "collected_at": "2026-09-18T00:00:00Z",
        "views": 1,
        "source": "manual",
    }]), encoding="utf-8")

    result = build_telemetry_receipt(
        export_path=export,
        db_path=db,
        telemetry_path=tel,
        receipt_path=tmp_path / "receipt.json",
    )

    assert result["status"] == "OBSERVATIONS_JOINED"
    assert result["joined_loop_run_ids"] == ["run-1"]
    assert result["orphan_loop_run_ids"] == []


def test_export_preflight_is_atomic_on_later_invalid_row(tmp_path: Path) -> None:
    export = tmp_path / "analytics.csv"
    export.write_text(
        "loop_run_id,project_name,platform,collected_at,views,avg_watch_pct,retention_score\n"
        "run-1,Demo,youtube_shorts,2026-09-19T00:00:00Z,100,50,70\n"
        "run-2,Demo,youtube_shorts,2026-09-19T00:01:00Z,100,51,71\n",
        encoding="utf-8",
    )
    db = tmp_path / "database.json"
    db.write_text("[]", encoding="utf-8")
    tel = tmp_path / "telemetry.json"
    result = build_telemetry_receipt(
        export_path=export,
        db_path=db,
        telemetry_path=tel,
        receipt_path=tmp_path / "receipt.json",
    )

    assert result["status"] == "BLOCKED"
    assert not tel.exists()


def test_missing_export_fails_closed(tmp_path: Path) -> None:
    result = build_telemetry_receipt(
        export_path=tmp_path / "missing.csv",
        db_path=tmp_path / "database.json",
        telemetry_path=tmp_path / "telemetry.json",
        receipt_path=tmp_path / "receipt.json",
    )
    assert result == {"status": "BLOCKED", "reason": "EXPORT_NOT_FOUND"}
