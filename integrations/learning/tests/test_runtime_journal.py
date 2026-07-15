"""Focused tests for runtime_journal.py.

All writes target tmp_path. These tests must never create the production
memory/runtime/practice-render.jsonl journal.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent
sys.path.insert(0, str(_PKG))

import runtime_journal as RJ  # noqa: E402


def _record(**overrides):
    base = {
        "record_type": "practice_render",
        "engine": "practice-loop",
        "project_name": "Practice tiktok_ig_yt_shorts #1",
        "platform_family": "tiktok_ig_yt_shorts",
        "format_id": "vertical_9_16",
        "render_source_id": "dry-run",
        "attempt_id": "daily-2026-07-15",
        "created_at": "2026-07-15T12:00:00",
        "payload": {"lesson": "kept locally"},
    }
    base.update(overrides)
    return RJ.ensure_runtime_record_id(base)


def test_append_writes_one_complete_jsonl_line_and_marker(tmp_path: Path):
    journal = tmp_path / "runtime" / "practice-render.jsonl"
    rec = _record()

    ok, info = RJ.append_runtime_record(rec, journal)

    assert ok is True, info
    lines = journal.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["runtime_record_id"] == rec["runtime_record_id"]
    assert (journal.parent / ".practice-render.jsonl.lock").exists()
    marker = journal.parent / ".practice-render.jsonl.integrity.json"
    assert marker.exists()
    assert json.loads(marker.read_text(encoding="utf-8"))["count"] == 1
    assert RJ.verify_runtime_integrity(journal) == (True, "ok")


def test_invalid_record_does_not_create_parent_directory(tmp_path: Path):
    journal = tmp_path / "runtime" / "practice-render.jsonl"

    ok, info = RJ.append_runtime_record({"engine": "practice-loop"}, journal)

    assert ok is False
    assert "runtime record invalid" in info
    assert not journal.parent.exists()


def test_non_object_record_rejected_without_creating_parent(tmp_path: Path):
    journal = tmp_path / "runtime" / "practice-render.jsonl"

    ok, info = RJ.append_runtime_record(["not", "an", "object"], journal)  # type: ignore[arg-type]

    assert ok is False
    assert "record is not an object" in info
    assert not journal.parent.exists()


def test_identity_ignores_created_at_and_requires_attempt_for_retry():
    rec1 = _record(created_at="2026-07-15T12:00:00")
    rec2 = _record(created_at="2026-07-15T12:30:00")
    rec3 = _record(created_at="2026-07-15T12:30:00", attempt_id="daily-2026-07-15-retry-2")

    assert rec1["runtime_record_id"] == rec2["runtime_record_id"]
    assert rec1["runtime_record_id"] != rec3["runtime_record_id"]


def test_identity_includes_each_primary_identifier():
    rec1 = _record(project_name="Same Project", run_id="run-1")
    rec2 = _record(project_name="Same Project", run_id="run-2")
    rec3 = _record(project_name="Same Project", run_id="run-1", job_id="job-2")

    assert rec1["runtime_record_id"] != rec2["runtime_record_id"]
    assert rec1["runtime_record_id"] != rec3["runtime_record_id"]


def test_duplicate_runtime_record_is_rejected_without_appending(tmp_path: Path):
    journal = tmp_path / "practice-render.jsonl"
    rec = _record()

    ok1, info1 = RJ.append_runtime_record(rec, journal)
    ok2, info2 = RJ.append_runtime_record(rec, journal)

    assert ok1 is True, info1
    assert ok2 is False
    assert "duplicate runtime_record_id" in info2
    assert len(journal.read_text(encoding="utf-8").splitlines()) == 1


def test_malformed_existing_line_fails_closed_without_repair(tmp_path: Path):
    journal = tmp_path / "practice-render.jsonl"
    journal.write_text(
        json.dumps(_record(), ensure_ascii=False, separators=(",", ":")) + "\n{\"broken\":\n",
        encoding="utf-8",
    )
    before = journal.read_bytes()

    ok, info = RJ.append_runtime_record(_record(attempt_id="daily-2026-07-16"), journal)

    assert ok is False
    assert "line 2" in info
    assert journal.read_bytes() == before
    assert "Practice tiktok" not in info


def test_existing_object_with_bad_runtime_id_fails_closed(tmp_path: Path):
    journal = tmp_path / "practice-render.jsonl"
    bad = _record()
    bad["runtime_record_id"] = "rt_wrong"
    journal.write_text(json.dumps(bad, ensure_ascii=False) + "\n", encoding="utf-8")
    before = journal.read_bytes()

    ok, info = RJ.append_runtime_record(_record(attempt_id="daily-2026-07-16"), journal)

    assert ok is False
    assert "line 1" in info
    assert "runtime_record_id does not match" in info
    assert journal.read_bytes() == before


def test_integrity_marker_tamper_rejects_next_append(tmp_path: Path):
    journal = tmp_path / "practice-render.jsonl"
    ok1, info1 = RJ.append_runtime_record(_record(), journal)
    assert ok1 is True, info1
    journal.write_text(
        journal.read_text(encoding="utf-8")
        + json.dumps(_record(attempt_id="outside-write"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    ok2, info2 = RJ.append_runtime_record(_record(attempt_id="daily-2026-07-16"), journal)

    assert ok2 is False
    assert "runtime integrity guard" in info2


def test_default_path_can_be_monkeypatched_for_test_isolation(tmp_path: Path, monkeypatch):
    journal = tmp_path / "isolated" / "practice-render.jsonl"
    monkeypatch.setattr(RJ, "DEFAULT_RUNTIME_JOURNAL", journal)

    ok, info = RJ.append_runtime_record(_record())

    assert ok is True, info
    assert journal.exists()


def test_load_runtime_records_reports_non_object_line_number(tmp_path: Path):
    journal = tmp_path / "practice-render.jsonl"
    journal.write_text("[]\n", encoding="utf-8")

    try:
        RJ.load_runtime_records(journal)
    except ValueError as exc:
        assert "line 1" in str(exc)
        assert "not an object" in str(exc)
    else:
        raise AssertionError("expected malformed line to fail closed")
