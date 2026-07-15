"""Focused tests for the canonical/runtime memory compatibility adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent
sys.path.insert(0, str(_PKG))

import memory_store as MS  # noqa: E402
import runtime_journal as RJ  # noqa: E402


def _canonical_record(project_name: str = "Canonical Project", created_at: str = "2026-07-15T12:00:00Z"):
    return {
        "project_name": project_name,
        "product_niche": "Gaming (MOBA)",
        "hook_successful": "hook",
        "editing_specs": "spec",
        "retention_score": 80,
        "lesson_learned": "lesson",
        "created_at": created_at,
    }


def _runtime_record(project_name: str = "Runtime Project", attempt_id: str = "attempt-1"):
    return RJ.ensure_runtime_record_id({
        "record_type": "practice_render",
        "engine": "practice-loop",
        "project_name": project_name,
        "platform_family": "tiktok_ig_yt_shorts",
        "format_id": "vertical_9_16",
        "render_source_id": "dry-run",
        "attempt_id": attempt_id,
        "created_at": "2026-07-15T12:00:00",
    })


def _write_canonical(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_runtime(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_default_read_is_canonical_only_and_ignores_malformed_runtime(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "memory" / "runtime" / "practice-render.jsonl"
    expected = _canonical_record()
    _write_canonical(canonical, [expected])
    runtime.parent.mkdir(parents=True)
    runtime.write_text("{malformed\n", encoding="utf-8")

    rows = MS.read_records(canonical_path=canonical, runtime_path=runtime)

    assert rows == [expected]
    assert "source_layer" not in rows[0]


def test_runtime_only_read_is_explicit_and_source_layered(tmp_path: Path):
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    rec = _runtime_record()
    _write_runtime(runtime, [rec])

    rows = MS.read_records(mode=MS.RUNTIME_ONLY, runtime_path=runtime)

    assert len(rows) == 1
    assert rows[0]["runtime_record_id"] == rec["runtime_record_id"]
    assert rows[0]["source_layer"] == "runtime"


def test_combined_read_marks_source_layer_and_canonical_wins_collision(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "memory" / "runtime" / "practice-render.jsonl"
    canon = _canonical_record(project_name="Same Project")
    duplicate_runtime = _runtime_record(project_name="Same Project", attempt_id="same-project-runtime")
    unique_runtime = _runtime_record(project_name="Runtime Only", attempt_id="unique-runtime")
    _write_canonical(canonical, [canon])
    _write_runtime(runtime, [duplicate_runtime, unique_runtime])

    rows = MS.read_records(mode=MS.COMBINED, canonical_path=canonical, runtime_path=runtime)

    assert [(row["project_name"], row["source_layer"]) for row in rows] == [
        ("Same Project", "canonical"),
        ("Runtime Only", "runtime"),
    ]


def test_runtime_malformed_blocks_runtime_and_combined_but_not_canonical(tmp_path: Path):
    canonical = tmp_path / "database.json"
    runtime = tmp_path / "practice-render.jsonl"
    _write_canonical(canonical, [_canonical_record()])
    runtime.write_text("[]\n", encoding="utf-8")

    assert len(MS.read_records(canonical_path=canonical, runtime_path=runtime)) == 1
    for mode in (MS.RUNTIME_ONLY, MS.COMBINED):
        try:
            MS.read_records(mode=mode, canonical_path=canonical, runtime_path=runtime)
        except ValueError as exc:
            assert "line 1" in str(exc)
        else:
            raise AssertionError(f"{mode} read should fail on malformed runtime")


def test_reads_do_not_create_missing_files_or_directories(tmp_path: Path):
    canonical = tmp_path / "missing" / "database.json"
    runtime = tmp_path / "missing-runtime" / "practice-render.jsonl"

    assert MS.read_records(canonical_path=canonical, runtime_path=runtime) == []
    assert MS.read_records(mode=MS.RUNTIME_ONLY, runtime_path=runtime) == []

    assert not canonical.parent.exists()
    assert not runtime.parent.exists()


def test_canonical_write_delegates_to_safe_append(monkeypatch, tmp_path: Path):
    calls = []

    def fake_safe_append(record, db_path=None):
        calls.append((record, db_path))
        return True, "canonical delegated"

    monkeypatch.setattr(MS._canonical_writer, "safe_append", fake_safe_append)
    path = tmp_path / "database.json"
    record = _canonical_record()

    ok, info = MS.append_canonical_record(record, canonical_path=path)

    assert (ok, info) == (True, "canonical delegated")
    assert calls == [(record, path)]


def test_runtime_write_delegates_to_runtime_journal(monkeypatch, tmp_path: Path):
    calls = []

    def fake_append_runtime_record(record, journal_path=None):
        calls.append((record, journal_path))
        return True, "runtime delegated"

    monkeypatch.setattr(MS._runtime_journal, "append_runtime_record", fake_append_runtime_record)
    path = tmp_path / "practice-render.jsonl"
    record = _runtime_record()

    ok, info = MS.append_runtime_record(record, runtime_path=path)

    assert (ok, info) == (True, "runtime delegated")
    assert calls == [(record, path)]


def test_append_record_requires_explicit_supported_layer(tmp_path: Path):
    try:
        MS.append_record(_canonical_record(), layer=MS.COMBINED, canonical_path=tmp_path / "db.json")
    except ValueError as exc:
        assert "unknown memory write layer" in str(exc)
    else:
        raise AssertionError("combined writes must not be supported")
