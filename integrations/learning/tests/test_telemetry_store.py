"""Focused tests for telemetry store fail-closed persistence behavior."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent
sys.path.insert(0, str(_PKG))

import telemetry as TEL  # noqa: E402


def _row(**overrides):
    row = {
        "loop_run_id": "loop-1",
        "project_name": "Project",
        "platform": "tiktok",
        "collected_at": "2026-07-16T00:00:00Z",
        "avg_watch_pct": 55,
    }
    row.update(overrides)
    return row


def test_non_array_telemetry_store_fails_closed(tmp_path: Path):
    store = tmp_path / "telemetry.json"
    store.write_text("{}", encoding="utf-8")
    before = store.read_bytes()

    try:
        TEL.load_telemetry(store)
    except ValueError as exc:
        assert "root is not a JSON array" in str(exc)
    else:
        raise AssertionError("non-array telemetry store must fail closed")

    ok, info = TEL.append_telemetry(_row(), path=store)
    assert ok is False
    assert "root is not a JSON array" in info
    assert store.read_bytes() == before


def test_malformed_telemetry_store_fails_closed_without_repair(tmp_path: Path):
    store = tmp_path / "telemetry.json"
    store.write_text("[{broken", encoding="utf-8")
    before = store.read_bytes()

    ok, info = TEL.append_telemetry(_row(), path=store)

    assert ok is False
    assert "telemetry store malformed" in info
    assert store.read_bytes() == before


def test_telemetry_survives_restart_read_from_temp_store(tmp_path: Path):
    store = tmp_path / "telemetry.json"
    ok, info = TEL.append_telemetry(_row(), path=store)
    assert ok is True, info

    reloaded = TEL.load_telemetry(store)

    assert reloaded == [_row()]
    assert json.loads(store.read_text(encoding="utf-8")) == [_row()]
